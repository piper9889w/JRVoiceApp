"""Small UI-facing models; protocol implementation comes in later milestones."""

import re
from dataclasses import dataclass, field
from enum import StrEnum


class ConnectionKind(StrEnum):
    SIP = "SIP TLS"
    WEBRTC = "WebRTC WSS"


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
class AccountConfig:
    """Non-secret account settings; passwords are stored separately in the OS keychain."""

    identifier: str
    label: str
    username: str
    server: str
    connection_kind: ConnectionKind
    web_rtc_engine: WebRtcEngine = WebRtcEngine.SIPJS
    voicemail_number: str = "*97"
    signaling: SignalingTemplates = field(default_factory=SignalingTemplates)

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
