"""Select exactly one engine per configured account."""

from jrvoiceapp.models import AccountConfig, ConnectionKind
from jrvoiceapp.telephony.base import TelephonyProvider
from jrvoiceapp.telephony.sipapp import SipAppProvider
from jrvoiceapp.telephony.webrtc import WebRtcProvider


class TelephonyController:
    def route_outbound(self, accounts: list[AccountConfig], destination: str) -> AccountConfig:
        """Choose predictably: explicit SIP domain match, then lexical account id."""
        if not accounts:
            raise ValueError("Configure an account before calling.")
        target_domain = destination.rsplit("@", 1)[-1].lower() if "@" in destination else ""
        matches = [
            account for account in accounts if account.server.lower().split(":")[0] == target_domain
        ]
        return min(matches or accounts, key=lambda account: account.identifier)

    def provider_for(self, account: AccountConfig, password: str) -> TelephonyProvider:
        account.validate()
        if account.connection_kind is ConnectionKind.WEBRTC:
            return WebRtcProvider(account, password)
        return SipAppProvider(account, password)
