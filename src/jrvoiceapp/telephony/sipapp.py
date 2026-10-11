"""JRVoiceApp adapter for the maintained SIPApp SIP implementation.

Passwords cross this boundary only as an in-memory value read by AccountStore
at connection time. They are never attached to provider events or diagnostics.
"""

from __future__ import annotations

from urllib.parse import urlparse

from jrvoiceapp.models import AccountConfig
from jrvoiceapp.telephony.base import ProviderState, TelephonyProvider
from jrvoiceapp.telephony.sipapp_core.audio_engine import AudioEngine
from jrvoiceapp.telephony.sipapp_core.registration_manager import (
    RegistrationManager,
    RegistrationStatus,
)
from jrvoiceapp.telephony.sipapp_core.sip_engine import SIPEngine, SIPLogEntry


class SipAppProvider(TelephonyProvider):
    """Connect an account through the maintained SIPApp transport and media core."""

    def __init__(self, account: AccountConfig, password: str) -> None:
        super().__init__()
        self.account = account
        self._password = password
        self.engine: SIPEngine | None = None
        self.registration: RegistrationManager | None = None
        self.audio = AudioEngine()

    def _profile(self) -> dict[str, object]:
        value = self.account.server.strip()
        parsed = urlparse(value if "://" in value else f"//{value}")
        host = parsed.hostname or value.split(":", 1)[0]
        port = parsed.port or 5061
        return {
            "id": self.account.identifier,
            "name": self.account.label,
            "username": self.account.username,
            "auth_user": self.account.username,
            "password": self._password,
            "domain": host,
            "port": port,
            "transport": "TLS",
            "tls_verify_cert": True,
            "expires": 3600,
        }

    def start(self) -> None:
        if not self._password:
            self.state = ProviderState.ERROR
            raise RuntimeError("No SIP password is available in the operating-system keychain.")
        profile = self._profile()
        self.engine = SIPEngine(local_port=0, transport="TLS", use_tls=True, tls_verify=True)
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
        target = self.engine.normalize_dial_target(destination, str(profile["domain"]))
        self.engine.start_outbound_invite(
            target,
            profile,
            10000,
            str(profile["domain"]),
            int(profile["port"]),
            transport="TLS",
            source_ip=self.engine.local_ip,
        )

    def answer(self) -> None:
        if not self.engine:
            raise RuntimeError("SIPApp is not running.")
        self.engine.answer_incoming_call()
        dialog = self.engine.active_dialog
        self._start_audio(
            dialog.get("req_msg").body if dialog.get("req_msg") else "", dialog.get("remote_ip", "")
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
        safe = {key: str(value) for key, value in details.items() if key != "password"}
        self._emit("call-state", state=state, **safe)

    def _on_log(self, entry: SIPLogEntry) -> None:
        # SIPApp redacts SDES key material before constructing the log entry.
        self._emit(
            "diagnostic", category=entry.category, level=entry.direction, summary=entry.summary
        )

    def _start_audio(self, sdp: str, fallback_ip: str) -> None:
        """Use SIPApp's RTP/G.711 engine after a successful SDP negotiation."""
        if self.audio.is_streaming or not sdp:
            return
        try:
            self.audio.negotiate_codec(sdp)
            remote_ip, remote_port = self.audio.parse_sdp_audio_target(sdp, fallback_ip)
            self.audio.start_rtp_stream(10000, remote_ip, remote_port)
            self._emit(
                "media",
                codec=self.audio.negotiated_codec,
                remote=f"{remote_ip}:{remote_port}",
                local=str(self.audio.local_rtp_port),
            )
        except (OSError, ValueError) as error:
            self._emit("media-error", detail=str(error))
