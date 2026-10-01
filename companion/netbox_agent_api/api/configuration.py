"""API for native configuration revisions, without an HTML/session dependency."""

from contextlib import contextmanager
import hashlib
import json

from core.forms import ConfigRevisionForm
from core.models import ConfigRevision
from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connections, router, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from netbox.api.authentication import TokenWritePermission
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class Conflict(APIException):
    status_code = 409
    default_detail = "The active configuration changed. Read it again before writing."


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and (unknown := set(data) - self.fields.keys()):
            raise ValidationError({name: "Unknown field." for name in sorted(unknown)})
        return super().to_internal_value(data)


class RevisionGuard(StrictSerializer):
    expected_active_revision = serializers.IntegerField(allow_null=True, min_value=1)
    changelog_message = serializers.CharField(
        required=False,
        write_only=True,
        help_text="Accepted MCP transport metadata. This native model has no ObjectChange log; retain the MCP receipt.",
    )


class RevisionCreate(RevisionGuard):
    comment = serializers.CharField(max_length=200, allow_blank=True, default="")
    parameters = serializers.DictField(
        help_text="Complete replacement of dynamic overrides. Omitted settings use native defaults."
    )


class RevisionResult(serializers.Serializer):
    id = serializers.IntegerField()
    active = serializers.BooleanField()
    created = serializers.DateTimeField()
    comment = serializers.CharField()
    data = serializers.JSONField()


class RevisionList(serializers.Serializer):
    active_revision = serializers.IntegerField(allow_null=True)
    results = RevisionResult(many=True)


def require_permission(request, action):
    permission = "core." + action + "_configrevision"
    if not request.user.has_perm(permission):
        raise PermissionDenied()
    return permission


def visible(request, action="view"):
    require_permission(request, action)
    return ConfigRevision.objects.restrict(request.user, action)


def revision_etag(revision):
    encoded = json.dumps(RevisionResult(revision).data, sort_keys=True).encode()
    return '"' + hashlib.sha256(encoded).hexdigest() + '"'


@contextmanager
def guarded_write(expected):
    # A table lock also covers the empty-table/first-revision case. Native website
    # writes acquire conflicting row-exclusive locks; no plugin-only advisory lock.
    alias = router.db_for_write(ConfigRevision)
    with transaction.atomic(using=alias):
        connection = connections[alias]
        with connection.cursor() as cursor:
            cursor.execute(
                "LOCK TABLE "
                + connection.ops.quote_name(ConfigRevision._meta.db_table)
                + " IN EXCLUSIVE MODE"
            )
        active = ConfigRevision.objects.using(alias).filter(active=True).first()
        if (active.pk if active else None) != expected:
            raise Conflict()
        yield alias


def validated_parameters(parameters):
    form = ConfigRevisionForm()
    # Copilot is outside this project's open-source scope.
    allowed = set(form.declared_fields) - {"COPILOT_ENABLED"}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValidationError({"parameters": {name: "Unsupported setting." for name in sorted(unknown)}})
    cleaned = {}
    errors = {}
    for name, value in parameters.items():
        field = form.fields[name]
        if field.disabled:
            errors[name] = "Statically configured; change the deployment configuration instead."
            continue
        # JSON uses actual arrays and booleans; do not accept Django's permissive
        # string coercions (e.g. an arbitrary string becoming True).
        if isinstance(field, forms.BooleanField) and not isinstance(value, bool):
            errors[name] = "Expected a JSON boolean."
            continue
        if isinstance(field, SimpleArrayField) and not isinstance(value, list):
            errors[name] = "Expected a JSON array."
            continue
        if isinstance(field, forms.IntegerField) and (isinstance(value, bool) or not isinstance(value, int)):
            errors[name] = "Expected a JSON integer."
            continue
        if (
            isinstance(field, forms.CharField)
            and not isinstance(field, (forms.JSONField, SimpleArrayField))
            and not isinstance(value, str)
        ):
            errors[name] = "Expected a JSON string."
            continue
        try:
            # Native JSON fields expect serialized input, unlike normal DRF JSON.
            native_value = json.dumps(value) if isinstance(field, forms.JSONField) else value
            cleaned[name] = field.clean(native_value)
        except DjangoValidationError as exc:
            errors[name] = exc.messages
    if errors:
        raise ValidationError({"parameters": errors})
    return cleaned


