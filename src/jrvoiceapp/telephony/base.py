"""Shared contract implemented by the SIP and WebRTC engines."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum


class ProviderState(StrEnum):
    IDLE = "idle"
    READY = "ready"
    REGISTERED = "registered"
    ERROR = "error"


class TelephonyProvider(ABC):
    def __init__(self) -> None:
        self.state = ProviderState.IDLE
        self._event_callbacks: list[Callable[[str, dict[str, str]], None]] = []

    def add_event_callback(self, callback: Callable[[str, dict[str, str]], None]) -> None:
        """Subscribe UI/controller code to non-secret provider events."""
        self._event_callbacks.append(callback)

    def _emit(self, event: str, **details: str) -> None:
        for callback in tuple(self._event_callbacks):
            callback(event, details)

    @abstractmethod
    def start(self) -> None:
        """Start the provider or raise a clear deployment error."""

    @abstractmethod
    def dial(self, destination: str) -> None:
        """Place a call once the provider is registered."""

    @abstractmethod
    def stop(self) -> None:
        """End the provider session and release process resources."""
