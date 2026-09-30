"""Read native FilterSets under the target view's own permissions; never read inventory."""

import re

from django.conf import settings
from django.urls import Resolver404, resolve
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(exclude=True)
class RootView(APIView):
    """Discover the companion's read-only metadata endpoints."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"filter-schema": request.build_absolute_uri("filter-schema/")})


class FilterSchemaView(APIView):
    """Return live filter definitions under the target API resource's permissions."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[OpenApiParameter("resource", str, required=True)], responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        resource = request.query_params.get("resource", "")
        if not re.fullmatch(r"(?:[a-zA-Z0-9_-]+/){2,}", resource) or resource.startswith("api/"):
            raise ValidationError({"resource": "Use a relative collection path such as dcim/devices/."})
        prefix = "/" + settings.BASE_PATH.strip("/") if settings.BASE_PATH else ""
        try:
            match = resolve(prefix + "/api/" + resource)
        except Resolver404:
            raise NotFound("Unknown native API resource")
        cls = getattr(match.func, "cls", None)
        if cls is None or not getattr(cls, "filterset_class", None):
            raise NotFound("This resource has no native FilterSet")
        target = cls(**getattr(match.func, "initkwargs", {}))
        target.request = request
        target.args = ()
        target.kwargs = match.kwargs
        target.format_kwarg = None
        target.action = getattr(match.func, "actions", {}).get("get", "list")
        # The caller must pass exactly the native resource's authentication/permission
        # checks, including token and model permissions. The plugin grants no rights.
        target.check_permissions(request)
        filters = target.filterset_class(queryset=target.get_queryset().none(), request=request).filters
        return Response(
            {
                "schema_version": 1,
                "resource": resource,
                "filters": {
                    name: {"type": type(field).__name__, "lookup": field.lookup_expr}
                    for name, field in sorted(filters.items())
                },
            }
        )
