"""Permission-checked, bounded byte reads from stock Community file and image fields."""

import base64
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
from .downloads import MAX_BYTES, TTL, bounded_bytes, snapshot

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
                "snapshot_limits": {"max_bytes": MAX_BYTES, "ttl_seconds": TTL, "slots_per_user": 1},
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
        instance = get_object_or_404(
            cls.objects.restrict(request.user, "view").defer("data")
            if model == "core.datafile"
            else cls.objects.restrict(request.user, "view"),
            pk=pk,
        )
        query = MediaQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        context = {
            "model": model,
            "pk": pk,
            "field": field,
            "updated": getattr(instance, "last_updated", None),
            "hash": getattr(instance, "hash", None),
        }
        file = None
        if model != "core.datafile":
            file = getattr(instance, field)
            if not file:
                raise NotFound()
            context["filename"] = file.name
            try:
                context["size"] = file.size
                context["modified"] = file.storage.get_modified_time(file.name)
            except NotImplementedError:
                # Backends without timestamps retain the native object revision guard.
                pass
            except FileNotFoundError as exc:
                raise NotFound() from exc

        def produce():
            try:
                stream = BytesIO(bytes(instance.data)) if file is None else file.open("rb")
                with stream:
                    raw = bounded_bytes(iter(lambda: stream.read(65536), b""))
            except FileNotFoundError as exc:
                raise NotFound() from exc
            filename = instance.path.rsplit("/", 1)[-1] if file is None else file.name.rsplit("/", 1)[-1]
            return raw, {"filename": filename}

        data = query.validated_data
        saved = snapshot(
            request.user,
            "media",
            context,
            data.get("expected_sha256"),
            produce,
            data["offset"],
            data["length"],
        )
        actual = saved["sha256"]
        if data.get("expected_sha256", actual) != actual:
            return Response({"detail": "File content changed; restart the download."}, status=412)
        start = data["offset"]
        size = saved["size"]
        if start > size:
            return Response({"detail": "Offset exceeds file size."}, status=416)
        chunk = saved["chunk"]
        return Response(
            {
                "filename": saved["filename"],
                "size": size,
                "sha256": actual,
                "offset": start,
                "length": len(chunk),
                "base64": base64.b64encode(chunk).decode(),
                "next_offset": start + len(chunk) if start + len(chunk) < size else None,
            }
        )
