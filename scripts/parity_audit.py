"""Map every pinned stock website route to a semantic API family.

This is a coverage denominator, not proof of successful execution. Each family's
qualification is recorded separately; unknown routes fail instead of being hidden
behind a generic HTML fallback.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Exact exceptions precede generic inheritance rules: otherwise a specialized
# ObjectView could be incorrectly counted as ordinary object retrieval.
SPECIAL = {
    "account.views.ChangePasswordView": "account",
    "account.views.ProfileView": "account",
    "account.views.UserConfigView": "preferences",
    "account.views.UserTokenListView": "own-tokens",
    "account.views.UserTokenView": "own-tokens",
    "account.views.UserTokenEditView": "own-tokens",
    "account.views.UserTokenDeleteView": "own-tokens",
    "account.views.LoginView": "identity-transport",
    "account.views.LogoutView": "identity-transport",
    "account.views.SocialAuthBeginView": "identity-transport",
    "social_django.views.auth": "identity-transport",
    "social_django.views.complete": "identity-transport",
    "social_django.views.disconnect": "account-connections",
    "core.views.SystemView": "administration",
    "core.views.SystemDBSchemaView": "administration",
    "core.views.PluginListView": "installed-plugins",
    "core.views.PluginView": "installed-plugins",
    "core.views.DataSourceSyncView": "data-sources",
    "core.views.DataFileView": "data-files",
    "core.views.DataFileDeleteView": "native-deletion",
    "core.views.DataFileBulkDeleteView": "native-deletion",
    "core.views.JobDeleteView": "native-deletion",
    "core.views.JobBulkDeleteView": "native-deletion",
    "core.views.JobLogView": "jobs",
    "dcim.views.VirtualChassisEditView": "chassis",
    "dcim.views.VirtualChassisAddMemberView": "chassis",
    "dcim.views.VirtualChassisRemoveMemberView": "chassis",
    "dcim.views.MACAddressSetPrimaryView": "primary-mac",
    "dcim.views.PathTraceView": "traces-elevations",
    "dcim.views.RackElevationListView": "traces-elevations",
    "dcim.views.DeviceConfigContextView": "config-context",
    "dcim.views.DeviceRenderConfigView": "render-config",
    "virtualization.views.VirtualMachineConfigContextView": "config-context",
    "virtualization.views.VirtualMachineRenderConfigView": "render-config",
    "extras.views.ScriptListView": "scripts",
    "extras.views.ScriptView": "scripts",
    "extras.views.ScriptSourceView": "scripts",
    "extras.views.ScriptJobsView": "scripts",
    "extras.views.ScriptResultView": "scripts",
    "extras.views.ScriptModuleCreateView": "scripts",
    "extras.views.ScriptModuleDeleteView": "native-deletion",
    "extras.views.RenderMarkdownView": "markdown",
    "extras.views.NotificationsView": "notifications",
    "extras.views.NotificationReadView": "notifications",
    "extras.views.NotificationDismissView": "notifications",
    "extras.views.NotificationDismissAllView": "notifications",
    "netbox.views.misc.HomeView": "dashboard",
    "netbox.views.misc.SearchView": "search",
    "netbox.views.misc.MediaView": "media",
    "netbox.views.errors.StaticMediaFailureView": "presentation",
    "netbox.views.htmx.ObjectSelectorView": "object-selection",
    "netbox.graphql.views.NetBoxGraphQLView": "graphql",
}
BASES = [
    ("ObjectSyncDataView", "sync"),
    ("BulkSyncDataView", "sync"),
    ("BulkDisconnectView", "disconnect"),
    ("BulkComponentCreateView", "patterns"),
    ("ComponentCreateView", "patterns"),
    ("BulkCreateView", "patterns"),
    ("BulkImportView", "imports"),
    ("BulkRenameView", "rename"),
    ("BulkEditView", "bulk-edit"),
    ("BulkDeleteView", "bulk-delete"),
    ("ObjectEditView", "crud"),
    ("ObjectDeleteView", "crud"),
    ("ObjectChangeLogView", "history"),
    ("ObjectJournalView", "journals"),
    ("ObjectImageAttachmentsView", "attachments"),
    ("ObjectJobsView", "jobs"),
    ("ObjectContactsView", "contacts"),
    ("ObjectChildrenView", "related-objects"),
    ("ObjectListView", "lists-exports"),
    ("ObjectView", "crud"),
]
FAMILIES = {
    "account": ("self/profile and self/password companion; native own-user identity", "test_account.py"),
    "preferences": ("native users/config plus guarded self/preferences", "test_account.py"),
    "own-tokens": ("native users/tokens under own-object permissions", "test_account.py"),
    "identity-transport": (
        "Token authentication replaces browser sessions. Initial external OAuth consent/login remains an identity-provider interaction.",
        None,
    ),
    "account-connections": (
        "self/connections uses the native disconnect pipeline and last-login guard",
        "test_connections.py",
    ),
    "administration": (
        "companion system, database-schema and queue-tasks; native queue/worker/task actions",
        "test_administration.py;test_utilities.py",
    ),
    "installed-plugins": (
        "companion system exposes installed local OSS plugin metadata; external commercial marketplace listings are outside product scope",
        "test_utilities.py",
    ),
    "data-sources": ("native data-source CRUD and sync worker action", "test_batch_actions.py"),
    "data-files": (
        "native data-file metadata; companion media/core.datafile/{id}/data byte content",
        "test_utilities.py",
    ),
    "native-deletion": (
        "companion native-delete previews and guarded single/bulk deletion; queue/filesystem effects cannot join database rollback",
        "test_deletion.py",
    ),
    "jobs": ("native core/jobs status, data, errors and log_entries", "test_scripts.py;test_inventory.py"),
    "chassis": (
        "native device/chassis relationships plus atomic companion member-position swaps",
        "test_chassis.py",
    ),
    "primary-mac": (
        "native interface/VM-interface primary_mac_address relationship",
        "test_chassis.py;test_domains.py",
    ),
    "traces-elevations": (
        "native trace and rack elevation actions; use native rack filters for sets",
        "test_inventory.py",
    ),
    "config-context": (
        "native device/VM config_context and local_context_data; native context/profile CRUD",
        "test_inventory.py",
    ),
    "render-config": ("native device/VM render-config actions", "test_inventory.py"),
    "scripts": (
        "native uploads, replacement, execution, scheduling and job results; companion variable schemas and class source",
        "test_scripts.py;test_inventory.py",
    ),
    "markdown": ("companion native Markdown renderer", "test_utilities.py"),
    "notifications": (
        "native own-notification CRUD plus self/notifications read/dismiss/dismiss-unread",
        "test_account.py",
    ),
    "dashboard": (
        "companion self/dashboard and native widget forms; native list counts for home statistics",
        "test_personal.py",
    ),
    "configuration": (
        "companion native configuration revisions, activation, restore and deletion",
        "test_configuration.py",
    ),
    "search": ("companion native scoped search backend", "test_utilities.py"),
    "media": ("native multipart upload; companion permission-checked byte download", "test_utilities.py"),
    "presentation": (
        "Browser layout and missing-static-file error presentation; no inventory operation",
        None,
    ),
    "object-selection": (
        "native model collections and filter schemas replace HTMX selectors",
        "test_inventory.py",
    ),
    "graphql": ("native GraphQL through the graphql MCP tool", "test_inventory.py"),
    "sync": ("native single-object sync plus guarded atomic companion bulk-sync", "test_batch_actions.py"),
    "disconnect": ("guarded atomic companion bulk-disconnect", "test_batch_actions.py"),
    "patterns": (
        "native range/component forms through pattern-create; items compose multiple parents atomically",
        "test_patterns.py;test_component_patterns.py",
    ),
    "imports": (
        "native CSV/JSON/YAML forms and related saves through companion imports",
        "test_imports.py;test_nested_imports.py",
    ),
    "rename": ("native literal/regex rename with companion preview and stale guards", "test_rename.py"),
    "bulk-edit": (
        "native bulk forms and save hooks with companion preview and stale guards",
        "test_bulk_edit.py",
    ),
    "bulk-delete": ("native REST bulk DELETE; durable generic action receipts", "test_inventory.py"),
    "crud": ("native REST object creation, retrieval, update and deletion", "test_inventory.py"),
    "history": ("native core/object-changes and MCP retained correlated history", "test_inventory.py"),
    "journals": ("native extras/journal-entries filtered by assigned object", "test_domains.py"),
    "attachments": (
        "native extras/image-attachments filtered by assigned object; companion byte downloads",
        "test_utilities.py",
    ),
    "contacts": ("native tenancy/contact-assignments and roles/groups", "test_domains.py"),
    "related-objects": (
        "native child collections with relationship/address-containment filters",
        "test_inventory.py",
    ),
    "lists-exports": (
        "native list/filter/order/pagination and companion native CSV/table/YAML/template exports",
        "test_exports.py;test_inventory.py",
    ),
}


def family(row):
    view = row["view"]
    if view in SPECIAL:
        return SPECIAL[view]
    if view.startswith("core.views.ConfigRevision"):
        return "configuration"
    if view.startswith(("core.views.Background", "core.views.Worker")):
        return "administration"
    if view.startswith("extras.views.Dashboard"):
        return "dashboard"
    for base, result in BASES:
        if base in row["view_bases"]:
            return result
    return None


def audit(surface):
    rows = [r for r in surface["routes"] if not r["route"].startswith("api/")]
    mapped = [{"route": row["route"], "view": row["view"], "family": family(row)} for row in rows]
    counts = Counter(row["family"] for row in mapped)
    native = {}
    for row in surface["routes"]:
        if row["route"].startswith("api/") and row.get("model"):
            native.setdefault(row["model"], set()).update(row["rest_actions"].values())
    method_gaps = []
    for row in rows:
        if family(row) != "crud" or not row.get("model"):
            continue
        if "ObjectDeleteView" in row["view_bases"]:
            action = "destroy"
        elif "ObjectEditView" in row["view_bases"]:
            action = "update" if "<" in row["route"] else "create"
        else:
            action = "retrieve"
        if action not in native.get(row["model"], set()):
            method_gaps.append({"route": row["route"], "model": row["model"], "action": action})
    return {
        "netbox_version": surface["netbox_version"],
        "website_route_count": len(rows),
        "native_method_gaps": method_gaps,
        "unknown": [r for r in mapped if r["family"] is None],
        "families": {
            name: {
                "routes": counts[name],
                "implementation": description,
                "integration_files": tests.split(";") if tests else [],
                "scope": "identity/presentation boundary"
                if tests is None
                else "semantic mapping; see validation evidence for qualification",
            }
            for name, (description, tests) in FAMILIES.items()
            if counts[name]
        },
        "routes": mapped,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    report = audit(json.loads((ROOT / "docs/netbox-4.7-surface.json").read_text()))
    if args.write:
        args.write.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "website_routes": report["website_route_count"],
                "families": len(report["families"]),
                "unknown": report["unknown"],
                "native_method_gaps": report["native_method_gaps"],
            },
            indent=2,
        )
    )
    return bool(report["unknown"] or report["native_method_gaps"])


if __name__ == "__main__":
    raise SystemExit(main())
