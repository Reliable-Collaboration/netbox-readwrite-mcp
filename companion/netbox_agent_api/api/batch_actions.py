"""Atomic native disconnection and data synchronization with explicit previews."""

from core.models import DataFile
from yaml import YAMLError
from core.signals import clear_events
from dcim.models import Cable
from dcim.views import BulkDisconnectView
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, router, transaction
from drf_spectacular.utils import extend_schema, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from netbox.views.generic import BulkSyncDataView
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.exceptions import AbortRequest, PermissionsViolation

from .bulk_edit import state_hash
from .configuration import Conflict, StrictSerializer
from .imports import permitted_view, registered_views


class BatchActionWrite(StrictSerializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    apply = serializers.BooleanField(default=False)
    expected = serializers.DictField(required=False)
    changelog_message = serializers.CharField(default="", allow_blank=True)


class BatchCatalogView(APIView):
    """Discover the permitted stock handlers for an atomic batch action."""

    permission_classes = [IsAuthenticated]
    family = None

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        results = []
        for model in sorted(registered_views(self.family)):
            try:
                permitted_view(request, model, self.family)
            except PermissionDenied:
                continue
            results.append({"model": model, "url": request.build_absolute_uri(model + "/")})
        return Response({"count": len(results), "results": results})


class DisconnectCatalogView(BatchCatalogView):
    """Discover the eight native Community bulk-disconnect component types."""

    family = BulkDisconnectView


class SyncCatalogView(BatchCatalogView):
    """Discover native context/profile/template bulk synchronization handlers."""

    family = BulkSyncDataView


class BatchActionView(APIView):
    """Preview and perform one stock batch action with object permissions."""

    permission_classes = [IsAuthenticated, TokenWritePermission]
    family = None

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, model):
        permitted_view(request, model, self.family)
        return Response(
            {
                "model": model,
                "instructions": "POST ids with apply=false to preview. Repeat with apply=true and the returned expected map. The whole request is atomic.",
            }
        )

    @extend_schema(request=BatchActionWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        view = permitted_view(request, model, self.family)
        body = BatchActionWrite(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        ids = data["ids"]
        if len(set(ids)) != len(ids):
            raise ValidationError({"ids": "Duplicate IDs are not allowed."})
        try:
            with transaction.atomic(using=router.db_for_write(view.queryset.model)):
                selected = list(view.queryset.select_for_update().filter(pk__in=ids).order_by("pk"))
                if len(selected) != len(ids):
                    raise PermissionDenied("One or more selected objects are missing or inaccessible.")
                if self.family is BulkDisconnectView:
                    cables = list(
                        Cable.objects.select_for_update()
                        .filter(pk__in={obj.cable_id for obj in selected if obj.cable_id})
                        .order_by("pk")
                    )
                    expected = {str(obj.pk): obj.cable_id for obj in selected}
                    result = {
                        "cable_ids": [cable.pk for cable in cables],
                        "skipped_ids": [obj.pk for obj in selected if not obj.cable_id],
                    }
                else:
                    files = {
                        obj.pk: obj
                        for obj in DataFile.objects.select_for_update()
                        .filter(pk__in={obj.data_file_id for obj in selected if obj.data_file_id})
                        .order_by("pk")
                    }
                    expected = {
                        str(obj.pk): {
                            "object": state_hash(obj),
                            "file": files[obj.data_file_id].hash if obj.data_file_id else None,
                        }
                        for obj in selected
                    }
                    result = {
                        "sync_ids": [obj.pk for obj in selected if obj.data_file_id],
                        "skipped_ids": [obj.pk for obj in selected if not obj.data_file_id],
                    }
                if data["apply"]:
                    if data.get("expected") != expected:
                        raise Conflict("Selected objects or inputs changed. Preview again.")
                    if self.family is BulkDisconnectView:
                        # Native website permission is change on the selected
                        # components; deleting their cables is that operation's effect.
                        for cable in cables:
                            cable._changelog_message = data["changelog_message"]
                            cable.delete()
                    else:
                        for obj in selected:
                            if obj.data_file_id:
                                obj.snapshot()
                                obj.data_file = files[obj.data_file_id]
                                obj._changelog_message = data["changelog_message"]
                                obj.sync(save=True)
                        if view.queryset.filter(pk__in=ids).count() != len(ids):
                            raise PermissionsViolation()
                return Response({"model": model, "applied": data["apply"], "expected": expected, **result})
        except (DjangoValidationError, IntegrityError, AbortRequest, PermissionsViolation, YAMLError) as exc:
            clear_events.send(sender=self)
            if isinstance(exc, PermissionsViolation):
                raise PermissionDenied("Batch action violates object permissions.") from exc
            if isinstance(exc, IntegrityError):
                raise ValidationError(
                    "Batch action violates a database constraint; all changes were rolled back."
                ) from exc
            if isinstance(exc, YAMLError):
                raise ValidationError(
                    "A native data file contains invalid JSON/YAML; all changes were rolled back."
                ) from exc
            raise ValidationError(
                getattr(exc, "messages", [getattr(exc, "message", "Batch action aborted.")])
            ) from exc


class DisconnectView(BatchActionView):
    """Atomically delete cables attached to permitted native components."""

    family = BulkDisconnectView


class SyncView(BatchActionView):
    """Atomically synchronize permitted objects from their native DataFiles."""

    family = BulkSyncDataView
