import socket
import ssl
import threading
import time
import uuid
import hashlib
import re
import urllib.parse
from string import Formatter
from typing import Dict, List, Optional, Callable, Tuple, Any
from jrvoiceapp.telephony.sipapp_core.version import USER_AGENT
from jrvoiceapp.telephony.sipapp_core.secure_media import crypto_attribute

DEFAULT_INVITE_TEMPLATE = """INVITE {target_uri} SIP/2.0
Via: SIP/2.0/{transport} {local_ip}:{local_port};branch={branch};rport
From: \"{display_name}\" <{from_uri}>;tag={from_tag}
To: <{target_uri}>
Call-ID: {call_id}
CSeq: {cseq} INVITE
Contact: {contact}
Max-Forwards: 70
User-Agent: {user_agent}
{authorization_header}Content-Type: application/sdp
Content-Length: {content_length}

{sdp_body}"""

DEFAULT_200_OK_TEMPLATE = """SIP/2.0 {status_code} {reason}
{via_headers}From: {from_header}
To: {to_header}
Call-ID: {call_id}
CSeq: {cseq_header}
User-Agent: {user_agent}
{custom_headers}{content_headers}

{sdp_body}"""

INVITE_TEMPLATE_REQUIRED_FIELDS = {
    "target_uri",
    "transport",
    "local_ip",
    "local_port",
    "branch",
    "display_name",
    "from_uri",
    "from_tag",
    "call_id",
    "cseq",
    "contact",
    "user_agent",
    "authorization_header",
    "content_length",
    "sdp_body",
}

INVITE_REQUIRED_HEADERS = {
    "via",
    "from",
    "to",
    "call-id",
    "cseq",
    "contact",
    "max-forwards",
    "user-agent",
    "content-type",
    "content-length",
}


class SIPMessage:
    """Represents a parsed or constructed SIP Request or Response."""

    def __init__(self, raw: str = ""):
        self.raw = raw
        self.is_request = False
        self.method = ""
        self.uri = ""
        self.version = "SIP/2.0"
        self.status_code = 0
        self.reason_phrase = ""
        self.headers: Dict[str, str] = {}
        self.header_values: Dict[str, List[str]] = {}
        self.body = ""

        if raw:
            self.parse(raw)

    def parse(self, raw: str):
        lines = raw.split("\r\n")
        if not lines or not lines[0]:
            lines = raw.split("\n")

        if not lines or not lines[0]:
            return

        start_line = lines[0].strip()
        parts = start_line.split(" ", 2)

        if start_line.startswith("SIP/2.0"):
            self.is_request = False
            if len(parts) >= 2:
                self.version = parts[0]
                try:
                    self.status_code = int(parts[1])
                except ValueError:
                    self.status_code = 0
                self.reason_phrase = parts[2] if len(parts) > 2 else ""
        else:
            self.is_request = True
            if len(parts) >= 3:
                self.method = parts[0]
                self.uri = parts[1]
                self.version = parts[2]

        i = 1
        body_lines = []
        in_body = False

        while i < len(lines):
            line = lines[i]
            if in_body:
                body_lines.append(line)
            else:
                if line == "" or line == "\r":
                    in_body = True
                else:
                    if ":" in line:
                        h_name, h_val = line.split(":", 1)
                        h_name_clean = h_name.strip()
                        norm_map = {
                            "v": "Via",
                            "f": "From",
                            "t": "To",
                            "i": "Call-ID",
                            "m": "Contact",
                            "c": "Content-Type",
                            "l": "Content-Length",
                            "pai": "P-Asserted-Identity",
                        }
                        h_key = norm_map.get(h_name_clean.lower(), h_name_clean)
                        value = h_val.strip()
                        normalized = h_key.lower()
                        self.header_values.setdefault(normalized, []).append(value)
                        if not any(existing.lower() == normalized for existing in self.headers):
                            self.headers[h_key] = value
            i += 1

        self.body = "\r\n".join(body_lines) if body_lines else ""

    def get_header(self, name: str) -> str:
        values = self.header_values.get(name.lower(), [])
        return values[0] if values else ""

    def get_headers(self, name: str) -> List[str]:
        return list(self.header_values.get(name.lower(), []))


class SIPLogEntry:
    """
    Log entry supporting granular categorization:
    - SIP: Raw SIP Packets
    - REG: User Registration Messages
    - DIAL: Dialed Call Attempts & Responses
    - SYS: System & Network Events
    """

    def __init__(
        self,
        category: str,
        direction: str,
        remote_addr: str,
        message: Optional[SIPMessage] = None,
        raw_text: str = "",
        sys_message: str = "",
    ):
        self.timestamp = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
        self.category = category  # "SIP", "REG", "DIAL", or "SYS"
        self.direction = {"SENT": "TX", "RECV": "RX"}.get(direction, direction)
        self.remote_addr = remote_addr
        self.message = message
        self.raw_text = raw_text
        self.sys_message = sys_message

        if message:
            if message.is_request:
                self.summary = f"{message.method} {message.uri}"
            else:
                self.summary = f"SIP/2.0 {message.status_code} {message.reason_phrase}"
                self.event_type = str(message.status_code)
            if message.is_request:
                self.event_type = message.method or "REQUEST"
        else:
            self.summary = sys_message or raw_text
            self.event_type = self.direction


