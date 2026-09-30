# NetBox Agent API Support

An Apache-2.0 companion plugin for **NetBox Community 4.7.2 only**. It exposes the
running resource's native filter definitions as JSON, including custom-field
filters omitted from OpenAPI. It has no database models and performs no writes.

## Install

Build the separate distribution with `python -m build companion`, then install
the wheel into NetBox's Python environment (or include it in your NetBox image).
Add `netbox_agent_api` to your existing `PLUGINS` list and restart NetBox using
your normal plugin installation process. For a deployment with no other plugins:

```python
PLUGINS = ["netbox_agent_api"]
```

The disposable Podman lab mounts this source and configuration for both web and
worker processes. An existing lab created before the plugin needs its web and
worker containers recreated with the new mounts; preserve its database volume.

## Contract

`GET /api/plugins/agent-support/filter-schema/?resource=dcim/devices/`

```json
{
  "schema_version": 1,
  "resource": "dcim/devices/",
  "filters": {
    "name": {"type": "MultiValueCharFilter", "lookup": "exact"}
  }
}
```

The example is abbreviated. Filter types and lookups come from the live native
FilterSet. No inventory rows, field values, credentials or choices are returned.
The endpoint checks the target API view's permissions under the caller's own
identity. It rejects external URLs/traversal and does not provide mutation verbs.

The MCP server uses this metadata for discovery and validation. Unknown filters
are rejected before querying inventory, because NetBox can silently ignore them.
Without the plugin, standard OpenAPI filters remain available; undocumented
dynamic filters are refused until their native definitions can be verified.
Custom-field metadata is fetched afresh so disabled/deleted filters do not become
stale accepted query parameters. Native API permissions still govern the actual
query. This is metadata support, not a universal API for every web-only action.

## Qualification

Real-NetBox tests check native and custom-field discovery, enable/disable changes,
wrong-model rejection, restricted-user permission equivalence, invalid paths and
unsupported mutation methods. Both the MCP and this plugin pin the same NetBox
release. Changes to NetBox internals require renewed qualification.
