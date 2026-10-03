"""Current-user account operations missing from native Community REST."""

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from users.forms import UserConfigForm
from users.models import UserConfig

from .configuration import StrictSerializer
from .dashboard import etag, GUARD
from .imports import field_schema


class ProfileView(APIView):
    """Read the caller's own profile without administrative user-list permission."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        user = request.user
        return Response(
            {
                name: getattr(user, name)
                for name in (
                    "id",
                    "username",
                    "first_name",
                    "last_name",
                    "email",
                    "is_active",
                    "date_joined",
                    "last_login",
                )
            }
        )


class PreferenceWrite(StrictSerializer):
    values = serializers.DictField(default=dict)
    clear_tables = serializers.ListField(child=serializers.CharField(), default=list)
    changelog_message = serializers.CharField(required=False, write_only=True)


def preference_form(instance, data=None):
    form = UserConfigForm(data=data, instance=instance)
    # Commercial preferences and unqualified third-party preferences are outside
    # this API's stock Community scope. Existing values remain untouched.
    for field in list(form.fields):
        if field == "ui.copilot_enabled" or field.startswith("plugins."):
            del form.fields[field]
    return form


class PreferencesView(APIView):
    """Validate native preference values and clear native saved table settings."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        instance = UserConfig.objects.filter(user=request.user).first() or UserConfig(user=request.user)
        form = preference_form(instance)
        clearable = [value for value, _ in form.fields.pop("pk").choices]
        return Response(
            {"data": instance.data, "fields": field_schema(form), "clearable_tables": clearable},
            headers={"ETag": etag(instance.data)},
        )

    @extend_schema(request=PreferenceWrite, parameters=GUARD, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request):
        body = PreferenceWrite(data=request.data)
        body.is_valid(raise_exception=True)
        values = body.validated_data["values"]
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            instance = UserConfig.objects.select_for_update().filter(user=request.user).first() or UserConfig(
                user=request.user
            )
            if not request.headers.get("If-Match"):
                return Response({"detail": "Read preferences and supply If-Match."}, status=428)
            if request.headers["If-Match"] != etag(instance.data):
                return Response({"detail": "Preferences changed; read them again."}, status=412)
            allowed = set(preference_form(instance).fields) - {"pk"}
            if set(values) - allowed:
                raise ValidationError({"values": "Unknown or excluded native preferences."})
            posted = QueryDict(mutable=True)
            posted.update(values)
            posted.setlist("pk", body.validated_data["clear_tables"])
            form = preference_form(instance, posted)
            # Native form save iterates cleaned fields. Removing omitted fields
            # gives PATCH semantics without resetting any unrelated preferences.
            for name in set(form.fields) - set(values) - {"pk"}:
                del form.fields[name]
            if not form.is_valid():
                raise ValidationError(form.errors)
            try:
                form.save()
            except TypeError as exc:
                raise ValidationError(
                    "Existing preference structure conflicts with the requested fields."
                ) from exc
            return Response({"data": instance.data}, headers={"ETag": etag(instance.data)})


class PasswordWrite(StrictSerializer):
    old_password = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password1 = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password2 = serializers.CharField(trim_whitespace=False, write_only=True)
    changelog_message = serializers.CharField(required=False, write_only=True)


class PasswordView(APIView):
    """Change only the authenticated user's local password using native validation."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(request=PasswordWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        if getattr(request.user, "ldap_username", None):
            raise ValidationError("Manage this LDAP password through the configured identity provider.")
        body = PasswordWrite(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            form = PasswordChangeForm(user=user, data=body.validated_data)
            if not form.is_valid():
                raise ValidationError(form.errors)
            form.save()
        return Response({"changed": True})


class NotificationAction(StrictSerializer):
    action = serializers.ChoiceField(choices=["read", "dismiss", "dismiss_unread"])
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)
    changelog_message = serializers.CharField(required=False, write_only=True)


class NotificationQuery(StrictSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=1000, default=100)
    offset = serializers.IntegerField(min_value=0, default=0)
    unread = serializers.BooleanField(required=False)


class NotificationsView(APIView):
    """Read and dismiss only the caller's notifications, using native server time."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", int),
            OpenApiParameter("offset", int),
            OpenApiParameter("unread", bool),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        query = NotificationQuery(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        data = query.validated_data
        qs = request.user.notifications.all()
        if "unread" in data:
            qs = qs.filter(read__isnull=data["unread"])
        count = qs.count()
        rows = list(
            qs[data["offset"] : data["offset"] + data["limit"]].values(
                "id", "created", "read", "object_type_id", "object_id", "object_repr", "event_type"
            )
        )
        return Response(
            {
                "count": count,
                "results": rows,
                "next_offset": data["offset"] + len(rows) if data["offset"] + len(rows) < count else None,
            }
        )

    @extend_schema(request=NotificationAction, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        body = NotificationAction(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if len(set(data["ids"])) != len(data["ids"]):
            raise ValidationError({"ids": "Duplicate IDs are not allowed."})
        if data["action"] == "dismiss_unread" and data["ids"]:
            raise ValidationError({"ids": "Omit ids when dismissing all unread notifications."})
        if data["action"] != "dismiss_unread" and not data["ids"]:
            raise ValidationError({"ids": "Select one or more notifications."})
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            qs = request.user.notifications.select_for_update()
            if data["action"] == "dismiss_unread":
                selected = list(qs.unread())
            else:
                selected = list(qs.filter(pk__in=data["ids"]))
                if len(selected) != len(data["ids"]):
                    raise NotFound("One or more notifications are missing or belong to another user.")
            if data["action"] == "read":
                now = timezone.now()
                for notification in selected:
                    notification.read = now
                    notification.save()
            else:
                request.user.notifications.filter(pk__in=[obj.pk for obj in selected]).delete()
        return Response(
            {"action": data["action"], "ids": [obj.pk for obj in selected], "count": len(selected)}
        )
