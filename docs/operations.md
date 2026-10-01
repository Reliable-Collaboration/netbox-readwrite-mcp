# Operations

The runtime accepts stable NetBox 4.7.x and later. NetBox 4.7.2 is the tested
release; later versions are accepted without claiming equivalent qualification.
Check discovery, affected workflows and recovery behavior against a test instance
before upgrading an existing deployment. The CI lab remains pinned to 4.7.2.

## Identities and credentials

Provision a dedicated non-superuser NetBox actor. Give it the native view/add/
change/delete permissions required for inventory and action permissions such as
run or render only where needed. Provide full view access to core.objectchange.
Do not grant audit-history deletion merely to manage inventory. Permissions on
configuration, scripts and users require separate deliberate operator choices.

The API token and optional website password belong to the same actor. Keep both
in mode-600 files under a protected directory. Website authentication uses native
sessions and CSRF; deployments enforcing SSO/MFA need a separately qualified
login mechanism. The password-based adapter does not bypass those controls.

The optional read_only connection policy blocks all exposed mutation paths.
For HTTP use a separate MCP bearer token, at least 32 random characters, and a
trusted TLS reverse proxy for remote use. Direct binding is loopback only.

## Evidence and retention

Set CHANGELOG_RETENTION=0 in effective NetBox configuration and disable purge
jobs. History and receipts can contain sensitive inventory. The journal uses
local SQLite WAL, synchronous FULL, append-only events, hash/projection checks,
and POSIX locks. All active processes for a deployment must share one local
journal. Do not use NFS or independent restored active copies.

Reconciliation is explicit and runs around writes; there is no background polling
while idle. Monitor observability for unresolved outcomes, archive failures,
correlation problems, tool errors and storage capacity. Tool events record name,
duration, outcome and operation ID. Hashes detect corruption; a privileged
administrator can rewrite them. Preserve independently stored backups.

```sh
netbox-readwrite-mcp --config config.json --backup /protected/new-backup.sqlite
netbox-readwrite-mcp --config config.json --export /protected/new-export.json
```

Existing destinations are refused. Back up NetBox's database too, retaining
capture times and instance lineage. A stale journal backup can miss later
operations. Never assume restoring it reconstructs missing intent.

## Existing journal migration

Existing events are preserved. The general-operation projection is an additive
table; opening a journal does not rewrite historical events. URL, lineage, actor
and scope remain bound to that journal. A restricted device journal does not
become general-purpose just because allowed_device_ids is removed from config.

For an established deployment, stop writers, back up both evidence stores,
reconcile all pending work, and review the scope transition before provisioning
a new broad-scope lineage/journal. Retain the previous journal for correction of
its existing operations. Do not create a new journal to evade unresolved work.
A new greenfield deployment starts directly with the broad configuration.

## Recovery and upgrades

On a storage or history failure stop mutation and restore observability first.
For uncertain operations preserve original keys and use reconciliation. Absence
of a matching change does not establish non-commit. Async job failures can have
partial effects. There is no force-resolution command.

preview_undo returns ready only for a verified correction contract. General
PATCH compensation detects same-field ABA and preserves unrelated fields.
Graph operations, creates/deletes, bulk changes, scripts and website actions may
require guided recovery. Exact original-ID graph restoration still requires the
proposed NetBox-side recovery extension; native REST recreation changes IDs.
Do not represent guided recovery as automatically completed undo.

Before a NetBox upgrade, test paired copies of the database and journal. Native
history may change under migrations; archived-row mismatches remain blocking.
Never rewrite archived evidence or start a new journal to suppress them.

The target deployment is a small home lab (roughly 1000 or fewer assets).
Full history scans favor a simple implementation. High availability, distributed
storage and large-estate throughput are not current qualification targets.

## Native history serialization

History synchronization requests immutable audit fields explicitly: IDs, time,
actor name, request ID, action, object type/ID, stored representation/message and
before/after snapshots. It omits live expanded object/user references. NetBox
4.7.2 can return HTTP 500 while expanding a live port-mapping change record; its
immutable fields remain readable. These are the same fields already retained in
the journal, so this transport change does not alter archived record hashes or
require resetting history. The client still fails closed if audit reads fail.
