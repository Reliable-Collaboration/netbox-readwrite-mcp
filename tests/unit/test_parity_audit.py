"""Fail closed when the pinned stock route denominator gains an unmapped view."""

import json

from scripts.parity_audit import ROOT, audit


def test_checked_route_mapping_is_complete_and_references_real_evidence_files():
    surface = json.loads((ROOT / "docs/netbox-4.7-surface.json").read_text())
    report = audit(surface)
    assert report == json.loads((ROOT / "docs/netbox-4.7-parity.json").read_text())
    assert not report["native_method_gaps"]
    assert report["netbox_version"] == "4.7.2"
    assert report["website_route_count"] == 1543 and not report["unknown"]
    for family in report["families"].values():
        for filename in family["integration_files"]:
            assert (ROOT / "tests/integration" / filename).is_file(), filename
    surface["routes"].append({"route": "new-feature/", "view": "newapp.UnknownView", "view_bases": ["View"]})
    assert audit(surface)["unknown"] == [
        {"route": "new-feature/", "view": "newapp.UnknownView", "family": None}
    ]
