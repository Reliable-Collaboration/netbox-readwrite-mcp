"""Container configuration overlay preserving the deployment's native settings."""

from importlib import import_module
import os

base_name = os.environ.get("NETBOX_AGENT_BASE_CONFIGURATION", "netbox.configuration")
if base_name == __name__:
    raise ValueError("NETBOX_AGENT_BASE_CONFIGURATION must name the underlying configuration")
_base = import_module(base_name)
# Preserve the directory used by NetBox to find LDAP configuration.
__file__ = _base.__file__
PLUGINS = list(getattr(_base, "PLUGINS", []))
if "netbox_agent_api" not in PLUGINS:
    PLUGINS.append("netbox_agent_api")


def __getattr__(name):
    return getattr(_base, name)


def __dir__():
    return sorted(set(dir(_base)) | {"PLUGINS"})
