"""Explicit stable-version policy; acceptance is distinct from qualification."""

import re

QUALIFIED_VERSIONS = ("4.6.10", "4.7.0", "4.7.1")
SUPPORTED_VERSIONS = "stable 4.7.x or legacy 4.6.10"


def normalization_profile(version):
    if version == "4.6.10":
        return "netbox-4.6.10-device-v1"
    if isinstance(version, str) and re.fullmatch(r"4\.7\.(0|[1-9][0-9]*)", version):
        return "netbox-4.7-device-v1"
    raise RuntimeError(
        "Unsupported NetBox version; requires "
        + SUPPORTED_VERSIONS
        + ". Prereleases are refused. Run the live contract suite before upgrading."
    )
