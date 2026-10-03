"""Conservative general-operation recovery assessments using retained native evidence."""

import json


def write_value(field, value):
    if field in {"custom_fields", "local_context_data", "config_context"}:
        return value
    if isinstance(value, dict):
        if "id" in value:
            return value["id"]
        if "value" in value:
            return value["value"]
    if isinstance(value, list):
        return [write_value(field, item) for item in value]
    return value


def assess(service, op):
    service.store.verify()
    service._sync()
    service._reconcile_resources()
    op = service.get_operation(op["id"])
    base = {
        "operation_id": op["id"],
        "automatic": False,
        "before": op["before"],
        "affected_objects": op["native_changes"],
        "conflicts": [],
        "external_effects": "Webhooks, scripts and downstream effects cannot be reversed by REST compensation.",
    }
    if op["state"] in {"failed", "no_change"}:
        return {**base, "status": "no_change"}
    if op["state"] != "applied":
        return {
            **base,
            "status": "blocked",
            "warning": "Native execution evidence is not verified; reconcile before correction.",
        }
    changes = op["native_changes"]
    affected = {(r["changed_object_type"], r["changed_object_id"]): r["id"] for r in changes}
    later = [
        r
        for r in service._records()
        if (r["changed_object_type"], r["changed_object_id"]) in affected
        and r["id"] > affected[(r["changed_object_type"], r["changed_object_id"])]
    ]
    if (
        op["transport"] == "rest"
        and op["method"] == "PATCH"
        and op["before"]
        and len(changes) == 1
        and not op.get("files")
    ):
        change = changes[0]
        fields = set(op["requested"]) - {"changelog_message"}
        before, after = change["prechange_data"], change["postchange_data"]
        if all(k in before and k in after for k in fields):
            fields = {k for k in fields if before[k] != after[k]}
            current = service.api.get(op["path"])
            # Cover edits (including B -> C -> B) between the first history
            # scan and this read. Its ETag protects changes after the read.
            service._sync()
            later = [
                r
                for r in service._records()
                if (r["changed_object_type"], r["changed_object_id"]) in affected
                and r["id"] > affected[(r["changed_object_type"], r["changed_object_id"])]
            ]
            inverse = {k: write_value(k, op["before"][k]) for k in fields if k in op["before"]}
            # Only verified field-level write/inverse pairs may be ignored for earlier task steps.
            ignored = {field: set() for field in fields}
            operations = {
                row[0]: json.loads(row[1])
                for row in service.store.db.execute("SELECT id,document FROM resource_operations")
            }
            for correction in operations.values():
                original = operations.get(correction.get("reverses"))
                if (
                    not original
                    or correction["state"] != "applied"
                    or len(original["native_changes"]) != 1
                    or len(correction["native_changes"]) != 1
                ):
                    continue
                first, second = original["native_changes"][0], correction["native_changes"][0]
                if (first["changed_object_type"], first["changed_object_id"]) != (
                    second["changed_object_type"],
                    second["changed_object_id"],
                ):
                    continue
                for field in fields:
                    if (
                        field in first["prechange_data"]
                        and field in second["postchange_data"]
                        and first["postchange_data"].get(field) == second["prechange_data"].get(field)
                        and first["prechange_data"][field] == second["postchange_data"][field]
                    ):
                        ignored[field].update([first["id"], second["id"]])
            conflicts = []
            for field in fields:
                if field not in current["body"] or write_value(field, current["body"][field]) != after[field]:
                    conflicts.append(
                        {"field": field, "reason": "Current value differs from committed effect"}
                    )
                for record in later:
                    if record["id"] in ignored[field]:
                        continue
                    if record["prechange_data"].get(field) != record["postchange_data"].get(field):
                        conflicts.append(
                            {
                                "field": field,
                                "native_id": record["id"],
                                "reason": "Intervening field change, including ABA",
                            }
                        )
            if conflicts:
                return {
                    **base,
                    "status": "conflicted",
                    "conflicts": conflicts,
                    "warning": "Newer edits affect fields being corrected. No automatic overwrite is allowed.",
                }
            if (
                fields == inverse.keys()
                and current["headers"].get("etag")
                and not any(isinstance(v, str) and v != v.strip() for v in inverse.values())
            ):
                return {
                    **base,
                    "status": "ready" if fields else "no_change",
                    "automatic": bool(fields),
                    "inverse": inverse,
                    "expected_native_values": {k: before[k] for k in fields},
                    "etag": current["headers"]["etag"],
                    "path": op["path"],
                }
    conflicts = [
        {
            "native_id": r["id"],
            "object_type": r["changed_object_type"],
            "object_id": r["changed_object_id"],
            "reason": "Affected object changed after the original operation",
        }
        for r in later
    ]
    return {
        **base,
        "status": "conflicted" if conflicts else "guided_recovery",
        "conflicts": conflicts,
        "warning": "Graph restoration requires dependency analysis and original-ID recovery support. Native before-images are retained; recreation may change IDs. Review new references and all affected objects before a separate corrective operation.",
    }
