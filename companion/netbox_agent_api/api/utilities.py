"""Native Community search and Markdown preview as structured API responses."""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from extras.forms import RenderMarkdownForm
from netbox.forms import SearchForm
from netbox.search import LookupTypes
from netbox.search.backends import search_backend
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.templatetags.builtins.filters import render_markdown

from .configuration import StrictSerializer
from .imports import field_schema


class SearchView(APIView):
    """Run the native permission-filtered global search, including match metadata."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str),
            OpenApiParameter("lookup", str),
            OpenApiParameter("obj_types", str, many=True),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        if "q" not in request.query_params:
            return Response({"fields": field_schema(SearchForm()), "results": []})
        form = SearchForm(request.query_params)
        # The pinned form's clean() indexes these keys even if field cleaning
        # failed. Keep its validators, but return their errors before that hook.
        for name in ("q", "lookup"):
            try:
                form.fields[name].clean(request.query_params.get(name))
            except DjangoValidationError as exc:
                raise ValidationError({name: exc.messages}) from exc
        if not form.is_valid():
            raise ValidationError(form.errors)
        types = [
            ContentType.objects.get_by_natural_key(*name.split("."))
            for name in form.cleaned_data["obj_types"]
        ]
        try:
            matches = search_backend.search(
                form.cleaned_data["q"],
                user=request.user,
                object_types=types,
                lookup=form.cleaned_data["lookup"] or LookupTypes.PARTIAL,
            )
        except DataError as exc:
            raise ValidationError("Invalid native search expression.") from exc
        results = [
            {
                "object_type": row.object_type.app_label + "." + row.object_type.model,
                "id": row.object_id,
                "display": row.name,
                "url": row.object.get_absolute_url(),
                "matched_field": row.field,
                "matched_value": str(row.value),
            }
            for row in matches
        ]
        return Response(
            {
                "count": len(results),
                "results": results,
                "limit": 1000,
                "source": "native search index; newly changed records may await worker indexing",
            }
        )


class MarkdownInput(StrictSerializer):
    text = serializers.CharField(allow_blank=True, trim_whitespace=False)
    changelog_message = serializers.CharField(required=False, write_only=True)


class MarkdownView(APIView):
    """Render Markdown with NetBox's own preview renderer; no data is saved."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=MarkdownInput, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        body = MarkdownInput(data=request.data)
        body.is_valid(raise_exception=True)
        form = RenderMarkdownForm(body.validated_data)
        if not form.is_valid():
            raise ValidationError(form.errors)
        return Response({"html": str(render_markdown(form.cleaned_data["text"]))})
