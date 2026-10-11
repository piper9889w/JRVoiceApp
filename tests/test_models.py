from jrvoiceapp.models import ConnectionKind, SAMPLE_RECENT_CALLS


def test_connection_labels_match_the_phone_ui() -> None:
    assert ConnectionKind.SIP == "SIP TLS"
    assert ConnectionKind.WEBRTC == "WebRTC WSS"


def test_shell_has_sample_recent_calls() -> None:
    assert len(SAMPLE_RECENT_CALLS) == 5
