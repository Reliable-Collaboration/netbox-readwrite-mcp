# NetBox-wide agent operations: requirements and implementation design

Status: product requirements. Version 0.3.0 implements general discovery, CRUD,
actions, workflows and native website forms; see feature-matrix.md for measured
coverage. Universal action qualification and original-ID graph recovery remain
separate acceptance work, not implied by a generic transport.

## Required outcome

Scope clarification (2026-09-30): implement fully open-source NetBox Community
features. Exclude Branching and commercial product integrations; the managed
MCP feature list is a source of open-source capability ideas, not a requirement
to adopt proprietary or restrictively licensed backends.

An agent must be able to perform the actions available to its human-equivalent
NetBox identity: create, modify, and delete objects across NetBox, including
relationships, custom fields, bulk operations, and specialized GUI workflows.
NetBox permissions and validation remain authoritative. The MCP must not impose
a device-only object scope or a three-field allowlist as the product boundary.

Every attempted mutation needs durable intent, attributable execution evidence,
an explicit outcome, retained prior values where available, and actionable
recovery guidance. An uncertain result must never trigger a blind retry. Recovery
must detect intervening changes and warn instead of overwriting them. There is
no routine human approval workflow.

Supporting an action and automatically reversing it are separate requirements.
Deleting an object can cascade, and API recreation can change its identity.
Scripts and external effects can exceed the database transaction. No design may
label recreation, a backup restore, or partial compensation as exact undo.

## Measured starting point

Read-only introspection of the stock NetBox 4.7.1 Docker 5.1.1 lab found, after
excluding format-suffix aliases:

- 312 REST viewset routes representing 140 distinct queryset models.
- 133 create mappings, 133 partial-update mappings, and 132 destroy mappings.
- Bulk create/update/delete behavior and additional actions for synchronization,
  script execution, job control, configuration rendering, traces, and paths.
- 35 API routes without viewset action mappings, requiring separate inspection.

These are discovery counts, not guarantees that all routes are mutable or
independently supported. Model-less routes and plugin behavior require review.
The machine-readable [baseline](netbox-4.7-surface.json) records special actions.
[scripts/inventory_surface.py](../scripts/inventory_surface.py) reproduces the
registered-route inventory inside a NetBox installation without reading object
data. OpenAPI alone is insufficient to prove parity with registered GUI views.

## Architecture

1. **Discover capabilities.** Build a versioned catalog of REST schemas,
   serializers, relationships, permissions, and GUI actions. Track each action
   as implemented/tested, mapped to an equivalent workflow, or a documented gap.
   Include multipart uploads, allocation endpoints, jobs and plugin routes.
   Inventory gaps cannot silently become claims of full coverage.
2. **Generalize the journal.** Replace device-specific operation identity with
   resource/model identity, action, object IDs, full raw intent, request ID,
   affected-object evidence, task linkage and compensation linkage. Preserve
   existing immutable events through an explicit, tested migration. Journal
   operation keys, snapshots, outcomes and recovery assessments durably.
3. **Implement model-independent CRUD.** Expose discovery, search, read, create,
   update and delete tools using NetBox's schema and validation. Support nullable
   fields, choices, FK/M2M relationships, generic relations, custom fields and
   nested serializers. A GET representation is not automatically valid POST or
   PATCH input. Record serializer transformations and all affected objects.
4. **Handle specialized workflows.** Add action adapters for allocations, bulk
   operations/imports, files, jobs, script execution and administration. A 202
   receipt starts job tracking; it is not verified completion. Retain partial
   failure details and distinguish local idempotency from backend idempotency.
5. **Capture execution evidence.** Correlate all native changes caused by a
   request, not only its primary object. Include cascades and automatically
   created children. Determine which models/actions lack sufficient native
   logging. A NetBox-side open-source extension is needed where REST cannot
   provide transaction-linked evidence or required recovery semantics. Do not
   substitute a post-request GET for committed effects.
6. **Plan recovery.** Return a dependency-aware plan, expected current state,
   conflict checks, exactness classification, and next actions. Apply supported
   compensation through the same durable write path. Preserve ID remappings for
   recreation. Inspect relationships created after the original operation before
   deleting an agent-created object. Cascades and graph restoration require
   server-side dependency analysis and concurrency control; a parent ETag alone
   does not establish an unchanged dependency graph.

Do not route around NetBox authorization or run unrestricted database writes as a
shortcut to GUI parity. A plugin must enforce the same permissions and validation.
Even a plugin cannot reverse external deliveries, recover unknown original
secrets, or promise exact rollback of arbitrary script effects.

## Recovery alternatives and subsequent investigation

The [deeper deletion investigation](deletion-recovery.md) now recommends original-ID, graph-aware restoration through a focused NetBox plugin. Fourteen lab tests establish feasibility and important hazards; the plugin is not yet implemented. This supersedes asking the user to accept new IDs before investigating the existing core helpers.

Two materially different contracts remain relevant for exceptional actions:

- **Broad execution with guided recovery:** allow authorized operations, retain
  durable evidence, and classify recovery as automatic compensation, guided
  recreation with ID remapping, or operator/backup recovery. Explicitly surface
  incomplete or irreversible effects. This matches broad GUI reach but cannot
  guarantee automatic exact undo for every operation.
- **Exact restoration required:** constrain execution to actions whose complete
  effects can be captured and restored, using a NetBox-side extension where
  necessary. Arbitrary scripts, external effects, unavailable secrets and some
  administrative actions still cannot meet an unconditional undo guarantee.
  Coordinated backup restoration is an operational fallback, not a selective
  concurrent undo of one transaction.

The choice is about the recovery contract, not permission to do the requested
work. Do not silently weaken the earlier history and recovery requirements while
expanding action coverage.

## Permissions and operational changes

The current instruction to grant only view/change on dcim.device belongs to the
existing restricted implementation. The expanded product will require view/add/
change/delete and action-specific permissions appropriate to the human-equivalent
role across the desired models. Do not prescribe superuser by default. Preserve
separate durable audit access/storage so an inventory action cannot erase its own
retained history. Changes to permissions, tokens and history retention need
explicit treatment because they can remove subsequent observability or access.

## Acceptance and test coverage

- A generated GUI/API coverage matrix must account for every stock 4.7 action;
  representative tests alone are not proof of universal coverage.
- Generate CRUD contract tests for every supported writable model, with valid
  fixtures and required dependency graphs. Keep special-action tests explicit.
- Cover uniqueness, read-only and required fields, null versus omission, defaults,
  normalization, Unicode, enum validation, constrained permissions and custom
  validators. Cover relationship assignment/removal and custom-field shapes.
- Verify cascade/protected deletion, automatically generated children, M2M and
  generic relations, recreation collisions, missing parents and ID remapping.
- Test stale writes/deletes, ABA changes, concurrent dependency insertion,
  partial bulk failures, asynchronous jobs, and concurrent human/agent actions.
- Exercise response loss and process termination before/after commit for every
  mutation class. Unknown outcomes must remain observable and block blind retry.
- Verify journal migration, backup/export/restart, complete affected-object
  correlation, archive failure, and local evidence integrity.
- Test MCP discovery, errors with corrective instructions, and a real agent-like
  sequence that discovers schemas and performs a multi-model lifecycle.
- Qualify plugins separately; discovery must expose untested actions honestly.

## Upstream references

- [REST API](https://netbox.readthedocs.io/en/stable/integrations/rest-api/)
- [NetBox 4.7 changes](https://netbox.readthedocs.io/en/stable/release-notes/version-4.7/)
- [Custom scripts](https://netbox.readthedocs.io/en/stable/customization/custom-scripts/)
