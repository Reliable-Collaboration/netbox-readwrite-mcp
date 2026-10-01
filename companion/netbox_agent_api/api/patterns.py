"""Native range and component expansion without HTML form submission."""

from types import SimpleNamespace
import json

from core.signals import clear_events
from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, router, transaction
from django.http import QueryDict
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from netbox.views.generic import BulkCreateView, ComponentCreateView
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.exceptions import AbortRequest, AbortTransaction, PermissionsViolation
from utilities.forms import restrict_form_fields

from .configuration import StrictSerializer
from .imports import field_schema, permitted_view, registered_views


def pattern_view(request, model):
    for base in (BulkCreateView, ComponentCreateView):
        if model in registered_views(base):
            return permitted_view(request, model, base)
    raise NotFound("No stock range or component handler for this model.")


def posted_values(values, form):
    posted = QueryDict(mutable=True)
    for name, value in values.items():
        if isinstance(form.fields.get(name), forms.JSONField):
            posted[name] = json.dumps(value)
        elif isinstance(value, list):
            posted.setlist(name, value)
        else:
            posted[name] = value
    return posted


class PatternWrite(StrictSerializer):
    items = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="One native form input object per range or parent. Each can expand patterns. The entire request is atomic.",
    )
    changelog_message = serializers.CharField(default="", allow_blank=True)


class PatternCatalogView(APIView):
    """Discover stock IP/VLAN range and component pattern handlers."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        results = []
        models = set(registered_views(BulkCreateView)) | set(registered_views(ComponentCreateView))
        for model in sorted(models):
            try:
                pattern_view(request, model)
            except PermissionDenied:
                continue
            results.append({"model": model, "url": request.build_absolute_uri(model + "/")})
        return Response({"count": len(results), "results": results})


class PatternView(APIView):
    """Expand patterns with native forms and save the complete batch atomically."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(
        parameters=[OpenApiParameter("field", str, required=False)], responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, model):
        view = pattern_view(request, model)
        form = view.form()
        restrict_form_fields(form, request.user)
        fields = field_schema(form, request.query_params.get("field"))
        if isinstance(view, BulkCreateView):
            model_form = view.model_form()
            restrict_form_fields(model_form, request.user)
            fields = {**field_schema(model_form, request.query_params.get("field")), **fields}
            fields.pop(view.pattern_target, None)
        return Response(
            {
                "model": model,
                "fields": fields,
                "pattern_fields": list(getattr(view.form, "replication_fields", ["pattern"])),
                "atomic": True,
            }
        )

    @extend_schema(request=PatternWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        view = pattern_view(request, model)
        payload = PatternWrite(data=request.data)
        payload.is_valid(raise_exception=True)
        objects = []
        form = None
        try:
            with transaction.atomic(using=router.db_for_write(view.queryset.model)):
                for index, values in enumerate(payload.validated_data["items"], 1):
                    unbound = view.form()
                    allowed = set(unbound.fields)
                    if isinstance(view, BulkCreateView):
                        allowed |= set(view.model_form().fields)
                        allowed.discard(view.pattern_target)
                    if set(values) - allowed or set(values) & {"id", "background_job", "changelog_message"}:
                        raise ValidationError({"items": f"Item {index} contains unknown or reserved fields."})
                    posted = posted_values(values, unbound)
                    posted["changelog_message"] = payload.validated_data["changelog_message"]
                    form = view.form(posted)
                    if isinstance(view, ComponentCreateView):
                        form.instance._replicated_base = True
                    restrict_form_fields(form, request.user)
                    if not form.is_valid():
                        raise ValidationError({"items": {index: form.errors}})
                    native_request = SimpleNamespace(POST=posted, user=request.user)
                    model_form_class = view.model_form

                    def model_form(data):
                        result = model_form_class(data)
                        restrict_form_fields(result, request.user)
                        return result

                    if isinstance(view, BulkCreateView):
                        # Native helper preserves range templates and per-model overrides.
                        view.model_form = model_form
                        try:
                            objects.extend(view._create_objects(form, native_request))
                        finally:
                            view.model_form = model_form_class
                    else:
                        replicated = view.form.replication_fields
                        for offset in range(len(form.cleaned_data[replicated[0]])):
                            record = posted.copy()
                            for field in replicated:
                                if form.cleaned_data.get(field):
                                    record[field] = form.cleaned_data[field][offset]
                            if hasattr(form, "get_iterative_data"):
                                for name, values in form.get_iterative_data(offset).items():
                                    record.setlist(name, values)
                            item = model_form(record)
                            if not item.is_valid():
                                raise ValidationError({"items": {index: item.errors}})
                            item.instance._changelog_message = payload.validated_data["changelog_message"]
                            objects.append(item.save())
                if view.queryset.filter(pk__in=[obj.pk for obj in objects]).count() != len(objects):
                    raise PermissionsViolation()
        except (
            DjangoValidationError,
            ValidationError,
            IntegrityError,
            AbortRequest,
            AbortTransaction,
            PermissionsViolation,
        ) as exc:
            clear_events.send(sender=self)
            if isinstance(exc, PermissionsViolation):
                raise PermissionDenied("Creation violates object permissions.") from exc
            if isinstance(exc, ValidationError):
                raise
            if isinstance(exc, AbortTransaction):
                raise ValidationError(form.errors if form else "Creation aborted.") from exc
            if isinstance(exc, IntegrityError):
                raise ValidationError(
                    "Creation violates a database constraint; no objects were saved."
                ) from exc
            raise ValidationError(
                getattr(exc, "messages", [getattr(exc, "message", "Creation aborted.")])
            ) from exc
        return Response({"model": model, "count": len(objects), "ids": [obj.pk for obj in objects]})
