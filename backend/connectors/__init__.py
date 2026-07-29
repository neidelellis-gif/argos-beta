from . import ubs_connector
from . import santander_connector
from . import tipranks_connector
from . import bradesco_connector
from .registry import ConnectorRegistry

registry = ConnectorRegistry()
registry.register(ubs_connector)
registry.register(santander_connector)
registry.register(bradesco_connector)
registry.register(tipranks_connector, active=False)

__all__ = [
    "registry", "ubs_connector", "santander_connector", "bradesco_connector",
    "tipranks_connector",
]
