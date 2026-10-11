"""Select exactly one engine per configured account."""

from jrvoiceapp.models import AccountConfig, ConnectionKind
from jrvoiceapp.telephony.baresip import BaresipProvider
from jrvoiceapp.telephony.base import TelephonyProvider
from jrvoiceapp.telephony.webrtc import WebRtcProvider


class TelephonyController:
    def provider_for(self, account: AccountConfig, password: str) -> TelephonyProvider:
        account.validate()
        if account.connection_kind is ConnectionKind.WEBRTC:
            return WebRtcProvider(account, password)
        return BaresipProvider(account, password)
