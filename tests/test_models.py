import pytest

from jrvoiceapp.models import SAMPLE_RECENT_CALLS, AccountConfig, ConnectionKind


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
