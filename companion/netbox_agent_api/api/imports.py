"""Stock Community import handlers exposed as structured, transactional APIs."""

from functools import lru_cache

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, router, transaction
from django.urls import URLResolver, get_resolver
from django import forms
from django.utils.choices import flatten_choices
from core.signals import clear_events
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from netbox.views.generic import BulkImportView, ObjectListView
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.exceptions import AbortRequest, PermissionsViolation
from utilities.forms import restrict_form_fields
from utilities.forms.bulk_import import BulkImportForm

from .configuration import StrictSerializer

STOCK_APPS = frozenset(
    {"circuits", "core", "dcim", "extras", "ipam", "tenancy", "users", "virtualization", "vpn", "wireless"}
)


@lru_cache(maxsize=8)
def registered_views(base):
    """Discover native registered handlers, never import a caller-supplied class."""
    found = {}

    def walk(resolver):
        for route in resolver.url_patterns:
            if isinstance(route, URLResolver):
                walk(route)
                continue
            cls = getattr(route.callback, "view_class", None)
            if cls is None or not issubclass(cls, base):
                continue
            if base is ObjectListView and not callable(getattr(cls, "table", None)):
                continue
            model = getattr(getattr(cls, "queryset", None), "model", None)
            if model is None and base is ObjectListView:
                model = getattr(getattr(getattr(cls, "table", None), "_meta", None), "model", None)
            if model is None or model._meta.app_label not in STOCK_APPS:
                continue
            if cls.__module__.split(".")[0] not in STOCK_APPS and not (
                base is ObjectListView and cls.__module__ == "account.views"
            ):
                continue
            found[model._meta.label_lower] = cls

    walk(get_resolver())
    return found


def import_views():
    return registered_views(BulkImportView)


def permitted_view(request, model, base=BulkImportView):
    cls = registered_views(base).get(model)
    if cls is None:
        raise NotFound("No stock Community handler for this operation and model.")
    view = cls()
    view.setup(request)
    view.queryset = view.get_queryset(request) if hasattr(view, "get_queryset") else view.queryset.all()
    # Native method applies additional permissions and restricts the queryset to
    # the caller's add constraints. Its helper separately checks change constraints.
    if not view.has_permission():
        raise PermissionDenied()
    return view


def field_schema(form, selected=None):
    fields = {}
    for name, field in form.fields.items():
        if selected and name != selected:
            continue
        row = {"type": type(field).__name__, "required": field.required, "help_text": str(field.help_text)}
        if isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
            row["related_model"] = field.queryset.model._meta.label_lower
            row["lookup"] = field.to_field_name or "pk"
        elif isinstance(field, forms.ChoiceField):
            row["choices"] = [
                {
                    "value": value
                    if value is None or isinstance(value, (str, int, float, bool))
                    else str(value),
                    "label": str(label),
                }
                for value, label in flatten_choices(field.choices)
            ]
        if not selected and len(row.get("choices", [])) > 50:
            row["choices_count"] = len(row.pop("choices"))
            row["choices_query"] = {"field": name}
        fields[name] = row
    return fields


class ImportWrite(StrictSerializer):
    data = serializers.CharField(
        trim_whitespace=False,
        help_text="Native CSV, JSON or YAML document; relationships use the import schema's lookups.",
    )
    format = serializers.ChoiceField(choices=["auto", "csv", "json", "yaml"], default="auto")
    csv_delimiter = serializers.ChoiceField(choices=["auto", ",", ";", "|", "\\t"], default="auto")
    changelog_message = serializers.CharField(required=False, allow_blank=True, default="")


class ImportCatalogView(APIView):
    """List permitted stock import handlers without reading inventory values."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        results = []
        for model in sorted(import_views()):
            try:
                permitted_view(request, model)
            except PermissionDenied:
                continue
            results.append({"model": model, "url": request.build_absolute_uri(model + "/")})
        return Response({"count": len(results), "results": results})


class ImportView(APIView):
    """Validate and import with native handlers in one transaction, without HTML."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(
        parameters=[OpenApiParameter("field", str, required=False)], responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, model):
        view = permitted_view(request, model)
        form = view.model_form()
        restrict_form_fields(form, request.user)
        return Response(
            {
                "model": model,
                "fields": field_schema(form, request.query_params.get("field")),
                "related_objects": {
                    name: field_schema(cls()) for name, cls in view.related_object_forms.items()
                },
                "update": "Include id to update; omitted fields are preserved. Requires change permission. Imports have no conditional-write guard.",
                "atomic": True,
            }
        )

    @extend_schema(request=ImportWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        view = permitted_view(request, model)
        payload = ImportWrite(data=request.data)
        payload.is_valid(raise_exception=True)
        form = BulkImportForm(payload.validated_data)
        restrict_form_fields(form, request.user)
        if not form.is_valid():
            raise ValidationError(form.errors)
        records = form.cleaned_data["data"]
        if not isinstance(records, list) or not records or any(not isinstance(row, dict) for row in records):
            raise ValidationError({"data": "Supply a nonempty list of object records."})
        # Reject malformed IDs before native int() conversion and unknown columns
        # before ModelForm can silently discard them.
        allowed = set(view.model_form().fields) | set(view.related_object_forms) | {"id"}
        for index, row in enumerate(records, 1):
            if set(row) - allowed:
                raise ValidationError(
                    {"data": f"Record {index}: unknown fields {sorted(set(row) - allowed)}"}
                )
            if row.get("id") is not None and row.get("id") != "":
                value = row["id"]
                if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
                    raise ValidationError({"data": f"Record {index}: id must be a positive integer."})
        try:
            with transaction.atomic(using=router.db_for_write(view.queryset.model)):
                objects = view.create_and_update_objects(form, request)
        except (DjangoValidationError, AbortRequest, PermissionsViolation, IntegrityError) as exc:
            clear_events.send(sender=self)
            if isinstance(exc, PermissionsViolation):
                raise PermissionDenied("Import violates object permissions.") from exc
            if isinstance(exc, IntegrityError):
                raise ValidationError(
                    "Import violates a database constraint; no records were saved."
                ) from exc
            raise ValidationError(
                getattr(exc, "messages", [getattr(exc, "message", "Import aborted.")])
            ) from exc
        return Response({"model": model, "count": len(objects), "ids": [obj.pk for obj in objects]})
