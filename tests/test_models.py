import pytest

from jrvoiceapp.models import (
    SAMPLE_RECENT_CALLS,
    AccountConfig,
    ConnectionKind,
    EmergencyConfig,
    SignalingTemplates,
    UserEmergencySettings,
    WebRtcEngine,
)
from jrvoiceapp.telephony.controller import TelephonyController
from jrvoiceapp.telephony.sipapp import SipAppProvider
from jrvoiceapp.telephony.sipapp_core.sip_engine import (
    DEFAULT_INVITE_TEMPLATE,
    SIPEngine,
    SIPMessage,
)
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


def test_controller_selects_the_maintained_sipapp_provider() -> None:
    account = AccountConfig("id", "Desk", "1001", "pbx.example:5061", ConnectionKind.SIP)
    provider = TelephonyController().provider_for(account, "secret")
    assert isinstance(provider, SipAppProvider)
    assert provider._profile()["domain"] == "pbx.example"
    assert provider._profile()["port"] == 5061


def test_sipapp_provider_never_puts_password_in_events() -> None:
    account = AccountConfig("id", "Desk", "1001", "pbx.example", ConnectionKind.SIP)
    provider = SipAppProvider(account, "do-not-expose")
    events = []
    provider.add_event_callback(lambda event, details: events.append((event, details)))
    provider._on_call_state("DIALING", {"password": "do-not-expose", "target": "1002"})
    assert events == [("call-state", {"state": "DIALING", "target": "1002"})]


def test_sipapp_template_renders_custom_header_variables() -> None:
    template = DEFAULT_INVITE_TEMPLATE.replace(
        "Max-Forwards: 70", "Max-Forwards: 70\n{custom_headers}X-Correlation: {trace_id}"
    )
    engine = SIPEngine(invite_template=template, header_variables={"trace_id": "abc-123"})
    packet, _ = engine.build_invite(
        "sip:1002@example.test", {"username": "1001", "domain": "example.test"}
    )
    assert "X-trace-id: abc-123" in packet
    assert "X-Correlation: abc-123" in packet


def test_signal_header_variable_names_and_values_are_safe() -> None:
    with pytest.raises(ValueError, match="variable names"):
        SignalingTemplates(header_variables={"not valid": "value"}).validate()
    with pytest.raises(ValueError, match="line breaks"):
        SignalingTemplates(header_variables={"trace_id": "value\r\nInjected: bad"}).validate()


def test_sipapp_200_ok_template_renders_header_variables() -> None:
    engine = SIPEngine(
        response_template="SIP/2.0 {status_code} {reason}\n{via_headers}From: {from_header}\n"
        "To: {to_header}\nCall-ID: {call_id}\nCSeq: {cseq_header}\n"
        "X-Correlation: {trace_id}\n{custom_headers}{content_headers}\n\n{sdp_body}",
        header_variables={"trace_id": "abc-123"},
    )
    request = SIPMessage(
        "INVITE sip:1001@example.test SIP/2.0\r\nVia: SIP/2.0/TLS peer;branch=one\r\n"
        "From: <sip:1002@example.test>;tag=peer\r\nTo: <sip:1001@example.test>\r\n"
        "Call-ID: test-call\r\nCSeq: 1 INVITE\r\nContent-Length: 0\r\n\r\n"
    )
    response = engine._build_response(request, 200, "OK", "v=0\r\n")
    assert "X-Correlation: abc-123" in response
    assert "X-trace-id: abc-123" in response


def test_emergency_location_and_user_dial_string_limits() -> None:
    config = EmergencyConfig(True, ["HQ", "Branch"], "HQ")
    config.validate()
    assert UserEmergencySettings("911, 112, 999").numbers() == {"911", "112", "999"}
    with pytest.raises(ValueError, match="five"):
        EmergencyConfig(locations=[str(index) for index in range(6)]).validate()


def test_sipapp_builds_dtmf_hold_and_refer_requests() -> None:
    engine = SIPEngine()
    sent = []
    engine.send_sip_message = lambda raw, *_args, **_kwargs: sent.append(raw) or True
    engine.call_state = "CONNECTED"
    engine.outbound_dialog = {
        "contact": "<sip:peer@example.test>",
        "from": "<sip:1001@example.test>;tag=local",
        "to": "<sip:1002@example.test>;tag=remote",
        "call_id": "test-call",
        "cseq": 1,
        "target_host": "example.test",
        "target_port": 5061,
        "transport": "TLS",
    }
    assert engine.send_dtmf("5")
    assert "INFO sip:peer@example.test SIP/2.0" in sent[-1]
    assert "Signal=5" in sent[-1]
    assert engine.set_hold(True)
    assert "UPDATE sip:peer@example.test SIP/2.0" in sent[-1]
    assert "a=sendonly" in sent[-1]
    assert engine.transfer_call("1003", "example.test")
    assert "REFER sip:peer@example.test SIP/2.0" in sent[-1]
    assert "Refer-To: <sip:1003@example.test>" in sent[-1]


def test_sipapp_diagnostics_redacts_credentials() -> None:
    account = AccountConfig("id", "Desk", "1001", "pbx.example", ConnectionKind.SIP)
    provider = SipAppProvider(account, "do-not-expose")
    provider.engine = SIPEngine()
    provider.engine.log_sys_event("Registration ready")
    report = provider.diagnostics()
    assert report["transport"] == "UDP"
    assert "Registration ready" in report["events"][0]
    assert "do-not-expose" not in str(report)
