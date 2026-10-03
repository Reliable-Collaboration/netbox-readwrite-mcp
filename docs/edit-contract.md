# Execution and recovery contracts

The general tools accept native NetBox payloads across resources; native
permissions, field validation and relationship constraints remain authoritative.
Supporting execution does not establish automatic reversibility.

| Operation | Execution | Recovery |
| --- | --- | --- |
| Read/search/schema/GraphQL | Native queries | No mutation |
| General create | POST with durable key and native evidence | Retained created-object graph; guided correction checks later affected-object changes |
| General detail PATCH | Fresh ETag, retained pre-image, correlated changes | Field-aware inverse when one native change and exact writable before/after values establish the contract; conflicts/ABA block |
| Detail DELETE | Fresh ETag and retained native cascade changes | Guided graph recovery; no claim that REST recreation preserves original IDs |
| Native bulk/action/upload | Durable request/receipt and all correlated native rows | Explicit action-specific evidence; no cross-object atomicity promise |
| Resumable bulk/workflow | Per-step derived keys, stop on failure/uncertainty | Inspect partial task; no blind workflow restart under a new key |
| Website forms | Native session/CSRF/permissions, retained request/result | Form validation and native evidence inspected; arbitrary form inverses are not synthesized |
| Script/job | Submission receipt and recognized job tracking | Acceptance separate from completion; job failure may have partial effects |
| Existing device description/serial/status path | Original normalization and conditional-write contract | Exact field-aware compensation, including repeated-field task recovery |

General compensation never dispatches a synthesized inverse for an unknown
serializer transformation. Scalar and compatible relationship values can be
converted from native REST representations. Only verified correction evidence
whose post-image equals original native pre-image establishes completed undo.
Newer unrelated fields survive; newer same-field changes, including ABA, conflict.

Graph restoration and original-ID undelete are still the subject of the proposed
NetBox-side extension described in deletion-recovery.md. Keeping a graph's
before-images is not equivalent to having implemented that extension. Recovery
assessments expose this boundary rather than declaring success.

Tests use the real pinned NetBox and distinguish successful lifecycle tests from
metadata/reachability sweeps. Deployment plugins and custom validators require
their own qualification.
