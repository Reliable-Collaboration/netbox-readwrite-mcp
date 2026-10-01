"""Guarded native deletion for stock objects omitted from REST deletion."""

import hashlib
import json

from core.signals import clear_events
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, router, transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError
from drf_spectacular.utils import extend_schema, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from netbox.views.generic import ObjectDeleteView
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.serialization import serialize_object

from .configuration import Conflict, StrictSerializer
from .imports import permitted_view

MODELS = {
    "core.datafile": "Deletes the database file copy; a later data-source sync can recreate it.",
    "core.job": "Also cancels the corresponding RQ job. Queue changes are not database-transactional.",
    "extras.scriptmodule": "Also deletes the source file and dependent scripts/jobs. Filesystem changes are not database-transactional.",
}


class DeleteWrite(StrictSerializer):
    id = serializers.IntegerField(min_value=1)
    apply = serializers.BooleanField(default=False)
    expected = serializers.CharField(required=False)
    changelog_message = serializers.CharField(default="", allow_blank=True)


def deletion_preview(obj, using):
    """Include dependent state, so new cascade members invalidate the preview."""
    collector = Collector(using=using)
    collector.collect([obj])
    rows = {}
    for model, objects in collector.data.items():
        rows.setdefault(model._meta.label_lower, []).extend(
            serialize_object(item, extra={"pk": item.pk}) for item in objects
        )
    for qs in collector.fast_deletes:
        rows.setdefault(qs.model._meta.label_lower, []).extend(
            serialize_object(item, extra={"pk": item.pk}) for item in qs
        )
    for values in rows.values():
        values.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
    external = {}
    if obj._meta.label_lower == "extras.scriptmodule":
        digest = hashlib.sha256()
        try:
            with obj.storage.open(obj.full_path, "rb") as source:
                while block := source.read(65536):
                    digest.update(block)
            external["source_sha256"] = digest.hexdigest()
        except FileNotFoundError:
            external["source_sha256"] = None
    payload = json.dumps({"objects": rows, "external": external}, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest(), {name: len(values) for name, values in rows.items()}


class DeleteCatalogView(APIView):
    """Discover guarded native deletion handlers."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from rest_framework.exceptions import PermissionDenied

        results = []
        for model, effects in MODELS.items():
            try:
                permitted_view(request, model, ObjectDeleteView)
            except PermissionDenied:
                continue
            results.append(
                {"model": model, "effects": effects, "url": request.build_absolute_uri(model + "/")}
            )
        return Response({"count": len(results), "results": results})


class DeleteView(APIView):
    """Preview and apply one guarded native deletion."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, model):
        if model not in MODELS:
            raise NotFound()
        permitted_view(request, model, ObjectDeleteView)
        return Response(
            {
                "model": model,
                "effects": MODELS[model],
                "instructions": "POST id to preview; repeat with apply=true and expected. One object per request. A lost response requires reconciliation, never blind replay.",
            }
        )

    @extend_schema(request=DeleteWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        if model not in MODELS:
            raise NotFound()
        view = permitted_view(request, model, ObjectDeleteView)
        body = DeleteWrite(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        using = router.db_for_write(view.queryset.model)
        try:
            with transaction.atomic(using=using):
                obj = view.queryset.select_for_update().filter(pk=data["id"]).first()
                if obj is None:
                    raise NotFound("Object is missing or inaccessible.")
                expected, cascade = deletion_preview(obj, using)
                if data["apply"]:
                    if data.get("expected") != expected:
                        raise Conflict("Object or dependent state changed. Preview again.")
                    if hasattr(obj, "snapshot"):
                        obj.snapshot()
                    obj._changelog_message = data["changelog_message"]
                    obj.delete()
                return Response(
                    {
                        "model": model,
                        "id": data["id"],
                        "applied": data["apply"],
                        "expected": expected,
                        "cascade": cascade,
                        "effects": MODELS[model],
                    }
                )
        except (ProtectedError, RestrictedError) as exc:
            clear_events.send(sender=self)
            raise ValidationError("Deletion is blocked by dependent objects.") from exc
        except (DjangoValidationError, IntegrityError) as exc:
            clear_events.send(sender=self)
            raise ValidationError(
                "Native deletion failed validation. Reconcile external queue/filesystem effects before retrying."
            ) from exc
