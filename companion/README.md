# NetBox Agent API Support

An Apache-2.0 companion plugin for **NetBox Community 4.7.2 only**. It exposes the
native filter definitions omitted from OpenAPI and typed APIs for Community
operations missing from native REST: imports and bulk forms, component patterns,
exports and file downloads, configuration revisions, dashboards, account actions,
search, synchronized data, chassis swaps and guarded deletion. See the
[operation map](../docs/api-completion.md) and [agent guide](../docs/agent-guide.md).
It adds no database models. Configuration endpoints can change the running NetBox
configuration; ordinary inventory work does not require them.

## Install

From the repository root, build the separate distribution:

```sh
python -m pip install build
python -m build companion
```

Install `companion/dist/netbox_agent_api-0.3.0-py3-none-any.whl` into the Python
environment used by both NetBox web and worker processes, or include it in their
shared NetBox image. For example, after copying the wheel to the NetBox host:

```sh
/opt/netbox/venv/bin/python -m pip install /path/to/netbox_agent_api-0.3.0-py3-none-any.whl
```

Replace those paths for your deployment. Add `netbox_agent_api` to your existing
`PLUGINS` list and restart both NetBox web and worker processes using your normal
plugin installation process. Invalidate cached OpenAPI responses on
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
has no side effects. `POST` initializes native defaults if absent; `PATCH` changes
only specified widgets; `PUT` replaces the complete layout/config; `DELETE` resets
to uninitialized. Every mutation
requires the exact `If-Match` ETag from a fresh read and a write-enabled token.
No administrative dashboard permission or browser visit is needed. No user ID
input is accepted. Prefer PATCH for one-widget edits: send only the entries to
add/replace in `layout` and `config`, or `{"remove":["widget-uuid"]}`. New widgets
need matching IDs in both layout and config. Specified entries are complete
replacements for those entries; other entries and their order are retained.
Empty patches, duplicate IDs, removing an unknown widget, and changing/removing
the same widget together are rejected. PUT still replaces the whole graph and
requires preserving every desired existing widget explicitly.

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
concurrent initialization, stale guards, per-widget PATCH lifecycle and preservation,
fresh OpenAPI, and response loss after
commit. Native `users/config/` preference PATCH is also tested for deep-merge
semantics and isolation. MCP sends preference bodies unchanged, without inserting
an audit marker into the user's data; native preferences have no ETag or native
ObjectChange recovery contract.

GLM also passed the per-widget PATCH scenario against nine existing native widgets
in 868.20 seconds, including required-content and stale-ETag rejections, verification
reads and exact restoration. It corrected one additional malformed request; that
attempt remains in the evidence. No host/browser tools or manual task completion
were used. See [agent evaluation](../docs/agent-evaluation.md) for the scoped proof
and earlier failed attempts.

## Native import and bulk operation APIs

Four catalogs expose stock Community handlers: `imports/`, `bulk-rename/`,
`bulk-edit/`, and `pattern-create/`, under `/api/plugins/agent-support/`.
Each lists models the caller may operate on. A model detail URL, for example
`imports/dcim.site/`, provides native field metadata on GET and accepts a typed
operation envelope on POST. OpenAPI documents the envelopes. The implementation
calls native Python forms and operation helpers without HTML/session requests.
See the [agent guide](../docs/agent-guide.md#native-imports-and-bulk-forms) for inputs.

Imports preserve native CSV/JSON/YAML parsing, relationship lookups, custom
fields, partial update semantics and model-specific save hooks. Native add and
change constraints are enforced separately. Malformed IDs and unknown fields
are rejected before saving. Every request is one transaction, including related
records. Imports retain the native lack of a conditional-write guard.

Rename uses native literal/regex substitution, restricts field selection to the
native rename fields and requires the previous preview's selected values when
applying. Bulk edit preserves native clearing, tag deltas and per-model hooks;
it requires hashes of selected records from the preceding validation request.
Both lock the selected rows before checking their guards and applying. These
are content guards, not globally enforced revisions or ABA-proof generations;
native website writers do not participate in this API's preview protocol.

Pattern creation expands native IP/prefix/VLAN ranges and component names,
labels and other replication fields. Multiple parent inputs can be combined in
one atomic request. Native field validation, add constraints and changelog
messages still apply. Bulk operations execute synchronously for the home-lab
scope. Native object APIs and native asynchronous jobs remain available.

Schema sweeps and representative lifecycle tests are recorded separately from
full feature qualification. These endpoints do not imply universal automatic
undo or that every native form combination has been tested. On response loss,
retain the operation key and reconcile native history before another mutation.

Additional API families cover own profile/preferences/password/notifications and external-account disconnection,
permission-scoped native search and Markdown preview, system/database/queue
metadata, authenticated image and data-file downloads, native table/CSV/YAML/template exports,
atomic cable disconnection and data-file synchronization, atomic virtual-chassis
position swaps, script form/source discovery, and guarded deletion of data files,
job records and script modules. Discover `api/plugins/agent-support/` for paths
and use the live OpenAPI schema for request fields. External queue and filesystem
effects of native deletion cannot be rolled back by a database transaction.
