# NetBox Agent API Support

An Apache-2.0 companion plugin for **NetBox Community 4.7.2 only**. It exposes the
running resource's native filter definitions as JSON, including custom-field
filters omitted from OpenAPI, and provides APIs for native configuration revisions and personal dashboards.
It adds no database models. Configuration endpoints can change the running NetBox
configuration; ordinary inventory work does not require them.

## Install

Build the separate distribution with `python -m build companion`, then install
the wheel into NetBox's Python environment (or include it in your NetBox image).
Add `netbox_agent_api` to your existing `PLUGINS` list and restart NetBox using
your normal plugin installation process. Invalidate cached OpenAPI responses on
upgrade so clients discover new endpoints immediately (native schema URLs can be
cached for a day); use your deployment cache maintenance procedure, not the job
queue. For a deployment with no other plugins:

```python
PLUGINS = ["netbox_agent_api"]
```

The disposable Podman lab mounts this source and configuration for both web and
worker processes. An existing lab created before the plugin needs its web and
worker containers recreated with the new mounts; preserve its database volume.

## Filter metadata contract

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
Qualification also forces a fresh OpenAPI response: NetBox caches schema URLs for
a day, so testing only a previously cached response can hide plugin schema errors.

## Configuration revisions

These endpoints fill a confirmed gap in the pinned Community release. They call
native Python validation and activation directly, without browser sessions or HTML.
Use MCP `query`, `get_schema`, and `execute_action` with paths relative to `/api/`.

| Endpoint under `plugins/agent-support/` | Operation |
| --- | --- |
| `configuration-schema/` | GET native field types and statically configured/read-only flags; no current values |
| `config-revisions/` | GET visible revisions and active revision ID; POST create and immediately activate |
| `config-revisions/{id}/` | GET a visible revision with ETag; DELETE an inactive revision |
| `config-revisions/{id}/activate/` | POST restore a visible saved revision |

Creation example (discover the current revision first):

```json
{
  "expected_active_revision": null,
  "comment": "Initial lab configuration",
  "parameters": {"BANNER_TOP": "Home lab", "PREFER_IPV4": true}
}
```

`null` means no active revision exists. Otherwise supply its integer ID. Every
mutation requires `expected_active_revision`; a stale value returns 409 without
writing. `parameters` is a **complete replacement of dynamic overrides**, not a
patch. Preserve desired existing writable overrides explicitly. Omitted writable
settings fall back to native defaults. Existing static and excluded commercial
overrides are retained unchanged; omit them from `parameters`. Static deployment
settings remain authoritative. Restoration refuses revisions that would change
the excluded commercial setting. JSON arrays,
booleans and integers must have their actual JSON types. Native form rendering
omits empty strings, nulls and empty arrays (resetting those overrides); false
booleans and empty JSON objects remain explicit values. Unknown, static and
commercial Copilot settings are rejected. The server uses native field validators;
it does not claim additional semantic validation beyond NetBox's own fields.

Listing/detail require `core.view_configrevision`; creation requires
`core.add_configrevision`, including object constraints on the resulting revision;
deletion requires `core.delete_configrevision` for the target. Token writes must
be enabled. Restoration preserves the native 4.7.2 website's unusual
`core.configrevision_edit` check and also requires visibility of the target.
In the tested setup restoration is an administrative/superuser operation; ordinary
`change_configrevision` permission does not satisfy that native check.
The inventory identity is never upgraded to superuser by this plugin.

DELETE refuses the active revision. Restore another revision first. Send
`If-Match` with the detail ETag for conditional deletion (required by MCP's detail
mutation contract); a mismatch returns 412. Revision creation/activation serialize
on the native PostgreSQL table, including the first-revision case, and compare
the expected active ID while locked. As with native NetBox activation, PostgreSQL
and the configuration cache are separate stores; this is not a distributed
transaction or an ABA-proof configuration generation counter.

Native `ConfigRevision` has **no ObjectChange history**. The MCP journal retains
intent and HTTP receipts, and reports a successful exchange as `completed`, not
verified native-history `applied`. Optional `changelog_message` is accepted as MCP
transport metadata but is not persisted as a native change log. A lost response
remains uncertain: inspect revisions and the journal; do not blindly retry or
claim automatic undo. Restoring a revision is a new explicit guarded operation.

Real-NetBox qualification covers lifecycle and actual cached activation, native
field validation, replacement semantics, rejected static/unknown/commercial
settings, missing guards, stale restoration/deletion, simultaneous writers,
object-constrained non-superusers, read-only tokens, ETags, cold OpenAPI generation,
MCP discovery/receipts, same-key replay, and response loss after commit. GLM also passed the
API-only create/reset/cleanup scenario in 163.88 seconds with no tool errors or
truncations, while disclosing and removing an extra revision it created. The
privileged restore action and response-loss path are qualified deterministically,
not by that LLM scenario. See [agent evaluation](../docs/agent-evaluation.md).

## Personal dashboards

`GET plugins/agent-support/self/dashboard/` returns only the current user's
`initialized`, `layout` and `config`, plus an ETag. Reading an absent dashboard
has no side effects. `POST` initializes native defaults if absent; `PUT` replaces
the complete layout/config; `DELETE` resets to uninitialized. Every mutation
requires the exact `If-Match` ETag from a fresh read and a write-enabled token.
No administrative dashboard permission or browser visit is needed. No user ID
input is accepted. Preserve existing widget IDs and configurations when editing.

`GET plugins/agent-support/dashboard-widgets/` describes the five built-in
Community widget types, native defaults, fields and choices. New/changed widget
configurations pass the native widget forms; unchanged configurations retain
their exact values. Layout IDs must match config IDs uniquely, and positions must
fit the twelve-column grid. Empty dashboards are valid. Other plugins' widgets
need separate qualification and are excluded here.

Companion mutations serialize on the user and existing dashboard rows, including
first use. Missing guards return 428 and stale guards 412. This content-based
ETag is not an ABA-proof generation counter; native website/API writers do not
participate in the conditional-write contract and can overwrite state later.
Dashboards have no native ObjectChange history: successful MCP receipts are
`completed`; response loss remains uncertain and requires inspection, not blind
replay or automatic undo. No HTML is used.

Live tests cover first use, reset, empty layouts, all five widgets with valid and
invalid inputs, preservation of native defaults, user isolation, read-only tokens,
concurrent initialization, stale guards, fresh OpenAPI, and response loss after
commit. Native `users/config/` preference PATCH is also tested for deep-merge
semantics and isolation. MCP sends preference bodies unchanged, without inserting
an audit marker into the user's data; native preferences have no ETag or native
ObjectChange recovery contract.
