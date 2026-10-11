"""WebRTC provider configuration for an embedded browser bridge."""

from dataclasses import dataclass

from jrvoiceapp.models import AccountConfig, WebRtcEngine
from jrvoiceapp.telephony.base import ProviderState, TelephonyProvider


@dataclass(frozen=True)
class WebRtcBridgeConfig:
    engine: WebRtcEngine
    username: str
    websocket_url: str


class WebRtcProvider(TelephonyProvider):
    def __init__(self, account: AccountConfig, password: str) -> None:
        super().__init__()
        self.account = account
        self.password = password
        self.bridge_config = WebRtcBridgeConfig(
            account.web_rtc_engine, account.username, account.server
        )

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

    def dial(self, destination: str) -> None:
        if self.state is not ProviderState.REGISTERED:
            raise RuntimeError(
                "WebRTC is not registered. Connect the embedded browser bridge first."
            )
        if not destination.strip():
            raise ValueError("Enter a destination before calling.")

    def stop(self) -> None:
        self.state = ProviderState.IDLE
