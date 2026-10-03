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
    id = serializers.IntegerField(min_value=1, required=False)
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False, required=False
    )
    apply = serializers.BooleanField(default=False)
    expected = serializers.CharField(required=False)
    changelog_message = serializers.CharField(default="", allow_blank=True)


def deletion_preview(objects, using):
    """Include cascades, SET_NULL dependents and source bytes in the guard."""
    collector = Collector(using=using)
    collector.collect(objects)
    rows = {}

    def capture(model, selected):
        pks = sorted({obj.pk for obj in selected})
        return [
            serialize_object(obj, extra={"pk": obj.pk})
            for obj in model._base_manager.using(using).select_for_update().filter(pk__in=pks).order_by("pk")
        ]

    for model, selected in collector.data.items():
        rows.setdefault(model._meta.label_lower, []).extend(capture(model, selected))
    for qs in collector.fast_deletes:
        rows.setdefault(qs.model._meta.label_lower, []).extend(capture(qs.model, qs))
    updates = {}
    for (field, value), batches in collector.field_updates.items():
        selected = [obj for batch in batches for obj in batch]
        updates[field.model._meta.label_lower + "." + field.name] = {
            "value": value,
            "objects": capture(field.model, selected),
        }
    for values in rows.values():
        values.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
    external = {}
    for obj in objects:
        if obj._meta.label_lower == "extras.scriptmodule":
            digest = hashlib.sha256()
            try:
                with obj.storage.open(obj.full_path, "rb") as source:
                    while block := source.read(65536):
                        digest.update(block)
                external[str(obj.pk)] = digest.hexdigest()
            except FileNotFoundError:
                external[str(obj.pk)] = None
    payload = json.dumps(
        {"objects": rows, "updates": updates, "external": external}, sort_keys=True, default=str
    ).encode()
    return (
        hashlib.sha256(payload).hexdigest(),
        {name: len(values) for name, values in rows.items()},
        {name: len(value["objects"]) for name, value in updates.items()},
    )


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
    """Preview and apply guarded native deletion, including stock bulk sets."""

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
                "instructions": "POST id or ids to preview; repeat with apply=true and expected. Database changes share a transaction; external queue/filesystem effects do not. A lost response requires reconciliation, never blind replay.",
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
        if ("id" in data) == ("ids" in data):
            raise ValidationError("Supply exactly one of id or ids.")
        ids = data.get("ids", [data.get("id")])
        if len(set(ids)) != len(ids):
            raise ValidationError("Duplicate IDs are not allowed.")
        using = router.db_for_write(view.queryset.model)
        try:
            with transaction.atomic(using=using):
                objects = list(view.queryset.select_for_update().filter(pk__in=ids).order_by("pk"))
                if len(objects) != len(ids):
                    raise NotFound("One or more objects are missing or inaccessible.")
                expected, cascade, updates = deletion_preview(objects, using)
                if data["apply"]:
                    if data.get("expected") != expected:
                        raise Conflict("Object or dependent state changed. Preview again.")
                    for obj in objects:
                        if hasattr(obj, "snapshot"):
                            obj.snapshot()
                        obj._changelog_message = data["changelog_message"]
                        obj.delete()
                return Response(
                    {
                        "model": model,
                        "id": data.get("id"),
                        "ids": ids,
                        "applied": data["apply"],
                        "expected": expected,
                        "cascade": cascade,
                        "updated_dependents": updates,
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
