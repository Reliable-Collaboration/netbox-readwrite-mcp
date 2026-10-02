"""Conservative, derived explanations of durable receipts; never mutation evidence."""

from collections import Counter

STATE_MEANINGS = {
    "applied": "Correlated native change evidence exists; inspect affected objects.",
    "completed": "HTTP exchange finished. This does NOT mean read-only or no mutation. Inspect the response and read back the target.",
    "failed": "Historical rejected/abandoned attempt; it remains recorded after a successful correction.",
    "no_change": "The guarded edit required no effective field change.",
    "accepted": "Job submitted; execution and effects are not yet established.",
    "job_scheduled": "Job scheduled for later; it has not been proved complete.",
    "job_completed": "Native job finished; inspect its output and resulting state.",
    "job_failed": "Native job failed; partial effects may remain.",
    "job_missing": "Acknowledged job is no longer visible; completion and rollback are not established.",
}


def operation_outcome(operation):
    """Explain only evidence actually present; never infer no change from absent history."""
    state = operation.get("state")
    receipt = operation.get("last_receipt") or {}
    status = receipt.get("status")
    if state == "applied":
        effect = "native_changes_correlated"
        explanation = STATE_MEANINGS[state]
    elif state == "no_change":
        effect = "guarded_no_change"
        explanation = STATE_MEANINGS[state]
    elif state == "failed":
        effect = "attempt_rejected_or_abandoned"
        explanation = STATE_MEANINGS[state]
    elif state == "completed":
        if operation.get("transport", "rest") == "rest" and status == 201:
            effect = "server_reported_creation"
            explanation = (
                "HTTP 201 reports creation, not a read-only exchange. "
                "No correlated changelog record; verify the created object with a fresh read."
            )
        else:
            effect = "effects_require_verification"
            explanation = STATE_MEANINGS[state]
    else:
        effect = "effects_require_verification"
        explanation = STATE_MEANINGS.get(state, "Outcome is not established; inspect receipts and reconcile.")
    return {"effect_evidence": effect, "explanation": explanation}


def journal_summary_text(operations):
    """Ready-to-quote journal accounting, independent of a model's arithmetic or prose."""
    counts = Counter(op["state"] for op in operations)
    tally = ", ".join(f"{state}={counts[state]}" for state in sorted(counts))
    parts = [f"Journal records {len(operations)} operations" + (f" ({tally})." if tally else ".")]
    parts.extend(
        f"{state}: {STATE_MEANINGS.get(state, 'Inspect receipts and reconcile; effects are not established.')}"
        for state in sorted(counts)
    )
    creations = sum(
        operation_outcome(op)["effect_evidence"] == "server_reported_creation" for op in operations
    )
    if creations:
        parts.append(
            f"Completed receipts reporting HTTP 201 creation: {creations}. Verify the created targets with fresh reads."
        )
    parts.append(
        "These are journal operation counts, not counts of all MCP tool errors; rejected calls before journaling are not included."
    )
    return " ".join(parts)


def with_reporting(result):
    """Annotate known operation envelopes without altering persisted journal documents."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if {"id", "operation_key", "state"} <= result.keys():
        out["outcome_details"] = operation_outcome(result)
    for key in ("operation", "correction"):
        if isinstance(result.get(key), dict):
            out[key] = with_reporting(result[key])
    return out
