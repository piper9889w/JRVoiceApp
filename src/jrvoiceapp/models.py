"""Small UI-facing models; protocol implementation comes in later milestones."""

from dataclasses import dataclass
from enum import StrEnum


class ConnectionKind(StrEnum):
    SIP = "SIP TLS"
    WEBRTC = "WebRTC WSS"


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