class SIPEngine:
    """
    Pure Python RFC 3261 SIP Stack implementation.
    Supports UDP, TCP, TLS, Outbound Proxies, and Direct IP Call Blocking.
    """

    def __init__(
        self,
        local_port: int = 5060,
        transport: str = "UDP",
        use_tls: bool = False,
        tls_verify: bool = True,
        block_direct_ip_calls: bool = False,
        user_agent: str = USER_AGENT,
        invite_template: str = "",
        response_template: str = "",
        header_variables: Optional[Dict[str, str]] = None,
    ):
        self.local_port = local_port
        self.transport = "TLS" if use_tls else transport.upper()
        self.use_tls = use_tls
        self.tls_verify = tls_verify
        self.block_direct_ip_calls = block_direct_ip_calls
        self.user_agent = user_agent
        self.invite_template = invite_template or DEFAULT_INVITE_TEMPLATE
        self.response_template = response_template or DEFAULT_200_OK_TEMPLATE
        self.header_variables = dict(header_variables or {})

        self.socket: Optional[socket.socket] = None
        self.running = False
        self.rx_thread: Optional[threading.Thread] = None
        self.stream_connections: Dict[Tuple[Any, ...], socket.socket] = {}
        self.stream_lock = threading.Lock()

        self.log_entries: List[SIPLogEntry] = []
        self.log_callbacks: List[Callable[[SIPLogEntry], None]] = []

        self.local_ip = self._get_local_ip()

        # Active Call State
        self.call_state = "IDLE"
        self.active_call_id = ""
        self.active_dialog: Dict[str, Any] = {}
        self.outbound_invite_context: Dict[str, Any] = {}
        self.outbound_dialog: Dict[str, Any] = {}
        self.last_sip_peer: Tuple[str, int, str] = ("", 0, "")
        self.last_send_error = ""
        self.registered_users: List[str] = []

        self.call_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self.account_status_callbacks: List[Callable[[str, str, str], None]] = []

    def _get_local_ip(self) -> str:
        try:
            self.last_send_error = ""
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_socket:
                route_socket.connect(("8.8.8.8", 80))
                return route_socket.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def get_local_ip_for_target(self, target_host: str, target_port: int) -> str:
        """Return the local IPv4 address selected by the OS route to a SIP peer."""
        try:
            target_ip = socket.gethostbyname(target_host)
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect((target_ip, target_port))
            local_ip = probe.getsockname()[0]
            probe.close()
            return local_ip
        except OSError:
            return self.local_ip

    @staticmethod
    def normalize_dial_target(target: str, account_domain: str = "") -> str:
        """Normalize extensions and direct user@host values into one valid SIP URI."""
        value = target.strip()
        if value.lower().startswith(("sip:", "sips:")):
            return value
        if "@" in value:
            return f"sip:{value}"
        return f"sip:{value}@{account_domain}" if account_domain else f"sip:{value}"

    def log_sys_event(self, text: str, category: str = "SYS", level: str = "INFO"):
        entry = SIPLogEntry(category, level, "LOCAL", sys_message=text)
        self.log_entries.append(entry)
        if len(self.log_entries) > 2000:
            self.log_entries.pop(0)

        for cb in self.log_callbacks:
            try:
                cb(entry)
            except Exception:
                pass

    def start(self) -> bool:
        if self.running:
            return True

        self.running = True
        try:
            if self.transport == "UDP":
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket.bind(("0.0.0.0", self.local_port))
            elif self.transport == "TLS":
                raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                raw_sock.bind(("0.0.0.0", self.local_port))
                raw_sock.listen(5)

                ctx = ssl.create_default_context()
                if not self.tls_verify:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                self.socket = ctx.wrap_socket(raw_sock, server_side=True)
            else:  # TCP
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket.bind(("0.0.0.0", self.local_port))
                self.socket.listen(5)

            # A provider may request port 0 to avoid colliding with another
            # desktop client. SIP Via and Contact must advertise the port the
            # operating system actually assigned, never the literal zero.
            self.local_port = int(self.socket.getsockname()[1])
            self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.rx_thread.start()
            self.log_sys_event(
                f"SIPEngine listening on {self.local_ip}:{self.local_port} ({self.transport})"
            )
            return True
        except Exception as e:
            self.log_sys_event(
                f"Failed to bind port {self.local_port}: {e}", category="SYS", level="ERROR"
            )
            self.running = False
            return False

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        with self.stream_lock:
            connections = list(self.stream_connections.values())
            self.stream_connections.clear()
        for connection in connections:
            try:
                connection.close()
            except Exception:
                pass
        self.log_sys_event("SIPEngine stopped.")

    def add_log_callback(self, callback: Callable[[SIPLogEntry], None]):
        self.log_callbacks.append(callback)

    def add_call_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        self.call_callbacks.append(callback)

    def add_account_status_callback(self, callback: Callable[[str, str, str], None]):
        self.account_status_callbacks.append(callback)

    @staticmethod
    def _redact_media_keys(raw_text: str) -> str:
        return re.sub(r"(?im)^(a=crypto:\d+\s+\S+\s+inline:)[^\s|]+", r"\1[REDACTED]", raw_text)

    def _log_packet(self, direction: str, remote_addr: str, raw_text: str):
        safe_text = self._redact_media_keys(raw_text)
        msg = SIPMessage(safe_text)

        # Categorize
        category = "SIP"
        cseq = msg.get_header("CSeq")
        if "REGISTER" in cseq:
            category = "REG"
        elif "INVITE" in cseq or "BYE" in cseq or "CANCEL" in cseq or "UPDATE" in cseq:
            category = "DIAL"

        entry = SIPLogEntry(category, direction, remote_addr, message=msg, raw_text=safe_text)
        self.log_entries.append(entry)
        if len(self.log_entries) > 2000:
            self.log_entries.pop(0)

        for cb in self.log_callbacks:
            try:
                cb(entry)
            except Exception as e:
                print(f"[SIPEngine] Log callback error: {e}")

    def _notify_call_state(self, state: str, details: Optional[Dict[str, Any]] = None):
        self.call_state = state
        details = details or {}
        for cb in self.call_callbacks:
            try:
                cb(state, details)
            except Exception as e:
                print(f"[SIPEngine] Call callback error: {e}")

    @staticmethod
    def resolve_send_endpoint(
        target_host: str, target_port: int, outbound_proxy: str = ""
    ) -> Tuple[str, int]:
        """Return the host/port that will receive the next-hop SIP packet."""
        send_host, send_port = target_host, target_port
        if outbound_proxy:
            clean_proxy = outbound_proxy.removeprefix("sip:").removeprefix("sips:")
            host, separator, port_text = clean_proxy.rpartition(":")
            if separator and host and port_text.isdigit():
                return host, int(port_text)
            return clean_proxy, send_port
        return send_host, send_port

    def send_sip_message(
        self,
        raw_msg: str,
        target_host: str,
        target_port: int,
        outbound_proxy: str = "",
        transport: str = "",
        tls_verify: Optional[bool] = None,
    ):
        """Send raw SIP message over network socket (supports Outbound Proxy routing)."""
        try:
            send_host, send_port = self.resolve_send_endpoint(
                target_host, target_port, outbound_proxy
            )
            selected_transport = (transport or self.transport).upper()

            self._log_packet("TX", f"{send_host}:{send_port}", raw_msg)
            target_ip = socket.gethostbyname(send_host)
            message = SIPMessage(raw_msg)
            cseq = message.get_header("CSeq").upper()
            if any(method in cseq for method in ("INVITE", "ACK", "BYE", "CANCEL", "UPDATE")):
                self.last_sip_peer = (target_ip, send_port, selected_transport)
                if self.outbound_invite_context:
                    self.outbound_invite_context["sip_peer_ip"] = target_ip
                    self.outbound_invite_context["sip_peer_port"] = send_port
            if selected_transport == "UDP":
                if self.socket and self.transport == "UDP":
                    self.socket.sendto(raw_msg.encode("utf-8"), (target_ip, send_port))
                else:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                        udp_socket.sendto(raw_msg.encode("utf-8"), (target_ip, send_port))
            else:
                s = self._get_stream_connection(
                    selected_transport,
                    send_host,
                    target_ip,
                    send_port,
                    self.tls_verify if tls_verify is None else tls_verify,
                )
                s.sendall(raw_msg.encode("utf-8"))
            return True
        except ssl.SSLCertVerificationError as e:
            self.last_send_error = f"TLS certificate/hostname verification failed: {e}"
            self.log_sys_event(
                f"TLS certificate/hostname verification failed for {send_host}:{send_port}: {e}",
                category="REG" if raw_msg.startswith("REGISTER ") else "DIAL",
                level="ERROR",
            )
            return False
        except Exception as e:
            self.last_send_error = str(e)
            method = raw_msg.lstrip().split(" ", 1)[0].upper() if raw_msg.strip() else ""
            category = (
                "REG"
                if method == "REGISTER"
                else "DIAL"
                if method in ("INVITE", "ACK", "BYE", "CANCEL", "UPDATE")
                else "SIP"
            )
            self.log_sys_event(
                f"Send error to {send_host}:{send_port} - {e}", category=category, level="ERROR"
            )
            return False

    def _get_stream_connection(
        self, transport: str, host: str, target_ip: str, port: int, tls_verify: bool = True
    ) -> socket.socket:
        key = (transport, host, port, tls_verify)
        with self.stream_lock:
            existing = self.stream_connections.get(key)
            if existing:
                return existing
            if transport == "TLS":
                context = ssl.create_default_context()
                if not tls_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                connection = context.wrap_socket(
                    socket.socket(socket.AF_INET, socket.SOCK_STREAM), server_hostname=host
                )
            else:
                connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.settimeout(8)
            connection.connect((target_ip, port))
            connection.settimeout(0.5)
            self.stream_connections[key] = connection
            threading.Thread(
                target=self._stream_receive_loop,
                args=(key, connection, target_ip, port),
                daemon=True,
            ).start()
            return connection

    def _stream_receive_loop(
        self, key: Tuple[str, str, int], connection: socket.socket, remote_ip: str, remote_port: int
    ):
        buffer = b""
        while self.running:
            try:
                chunk = connection.recv(65535)
                if not chunk:
                    break
                buffer += chunk
                while b"\r\n\r\n" in buffer:
                    header_end = buffer.index(b"\r\n\r\n") + 4
                    header_text = buffer[:header_end].decode("utf-8", errors="replace")
                    length_match = re.search(r"(?im)^Content-Length:\s*(\d+)", header_text)
                    content_length = int(length_match.group(1)) if length_match else 0
                    message_end = header_end + content_length
                    if len(buffer) < message_end:
                        break
                    raw_text = buffer[:message_end].decode("utf-8", errors="replace")
                    buffer = buffer[message_end:]
                    self._log_packet("RX", f"{remote_ip}:{remote_port}", raw_text)
                    self._handle_incoming_sip(
                        SIPMessage(raw_text), remote_ip, remote_port, transport=key[0]
                    )
            except socket.timeout:
                continue
            except Exception:
                break
        with self.stream_lock:
            if self.stream_connections.get(key) is connection:
                self.stream_connections.pop(key, None)
        try:
            connection.close()
        except Exception:
            pass

    def _receive_loop(self):
        while self.running and self.socket:
            try:
                self.socket.settimeout(0.5)
                if self.transport == "UDP":
                    data, addr = self.socket.recvfrom(65535)
                    raw_text = data.decode("utf-8", errors="replace")
                    remote_str = f"{addr[0]}:{addr[1]}"
                    self._log_packet("RX", remote_str, raw_text)
                    self._handle_incoming_sip(SIPMessage(raw_text), addr[0], addr[1])
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    break

    def _handle_incoming_sip(
        self, msg: SIPMessage, remote_ip: str, remote_port: int, transport: str = ""
    ):
        response_transport = transport or self.transport
        if not msg.is_request:
            cseq_header = msg.get_header("CSeq")
            call_id = msg.get_header("Call-ID")

            if "INVITE" in cseq_header:
                if msg.status_code in (401, 407):
                    self._handle_invite_auth_challenge(msg)
                elif msg.status_code in (180, 183):
                    self._notify_call_state(
                        "RINGING", {"call_id": call_id, "status": msg.status_code}
                    )
                elif msg.status_code == 200:
                    context = (
                        self.outbound_invite_context
                        if self.outbound_invite_context.get("call_id") == call_id
                        else {}
                    )
                    if not context:
                        self.log_sys_event(
                            f"Ignoring stale/unmatched INVITE 200 OK for Call-ID={call_id}",
                            category="DIAL",
                            level="WARN",
                        )
                        return
                    route_set = list(reversed(msg.get_headers("Record-Route")))
                    remote_target = self._uri_from_header(
                        msg.get_header("Contact"), context.get("target_uri", "")
                    )
                    ack_msg = self._build_ack(
                        msg,
                        target_uri=remote_target,
                        cseq=int(context.get("cseq", 1)),
                        transport=context.get("transport", response_transport),
                        reuse_invite_branch=False,
                        source_ip=context.get("source_ip", ""),
                        route_headers=route_set,
                    )
                    self.send_sip_message(
                        ack_msg,
                        context.get("target_host", remote_ip),
                        context.get("target_port", remote_port),
                        outbound_proxy=context.get("outbound_proxy", ""),
                        transport=context.get("transport", response_transport),
                        tls_verify=context.get("tls_verify", True),
                    )
                    local_contact = SIPMessage(context.get("invite_packet", "")).get_header(
                        "Contact"
                    )
                    self.outbound_dialog = {
                        **context,
                        "from": msg.get_header("From"),
                        "to": msg.get_header("To"),
                        "contact": msg.get_header("Contact"),
                        "route_set": route_set,
                        "local_contact": local_contact,
                        "cseq": int(context.get("cseq", 1)),
                    }
                    if context.get("cancel_requested"):
                        self.call_state = "CONNECTED"
                        self._send_bye(self.outbound_dialog, "late 200 OK after CANCEL")
                        self._notify_call_state(
                            "TERMINATED",
                            {"reason": "Cancelled call answered late; ACK and BYE sent"},
                        )
                        return
                    self._notify_call_state(
                        "CONNECTED",
                        {
                            "call_id": call_id,
                            "remote_ip": remote_ip,
                            "remote_port": remote_port,
                            "sdp": msg.body,
                        },
                    )
                elif msg.status_code >= 400:
                    self._notify_call_state(
                        "TERMINATED", {"reason": f"{msg.status_code} {msg.reason_phrase}"}
                    )
            elif "UPDATE" in cseq_header:
                if 200 <= msg.status_code < 300:
                    self.log_sys_event(
                        f"Call session refreshed: {msg.status_code} {msg.reason_phrase}",
                        category="DIAL",
                    )
                elif msg.status_code >= 300:
                    self.log_sys_event(
                        f"Call refresh failed: {msg.status_code} {msg.reason_phrase}",
                        category="DIAL",
                        level="ERROR",
                    )
                    self._notify_call_state("TERMINATED", {"reason": "Session refresh failed"})
        else:
            if msg.method == "INVITE":
                to_hdr = msg.get_header("To")
                # Direct IP Blocking Security Feature
                if self.block_direct_ip_calls:
                    # Check if Request URI or To header matches any registered username
                    matched = False
                    for reg_user in self.registered_users:
                        if reg_user and reg_user in to_hdr:
                            matched = True
                            break
                    if not matched and (self.local_ip in msg.uri or "127.0.0.1" in msg.uri):
                        # Block uninvited Direct IP call!
                        forbidden_resp = self._build_response(msg, 403, "Direct IP Calls Blocked")
                        self.send_sip_message(
                            forbidden_resp, remote_ip, remote_port, transport=response_transport
                        )
                        self.log_sys_event(
                            f"Blocked Direct IP call from {remote_ip}:{remote_port} (URI: {msg.uri})",
                            category="SYS",
                            level="WARN",
                        )
                        return

                call_id = msg.get_header("Call-ID")
                from_hdr = msg.get_header("From")
                pai_hdr = msg.get_header("P-Asserted-Identity") or msg.get_header("PAI") or "None"

                ringing_resp = self._build_response(msg, 180, "Ringing")
                self.send_sip_message(
                    ringing_resp, remote_ip, remote_port, transport=response_transport
                )
                self.active_dialog = {
                    "call_id": call_id,
                    "remote_ip": remote_ip,
                    "remote_port": remote_port,
                    "transport": response_transport,
                    "req_msg": msg,
                }
                self._notify_call_state(
                    "INCOMING_CALL",
                    {
                        "call_id": call_id,
                        "from": from_hdr,
                        "pai": pai_hdr,
                        "to": to_hdr,
                        "server_url": f"sip:{remote_ip}:{remote_port}",
                        "remote_ip": remote_ip,
                        "remote_port": remote_port,
                        "transport": response_transport,
                        "sdp": msg.body,
                    },
                )
            elif msg.method == "BYE":
                resp_200 = self._build_response(msg, 200, "OK")
                self.send_sip_message(
                    resp_200, remote_ip, remote_port, transport=response_transport
                )
                self.outbound_dialog = {}
                self.active_dialog = {}
                self._notify_call_state("TERMINATED", {"reason": "Hangup by Remote"})
            elif msg.method == "CANCEL":
                resp_200 = self._build_response(msg, 200, "OK")
                self.send_sip_message(
                    resp_200, remote_ip, remote_port, transport=response_transport
                )
                self._notify_call_state("TERMINATED", {"reason": "Call Cancelled"})
            elif msg.method == "OPTIONS":
                resp_200 = self._build_response(msg, 200, "OK")
                self.send_sip_message(
                    resp_200, remote_ip, remote_port, transport=response_transport
                )

    def _handle_invite_auth_challenge(self, response: SIPMessage):
        call_id = response.get_header("Call-ID")
        context = self.outbound_invite_context
        if not context or context.get("call_id") != call_id:
            self.log_sys_event(
                f"INVITE digest challenge did not match the active call: Call-ID={call_id}",
                category="DIAL",
                level="ERROR",
            )
            self._notify_call_state(
                "TERMINATED", {"reason": "Unmatched INVITE authentication challenge"}
            )
            return

        status_code = response.status_code
        try:
            challenge_cseq = int(response.get_header("CSeq").split(" ", 1)[0] or 1)
        except ValueError:
            challenge_cseq = int(context.get("cseq", 1))
        challenge_ack = self._build_ack(
            response,
            target_uri=context["target_uri"],
            cseq=challenge_cseq,
            transport=context.get("transport", self.transport),
            source_ip=context.get("source_ip", ""),
        )
        self.send_sip_message(
            challenge_ack,
            context["target_host"],
            context["target_port"],
            outbound_proxy=context.get("outbound_proxy", ""),
            transport=context.get("transport", "UDP"),
            tls_verify=context.get("tls_verify", True),
        )

        if context.get("auth_attempted"):
            self.log_sys_event(
                f"Authenticated INVITE rejected with {status_code} {response.reason_phrase}",
                category="DIAL",
                level="ERROR",
            )
            self._notify_call_state(
                "TERMINATED", {"reason": f"{status_code} INVITE authentication rejected"}
            )
            return

        account = context.get("account", {})
        if not account.get("username") or not account.get("password"):
            self.log_sys_event(
                "INVITE challenge received but the selected account has no credentials",
                category="DIAL",
                level="ERROR",
            )
            self._notify_call_state(
                "TERMINATED", {"reason": "Missing credentials for INVITE authentication"}
            )
            return

        challenge_header = "WWW-Authenticate" if status_code == 401 else "Proxy-Authenticate"
        challenge = response.get_header(challenge_header)
        parsed = self.parse_auth_challenge(challenge)
        realm = parsed.get("realm", account.get("domain", ""))
        nonce = parsed.get("nonce", "")
        opaque = parsed.get("opaque", "")
        algorithm = parsed.get("algorithm", "MD5").upper()
        qop_options = parsed.get("qop", "")
        qop = "auth" if "auth" in qop_options.lower() else ""

        if not challenge or not nonce:
            self.log_sys_event(
                "INVITE digest challenge is missing a nonce", category="DIAL", level="ERROR"
            )
            self._notify_call_state("TERMINATED", {"reason": "Malformed INVITE digest challenge"})
            return
        if algorithm not in ("MD5", ""):
            self.log_sys_event(
                f"Unsupported INVITE digest algorithm: {algorithm}", category="DIAL", level="ERROR"
            )
            self._notify_call_state(
                "TERMINATED", {"reason": f"Unsupported digest algorithm: {algorithm}"}
            )
            return
        if qop_options and not qop:
            self.log_sys_event(
                f"Unsupported INVITE digest qop: {qop_options}", category="DIAL", level="ERROR"
            )
            self._notify_call_state(
                "TERMINATED", {"reason": f"Unsupported digest qop: {qop_options}"}
            )
            return

        target_uri = context["target_uri"]
        auth_user = account.get("auth_user") or account["username"]
        cnonce = uuid.uuid4().hex[:16]
        nc = "00000001"
        digest_response = self.calculate_digest_response(
            auth_user,
            account["password"],
            realm,
            nonce,
            target_uri,
            "INVITE",
            qop=qop,
            nc=nc,
            cnonce=cnonce,
        )
        auth_value = (
            f'Digest username="{auth_user}", realm="{realm}", nonce="{nonce}", '
            f'uri="{target_uri}", response="{digest_response}"'
        )
        if qop:
            auth_value += f', qop={qop}, nc={nc}, cnonce="{cnonce}"'
        if opaque:
            auth_value += f', opaque="{opaque}"'
        auth_value += ", algorithm=MD5"

        authenticated_cseq = challenge_cseq + 1
        authenticated_invite, _ = self.build_invite(
            target_uri,
            from_account=account,
            rtp_port=context["rtp_port"],
            auth_header=auth_value,
            cseq=authenticated_cseq,
            call_id=call_id,
            auth_header_name="Authorization" if status_code == 401 else "Proxy-Authorization",
            source_ip=context.get("source_ip", ""),
            media_ip=context.get("media_ip", ""),
            session_refresh_seconds=int(context.get("session_refresh_seconds", 0)),
            media_security=context.get("media_security", "RTP"),
            srtp_local_key=context.get("srtp_local_key", b""),
        )
        context["auth_attempted"] = True
        context["cseq"] = authenticated_cseq
        context["invite_packet"] = authenticated_invite
        self.log_sys_event(
            f"Accepted {status_code} INVITE digest challenge; sending authenticated INVITE "
            f"with CSeq {authenticated_cseq}",
            category="DIAL",
        )
        self.send_sip_message(
            authenticated_invite,
            context["target_host"],
            context["target_port"],
            outbound_proxy=context.get("outbound_proxy", ""),
            transport=context.get("transport", "UDP"),
            tls_verify=context.get("tls_verify", True),
        )

    @staticmethod
    def calculate_digest_response(
        username: str,
        password: str,
        realm: str,
        nonce: str,
        uri: str,
        method: str,
        qop: str = "",
        nc: str = "00000001",
        cnonce: str = "",
    ) -> str:
        ha1_raw = f"{username}:{realm}:{password}"
        ha1 = hashlib.md5(ha1_raw.encode("utf-8")).hexdigest()

        ha2_raw = f"{method}:{uri}"
        ha2 = hashlib.md5(ha2_raw.encode("utf-8")).hexdigest()

        if qop and ("auth" in qop.lower()):
            if not cnonce:
                cnonce = uuid.uuid4().hex[:16]
            response_raw = f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}"
        else:
            response_raw = f"{ha1}:{nonce}:{ha2}"

        return hashlib.md5(response_raw.encode("utf-8")).hexdigest()

    @staticmethod
    def parse_auth_challenge(challenge_header: str) -> Dict[str, str]:
        res = {}
        pattern = re.compile(r'(\w+)=["\']?([^"\',]+)["\']?')
        for match in pattern.finditer(challenge_header):
            res[match.group(1)] = match.group(2)
        return res

    def build_register(
        self,
        account: Dict[str, Any],
        cseq: int = 1,
        auth_header: str = "",
        expires: int = 3600,
        call_id: str = "",
        auth_header_name: str = "Authorization",
    ) -> Tuple[str, str]:
        domain = account["domain"]
        user = account["username"]
        call_id = call_id or f"{uuid.uuid4().hex[:16]}@{self.local_ip}"
        branch = f"z9hG4bK-{uuid.uuid4().hex[:12]}"
        stable_tag_source = f"{account.get('id', user)}@{self.local_ip}"
        tag = hashlib.md5(stable_tag_source.encode("utf-8")).hexdigest()[:8]

        uri = f"sip:{domain}"
        from_tag = f"sip:{user}@{domain}"
        contact = f"<sip:{user}@{self.local_ip}:{self.local_port}>"
        transport = account.get("transport", self.transport).upper()

        headers = [
            f"REGISTER {uri} SIP/2.0",
            f"Via: SIP/2.0/{transport} {self.local_ip}:{self.local_port};branch={branch};rport",
            f'From: "{account.get("name", user)}" <{from_tag}>;tag={tag}',
            f"To: <{from_tag}>",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq} REGISTER",
            f"Contact: {contact}",
            f"Max-Forwards: 70",
            f"User-Agent: {self.user_agent}",
            f"Expires: {expires}",
        ]

        if auth_header:
            headers.append(f"{auth_header_name}: {auth_header}")

        headers.append("Content-Length: 0\r\n\r\n")
        return "\r\n".join(headers), call_id

    def build_invite(
        self,
        target_uri: str,
        from_account: Optional[Dict[str, Any]] = None,
        rtp_port: int = 10000,
        auth_header: str = "",
        cseq: int = 1,
        call_id: str = "",
        auth_header_name: str = "Authorization",
        source_ip: str = "",
        media_ip: str = "",
        session_refresh_seconds: int = 0,
        media_security: str = "RTP",
        srtp_local_key: bytes = b"",
    ) -> Tuple[str, str]:
        selected_source_ip = source_ip or self.local_ip
        selected_media_ip = media_ip or selected_source_ip
        call_id = call_id or f"call-{uuid.uuid4().hex[:16]}@{selected_source_ip}"
        branch_seed = f"{call_id}:{cseq}"
        branch = f"z9hG4bK-{hashlib.md5(branch_seed.encode('utf-8')).hexdigest()[:12]}"
        tag = hashlib.md5(call_id.encode("utf-8")).hexdigest()[:8]

        if from_account:
            domain = from_account["domain"]
            user = from_account["username"]
            display_name = from_account.get("name", user) or user
            from_uri = f"sip:{user}@{domain}"
        else:
            domain = selected_source_ip
            user = "anon-sipapp"
            display_name = "Direct URI Caller"
            from_uri = f"sip:{user}@{selected_source_ip}"

        contact = f"<sip:{user}@{selected_source_ip}:{self.local_port}>"
        transport = (
            from_account.get("transport", self.transport).upper()
            if from_account
            else self.transport
        )

        if not target_uri.startswith("sip:"):
            target_uri = f"sip:{target_uri}"

        secure_media = media_security.upper() == "SDES-SRTP"
        media_profile = "RTP/SAVP" if secure_media else "RTP/AVP"
        crypto_line = f"{crypto_attribute(srtp_local_key)}\r\n" if secure_media else ""
        sdp_body = (
            f"v=0\r\n"
            f"o={user} 123456 123456 IN IP4 {selected_media_ip}\r\n"
            f"s=Python SIPApp Call\r\n"
            f"c=IN IP4 {selected_media_ip}\r\n"
            f"t=0 0\r\n"
            f"m=audio {rtp_port} {media_profile} 0 8 101\r\n"
            f"a=rtpmap:0 PCMU/8000\r\n"
            f"a=rtpmap:8 PCMA/8000\r\n"
            f"a=rtpmap:101 telephone-event/8000\r\n"
            f"{crypto_line}"
            f"a=sendrecv\r\n"
        )

        context = {
            "target_uri": target_uri,
            "transport": transport,
            "local_ip": selected_source_ip,
            "local_port": self.local_port,
            "branch": branch,
            "display_name": display_name,
            "from_uri": from_uri,
            "from_tag": tag,
            "call_id": call_id,
            "cseq": cseq,
            "contact": contact,
            "user_agent": self.user_agent,
            "authorization_header": (
                (f"{auth_header_name}: {auth_header}\n" if auth_header else "")
                + (
                    f"Supported: timer\nSession-Expires: {max(90, session_refresh_seconds * 2)};refresher=uac\nMin-SE: 90\n"
                    if session_refresh_seconds > 0
                    else ""
                )
            ),
            "content_length": len(sdp_body.encode("utf-8")),
            "sdp_body": sdp_body.replace("\r\n", "\n"),
        }
        context.update(self.header_variables)
        context["custom_headers"] = self._custom_header_lines()
        template = self.invite_template or DEFAULT_INVITE_TEMPLATE
        valid, error = self.validate_invite_template(
            template, set(self.header_variables) | {"custom_headers"}
        )
        if not valid:
            self.log_sys_event(
                f"Invalid saved INVITE template; using default: {error}",
                category="DIAL",
                level="ERROR",
            )
            template = DEFAULT_INVITE_TEMPLATE
        try:
            packet = template.replace("\r\n", "\n").format_map(context).replace("\n", "\r\n")
        except (KeyError, ValueError) as exc:
            self.log_sys_event(
                f"INVITE template rendering failed; using default: {exc}",
                category="DIAL",
                level="ERROR",
            )
            packet = DEFAULT_INVITE_TEMPLATE.format_map(context).replace("\n", "\r\n")
        self.active_call_id = call_id
        return packet, call_id

    @staticmethod
    def validate_invite_template(
        template: str, allowed_fields: Optional[set[str]] = None
    ) -> Tuple[bool, str]:
        errors = SIPEngine.inspect_invite_template(template, allowed_fields)
        return (not errors, "; ".join(errors))

    @staticmethod
    def inspect_invite_template(
        template: str, allowed_fields: Optional[set[str]] = None
    ) -> List[str]:
        """Return actionable structural errors for an editable INVITE template."""
        if not template.strip():
            return ["Template cannot be empty"]
        try:
            parsed = list(Formatter().parse(template))
        except ValueError as exc:
            return [f"Invalid braces: {exc}"]
        if any(
            format_spec or conversion
            for _, field_name, format_spec, conversion in parsed
            if field_name
        ):
            return ["Placeholder conversions and format specifications are not supported"]
        fields = {field_name for _, field_name, _, _ in parsed if field_name}
        unknown = fields - INVITE_TEMPLATE_REQUIRED_FIELDS - (allowed_fields or set())
        missing = INVITE_TEMPLATE_REQUIRED_FIELDS - fields
        errors = []
        if unknown:
            errors.append(f"Unknown placeholders: {', '.join(sorted(unknown))}")
        if missing:
            errors.append(f"Missing placeholders: {', '.join(sorted(missing))}")
        if errors:
            return errors

        sample = {
            "target_uri": "sip:2000@pbx.example.com",
            "transport": "UDP",
            "local_ip": "192.0.2.10",
            "local_port": 5060,
            "branch": "z9hG4bK-validation",
            "display_name": "Validation Account",
            "from_uri": "sip:1001@pbx.example.com",
            "from_tag": "validation",
            "call_id": "validation@192.0.2.10",
            "cseq": 2,
            "contact": "<sip:1001@192.0.2.10:5060>",
            "user_agent": "Python-SIPApp/validation",
            "authorization_header": "Authorization: Digest validation=true\n",
            "sdp_body": "v=0\ns=Validation\n",
            "content_length": len("v=0\r\ns=Validation\r\n".encode("utf-8")),
        }
        sample.update({field: "X-Validation: value\n" if field == "custom_headers" else "value" for field in (allowed_fields or set())})
        try:
            rendered = template.replace("\r\n", "\n").format_map(sample).replace("\n", "\r\n")
        except (KeyError, ValueError, TypeError) as exc:
            return [f"Template could not be rendered: {exc}"]

        if "\r\n\r\n" not in rendered:
            return ["Missing blank line between SIP headers and SDP body"]
        header_block, body = rendered.split("\r\n\r\n", 1)
        lines = header_block.split("\r\n")
        if not re.fullmatch(r"INVITE\s+sips?:\S+\s+SIP/2\.0", lines[0]):
            errors.append("Request line must be: INVITE {target_uri} SIP/2.0")

        headers: Dict[str, List[str]] = {}
        token_pattern = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
        for line_number, line in enumerate(lines[1:], start=2):
            if not line or ":" not in line:
                errors.append(f"Line {line_number} is not a valid Name: value header")
                continue
            name, value = line.split(":", 1)
            name = name.strip()
            value = value.strip()
            if not token_pattern.fullmatch(name):
                errors.append(f"Line {line_number} has an invalid header name: {name or '(empty)'}")
                continue
            if not value:
                errors.append(f"Header {name} has no value")
            headers.setdefault(name.lower(), []).append(value)

        missing_headers = INVITE_REQUIRED_HEADERS - set(headers)
        if missing_headers:
            errors.append(f"Missing SIP headers: {', '.join(sorted(missing_headers))}")
        if "cseq" in headers and not re.fullmatch(
            r"\d+\s+INVITE", headers["cseq"][0], re.IGNORECASE
        ):
            errors.append("CSeq must contain a number followed by INVITE")
        if "via" in headers and not re.match(
            r"SIP/2\.0/(UDP|TCP|TLS)\s+\S+", headers["via"][0], re.IGNORECASE
        ):
            errors.append("Via must contain SIP/2.0/UDP, TCP, or TLS and a sent-by address")
        if "content-type" in headers and headers["content-type"][0].lower() != "application/sdp":
            errors.append("Content-Type must be application/sdp")
        if "max-forwards" in headers:
            try:
                max_forwards = int(headers["max-forwards"][0])
                if not 0 <= max_forwards <= 255:
                    raise ValueError
            except ValueError:
                errors.append("Max-Forwards must be an integer from 0 through 255")
        if "content-length" in headers:
            try:
                if int(headers["content-length"][0]) != len(body.encode("utf-8")):
                    errors.append("Content-Length does not match the rendered SDP body")
            except ValueError:
                errors.append("Content-Length must be an integer")
        return errors

    def start_outbound_invite(
        self,
        target_uri: str,
        account: Optional[Dict[str, Any]],
        rtp_port: int,
        target_host: str,
        target_port: int,
        outbound_proxy: str = "",
        transport: str = "UDP",
        source_ip: str = "",
        media_ip: str = "",
        session_refresh_seconds: int = 0,
        media_security: str = "RTP",
        srtp_local_key: bytes = b"",
    ) -> str:
        packet, call_id = self.build_invite(
            target_uri,
            from_account=account,
            rtp_port=rtp_port,
            source_ip=source_ip,
            media_ip=media_ip,
            session_refresh_seconds=session_refresh_seconds,
            media_security=media_security,
            srtp_local_key=srtp_local_key,
        )
        self.outbound_invite_context = {
            "call_id": call_id,
            "target_uri": target_uri,
            "account": account or {},
            "rtp_port": rtp_port,
            "target_host": target_host,
            "target_port": target_port,
            "outbound_proxy": outbound_proxy,
            "transport": transport.upper(),
            "tls_verify": bool((account or {}).get("tls_verify_cert", True)),
            "cseq": 1,
            "auth_attempted": False,
            "source_ip": source_ip,
            "media_ip": media_ip,
            "session_refresh_seconds": session_refresh_seconds,
            "invite_packet": packet,
            "media_security": media_security,
            "srtp_local_key": srtp_local_key,
        }
        self.last_sip_peer = ("", 0, transport.upper())
        self._notify_call_state("DIALING", {"call_id": call_id, "target": target_uri})
        sent = self.send_sip_message(
            packet,
            target_host,
            target_port,
            outbound_proxy=outbound_proxy,
            transport=transport,
            tls_verify=bool((account or {}).get("tls_verify_cert", True)),
        )
        if sent is False:
            self._notify_call_state(
                "TERMINATED", {"reason": self.last_send_error or "Secure signaling send failed"}
            )
        return call_id

    def _build_ack(
        self,
        resp_msg: SIPMessage,
        target_uri: str = "",
        cseq: int = 1,
        transport: str = "",
        reuse_invite_branch: bool = True,
        source_ip: str = "",
        route_headers: Optional[List[str]] = None,
    ) -> str:
        to_hdr = resp_msg.get_header("To")
        from_hdr = resp_msg.get_header("From")
        call_id = resp_msg.get_header("Call-ID")
        if reuse_invite_branch:
            branch_seed = f"{call_id}:{cseq}"
            branch = f"z9hG4bK-{hashlib.md5(branch_seed.encode('utf-8')).hexdigest()[:12]}"
        else:
            branch = f"z9hG4bK-{uuid.uuid4().hex[:12]}"
        selected_transport = (transport or self.transport).upper()
        selected_source_ip = source_ip or self.local_ip

        headers = [
            f"ACK {target_uri or resp_msg.uri or 'sip:' + self.local_ip} SIP/2.0",
            f"Via: SIP/2.0/{selected_transport} {selected_source_ip}:{self.local_port};branch={branch};rport",
            f"From: {from_hdr}",
            f"To: {to_hdr}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq} ACK",
            f"Max-Forwards: 70",
            f"User-Agent: {self.user_agent}",
        ]
        headers.extend(f"Route: {route}" for route in (route_headers or []))
        headers.append("Content-Length: 0\r\n\r\n")
        return "\r\n".join(headers)

    def _build_response(
        self, req_msg: SIPMessage, status_code: int, reason: str, sdp_body: str = ""
    ) -> str:
        via_headers = req_msg.get_headers("Via")
        from_hdr = req_msg.get_header("From")
        to_hdr = req_msg.get_header("To")
        if ";tag=" not in to_hdr.lower():
            to_hdr += f";tag={uuid.uuid4().hex[:8]}"
        call_id = req_msg.get_header("Call-ID")
        cseq_hdr = req_msg.get_header("CSeq")

        content_headers = (
            f"Content-Type: application/sdp\nContent-Length: {len(sdp_body.encode('utf-8'))}"
            if sdp_body
            else "Content-Length: 0"
        )
        context = {
            "status_code": status_code,
            "reason": reason,
            "via_headers": "".join(f"Via: {via}\n" for via in via_headers),
            "from_header": from_hdr,
            "to_header": to_hdr,
            "call_id": call_id,
            "cseq_header": cseq_hdr,
            "user_agent": self.user_agent,
            "content_headers": content_headers,
            "content_length": len(sdp_body.encode("utf-8")),
            "sdp_body": sdp_body.replace("\r\n", "\n"),
            "custom_headers": self._custom_header_lines(),
        }
        context.update(self.header_variables)
        template = self.response_template if status_code == 200 else DEFAULT_200_OK_TEMPLATE
        try:
            return template.replace("\r\n", "\n").format_map(context).replace("\n", "\r\n")
        except (KeyError, ValueError) as exc:
            self.log_sys_event(
                f"200 OK template rendering failed; using default: {exc}", category="DIAL", level="ERROR"
            )
            return DEFAULT_200_OK_TEMPLATE.format_map(context).replace("\n", "\r\n")

    def _custom_header_lines(self) -> str:
        """Return explicit unknown/X-headers without allowing line injection."""
        headers = []
        for name, value in self.header_variables.items():
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                continue
            if ":" in name:
                header_name = name
            else:
                header_name = f"X-{name.replace('_', '-') }"
            headers.append(f"{header_name}: {value}\n")
        return "".join(headers)

    def answer_incoming_call(
        self,
        rtp_port: int = 10000,
        media_ip: str = "",
        media_security: str = "RTP",
        srtp_local_key: bytes = b"",
        srtp_tag: int = 1,
        codec: str = "PCMU",
        payload_type: int = 0,
    ):
        if not self.active_dialog:
            return

        req_msg = self.active_dialog["req_msg"]
        remote_ip = self.active_dialog["remote_ip"]
        remote_port = self.active_dialog["remote_port"]
        transport = self.active_dialog.get("transport", self.transport)
        self.last_sip_peer = (remote_ip, remote_port, transport.upper())
        secure_media = media_security.upper() == "SDES-SRTP"
        media_profile = "RTP/SAVP" if secure_media else "RTP/AVP"
        crypto_line = f"{crypto_attribute(srtp_local_key, srtp_tag)}\r\n" if secure_media else ""
        advertised_media_ip = media_ip or self.local_ip
        codec = codec.upper()
        if codec not in ("PCMU", "PCMA"):
            raise ValueError(f"Unsupported answer codec: {codec}")
        static_payload = 0 if codec == "PCMU" else 8
        payload_type = int(payload_type if payload_type is not None else static_payload)

        user = "anon"
        sdp_body = (
            f"v=0\r\n"
            f"o={user} 654321 654321 IN IP4 {advertised_media_ip}\r\n"
            f"s=Python SIPApp Call\r\n"
            f"c=IN IP4 {advertised_media_ip}\r\n"
            f"t=0 0\r\n"
            f"m=audio {rtp_port} {media_profile} {payload_type} 101\r\n"
            f"a=rtpmap:{payload_type} {codec}/8000\r\n"
            f"a=rtpmap:101 telephone-event/8000\r\n"
            f"{crypto_line}"
            f"a=sendrecv\r\n"
        )

        ok_resp = self._build_response(req_msg, 200, "OK", sdp_body)
        self.send_sip_message(ok_resp, remote_ip, remote_port, transport=transport)
        ok_message = SIPMessage(ok_resp)
        self.active_dialog.update(
            {
                "direction": "incoming",
                "target_uri": self._uri_from_header(
                    req_msg.get_header("Contact"),
                    self._uri_from_header(req_msg.get_header("From"), req_msg.uri),
                ),
                "contact": req_msg.get_header("Contact"),
                "from": ok_message.get_header("To"),
                "to": req_msg.get_header("From"),
                "call_id": req_msg.get_header("Call-ID"),
                "cseq": 0,
                "source_ip": advertised_media_ip,
                "target_host": remote_ip,
                "target_port": remote_port,
            }
        )
        self._notify_call_state(
            "CONNECTED",
            {
                "call_id": req_msg.get_header("Call-ID"),
                "remote_ip": remote_ip,
                "remote_port": remote_port,
            },
        )

    def reject_incoming_call(self, status_code: int = 488, reason: str = "Not Acceptable Here"):
        if not self.active_dialog:
            return
        dialog = self.active_dialog
        response = self._build_response(dialog["req_msg"], status_code, reason)
        self.send_sip_message(
            response,
            dialog["remote_ip"],
            dialog["remote_port"],
            transport=dialog.get("transport", self.transport),
        )
        self.active_dialog = {}
        self._notify_call_state("TERMINATED", {"reason": f"{status_code} {reason}"})

    @staticmethod
    def _uri_from_header(value: str, fallback: str) -> str:
        match = re.search(r"<(sips?:[^>]+)>", value or "", re.IGNORECASE)
        return match.group(1) if match else fallback

    def _build_dialog_request(
        self,
        method: str,
        dialog: Dict[str, Any],
        cseq: int,
        session_interval: int = 0,
        extra_headers: Optional[List[str]] = None,
        body: str = "",
    ) -> str:
        request_uri = self._uri_from_header(dialog.get("contact", ""), dialog.get("target_uri", ""))
        source_ip = dialog.get("source_ip") or self.local_ip
        transport = dialog.get("transport", self.transport).upper()
        headers = [
            f"{method} {request_uri} SIP/2.0",
            f"Via: SIP/2.0/{transport} {source_ip}:{self.local_port};branch=z9hG4bK-{uuid.uuid4().hex[:12]};rport",
            f"From: {dialog.get('from', '')}",
            f"To: {dialog.get('to', '')}",
            f"Call-ID: {dialog.get('call_id', '')}",
            f"CSeq: {cseq} {method}",
            "Max-Forwards: 70",
            f"User-Agent: {self.user_agent}",
        ]
        headers.extend(f"Route: {route}" for route in dialog.get("route_set", []))
        if method == "UPDATE" and session_interval:
            local_contact = dialog.get("local_contact", "")
            if not local_contact:
                account = dialog.get("account", {})
                username = account.get("username", "")
                if username:
                    local_contact = f"<sip:{username}@{source_ip}:{self.local_port}>"
            if local_contact:
                headers.append(f"Contact: {local_contact}")
            headers.extend(
                [
                    "Supported: timer",
                    f"Session-Expires: {session_interval};refresher=uac",
                    "Min-SE: 90",
                ]
            )
        headers.extend(extra_headers or [])
        headers.append(f"Content-Length: {len(body.encode('utf-8'))}")
        return "\r\n".join(headers) + "\r\n\r\n" + body

    def _active_connected_dialog(self) -> Dict[str, Any]:
        if self.call_state not in ("CONNECTED", "HELD"):
            return {}
        return self.outbound_dialog or (
            self.active_dialog if self.active_dialog.get("direction") == "incoming" else {}
        )

    def _send_dialog_request(
        self, method: str, extra_headers: Optional[List[str]] = None, body: str = ""
    ) -> bool:
        dialog = self._active_connected_dialog()
        if not dialog:
            return False
        dialog["cseq"] = int(dialog.get("cseq", 0)) + 1
        request = self._build_dialog_request(
            method, dialog, dialog["cseq"], extra_headers=extra_headers, body=body
        )
        return bool(
            self.send_sip_message(
                request,
                dialog["target_host"],
                dialog["target_port"],
                outbound_proxy=dialog.get("outbound_proxy", ""),
                transport=dialog.get("transport", "UDP"),
                tls_verify=dialog.get("tls_verify", True),
            )
        )

    def send_dtmf(self, digit: str) -> bool:
        if digit not in "0123456789*#ABCD":
            raise ValueError("DTMF must be one digit: 0-9, *, #, or A-D.")
        body = f"Signal={digit}\r\nDuration=160\r\n"
        sent = self._send_dialog_request("INFO", ["Content-Type: application/dtmf-relay"], body)
        if sent:
            self.log_sys_event(f"Sent DTMF {digit} using SIP INFO", category="DIAL")
        return sent

    def set_hold(self, held: bool, rtp_port: int = 10000) -> bool:
        direction = "sendonly" if held else "sendrecv"
        body = (
            f"v=0\r\no=JRVoiceApp 1 1 IN IP4 {self.local_ip}\r\ns=SIP hold\r\n"
            f"c=IN IP4 {self.local_ip}\r\nt=0 0\r\nm=audio {rtp_port} RTP/AVP 0 8 101\r\n"
            "a=rtpmap:0 PCMU/8000\r\na=rtpmap:8 PCMA/8000\r\n"
            "a=rtpmap:101 telephone-event/8000\r\n"
            f"a={direction}\r\n"
        )
        sent = self._send_dialog_request("UPDATE", ["Content-Type: application/sdp"], body)
        if sent:
            self._notify_call_state("HELD" if held else "CONNECTED", {"held": held})
        return sent

    def transfer_call(self, destination: str, account_domain: str = "") -> bool:
        target = self.normalize_dial_target(destination, account_domain)
        sent = self._send_dialog_request("REFER", [f"Refer-To: <{target}>"])
        if sent:
            self.log_sys_event(f"Sent blind transfer REFER to {target}", category="DIAL")
        return sent

    def cancel_outbound_call(self) -> bool:
        context = self.outbound_invite_context
        raw_invite = context.get("invite_packet", "")
        if not context or not raw_invite:
            return False
        context["cancel_requested"] = True
        invite = SIPMessage(raw_invite)
        cseq = invite.get_header("CSeq").split(" ", 1)[0] or "1"
        cancel = (
            "\r\n".join(
                [
                    f"CANCEL {invite.uri} SIP/2.0",
                    f"Via: {invite.get_header('Via')}",
                    f"From: {invite.get_header('From')}",
                    f"To: {invite.get_header('To')}",
                    f"Call-ID: {invite.get_header('Call-ID')}",
                    f"CSeq: {cseq} CANCEL",
                    "Max-Forwards: 70",
                    f"User-Agent: {self.user_agent}",
                    "Content-Length: 0",
                    "",
                ]
            )
            + "\r\n"
        )
        self.send_sip_message(
            cancel,
            context["target_host"],
            context["target_port"],
            outbound_proxy=context.get("outbound_proxy", ""),
            transport=context.get("transport", "UDP"),
            tls_verify=context.get("tls_verify", True),
        )
        self.log_sys_event("Sent CANCEL for the pending outbound call", category="DIAL")
        self._notify_call_state("TERMINATED", {"reason": "Call cancelled by user"})
        return True

    def _send_bye(self, dialog: Dict[str, Any], reason: str = "active call") -> bool:
        if not dialog:
            return False
        dialog["cseq"] = int(dialog.get("cseq", 0)) + 1
        bye = self._build_dialog_request("BYE", dialog, dialog["cseq"])
        self.send_sip_message(
            bye,
            dialog["target_host"],
            dialog["target_port"],
            outbound_proxy=dialog.get("outbound_proxy", ""),
            transport=dialog.get("transport", "UDP"),
            tls_verify=dialog.get("tls_verify", True),
        )
        self.log_sys_event(f"Sent BYE for {reason}, CSeq={dialog['cseq']}", category="DIAL")
        return True

    def send_session_refresh(self) -> bool:
        dialog = self.outbound_dialog
        if self.call_state != "CONNECTED" or not dialog:
            return False
        refresh_seconds = int(dialog.get("session_refresh_seconds", 0))
        if refresh_seconds <= 0:
            return False
        dialog["cseq"] = int(dialog.get("cseq", 1)) + 1
        update = self._build_dialog_request(
            "UPDATE", dialog, dialog["cseq"], max(90, refresh_seconds * 2)
        )
        self.send_sip_message(
            update,
            dialog["target_host"],
            dialog["target_port"],
            outbound_proxy=dialog.get("outbound_proxy", ""),
            transport=dialog.get("transport", "UDP"),
            tls_verify=dialog.get("tls_verify", True),
        )
        self.log_sys_event(
            f"Sent call session refresh (UPDATE), CSeq={dialog['cseq']}", category="DIAL"
        )
        return True

    def hangup_call(self, target_host: str = "", target_port: int = 0) -> bool:
        if self.call_state in ("DIALING", "RINGING"):
            return self.cancel_outbound_call()
        dialog = self.outbound_dialog or (
            self.active_dialog if self.active_dialog.get("direction") == "incoming" else {}
        )
        if self.call_state == "CONNECTED" and dialog:
            self._send_bye(dialog)
        elif self.call_state == "CONNECTED":
            self.log_sys_event(
                "Cannot send BYE: active dialog routing information is missing",
                category="DIAL",
                level="ERROR",
            )
        self._notify_call_state("TERMINATED", {"reason": "Call ended by user"})
        self.outbound_dialog = {}
        self.active_dialog = {}
        self.discard_media_keys()
        return True

    def discard_media_keys(self) -> None:
        """Remove ephemeral SDES key material while preserving dialog routing."""
        for context in (self.outbound_invite_context, self.outbound_dialog, self.active_dialog):
            context.pop("srtp_local_key", None)
            if context.get("invite_packet"):
                context["invite_packet"] = self._redact_media_keys(context["invite_packet"])
            request = context.get("req_msg")
            if request:
                request.raw = self._redact_media_keys(request.raw)
                request.body = self._redact_media_keys(request.body)
