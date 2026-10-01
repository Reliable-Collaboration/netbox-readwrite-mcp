"""Native read-only system and queue views absent from the stock REST surface."""

from dataclasses import asdict
import json

from core.api.serializers import BackgroundTaskSerializer
from core.plugins import get_local_plugins
from core.utils import get_db_schema, get_rq_jobs_from_status
from core.views import SystemView as NativeSystemView
from django_rq.queues import get_queue
from django_rq.settings import get_queues_list
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from utilities.api import IsSuperuser
from netbox.config import PARAMS, get_config
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from utilities.apps import get_installed_apps
from utilities.json import ConfigJSONEncoder


class SystemView(APIView):
    """Administrative native runtime, configuration and model-count information."""

    permission_classes = [IsSuperuser]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        native = NativeSystemView()
        stats = native._get_stats()
        stats["netbox_release"] = stats["netbox_release"].asdict()
        config = get_config()
        data = {
            **stats,
            "django_apps": get_installed_apps(),
            "plugins": {name: asdict(plugin) for name, plugin in get_local_plugins().items()},
            "objects": {
                ot.app_label + "." + ot.model: count for ot, count in native._get_object_counts().items()
            },
            "config": {
                param.name: getattr(config, param.name)
                for param in PARAMS
                if not param.name.startswith("COPILOT_")
            },
        }
        return Response(json.loads(json.dumps(data, cls=ConfigJSONEncoder)))


class DatabaseSchemaView(APIView):
    """Read native PostgreSQL schema metadata under the website's superuser gate."""

    permission_classes = [IsSuperuser]

    @extend_schema(parameters=[OpenApiParameter("table", str)], responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        tables = get_db_schema()
        if name := request.query_params.get("table"):
            tables = [row for row in tables if row["name"] == name]
        return Response({"count": len(tables), "results": tables})


class QueueTasksView(APIView):
    """Inspect all native RQ registries, including failed and scheduled tasks."""

    permission_classes = [IsSuperuser]

    @extend_schema(
        parameters=[OpenApiParameter("queue", str, required=True), OpenApiParameter("status", str)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        names = [queue["name"] for queue in get_queues_list()]
        name = request.query_params.get("queue")
        statuses = ["queued", "started", "deferred", "finished", "failed", "scheduled"]
        if name is None:
            return Response({"queues": names, "statuses": statuses})
        status = request.query_params.get("status", "queued")
        if name not in names or status not in statuses:
            raise ValidationError("Select a configured queue and native registry status.")
        queue = get_queue(name)
        jobs = queue.get_jobs() if status == "queued" else get_rq_jobs_from_status(queue, status)
        return Response(
            {
                "queue": name,
                "status": status,
                "count": len(jobs),
                "results": BackgroundTaskSerializer(jobs, many=True, context={"request": request}).data,
            }
        )
