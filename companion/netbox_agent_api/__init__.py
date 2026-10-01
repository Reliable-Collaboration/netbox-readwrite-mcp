"""Apache-2.0 companion API for NetBox Community 4.7.2."""

from netbox.plugins import PluginConfig


class AgentAPIConfig(PluginConfig):
    name = "netbox_agent_api"
    verbose_name = "Agent API Support"
    description = "Native metadata, guarded configuration and personal dashboards"
    version = "0.3.0"
    author = "Reliable Collaboration contributors"
    base_url = "agent-support"
    min_version = "4.7.2"
    max_version = "4.7.2"
    default_settings = {}


config = AgentAPIConfig
