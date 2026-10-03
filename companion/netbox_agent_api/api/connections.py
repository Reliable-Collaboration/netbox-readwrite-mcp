"""Own social-login associations through the configured native disconnect pipeline."""

import hashlib
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from social_core.exceptions import MissingBackend, NotAllowedToDisconnect
from social_django.utils import load_backend, load_strategy

from .configuration import Conflict, StrictSerializer


def connection_state(user):
    entries = list(user.social_auth.order_by("pk").values("id", "provider", "uid"))
    return {
        "results": entries,
        "expected": hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest(),
    }


class DisconnectWrite(StrictSerializer):
    provider = serializers.CharField()
    id = serializers.IntegerField(min_value=1, required=False)
    expected = serializers.CharField()
    changelog_message = serializers.CharField(required=False, write_only=True)


class ConnectionsView(APIView):
    """List own associations and invoke native account-disconnection validation."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(connection_state(request.user))

    @extend_schema(request=DisconnectWrite, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        body = DisconnectWrite(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                list(user.social_auth.select_for_update().all())
                before = connection_state(user)
                if before["expected"] != data["expected"]:
                    raise Conflict("Account associations changed. Read them again.")
                selected = user.social_auth.filter(provider=data["provider"])
                if "id" in data:
                    selected = selected.filter(pk=data["id"])
                if not selected.exists():
                    raise NotFound("Association is missing or belongs to another user.")
                strategy = load_strategy(request._request)
                backend = load_backend(strategy, data["provider"], redirect_uri=None)
                result = backend.disconnect(user=user, association_id=data.get("id"))
                if not isinstance(result, dict):
                    raise ValidationError(
                        "The configured custom disconnect pipeline requires an interactive identity-provider flow."
                    )
                return Response(connection_state(user))
        except NotAllowedToDisconnect as exc:
            raise ValidationError(
                "Native identity validation prevents removing the last usable login method."
            ) from exc
        except MissingBackend as exc:
            raise ValidationError("This association's authentication backend is not configured.") from exc
