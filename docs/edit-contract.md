# Edit coverage and extension contract

Considering each edit category means defining a recovery contract or refusing it, not passing arbitrary bodies through.

| Category | Examples | Policy / recovery concern |
| --- | --- | --- |
| Scalar text | Device description, serial; Unicode, multiline, empty | Supported; previous values retained, NetBox validates. |
| Choice | Device status | Supported strings; invalid choices yield durable validation receipts. |
| Multiple fields | Description + serial + status | One supported detail PATCH; inverse includes only effective changes. |
| No-op / replay | Same value / key | Retained no-op / original receipt. |
| Multiple objects | Several edits in one task | Sequential writes, resumable compensation, explicit partial outcomes. |
| Unique identifiers | Name, asset tag | Refused; another object may claim the old value. |
| Foreign keys | Site, role, tenant, platform, primary IP | Refused; references, permissions, and validation can change or disappear. |
| Placement | Rack, position, face, chassis | Refused; occupancy and multi-field constraints. |
| Collections | Tags, memberships | Refused; normalization and concurrent set changes need an adapter. |
| Structured fields | Custom fields, JSON context | Refused; schema, defaults, nested paths, merge semantics. |
| Create/allocate/clone | Devices, addresses, prefixes, VLANs, VMs | No tool; lost POST receipts and new dependents complicate undo. |
| Delete/cascade | Interfaces, cables, devices | No tool; recreation changes IDs and can lose dependent graphs. |
| Other resources | Circuits, power, wireless, contacts, tenancy, plugins | No generic writes; resource-specific contracts required. |
| Bulk PUT/PATCH/DELETE | List endpoint mutations | No tool; batch atomicity and result ambiguity differ. |
| Reserved/read-only | IDs, timestamps, URLs, changelog marker | Rejected; caller cannot forge correlation markers. |
| Force/redo | Ignore concurrency / undo a correction | No tool; reviewed new forward edit required. |

Tests exercise every supported field, representative values from each unsupported field category, malformed tool inputs, unlisted mutation tools, and native validation/permission failures. They do not claim to test every internal NetBox model validator.

## Extension requirements

Before adding an adapter, define and test read/write normalization; full mutation effects and cascades; durable intent and lost-response correlation; inverse preconditions and preserved newer work; uniqueness and dependency changes; schema upgrades; permission changes; and backup compatibility.

Require real NetBox integration tests plus independent offline invariants. Include an actionable refusal when safe recovery cannot be proved. Merely adding a field to an allowlist does not establish reversibility.
