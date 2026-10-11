"""Small UI-facing models; protocol implementation comes in later milestones."""

from dataclasses import dataclass
from enum import StrEnum


class ConnectionKind(StrEnum):
    SIP = "SIP TLS"
    WEBRTC = "WebRTC WSS"


class WebRtcEngine(StrEnum):
    SIPJS = "SIP.js (recommended)"
    JSSIP = "JsSIP"
    AIORTC = "aiortc (experimental)"


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

    def validate(self) -> None:
        if not self.identifier.strip() or not self.label.strip():
            raise ValueError("An account name is required.")
        if not self.username.strip() or not self.server.strip():
            raise ValueError("Extension and server are required.")
        if self.connection_kind is ConnectionKind.WEBRTC and not self.server.startswith(
            ("wss://", "ws://")
        ):
            raise ValueError("A WebRTC account needs a ws:// or wss:// server URL.")


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
