"""Permission-checked, bounded byte reads from stock Community file and image fields."""

import base64
import hashlib
from io import BytesIO

from core.models import DataFile

from dcim.models import DeviceType
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from extras.models import ImageAttachment
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .configuration import StrictSerializer

FIELDS = {
    "core.datafile": (DataFile, {"data"}),
    "dcim.devicetype": (DeviceType, {"front_image", "rear_image"}),
    "extras.imageattachment": (ImageAttachment, {"image"}),
}


class MediaQuery(StrictSerializer):
    offset = serializers.IntegerField(min_value=0, default=0)
    length = serializers.IntegerField(min_value=1, max_value=16384, default=8192)
    expected_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)


class MediaCatalogView(APIView):
    """List supported native file and image fields; object access is checked on download."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "models": {name: sorted(fields) for name, (_, fields) in FIELDS.items()},
                "path": "media/{model}/{id}/{field}/",
                "instructions": "Read bounded base64 chunks with offset and length. Supply expected_sha256 from the first response on later reads. Upload through the native object's multipart API.",
            }
        )


class MediaView(APIView):
    """Download native file and image bytes without accepting arbitrary filesystem paths."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("offset", int),
            OpenApiParameter("length", int),
            OpenApiParameter("expected_sha256", str),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, model, pk, field):
        if model not in FIELDS or field not in FIELDS[model][1]:
            raise NotFound()
        cls = FIELDS[model][0]
        instance = get_object_or_404(cls.objects.restrict(request.user, "view"), pk=pk)
        query = MediaQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        if model == "core.datafile":
            stream = BytesIO(bytes(instance.data))
            filename = instance.path.rsplit("/", 1)[-1]
        else:
            file = getattr(instance, field)
            if not file:
                raise NotFound()
            try:
                stream = file.open("rb")
            except FileNotFoundError as exc:
                raise NotFound() from exc
            filename = file.name.rsplit("/", 1)[-1]
        start = query.validated_data["offset"]
        end = start + query.validated_data["length"]
        digest = hashlib.sha256()
        offset = 0
        chunks = []
        try:
            with stream:
                while block := stream.read(65536):
                    digest.update(block)
                    if offset < end and offset + len(block) > start:
                        chunks.append(block[max(0, start - offset) : min(len(block), end - offset)])
                    offset += len(block)
        except FileNotFoundError as exc:
            raise NotFound() from exc
        actual = digest.hexdigest()
        if query.validated_data.get("expected_sha256", actual) != actual:
            return Response({"detail": "File content changed; restart the download."}, status=412)
        if start > offset:
            return Response({"detail": "Offset exceeds file size."}, status=416)
        data = b"".join(chunks)
        return Response(
            {
                "filename": filename,
                "size": offset,
                "sha256": actual,
                "offset": start,
                "length": len(data),
                "base64": base64.b64encode(data).decode(),
                "next_offset": start + len(data) if start + len(data) < offset else None,
            }
        )
