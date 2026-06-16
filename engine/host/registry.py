from typing import Type
from engine.host.adapter import HostAdapter, HostName

_REGISTRY: dict[HostName, Type[HostAdapter]] = {}


def register(name: HostName, cls: Type[HostAdapter]) -> None:
    _REGISTRY[name] = cls


def get_adapter_class(name: HostName) -> Type[HostAdapter]:
    if name not in _REGISTRY:
        raise KeyError(f"Adapter not registered: {name.value}")
    return _REGISTRY[name]


def clear_registry() -> None:
    _REGISTRY.clear()
