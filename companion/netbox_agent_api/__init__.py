"""Apache-2.0 companion API for NetBox Community 4.7+, tested on 4.7.2."""

from netbox.plugins import PluginConfig


class AgentAPIConfig(PluginConfig):
    name = "netbox_agent_api"
    verbose_name = "Agent API Support"
    description = "Native Community workflow APIs for inventory agents"
    version = "0.4.3"
    author = "Reliable Collaboration contributors"
    base_url = "agent-support"
    min_version = "4.7.0"
    default_settings = {}


config = AgentAPIConfig
