"""Resolve SIP account destinations, including RFC 3263-style SRV lookup."""

from typing import Tuple


def resolve_sip_target(host: str, port: int, transport: str) -> Tuple[str, int, str]:
    """Return host, port, and a short discovery description.

    An explicit non-zero port uses the configured host directly. Port 0 requests
    an SRV lookup for the selected transport. If the domain has no SRV record,
    the original host and the conventional SIP/SIPS port are used.
    """
    clean_host = host.strip().replace("sip:", "").replace("sips:", "")
    selected_transport = transport.upper()
    if port:
        return clean_host, port, f"explicit {clean_host}:{port}"

    service = "_sips._tcp" if selected_transport == "TLS" else f"_sip._{selected_transport.lower()}"
    query_name = f"{service}.{clean_host.rstrip('.')}"
    fallback_port = 5061 if selected_transport == "TLS" else 5060

    try:
        import dns.resolver

        answers = sorted(
            dns.resolver.resolve(query_name, "SRV"),
            key=lambda record: (int(record.priority), -int(record.weight)),
        )
        if answers:
            record = answers[0]
            target = str(record.target).rstrip(".")
            return target, int(record.port), f"SRV {query_name} → {target}:{record.port}"
    except Exception as exc:
        return (
            clean_host,
            fallback_port,
            f"SRV unavailable ({exc}); A-record fallback {clean_host}:{fallback_port}",
        )

    return clean_host, fallback_port, f"A-record fallback {clean_host}:{fallback_port}"
