"""JRVoiceApp adapter for the maintained SIPApp SIP implementation.

Passwords cross this boundary only as an in-memory value read by AccountStore
at connection time. They are never attached to provider events or diagnostics.
"""

from __future__ import annotations

from urllib.parse import urlparse

from jrvoiceapp.models import AccountConfig
from jrvoiceapp.pidflo import build_pidf_lo
from jrvoiceapp.telephony.base import ProviderState, TelephonyProvider
from jrvoiceapp.telephony.sipapp_core.audio_engine import AudioEngine
from jrvoiceapp.telephony.sipapp_core.registration_manager import (
    RegistrationManager,
    RegistrationStatus,
)
from jrvoiceapp.telephony.sipapp_core.sip_engine import SIPEngine, SIPLogEntry, SIPMessage


class SipAppProvider(TelephonyProvider):
    """Connect an account through the maintained SIPApp transport and media core."""

    def __init__(self, account: AccountConfig, password: str) -> None:
        super().__init__()
        self.account = account
        self._password = password
        self.engine: SIPEngine | None = None
        self.registration: RegistrationManager | None = None
        self.audio = AudioEngine()
        self.emergency_location = ""
        self.pidf_lo_body = ""
        self.geolocation_header = ""

    def _profile(self) -> dict[str, object]:
        value = self.account.server.strip()
        parsed = urlparse(value if "://" in value else f"//{value}")
        host = parsed.hostname or value.split(":", 1)[0]
        transport = self.account.sip_transport.value
        port = parsed.port or (5061 if transport == "TLS" else 5060)
        return {
            "id": self.account.identifier,
            "name": self.account.label,
            "username": self.account.username,
            "auth_user": self.account.username,
            "password": self._password,
            "domain": host,
            "port": port,
            "transport": transport,
            "tls_verify_cert": transport == "TLS",
            "expires": 3600,
        }

    def start(self) -> None:
        if not self._password:
            self.state = ProviderState.ERROR
            raise RuntimeError("No SIP password is available in the operating-system keychain.")
        profile = self._profile()
        self.engine = SIPEngine(
            local_port=0,
            transport=str(profile["transport"]),
            use_tls=profile["transport"] == "TLS",
            tls_verify=bool(profile["tls_verify_cert"]),
            invite_template=self.account.signaling.sip_invite,
            response_template=self.account.signaling.sip_ok,
            header_variables=self.account.signaling.header_variables,
        )
        self.engine.add_log_callback(self._on_log)
        self.engine.add_call_callback(self._on_call_state)
        if not self.engine.start():
            self.state = ProviderState.ERROR
            raise RuntimeError(
                self.engine.last_send_error or "Could not start the SIPApp transport."
            )
        self.registration = RegistrationManager(self.engine)
        self.registration.add_status_callback(self._on_registration_state)
        self.state = ProviderState.READY
        self._emit("provider-ready", account=self.account.identifier)
        self.registration.register_account(profile)

    def dial(self, destination: str) -> None:
        if self.state is not ProviderState.REGISTERED or not self.engine:
            raise RuntimeError("SIPApp is not registered.")
        if not destination.strip():
            raise ValueError("Enter a destination before calling.")
        profile = self._profile()
        # Bind before creating the SDP offer.  Advertising a port before it is
        # listening produces a connected SIP dialog with no RTP on many PBXs.
        self._prepare_audio()
        target = self.engine.normalize_dial_target(destination, str(profile["domain"]))
        self.engine.start_outbound_invite(
            target,
            profile,
            self.audio.local_rtp_port,
            str(profile["domain"]),
            int(profile["port"]),
            transport=str(profile["transport"]),
            source_ip=self.engine.local_ip,
            media_ip=self.audio.advertised_ip,
        )

    def answer(self) -> None:
        if not self.engine:
            raise RuntimeError("SIPApp is not running.")
        dialog = self.engine.active_dialog
        offer = dialog.get("req_msg").body if dialog.get("req_msg") else ""
        self._prepare_audio(offer, str(dialog.get("remote_ip", "")))
        self.engine.answer_incoming_call(
            rtp_port=self.audio.local_rtp_port,
            media_ip=self.audio.advertised_ip,
            codec=self.audio.negotiated_codec,
            payload_type=self.audio.payload_types[self.audio.negotiated_codec],
        )

    def ignore(self, voicemail: bool = False) -> None:
        if self.engine:
            self.engine.reject_incoming_call(486 if not voicemail else 480, "Busy Here")

    def hangup(self) -> None:
        if self.engine:
            self.engine.hangup_call()
            self.audio.stop_rtp_stream()

    def dial_voicemail(self) -> None:
        self.dial(self.account.voicemail_number)

    def send_dtmf(self, digit: str) -> None:
        if not self.engine or not self.engine.send_dtmf(digit):
            raise RuntimeError("No connected SIP dialog is available for DTMF.")

    def set_hold(self, held: bool) -> None:
        if not self.engine or not self.engine.set_hold(held, self.audio.local_rtp_port or 10000):
            raise RuntimeError("No connected SIP dialog is available for hold/resume.")

    def transfer(self, destination: str) -> None:
        if not self.engine or not self.engine.transfer_call(
            destination, str(self._profile()["domain"])
        ):
            raise RuntimeError("No connected SIP dialog is available for transfer.")

    def set_muted(self, muted: bool) -> None:
        self.audio.set_muted(muted)
        self._emit("media", muted=str(muted))

    def set_speaker_volume(self, percent: int) -> None:
        self.audio.set_speaker_volume(percent)
        self._emit("media", speaker_volume=str(percent))

    def available_audio_devices(self) -> dict[str, object]:
        return self.audio.get_audio_devices()

    def diagnostics(self) -> dict[str, object]:
        """Return a password-free snapshot suitable for the desktop diagnostics view."""
        stats = self.audio.get_rtp_stats()
        engine = self.engine
        events = []
        if engine:
            events = [
                f"{entry.timestamp} {entry.category}/{entry.direction} {entry.remote_addr} — {entry.summary}"
                for entry in engine.log_entries[-100:]
            ]
        peer_host, peer_port, peer_transport = engine.last_sip_peer if engine else ("", 0, "")
        return {
            "provider_state": self.state.value,
            "transport": engine.transport if engine else "not started",
            "tls_verification": "enabled" if engine and engine.tls_verify else "not used",
            "local_signaling": f"{engine.local_ip}:{engine.local_port}" if engine else "—",
            "signaling_destination": (
                f"{peer_host}:{peer_port} ({peer_transport})" if peer_host else "—"
            ),
            "last_network_error": engine.last_send_error if engine else "",
            "codec": self.audio.negotiated_codec,
            "media_security": stats["media_security"],
            "rtp_local": f"{stats['advertised_ip']}:{stats['advertised_port']}",
            "rtp_remote": f"{stats['remote_ip']}:{stats['remote_port']}",
            "rtp_packets": f"TX {stats['packets_sent']} / RX {stats['packets_received']}",
            "rtp_packet_rate": (
                f"TX {stats['packets_sent_per_second']}/s / "
                f"RX {stats['packets_received_per_second']}/s"
            ),
            "jitter": f"lost {stats['jitter_lost']} / duplicates {stats['jitter_duplicates']}",
            "nat": stats["nat_status"],
            "audio_error": stats["audio_error"],
            "events": events,
        }

    def set_emergency_location(self, location: str) -> None:
        """Keep a verified session location without writing it to diagnostics."""
        self.emergency_location = location
        if self.account.emergency.enabled:
            self.pidf_lo_body, self.geolocation_header = build_pidf_lo(
                location, f"sip:{self.account.username}@{self._profile()['domain']}"
            )
        self._emit("emergency-location-verified")

    def stop(self) -> None:
        self.audio.stop_rtp_stream()
        if self.registration:
            self.registration.stop_all()
        if self.engine:
            self.engine.stop()
        self._password = ""
        self.state = ProviderState.IDLE
        self._emit("provider-stopped", account=self.account.identifier)

    def _on_registration_state(self, _account_id: str, status: str, detail: str) -> None:
        if status == RegistrationStatus.REGISTERED:
            self.state = ProviderState.REGISTERED
        elif status == RegistrationStatus.FAILED:
            self.state = ProviderState.ERROR
        self._emit("registration", status=status, detail=detail)

    def _on_call_state(self, state: str, details: dict[str, object]) -> None:
        if state == "CONNECTED":
            self._start_audio(str(details.get("sdp", "")), str(details.get("remote_ip", "")))
        elif state == "TERMINATED":
            self.audio.stop_rtp_stream()
        safe = {key: str(value) for key, value in details.items() if key not in {"password", "sdp"}}
        if self.engine and self.engine.outbound_invite_context:
            invite = SIPMessage(self.engine.outbound_invite_context.get("invite_packet", ""))
            safe.setdefault("from", invite.get_header("From"))
            safe.setdefault("request_uri", invite.uri)
        self._emit("call-state", state=state, **safe)

    def _on_log(self, entry: SIPLogEntry) -> None:
        # SIPApp redacts SDES key material before constructing the log entry.
        self._emit(
            "diagnostic", category=entry.category, level=entry.direction, summary=entry.summary
        )

    def _start_audio(self, sdp: str, fallback_ip: str) -> None:
        """Use SIPApp's RTP/G.711 engine after a successful SDP negotiation."""
        if not sdp:
            return
        try:
            self.audio.negotiate_codec(sdp)
            remote_ip, remote_port = self.audio.parse_sdp_audio_target(sdp, fallback_ip)
            if not remote_ip or not remote_port:
                raise ValueError("Peer SDP has no usable IPv4 RTP address and port.")
            if self.audio.is_streaming:
                self.audio.set_remote_rtp_target(remote_ip, remote_port)
            else:
                self.audio.start_rtp_stream(
                    10000,
                    remote_ip,
                    remote_port,
                    advertised_ip=self.engine.local_ip if self.engine else "",
                )
            self._emit(
                "media",
                codec=self.audio.negotiated_codec,
                remote=f"{remote_ip}:{remote_port}",
                local=str(self.audio.local_rtp_port),
            )
        except (OSError, ValueError) as error:
            self._emit("media-error", detail=str(error))

    def _prepare_audio(self, offer_sdp: str = "", fallback_ip: str = "") -> None:
        """Bind the local RTP endpoint before it is placed in SDP."""
        if self.audio.is_streaming:
            return
        remote_ip = ""
        remote_port = 0
        if offer_sdp:
            self.audio.negotiate_codec(offer_sdp)
            remote_ip, remote_port = self.audio.parse_sdp_audio_target(offer_sdp, fallback_ip)
            if not remote_ip or not remote_port:
                raise ValueError("Peer SDP has no usable IPv4 RTP address and port.")
        advertised_ip = self.engine.local_ip if self.engine else ""
        self.audio.start_rtp_stream(10000, remote_ip, remote_port, advertised_ip=advertised_ip)
