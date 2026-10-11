"""SDES-SRTP key negotiation helpers and pylibsrtp packet protection."""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass

try:
    import pylibsrtp
except ImportError:
    pylibsrtp = None


SDES_SUITE = "AES_CM_128_HMAC_SHA1_80"
MASTER_KEY_LENGTH = 30  # 16-byte AES key + 14-byte salt


class SecureMediaError(RuntimeError):
    pass


def backend_available() -> bool:
    return pylibsrtp is not None


def generate_master_key() -> bytes:
    if not backend_available():
        raise SecureMediaError("pylibsrtp is not installed")
    return os.urandom(MASTER_KEY_LENGTH)


def crypto_attribute(key: bytes, tag: int = 1) -> str:
    if len(key) != MASTER_KEY_LENGTH:
        raise SecureMediaError("Invalid SDES-SRTP master key length")
    encoded = base64.b64encode(key).decode("ascii")
    return f"a=crypto:{tag} {SDES_SUITE} inline:{encoded}"


def parse_crypto_offer(sdp: str) -> tuple[int, bytes]:
    match = re.search(
        rf"(?im)^a=crypto:(\d+)\s+{SDES_SUITE}\s+inline:([A-Za-z0-9+/=]+)(?:[|\s]|$)",
        sdp or "",
    )
    if not match:
        raise SecureMediaError(f"Peer did not negotiate {SDES_SUITE}")
    try:
        key = base64.b64decode(match.group(2), validate=True)
    except ValueError as exc:
        raise SecureMediaError("Peer supplied invalid SDES-SRTP key material") from exc
    if len(key) != MASTER_KEY_LENGTH:
        raise SecureMediaError("Peer supplied an invalid SDES-SRTP master key length")
    return int(match.group(1)), key


def parse_crypto_attribute(sdp: str, expected_tag: int | None = None) -> bytes:
    tag, key = parse_crypto_offer(sdp)
    if expected_tag is not None and tag != expected_tag:
        raise SecureMediaError(f"Peer selected unexpected SDES-SRTP crypto tag {tag}")
    return key


@dataclass
class SRTPSessionPair:
    outbound_key: bytes
    inbound_key: bytes | None = None

    def __post_init__(self) -> None:
        if not backend_available():
            raise SecureMediaError("pylibsrtp is not installed")
        self.outbound = pylibsrtp.Session(
            pylibsrtp.Policy(
                key=self.outbound_key,
                ssrc_type=pylibsrtp.Policy.SSRC_ANY_OUTBOUND,
                srtp_profile=pylibsrtp.Policy.SRTP_PROFILE_AES128_CM_SHA1_80,
            )
        )
        self.inbound = None
        if self.inbound_key:
            self.set_inbound_key(self.inbound_key)

    def set_inbound_key(self, key: bytes) -> None:
        if len(key) != MASTER_KEY_LENGTH:
            raise SecureMediaError("Invalid inbound SDES-SRTP master key length")
        self.inbound_key = key
        self.inbound = pylibsrtp.Session(
            pylibsrtp.Policy(
                key=key,
                ssrc_type=pylibsrtp.Policy.SSRC_ANY_INBOUND,
                srtp_profile=pylibsrtp.Policy.SRTP_PROFILE_AES128_CM_SHA1_80,
            )
        )

    def protect(self, packet: bytes) -> bytes:
        return self.outbound.protect(packet)

    def unprotect(self, packet: bytes) -> bytes:
        if self.inbound is None:
            raise SecureMediaError("Peer SRTP key has not been negotiated")
        try:
            return self.inbound.unprotect(packet)
        except pylibsrtp.Error as exc:
            raise SecureMediaError("SRTP authentication or replay check failed") from exc
