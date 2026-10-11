"""Runtime capability discovery for optional SIPApp media features."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
import platform
from typing import Dict


@dataclass(frozen=True)
class MediaCapability:
    available: bool
    detail: str


def discover_media_capabilities() -> Dict[str, MediaCapability]:
    """Return honest, non-fatal availability information for optional features."""
    opus = find_spec("opuslib") is not None
    webrtc = find_spec("webrtc_audio_processing") is not None
    srtp_dependency = find_spec("pylibsrtp") is not None
    return {
        "G.711 PCMU": MediaCapability(True, "Built in"),
        "G.711 PCMA": MediaCapability(True, "Built in"),
        "G.722": MediaCapability(False, "G.722 RTP codec backend is not installed"),
        "Opus": MediaCapability(
            opus, "opuslib detected" if opus else "Install an Opus RTP codec backend"
        ),
        "SRTP": MediaCapability(
            srtp_dependency,
            "SDES-SRTP AES_CM_128_HMAC_SHA1_80 available"
            if srtp_dependency
            else "Install optional pylibsrtp to enable SDES-SRTP",
        ),
        "AEC": MediaCapability(
            webrtc,
            "WebRTC audio processing detected"
            if webrtc
            else "WebRTC audio processing is not installed",
        ),
        "Noise suppression": MediaCapability(
            webrtc,
            "WebRTC audio processing detected"
            if webrtc
            else "WebRTC audio processing is not installed",
        ),
        "Silence detection": MediaCapability(
            webrtc,
            "WebRTC audio processing detected"
            if webrtc
            else "WebRTC audio processing is not installed",
        ),
        "WASAPI": MediaCapability(
            platform.system() == "Windows",
            "Windows audio host" if platform.system() == "Windows" else "WASAPI is Windows-only",
        ),
    }


def unavailable_summary() -> str:
    missing = [
        f"{name}: {cap.detail}"
        for name, cap in discover_media_capabilities().items()
        if not cap.available
    ]
    return "\n".join(missing)
