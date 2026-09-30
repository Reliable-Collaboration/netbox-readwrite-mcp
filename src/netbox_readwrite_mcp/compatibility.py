"""One explicit, tested NetBox target. Upgrade code and lab together."""

NETBOX_VERSION = "4.7.2"
QUALIFIED_VERSIONS = (NETBOX_VERSION,)
SUPPORTED_VERSIONS = NETBOX_VERSION


def normalization_profile(version):
    if version == NETBOX_VERSION:
        return "netbox-4.7-device-v1"
    raise RuntimeError(
        f"Unsupported NetBox version; requires exactly {NETBOX_VERSION}. Run the live contract suite before upgrading."
    )
