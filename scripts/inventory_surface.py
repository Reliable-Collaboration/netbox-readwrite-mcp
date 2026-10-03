"""Read-only route inventory; execute inside NetBox via manage.py shell.

Example: podman exec -i <netbox-container> /opt/netbox/venv/bin/python
/opt/netbox/netbox/manage.py shell < scripts/inventory_surface.py

Inspects registered routes, not user inventory. Routes are candidates for coverage,
not evidence that this MCP implements them. Includes installed plugin routes.
"""

import json

from django.conf import settings
from django.urls import URLResolver, get_resolver


def inventory(resolver, prefix=""):
    rows = []
    for route in resolver.url_patterns:
        path = prefix + str(route.pattern)
        if isinstance(route, URLResolver):
            rows.extend(inventory(route, path))
            continue
        callback = route.callback
        cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
        actions = getattr(callback, "actions", {})
        queryset = getattr(cls, "queryset", None)
        model = getattr(queryset, "model", None) or getattr(cls, "model", None)
        rows.append(
            {
                "route": path,
                "name": route.name,
                "view": f"{cls.__module__}.{cls.__name__}"
                if cls
                else callback.__module__ + "." + callback.__name__,
                "model": model._meta.label_lower if hasattr(model, "_meta") else None,
                "rest_actions": dict(sorted(actions.items())),
                "view_bases": [base.__name__ for base in cls.__mro__] if cls else [],
            }
        )
    return sorted(rows, key=lambda row: (row["route"], row["name"] or ""))


print(
    "NETBOX_SURFACE="
    + json.dumps(
        {"netbox_version": str(getattr(settings, "VERSION", "unknown")), "routes": inventory(get_resolver())},
        sort_keys=True,
    )
)
