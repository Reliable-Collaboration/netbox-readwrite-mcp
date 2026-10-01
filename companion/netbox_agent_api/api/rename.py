"""Native bulk rename with structured previews and an explicit value guard."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, router, transaction
from django.http import QueryDict
from core.signals import clear_events
from drf_spectacular.utils import extend_schema, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from netbox.views.generic import BulkRenameView
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.exceptions import AbortRequest, PermissionsViolation
from utilities.forms import restrict_form_fields

from .configuration import Conflict, StrictSerializer
from .imports import permitted_view, registered_views


class RenameWrite(StrictSerializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    find = serializers.CharField(allow_blank=True, trim_whitespace=False)
    replace = serializers.CharField(allow_blank=True, trim_whitespace=False)
    use_regex = serializers.BooleanField(default=False)
    fields = serializers.ListField(child=serializers.CharField(), allow_empty=False, required=False)
    apply = serializers.BooleanField(default=False)
    expected = serializers.DictField(child=serializers.DictField(), required=False)
    changelog_message = serializers.CharField(default="", allow_blank=True)


class RenameCatalogView(APIView):
    """Discover permitted native rename handlers."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        results = []
        for model in sorted(registered_views(BulkRenameView)):
            try:
                permitted_view(request, model, BulkRenameView)
            except PermissionDenied:
                continue
            results.append({"model": model, "url": request.build_absolute_uri(model + "/")})
        return Response({"count": len(results), "results": results})


class RenameView(APIView):
    """Preview native literal/regex substitutions, then apply against the preview."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, model):
        view = permitted_view(request, model, BulkRenameView)
        return Response(
            {
                "model": model,
                "fields": list(view.rename_fields) or [view.field_name],
                "instructions": "POST with apply=false to preview. Copy expected from the preview into the same request with apply=true. Changes are atomic.",
            }
        )

    @extend_schema(request=RenameWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        view = permitted_view(request, model, BulkRenameView)
        payload = RenameWrite(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        ids = data["ids"]
        if len(set(ids)) != len(ids):
            raise ValidationError({"ids": "Duplicate IDs are not allowed."})
        allowed = list(view.rename_fields) or [view.field_name]
        fields = data.get("fields", allowed)
        if len(set(fields)) != len(fields) or set(fields) - set(allowed):
            raise ValidationError({"fields": "Select distinct native rename fields."})
        posted = QueryDict(mutable=True)
        posted.setlist("pk", [str(pk) for pk in ids])
        posted.update({key: data[key] for key in ("find", "replace", "use_regex", "changelog_message")})
        form = view.form(posted, initial={"pk": ids})
        restrict_form_fields(form, request.user)
        if not form.is_valid():
            raise ValidationError(form.errors)
        try:
            with transaction.atomic(using=router.db_for_write(view.queryset.model)):
                selected = list(view.queryset.select_for_update().filter(pk__in=ids).order_by("pk"))
                if len(selected) != len(ids):
                    raise PermissionDenied("One or more selected objects are missing or inaccessible.")
                expected = {str(obj.pk): {field: getattr(obj, field) for field in fields} for obj in selected}
                if data["apply"] and data.get("expected") != expected:
                    raise Conflict("Selected values changed or expected preview is absent. Preview again.")
                view._rename_objects(form, selected, fields)
                changes = [
                    {
                        "id": obj.pk,
                        "before": expected[str(obj.pk)],
                        "after": {field: getattr(obj.new_names, field) for field in fields},
                    }
                    for obj in selected
                ]
                if data["apply"]:
                    for obj in selected:
                        for field in fields:
                            setattr(obj, field, getattr(obj.new_names, field))
                        obj._changelog_message = data["changelog_message"]
                        obj.full_clean()
                        obj.save()
                    if view.queryset.filter(pk__in=ids).count() != len(ids):
                        raise PermissionsViolation()
        except (DjangoValidationError, IntegrityError, AbortRequest, PermissionsViolation) as exc:
            clear_events.send(sender=self)
            if isinstance(exc, PermissionsViolation):
                raise PermissionDenied("Rename violates object permissions.") from exc
            if isinstance(exc, IntegrityError):
                raise ValidationError(
                    "Rename violates a database constraint; no objects were changed."
                ) from exc
            raise ValidationError(
                getattr(exc, "messages", [getattr(exc, "message", "Rename aborted.")])
            ) from exc
        return Response({"model": model, "applied": data["apply"], "expected": expected, "changes": changes})
