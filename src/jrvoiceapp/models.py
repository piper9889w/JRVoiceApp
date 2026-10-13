"""Small UI-facing models; protocol implementation comes in later milestones."""

import re
from dataclasses import dataclass, field
from enum import StrEnum


class ConnectionKind(StrEnum):
    SIP = "SIP"
    WEBRTC = "WebRTC WSS"


class SipTransport(StrEnum):
    UDP = "UDP"
    TCP = "TCP"
    TLS = "TLS"


class WebRtcEngine(StrEnum):
    SIPJS = "SIP.js (recommended)"
    JSSIP = "JsSIP"
    AIORTC = "aiortc (experimental)"


HEADER_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SignalingTemplates:
    """Non-secret, per-account SIP-message templates and header variables."""

    sip_invite: str = ""
    sip_ok: str = ""
    webrtc_invite: str = ""
    webrtc_ok: str = ""
    header_variables: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        for name, value in self.header_variables.items():
            if not HEADER_VARIABLE.fullmatch(name):
                raise ValueError(
                    "Custom-header variable names use letters, numbers, and underscores only."
                )
            if "\r" in value or "\n" in value:
                raise ValueError("Custom-header variable values cannot contain line breaks.")


@dataclass(frozen=True)
class EmergencyConfig:
    """Non-secret PIDF-LO preferences for an individual account."""

    enabled: bool = False
    locations: list[str] = field(default_factory=list)
    default_location: str = ""

    def validate(self) -> None:
        if len(self.locations) > 5:
            raise ValueError("Save at most five emergency locations per account.")
        if any(not location.strip() for location in self.locations):
            raise ValueError("Emergency locations cannot be blank.")
        if self.default_location and self.default_location not in self.locations:
            raise ValueError("The default emergency location must be one of the saved locations.")


@dataclass(frozen=True)
class UserEmergencySettings:
    """Application-wide dial strings; deliberately separate from SIP credentials."""

    dial_strings: str = "911"

    def numbers(self) -> set[str]:
        return {value.strip() for value in self.dial_strings.split(",") if value.strip()}

    def validate(self) -> None:
        if not self.numbers():
            raise ValueError("Enter at least one emergency dial string.")


@dataclass(frozen=True)
class AccountConfig:
    """Non-secret account settings; passwords are stored separately in the OS keychain."""

    identifier: str
    label: str
    username: str
    server: str
    connection_kind: ConnectionKind
    web_rtc_engine: WebRtcEngine = WebRtcEngine.SIPJS
    sip_transport: SipTransport = SipTransport.TLS
    voicemail_number: str = "*97"
    signaling: SignalingTemplates = field(default_factory=SignalingTemplates)
    emergency: EmergencyConfig = field(default_factory=EmergencyConfig)
    provisioning_server: str = ""

    def validate(self) -> None:
        if not self.identifier.strip() or not self.label.strip():
            raise ValueError("An account name is required.")
        if not self.username.strip() or not self.server.strip():
            raise ValueError("Extension and server are required.")
        if self.connection_kind is ConnectionKind.WEBRTC and not self.server.startswith(
            ("wss://", "ws://")
        ):
            raise ValueError("A WebRTC account needs a ws:// or wss:// server URL.")
        self.signaling.validate()
        self.emergency.validate()


@dataclass(frozen=True)
class RecentCall:
    initials: str
    caller: str
    direction: str
    time_label: str
    accent: str


SAMPLE_RECENT_CALLS = (
    RecentCall("MC", "Marcus Chen", "Incoming", "10:24 AM", "#3478f6"),
    RecentCall("SP", "Sarah Patel", "Missed", "9:17 AM", "#7856f5"),
    RecentCall("JD", "James Diaz", "Outgoing", "Yesterday", "#2d9f75"),
    RecentCall("EL", "Emma Lee", "Outgoing", "Yesterday", "#b7813e"),
    RecentCall("RK", "Ryan Kim", "Missed", "Mon 4:03 PM", "#7657f7"),
)
