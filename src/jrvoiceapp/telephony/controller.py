"""Select exactly one engine per configured account."""

from jrvoiceapp.models import AccountConfig, ConnectionKind
from jrvoiceapp.telephony.base import TelephonyProvider
from jrvoiceapp.telephony.sipapp import SipAppProvider
from jrvoiceapp.telephony.webrtc import WebRtcProvider


class TelephonyController:
    def provider_for(self, account: AccountConfig, password: str) -> TelephonyProvider:
        account.validate()
        if account.connection_kind is ConnectionKind.WEBRTC:
            return WebRtcProvider(account, password)
        return SipAppProvider(account, password)
