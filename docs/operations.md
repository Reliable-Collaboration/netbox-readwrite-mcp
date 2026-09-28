# Operator guide

## Prerequisites and permissions

Use a qualified NetBox version (4.7.1 recommended; 4.7.0 and legacy 4.6.10 also qualified), unmodified native change logging, a dedicated token identity, and durable local storage. NetBox 4.5 lacks the required conditional-update contract and is refused.

In NetBox's permission administration, create:

| Object type | Actions | Constraints |
| --- | --- | --- |
| dcim.device | view, change | For example: {"id__in": [42, 43]} |
| core.objectchange | view | Complete history visible to this deployment |

Attach these permissions to the agent user or its dedicated group. Do not grant add/delete or superuser status. Create a write-enabled token owned by that user. Match the username exactly in the server configuration. The synthetic lab seed script demonstrates this setup; **do not run the seed script against production**.

Native device permissions protect the object scope if a token escapes the MCP boundary. NetBox's change permission is not a per-field permission: a holder of the raw token may edit fields this server refuses. Keep the token outside model prompts and general-purpose agent shell access. The server's field restrictions depend on that boundary.

Complete history permission can reveal inventory outside the writable device scope. This version archives the full accessible history to detect loss and intervening changes. Protect the journal as sensitive inventory data. A stricter history-scope adapter needs separate qualification.

## Retention and reconciliation

Set CHANGELOG_RETENTION to 0 in effective NetBox configuration, restart the relevant processes, and confirm it through your deployment's configuration tooling. Do not rely only on an environment variable being present: deployment wrappers can override it. Remove independent purge jobs.

The server has no age-based pruning. It archives native history before writes and during explicit reconcile calls. It is **not a background daemon that continuously polls while idle**. Schedule reconcile through an MCP client if you need freshness independent of editing; keep native retention disabled in all cases. History access failure blocks writes. Previously archived rows remain available even when upstream history disappears.

Monitor observability:

- Unresolved operations: investigated until the outcome is proved; no automatic retry.
- Archive age, stale flag (over 60 seconds), and missing native IDs.
- Counts of archive_failed, correlation_conflict, and tool_refused events.
- Integrity result and disk capacity.

The stale flag is informational: preflight refreshes before writing. Missing history and integrity failures are blocking. Monitor failed operations separately; definitive validation failures can be corrected deliberately.

## Storage and backup

Use a dedicated OS account and a mode-700 parent directory. Token, journal, lock, WAL, and backup data belong to that account. Keep all active server processes on the same local filesystem and journal. Do not use NFS, an ephemeral container layer, or multiple restored copies as concurrent writers.

The application uses synchronous FULL and WAL. This cannot compensate for storage that lies about fsync or loss of all replicas. Back up both NetBox's database and this journal, preserving version, configuration identity, and their capture times.

~~~sh
netbox-readwrite-mcp --config /etc/netbox-rw/config.json --backup /backups/new-journal.sqlite
netbox-readwrite-mcp --config /etc/netbox-rw/config.json --export /backups/new-journal.json
~~~

The backup operation returns a SHA-256 receipt. JSON exports have a SHA-256 sidecar and are for inspection; there is no JSON-import command. Preserve copies off-host and protect against alteration. Evidence includes full server receipts, potentially including custom inventory data; it must not be published as ordinary application logs.

## Recovery drill

1. Stop all writer clients/processes. Preserve the current journal and sidecars for investigation.
2. Verify the independently stored backup digest. Restore the SQLite backup to a new protected path.
3. Point configuration at that path while preserving NetBox URL, instance ID, actor, and scope.
4. Inspect observability and recovery bundles. Reconcile against the original NetBox lineage.
5. Preview undo; verify current field values and evidence. Apply only an eligible correction.
6. Resume a single writer deployment after investigation. Never leave both original and restored copies active.

A stale journal backup can miss operations that occurred after the backup. Native markers without corresponding durable intents are not automatically imported as reconstructed operations. Treat post-backup activity as an audit incident; do not assume restoring a file gives a complete current journal.

