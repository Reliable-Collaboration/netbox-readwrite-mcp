"""Native table, YAML and saved-template exports without rendering website pages."""

import base64
from copy import copy
import hashlib

from core.models import ObjectType
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from extras.models import ExportTemplate
from netbox.views.generic import ObjectListView
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .configuration import StrictSerializer
from .imports import permitted_view, registered_views


class ExportWrite(StrictSerializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    format = serializers.ChoiceField(choices=["csv", "table", "yaml", "template"], default="csv")
    columns = serializers.ListField(child=serializers.CharField(), required=False)
    template_id = serializers.IntegerField(min_value=1, required=False)
    offset = serializers.IntegerField(min_value=0, default=0)
    length = serializers.IntegerField(min_value=1, max_value=16384, default=8192)
    expected_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)
    changelog_message = serializers.CharField(required=False, write_only=True)


def native_table(view, request):
    # Configure the native table without forwarding arbitrary UI query controls
    # such as tableconfig_id, which would persist a user preference on read.
    native_request = copy(request._request)
    native_request.GET = QueryDict()
    return view.get_table(view.queryset, native_request, False)


class ExportCatalogView(APIView):
    """Discover stock model exports under their native view permissions."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        results = []
        for model in sorted(registered_views(ObjectListView)):
            try:
                permitted_view(request, model, ObjectListView)
            except PermissionDenied:
                continue
            results.append({"model": model, "url": request.build_absolute_uri(model + "/")})
        return Response({"count": len(results), "results": results})


class ExportView(APIView):
    """Read native export bytes in bounded chunks, guarded against changing content."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("export", str),
            OpenApiParameter("ids", int, many=True),
            OpenApiParameter("columns", str, many=True),
            OpenApiParameter("template_id", int),
            OpenApiParameter("offset", int),
            OpenApiParameter("length", int),
            OpenApiParameter("expected_sha256", str),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, model):
        if "export" in request.query_params:
            data = request.query_params.copy()
            data["format"] = data.pop("export")[-1]
            return self.render_export(request, model, data)
        view = permitted_view(request, model, ObjectListView)
        table = native_table(view, request)
        columns = table.selected_columns + table.available_columns
        object_type = ObjectType.objects.get_for_model(view.queryset.model)
        templates = ExportTemplate.objects.restrict(request.user, "view").filter(object_types=object_type)
        return Response(
            {
                "model": model,
                "columns": [
                    {"name": name, "label": str(label)}
                    for name, label in columns
                    if name not in {"pk", "actions"}
                ],
                "yaml": hasattr(view.queryset.model, "to_yaml"),
                "templates": [{"id": obj.pk, "name": obj.name} for obj in templates],
                "instructions": "POST selects ids (omit for all visible), format and optional columns/template_id. Reassemble base64 chunks using next_offset and the original expected_sha256. No data is mutated.",
            }
        )

    @extend_schema(request=ExportWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, model):
        return self.render_export(request, model, request.data)

    def render_export(self, request, model, payload):
        view = permitted_view(request, model, ObjectListView)
        body = ExportWrite(data=payload)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if "ids" in data:
            if len(set(data["ids"])) != len(data["ids"]):
                raise ValidationError({"ids": "Duplicate IDs are not allowed."})
            view.queryset = view.queryset.filter(pk__in=data["ids"])
            if view.queryset.count() != len(data["ids"]):
                raise PermissionDenied("One or more selected objects are missing or inaccessible.")
        response = None
        if data["format"] == "yaml":
            if not hasattr(view.queryset.model, "to_yaml"):
                raise ValidationError({"format": "This native model has no YAML export."})
            raw = view.export_yaml().encode()
            content_type = "text/yaml"
        elif data["format"] == "template":
            if not data.get("template_id"):
                raise ValidationError({"template_id": "Select an export template."})
            template = get_object_or_404(
                ExportTemplate.objects.restrict(request.user, "view"),
                pk=data["template_id"],
                object_types=ObjectType.objects.get_for_model(view.queryset.model),
            )
            try:
                response = template.render_to_response(queryset=view.queryset)
            except Exception as exc:
                raise ValidationError("Native export template rendering failed.") from exc
        else:
            table = native_table(view, request)
            allowed = {name for name, _ in table.selected_columns + table.available_columns} - {
                "pk",
                "actions",
            }
            columns = data.get("columns")
            if columns is not None and (not columns or set(columns) - allowed):
                raise ValidationError({"columns": "Select native export columns."})
            if columns is None and data["format"] == "table":
                columns = [name for name, _ in table.selected_columns]
            response = view.export_table(table, columns, delimiter=request.user.config.get("csv_delimiter"))
        if response is not None:
            try:
                raw = b"".join(response.streaming_content) if response.streaming else response.content
                content_type = response.get("Content-Type", "application/octet-stream")
            finally:
                response.close()
        digest = hashlib.sha256(raw).hexdigest()
        if data.get("expected_sha256", digest) != digest:
            return Response({"detail": "Export content changed; restart the download."}, status=412)
        start, end = data["offset"], data["offset"] + data["length"]
        if start > len(raw):
            return Response({"detail": "Offset exceeds export size."}, status=416)
        chunk = raw[start:end]
        return Response(
            {
                "content_type": content_type,
                "size": len(raw),
                "sha256": digest,
                "offset": start,
                "length": len(chunk),
                "base64": base64.b64encode(chunk).decode(),
                "text": chunk.decode("utf-8", errors="replace"),
                "next_offset": start + len(chunk) if start + len(chunk) < len(raw) else None,
            }
        )
