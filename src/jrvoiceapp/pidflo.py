"""PIDF-LO construction; carrier/PBX transmission remains deployment-validated work."""

from __future__ import annotations

from html import escape
from uuid import uuid4


def build_pidf_lo(location: str, entity: str) -> tuple[str, str]:
    """Build a minimal civic-address PIDF-LO body and matching Geolocation header."""
    if not location.strip() or not entity.strip():
        raise ValueError("A verified location and account identity are required.")
    content_id = f"{uuid4().hex}@jrvoiceapp"
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        '<presence xmlns="urn:ietf:params:xml:ns:pidf" entity="'
        + escape(entity, quote=True)
        + '"><tuple id="location"><status><basic>open</basic></status>'
        '<geopriv xmlns="urn:ietf:params:xml:ns:pidf:geopriv10"><location-info>'
        '<civicAddress xmlns="urn:ietf:params:xml:ns:pidf:geopriv10:civicAddr">'
        f"<A1>{escape(location)}</A1>"
        "</civicAddress></location-info><usage-rules/></geopriv>"
        "</tuple></presence>"
    )
    return body, f"<cid:{content_id}>;routing-allowed=yes"
