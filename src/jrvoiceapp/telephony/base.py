"""Shared contract implemented by the SIP and WebRTC engines."""

from abc import ABC, abstractmethod
from enum import StrEnum


class ProviderState(StrEnum):
    IDLE = "idle"
    READY = "ready"
    REGISTERED = "registered"
    ERROR = "error"


class TelephonyProvider(ABC):
    def __init__(self) -> None:
        self.state = ProviderState.IDLE

    @abstractmethod
    def start(self) -> None:
        """Start the provider or raise a clear deployment error."""

    @abstractmethod
    def dial(self, destination: str) -> None:
        """Place a call once the provider is registered."""

    @abstractmethod
    def stop(self) -> None:
        """End the provider session and release process resources."""