The integration suite verifies backup restoration and guarded correction, not every infrastructure disaster scenario.

## Conflicts and uncertain dispatches

A conflict is an expected safe result. Review the original change, current values, and intervening native evidence. If a person chooses a new value, submit a new forward edit against fresh state. Do not manually replay an exported inverse.

An uncertain dispatch may have no matching native record indefinitely. This release cannot safely prove non-commit from absence alone, and offers no force-resolution tool. Investigate NetBox/proxy logs and database history. Retain evidence and involve the operator; do not erase the pending row or switch journals to bypass it.

## Upgrades and configuration changes

Journal identity binds URL, lineage ID, actor, device scope, and policy version. Rotating a token for the same actor is supported; changing identity or scope is intentionally refused on an existing journal. Version 0.1 has no automatic migration command for these changes.

Qualify upgrades and planned scope/identity migrations in a copied isolated lab first. Preserve the previous journal and native history. Do not point a new empty journal at an existing deployment to evade pending operations. A restored NetBox database can reuse IDs or change history snapshots; preserve lineage and investigate mismatches before writing.

Full archive scans and hash verification grow with retained history. Measure latency and storage on your estate before rollout. Large-scale performance and high availability have not been qualified.


## Upgrading from 0.1.0 to 0.1.1

1. Stop all writer clients and retain a verified journal backup and export. Preserve the original evidence.
2. Upgrade every process that shares the journal; do not mix old and new binaries.
3. Keep the same configuration identity and journal path. No schema rewrite or new empty journal is required.
4. Call reconcile before resuming edits. It can append evidence-backed repairs for old dispatched no_change, uncertain, and applied_unverified receipts whose recorded post-image came from raw input or a later response representation. Previously appended events are preserved.
5. Inspect unresolved operations and preview any prior undo. A previously applied correction whose actual value differs from the original inverse now reports incomplete_restore. It does not authorize another automatic correction.
6. Resume only when outcomes have been reviewed. If native evidence cannot prove a legacy dispatch, it remains uncertain and blocks that device; do not delete it or retry with a new key.

Description and serial normalization is qualified against NetBox 4.6.10, 4.7.0, and 4.7.1 serializers.
Raw and normalized intent are both retained for new operations. Older records without
a normalization event use that same qualified profile when correlating native evidence.
A stored previous value with surrounding whitespace cannot be recreated exactly through
this REST serializer. New edits affecting such a value are blocked with UNRESTORABLE_VALUE;
historical inverses are refused with their previous values and an operator warning.
This is an explicit limitation, not a silently approximate undo.

## Targeting NetBox 4.7 with MCP 0.2.0

Stable 4.7.x versions are accepted; the live contract suite qualifies 4.7.0 and
4.7.1 individually. Future patches require qualification in your environment.
Prereleases, development builds, and other minor versions are refused. Legacy
4.6.10 remains accepted. The capabilities tool reports this distinction.

Updating this MCP server requires no configuration or journal schema change.
Stop writer processes, retain a verified backup, update all clients sharing the
journal, then reconcile before resuming. New intent events record the actual
NetBox version and normalization profile; previous events remain immutable.
The server continues using synchronous detail PATCH with If-Match; it does not
request NetBox 4.7 background REST execution or bulk operations.

**Upgrading the NetBox database is a separate operation.** These tests use fresh
databases and do not certify a 4.6-to-4.7 migration with an existing journal.
Follow the [NetBox 4.7 release notes](https://netbox.readthedocs.io/en/stable/release-notes/version-4.7/)
and upgrade procedure. First stop writers and preserve paired NetBox and journal
backups plus an evidence export. Test the upgrade on isolated copies with the
complete historical data. NetBox schema migrations can alter historical data;
reconciliation must still reject a native record that differs from its archived
copy. Inspect those differences before resuming. Do not remove journal records,
rewrite archived evidence, or start an empty journal to bypass a mismatch.
Retain the original evidence and restore the paired backups if the upgrade
cannot preserve the recovery contract. Production plugins and validators also
require deployment-specific qualification.
