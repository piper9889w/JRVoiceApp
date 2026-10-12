"""WebRTC provider configuration for an embedded browser bridge."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from jrvoiceapp.models import AccountConfig, WebRtcEngine
from jrvoiceapp.telephony.base import ProviderState, TelephonyProvider

if TYPE_CHECKING:
    from jrvoiceapp.telephony.webrtc_bridge import EmbeddedWebRtcBridge


@dataclass(frozen=True)
class WebRtcBridgeConfig:
    engine: WebRtcEngine
    username: str
    websocket_url: str
    invite_template: str
    ok_template: str
    header_variables: dict[str, str]


class WebRtcProvider(TelephonyProvider):
    def __init__(self, account: AccountConfig, password: str) -> None:
        super().__init__()
        self.account = account
        self.password = password
        self.bridge_config = WebRtcBridgeConfig(
            account.web_rtc_engine,
            account.username,
            account.server,
            account.signaling.webrtc_invite,
            account.signaling.webrtc_ok,
            dict(account.signaling.header_variables),
        )
        self.bridge: EmbeddedWebRtcBridge | None = None

    def start(self) -> None:
        if self.account.web_rtc_engine is WebRtcEngine.AIORTC:
            self.state = ProviderState.ERROR
            raise RuntimeError(
                "aiortc is experimental and cannot register SIP-over-WSS accounts yet."
            )
        if not self.account.server.startswith("wss://"):
            self.state = ProviderState.ERROR
            raise RuntimeError("WebRTC requires a secure wss:// server URL.")
        self.state = ProviderState.READY
        from jrvoiceapp.telephony.webrtc_bridge import EmbeddedWebRtcBridge

        self.bridge = EmbeddedWebRtcBridge()
        self.bridge.start(self.bridge_config, self.password, self._on_bridge_event)
        self._emit("webrtc-runtime", state="starting", engine=self.account.web_rtc_engine.value)

    def dial(self, destination: str) -> None:
        if self.state is not ProviderState.REGISTERED:
            raise RuntimeError(
                "WebRTC is not registered. Connect the embedded browser bridge first."
            )
        if not destination.strip():
            raise ValueError("Enter a destination before calling.")

    def stop(self) -> None:
        if self.bridge:
            self.bridge.stop()
            self.bridge = None
        self.state = ProviderState.IDLE

    def _on_bridge_event(self, event: str, details: dict[str, str]) -> None:
        if event == "registered":
            self.state = ProviderState.REGISTERED
        elif event == "runtime-error":
            self.state = ProviderState.ERROR
        self._emit("webrtc-runtime", event=event, **details)
