"""Runtime acceptance policy, kept separate from tested release qualification."""

import re

NETBOX_VERSION = "4.7.2"
QUALIFIED_VERSIONS = (NETBOX_VERSION,)
SUPPORTED_VERSIONS = ">=4.7.0 (stable releases)"


def normalization_profile(version):
    if isinstance(version, str) and re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version
    ):
        if tuple(map(int, version.split("."))) >= (4, 7, 0):
            return "netbox-4.7-device-v1"
    raise RuntimeError("Unsupported NetBox version; requires a stable release >=4.7.0. Tested on 4.7.2.")