class ConfigurationSchemaView(APIView):
    """Describe supported native configuration fields without reading their values."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request):
        require_permission(request, "view")
        form = ConfigRevisionForm()
        return Response(
            {
                "replacement_semantics": "parameters replaces all dynamic overrides; omitted settings use defaults",
                "parameters": {
                    name: {
                        "type": type(field).__name__,
                        "read_only": field.disabled,
                        "help": str(field.label),
                        "min_value": getattr(field, "min_value", None),
                        "max_value": getattr(field, "max_value", None),
                    }
                    for name, field in form.fields.items()
                    if name in form.declared_fields and name != "COPILOT_ENABLED"
                },
            }
        )


class RevisionCollectionView(APIView):
    """Read native revisions or create and immediately activate a validated revision."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses=RevisionList)
    def get(self, request):
        rows = visible(request)
        return Response(
            {
                "active_revision": rows.filter(active=True).values_list("pk", flat=True).first(),
                "results": RevisionResult(rows, many=True).data,
            }
        )

    @extend_schema(request=RevisionCreate, responses={201: RevisionResult})
    def post(self, request):
        permission = require_permission(request, "add")
        serializer = RevisionCreate(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with guarded_write(data["expected_active_revision"]) as alias:
            revision = ConfigRevision(comment=data["comment"], data=validated_parameters(data["parameters"]))
            revision.full_clean()
            # Native save's signal activates BEFORE object-permission validation.
            # Insert without signals, validate the persisted object's constraints,
            # then explicitly invoke the same native activation operation.
            ConfigRevision.objects.using(alias).bulk_create([revision])
            # Check constraints against the final persisted state, without making
            # the unapproved configuration visible through the shared cache.
            ConfigRevision.objects.using(alias).filter(active=True).update(active=False)
            ConfigRevision.objects.using(alias).filter(pk=revision.pk).update(active=True)
            revision.active = True
            if not request.user.has_perm(permission, revision):
                raise PermissionDenied()
            revision.activate()
            revision.active = True
        return Response(RevisionResult(revision).data, status=201)


class RevisionDetailView(APIView):
    """Inspect a revision or delete an inactive one with an active-revision guard."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses=RevisionResult)
    def get(self, request, pk):
        revision = get_object_or_404(visible(request), pk=pk)
        return Response(RevisionResult(revision).data, headers={"ETag": revision_etag(revision)})

    @extend_schema(request=RevisionGuard, responses={204: None})
    def delete(self, request, pk):
        rows = visible(request, "delete")
        serializer = RevisionGuard(data=request.data)
        serializer.is_valid(raise_exception=True)
        with guarded_write(serializer.validated_data["expected_active_revision"]):
            revision = get_object_or_404(rows, pk=pk)
            if request.headers.get("If-Match") and request.headers["If-Match"] != revision_etag(revision):
                return Response({"detail": "Revision ETag changed."}, status=412)
            if revision.active:
                raise Conflict("Activate another revision before deleting the active revision.")
            revision.delete()
        return Response(status=204)


class RevisionActivateView(APIView):
    """Restore a saved revision using the native website's restore permission."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(request=RevisionGuard, responses=RevisionResult)
    def post(self, request, pk):
        # This unusual permission spelling is used by NetBox 4.7.2's native
        # ConfigRevisionRestoreView. Do not silently substitute change permission.
        if not request.user.has_perm("core.configrevision_edit"):
            raise PermissionDenied()
        serializer = RevisionGuard(data=request.data)
        serializer.is_valid(raise_exception=True)
        with guarded_write(serializer.validated_data["expected_active_revision"]):
            revision = get_object_or_404(visible(request), pk=pk)
            revision.activate()
            revision.active = True
        return Response(RevisionResult(revision).data)
