"""Atomic member-position swaps using the stock virtual-chassis formset."""

import hashlib
import json

from core.signals import clear_events
from dcim.forms import BaseVCMemberFormSet, DeviceVCMembershipForm
from dcim.models import Device, VirtualChassis
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.forms import modelformset_factory
from drf_spectacular.utils import extend_schema, OpenApiTypes
from netbox.api.authentication import TokenWritePermission
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .configuration import Conflict, StrictSerializer


class MemberWrite(StrictSerializer):
    id = serializers.IntegerField(min_value=1)
    vc_position = serializers.IntegerField(min_value=0, max_value=255)
    vc_priority = serializers.IntegerField(min_value=0, max_value=255, allow_null=True)


class ChassisWrite(StrictSerializer):
    members = MemberWrite(many=True)
    expected = serializers.CharField()
    changelog_message = serializers.CharField(default="", allow_blank=True)


def visible_chassis(request, pk, action):
    if not request.user.has_perm("dcim." + action + "_virtualchassis"):
        raise PermissionDenied()
    obj = VirtualChassis.objects.restrict(request.user, action).filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    return obj


def snapshot(chassis, members):
    rows = [{"id": obj.pk, "vc_position": obj.vc_position, "vc_priority": obj.vc_priority} for obj in members]
    state = {"id": chassis.pk, "master": chassis.master_id, "members": rows}
    return {**state, "expected": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()}


class ChassisMembersView(APIView):
    """Read or atomically reorder native virtual-chassis members."""

    permission_classes = [IsAuthenticated, TokenWritePermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, pk):
        chassis = visible_chassis(request, pk, "view")
        return Response(snapshot(chassis, chassis.members.order_by("pk")))

    @extend_schema(request=ChassisWrite, responses={200: OpenApiTypes.OBJECT})
    def put(self, request, pk):
        body = ChassisWrite(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            with transaction.atomic():
                visible_chassis(request, pk, "change")
                chassis = VirtualChassis.objects.select_for_update().get(pk=pk)
                # Lock members and the parent before validating the complete formset.
                members = list(chassis.members.select_for_update().order_by("pk"))
                before = snapshot(chassis, members)
                if data["expected"] != before["expected"]:
                    raise Conflict("Membership changed. Read it again before editing.")
                ids = [row["id"] for row in data["members"]]
                if len(set(ids)) != len(ids) or set(ids) != {obj.pk for obj in members}:
                    raise ValidationError(
                        {
                            "members": "Include each current member exactly once. Use native device CRUD to add or remove members."
                        }
                    )
                values = {"form-TOTAL_FORMS": len(members), "form-INITIAL_FORMS": len(members)}
                for index, row in enumerate(data["members"]):
                    for key, value in row.items():
                        values[f"form-{index}-{key}"] = "" if value is None else value
                factory = modelformset_factory(
                    Device, form=DeviceVCMembershipForm, formset=BaseVCMemberFormSet, extra=0
                )
                formset = factory(values, queryset=chassis.members.order_by("pk"))
                if not formset.is_valid():
                    raise ValidationError({"members": formset.errors, "errors": formset.non_form_errors()})
                changed = formset.save(commit=False)
                for obj in Device.objects.filter(pk__in=[item.pk for item in changed]):
                    obj.snapshot()
                    obj.vc_position = None
                    obj._changelog_message = data["changelog_message"]
                    obj.save()
                for obj in changed:
                    obj._changelog_message = data["changelog_message"]
                    obj.save()
                return Response(snapshot(chassis, chassis.members.order_by("pk")))
        except (DjangoValidationError, IntegrityError) as exc:
            clear_events.send(sender=self)
            raise ValidationError(
                "Native membership validation failed; all changes were rolled back."
            ) from exc


class ChassisCatalogView(APIView):
    """Discover native virtual-chassis membership operations."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "collection": "dcim/virtual-chassis/",
                "members_path": "virtual-chassis/{id}/members/",
                "instructions": "Discover chassis and device IDs with native REST. Add/remove members through device CRUD. GET members for the expected guard; PUT all members to atomically swap positions using native form validation.",
            }
        )
