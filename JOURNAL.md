# Development journal

## 2026-09-28 — Public product baseline

Committed and pushed the preliminary research (7a0c6b6) after scanning tracked
candidates for known generated credentials. Created this separate public repository
at the user's request. All product commits are on feat/auditable-write-recovery.

The initial release will harden the proven direct REST/device update recovery
contract, package it independently of the research workspace, and provide both
offline tests and a disposable real-NetBox integration lab. Unsupported mutation
categories must be explicit, actionable refusals. Apache-2.0 applies to this
product; the original research MIT notice is retained.

No claim of universal reversibility or established production maturity is made.

## Direct REST engine and operator boundary

Ported the researched durable-intent/conditional-PATCH/native-history reconciliation
engine into an installable package, preserving its original license notice.
Added lookup by operation key for lost MCP responses, exposed validation receipts,
strict configuration with HTTPS outside loopback, relative config paths, protocol
input limits, stable error codes, and explicit capability annotations. The runtime
has no third-party Python dependencies. The test environment uses pytest,
Hypothesis, and the official MCP SDK to audit behavior independently.

Support is intentionally limited to NetBox 4.6.10 until the new standalone suite
qualifies additional versions. Recovery is compensation, not a database rollback.
