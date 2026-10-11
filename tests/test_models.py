import pytest

from jrvoiceapp.models import SAMPLE_RECENT_CALLS, AccountConfig, ConnectionKind, WebRtcEngine
from jrvoiceapp.telephony.controller import TelephonyController
from jrvoiceapp.telephony.webrtc import WebRtcProvider


def test_connection_labels_match_the_phone_ui() -> None:
    assert ConnectionKind.SIP == "SIP TLS"
    assert ConnectionKind.WEBRTC == "WebRTC WSS"


def test_shell_has_sample_recent_calls() -> None:
    assert len(SAMPLE_RECENT_CALLS) == 5


def test_webrtc_accounts_require_a_websocket_url() -> None:
    account = AccountConfig("id", "Office", "1001", "pbx.example", ConnectionKind.WEBRTC)
    with pytest.raises(ValueError, match="wss"):
        account.validate()


def test_sip_account_allows_a_hostname() -> None:
    account = AccountConfig("id", "Office", "1001", "pbx.example", ConnectionKind.SIP)
    account.validate()


def test_controller_selects_webrtc_provider() -> None:
    account = AccountConfig(
        "id", "Web phone", "1001", "wss://pbx.example/sip", ConnectionKind.WEBRTC
    )
    assert isinstance(TelephonyController().provider_for(account, "secret"), WebRtcProvider)


def test_aiortc_is_clearly_rejected_for_sip_over_wss() -> None:
    account = AccountConfig(
        "id", "Lab", "1001", "wss://pbx.example/sip", ConnectionKind.WEBRTC, WebRtcEngine.AIORTC
    )
    with pytest.raises(RuntimeError, match="experimental"):
        WebRtcProvider(account, "secret").start()
