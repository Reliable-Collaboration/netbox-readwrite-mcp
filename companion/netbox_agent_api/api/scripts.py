"""Native script variable forms and class source without website parsing."""

import base64
import hashlib

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from extras.models import Script
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.forms import restrict_form_fields

from .imports import field_schema
from .media import MediaQuery


def visible_script(request, pk):
    if not request.user.has_perm("extras.view_script"):
        raise PermissionDenied()
    return get_object_or_404(Script.objects.restrict(request.user, "view"), pk=pk)


class ScriptCatalogView(APIView):
    """Discover native script metadata and source endpoints."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "collection": "extras/scripts/",
                "schema": "scripts/{id}/",
                "source": "scripts/{id}/source/",
                "execution": "POST extras/scripts/{id}/ with data, commit and optional schedule_at/interval/notifications. Native multipart supports FileVar. Results and logs are in core/jobs/.",
            }
        )


class ScriptSchemaView(APIView):
    """Read permission-scoped native script variable fields."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("field", str)], responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        script = visible_script(request, pk)
        if not script.python_class:
            raise ValidationError("The native script class cannot be loaded.")
        instance = script.python_class()
        form = instance.as_form()
        restrict_form_fields(form, request.user)
        return Response(
            {
                "id": script.pk,
                "module_id": script.module_id,
                "name": script.name,
                "fields": field_schema(form, request.query_params.get("field")),
                "scheduling_enabled": instance.scheduling_enabled,
                "executable": script.is_executable,
            }
        )


class ScriptSourceView(APIView):
    """Read bounded native script class source."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("offset", int),
            OpenApiParameter("length", int),
            OpenApiParameter("expected_sha256", str),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, pk):
        script = visible_script(request, pk)
        if not script.python_class:
            raise ValidationError("The native script class cannot be loaded.")
        query = MediaQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        raw = script.python_class().source.encode()
        digest = hashlib.sha256(raw).hexdigest()
        if data.get("expected_sha256", digest) != digest:
            return Response({"detail": "Script source changed; restart the download."}, status=412)
        start = data["offset"]
        if start > len(raw):
            return Response({"detail": "Offset exceeds source size."}, status=416)
        chunk = raw[start : start + data["length"]]
        return Response(
            {
                "id": script.pk,
                "filename": script.module.file_path,
                "size": len(raw),
                "sha256": digest,
                "offset": start,
                "base64": base64.b64encode(chunk).decode(),
                "text": chunk.decode(errors="replace"),
                "next_offset": start + len(chunk) if start + len(chunk) < len(raw) else None,
            }
        )
