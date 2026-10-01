"""Structured native bulk edits, retaining nullification and model-specific hooks."""

import hashlib
import json
from types import SimpleNamespace

from core.signals import clear_events
from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, router, transaction
from django.http import QueryDict
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from netbox.views.generic import BulkEditView
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.exceptions import AbortRequest, PermissionsViolation
from utilities.forms import restrict_form_fields
from utilities.serialization import serialize_object

from .configuration import Conflict, StrictSerializer
from .imports import field_schema, permitted_view, registered_views


class BulkEditWrite(StrictSerializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    values = serializers.DictField(default=dict)
    context = serializers.DictField(child=serializers.IntegerField(min_value=1), default=dict)
    nullify = serializers.ListField(child=serializers.CharField(), default=list)
    apply = serializers.BooleanField(default=False)
    expected = serializers.DictField(child=serializers.CharField(), required=False)
    changelog_message = serializers.CharField(default="", allow_blank=True)


def state_hash(obj):
    return hashlib.sha256(json.dumps(serialize_object(obj), sort_keys=True).encode()).hexdigest()


class BulkEditCatalogView(APIView):
    """Discover permitted stock native bulk edit handlers."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        results = []
        for model in sorted(registered_views(BulkEditView)):
            try:
                permitted_view(request, model, BulkEditView)
            except PermissionDenied:
                continue
            results.append({"model": model, "url": request.build_absolute_uri(model + "/")})
        return Response({"count": len(results), "results": results})


class BulkEditAPIView(APIView):
    """Validate a native bulk edit, capture state guards, then apply atomically."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(
        parameters=[OpenApiParameter("field", str, required=False)], responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, model):
        view = permitted_view(request, model, BulkEditView)
        form = view.form(initial={})
        restrict_form_fields(form, request.user)
        for name in ("pk", "background_job", "changelog_message"):
            form.fields.pop(name, None)
        return Response(
            {
                "model": model,
                "fields": field_schema(form, request.query_params.get("field")),
                "nullable_fields": list(getattr(form, "nullable_fields", [])),
                "instructions": "POST apply=false to validate inputs and capture expected state hashes. Repeat with apply=true and those hashes. Model validation also runs at apply; any failure rolls back the whole batch.",
            }
        )

    @extend_schema(request=BulkEditWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        view = permitted_view(request, model, BulkEditView)
        payload = BulkEditWrite(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        ids = data["ids"]
        if len(set(ids)) != len(ids):
            raise ValidationError({"ids": "Duplicate IDs are not allowed."})
        if set(data["context"]) - {"device", "device_type", "virtual_machine"} or len(data["context"]) > 1:
            raise ValidationError(
                {"context": "Use one native parent context: device, device_type or virtual_machine."}
            )
        unbound = view.form(initial=data["context"])
        allowed = set(unbound.fields) - {"pk", "background_job", "changelog_message"}
        if set(data["values"]) - allowed:
            raise ValidationError({"values": "Unknown or reserved native form fields."})
        if set(data["nullify"]) - set(getattr(unbound, "nullable_fields", [])):
            raise ValidationError({"nullify": "Only native nullable fields can be cleared."})
        posted = QueryDict(mutable=True)
        posted.setlist("pk", [str(pk) for pk in ids])
        posted.setlist("_nullify", data["nullify"])
        posted["changelog_message"] = data["changelog_message"]
        for name, value in data["values"].items():
            field = unbound.fields[name]
            if isinstance(field, forms.JSONField):
                posted[name] = json.dumps(value)
            elif isinstance(value, list):
                posted.setlist(name, value)
            else:
                posted[name] = value
        form = view.form(posted, initial={"pk": ids, **data["context"]})
        restrict_form_fields(form, request.user)
        if not form.is_valid():
            raise ValidationError(form.errors)
        try:
            with transaction.atomic(using=router.db_for_write(view.queryset.model)):
                selected = list(view.queryset.select_for_update().filter(pk__in=ids).order_by("pk"))
                if len(selected) != len(ids):
                    raise PermissionDenied("One or more selected objects are missing or inaccessible.")
                expected = {str(obj.pk): state_hash(obj) for obj in selected}
                if data["apply"]:
                    if data.get("expected") != expected:
                        raise Conflict(
                            "Selected objects changed or expected state is absent. Validate again."
                        )
                    # Native helper only reads POST, user and background-job state.
                    # A separate request facade avoids mutating DRF's parsed input.
                    native_request = SimpleNamespace(POST=posted, user=request.user)
                    objects = view._update_objects(form, native_request)
                    if view.queryset.filter(pk__in=[obj.pk for obj in objects]).count() != len(ids):
                        raise PermissionsViolation()
        except (DjangoValidationError, IntegrityError, AbortRequest, PermissionsViolation) as exc:
            clear_events.send(sender=self)
            if isinstance(exc, PermissionsViolation):
                raise PermissionDenied("Bulk edit violates object permissions.") from exc
            if isinstance(exc, IntegrityError):
                raise ValidationError(
                    "Bulk edit violates a database constraint; no objects were changed."
                ) from exc
            raise ValidationError(
                getattr(exc, "messages", [getattr(exc, "message", "Bulk edit aborted.")])
            ) from exc
        return Response({"model": model, "ids": ids, "applied": data["apply"], "expected": expected})
