"""Validated, current-user dashboard state without browser initialization."""

import hashlib
import json

from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.choices import flatten_choices
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from extras.dashboard.forms import DashboardWidgetForm
from extras.dashboard.utils import get_default_dashboard, get_widget_class
from extras.models import Dashboard
from netbox.api.authentication import TokenWritePermission
from netbox.registry import registry
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .configuration import StrictSerializer


class LayoutItem(StrictSerializer):
    id = serializers.UUIDField()
    w = serializers.IntegerField(min_value=1, max_value=12)
    h = serializers.IntegerField(min_value=1)
    x = serializers.IntegerField(min_value=0, allow_null=True, default=None)
    y = serializers.IntegerField(min_value=0, allow_null=True, default=None)


class DashboardWrite(StrictSerializer):
    layout = LayoutItem(many=True)
    config = serializers.DictField(child=serializers.DictField())
    changelog_message = serializers.CharField(required=False, write_only=True)

    def validate(self, data):
        ids = [str(item["id"]) for item in data["layout"]]
        if len(ids) != len(set(ids)) or set(ids) != set(data["config"]):
            raise ValidationError("Each widget needs exactly one matching layout and config entry.")
        for item in data["layout"]:
            item["id"] = str(item["id"])
            if item["x"] is not None and item["x"] + item["w"] > 12:
                raise ValidationError("Widget position extends beyond the 12-column dashboard.")
        for key, value in data["config"].items():
            if set(value) - {"class", "title", "color", "config"}:
                raise ValidationError({key: "Unknown widget properties."})
            name = value.get("class")
            if not isinstance(name, str) or not name.startswith("extras."):
                raise ValidationError({key: "Only registered NetBox Community widgets are supported."})
            try:
                cls = get_widget_class(name)
            except ValueError as exc:
                raise ValidationError({key: str(exc)})
            options = value.get("config", {})
            if not isinstance(options, dict):
                raise ValidationError({key: "Widget config must be an object."})
            config_form = cls.ConfigForm()
            if set(options) - config_form.fields.keys():
                raise ValidationError({key: "Unknown widget configuration fields."})
            options = {**cls.default_config, **options}
            options = {
                name: json.dumps(v) if isinstance(config_form.fields[name], forms.JSONField) else v
                for name, v in options.items()
            }
            config_form = cls.ConfigForm(options)
            widget_form = DashboardWidgetForm({k: value.get(k) for k in ("title", "color")})
            try:
                valid = config_form.is_valid() and widget_form.is_valid()
            except (ValueError, TypeError) as exc:
                raise ValidationError({key: str(exc)})
            if not valid:
                raise ValidationError({key: {"widget": widget_form.errors, "config": config_form.errors}})
            if value != self.context.get("existing", {}).get(key):
                data["config"][key] = {
                    "class": name,
                    **widget_form.cleaned_data,
                    "config": config_form.cleaned_data,
                }
        return data


class EmptyWrite(StrictSerializer):
    changelog_message = serializers.CharField(required=False, write_only=True)


def state(dashboard):
    return {
        "initialized": dashboard is not None,
        "layout": dashboard.layout if dashboard else [],
        "config": dashboard.config if dashboard else {},
    }


def etag(value):
    return '"' + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest() + '"'


GUARD = [OpenApiParameter("If-Match", str, location=OpenApiParameter.HEADER, required=True)]


class DashboardView(APIView):
    """Read, initialize, replace or reset only the authenticated user's dashboard."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        value = state(Dashboard.objects.filter(user=request.user).first())
        return Response(value, headers={"ETag": etag(value)})

    def write(self, request):
        body = DashboardWrite(data=request.data) if request.method == "PUT" else EmptyWrite(data=request.data)
        with transaction.atomic():
            # Lock the user too: there may not be a dashboard row yet. Existing
            # dashboards are locked against ordinary native UPDATE/DELETE writes.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            dashboard = Dashboard.objects.select_for_update().filter(user=request.user).first()
            current = state(dashboard)
            if not request.headers.get("If-Match"):
                return Response(
                    {"detail": "Read this endpoint and supply its exact If-Match ETag."}, status=428
                )
            if request.headers["If-Match"] != etag(current):
                return Response({"detail": "Dashboard changed; read it again."}, status=412)
            body.context["existing"] = current["config"]
            body.is_valid(raise_exception=True)
            if request.method == "DELETE":
                if dashboard:
                    dashboard.delete()
                return Response(status=204)
            if request.method == "POST":
                if dashboard is None:
                    dashboard = get_default_dashboard()
                    dashboard.user = request.user
                    dashboard.save()
            else:
                if dashboard is None:
                    dashboard = Dashboard(user=request.user)
                dashboard.layout = body.validated_data["layout"]
                dashboard.config = body.validated_data["config"]
                # Native dashboards allow an empty layout/config after the last
                # widget is removed; validation is done by the serializers/forms.
                dashboard.save()
            value = state(dashboard)
            return Response(value, headers={"ETag": etag(value)})

    @extend_schema(request=EmptyWrite, parameters=GUARD, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        """Initialize native default widgets if absent, preserving an existing dashboard."""
        return self.write(request)

    @extend_schema(request=DashboardWrite, parameters=GUARD, responses={200: OpenApiTypes.OBJECT})
    def put(self, request):
        """Replace layout and widget configuration after native form validation."""
        return self.write(request)

    @extend_schema(request=EmptyWrite, parameters=GUARD, responses={204: None})
    def delete(self, request):
        """Reset by deleting the current user's dashboard, as the native website does."""
        return self.write(request)


class DashboardWidgetSchemaView(APIView):
    """Describe registered Community widgets and their native configuration fields."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                name: {
                    "description": str(cls.description),
                    "defaults": cls.default_config,
                    "fields": {
                        key: {
                            "type": type(field).__name__,
                            "required": field.required,
                            "min_value": getattr(field, "min_value", None),
                            "max_value": getattr(field, "max_value", None),
                            **(
                                {"choices": [str(value) for value, _ in flatten_choices(field.choices)]}
                                if hasattr(field, "choices")
                                else {}
                            ),
                        }
                        for key, field in cls.ConfigForm().fields.items()
                    },
                }
                for name, cls in registry["widgets"].items()
                if name.startswith("extras.")
            }
        )
