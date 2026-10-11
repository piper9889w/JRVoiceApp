import threading
import time
import uuid
from typing import Dict, List, Any, Callable, Optional
from jrvoiceapp.telephony.sipapp_core.sip_engine import SIPEngine, SIPLogEntry
from jrvoiceapp.telephony.sipapp_core.sip_resolver import resolve_sip_target


class RegistrationStatus:
    UNREGISTERED = "UNREGISTERED"
    REGISTERING = "REGISTERING"
    REGISTERED = "REGISTERED"
    FAILED = "FAILED"


class RegistrationManager:
    """
    Manages multiple SIP registrations concurrently.
    Runs background threads for each configured SIP auth account.
    """

    def __init__(self, sip_engine: SIPEngine):
        self.sip_engine = sip_engine
        self.account_states: Dict[str, Dict[str, Any]] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.running = False
        self.status_callbacks: List[Callable[[str, str, str], None]] = []
        self.account_generations: Dict[str, int] = {}

        self.sip_engine.add_log_callback(self._on_sip_log)

    def add_status_callback(self, callback: Callable[[str, str, str], None]):
        self.status_callbacks.append(callback)

    def _notify_status(self, account_id: str, status: str, detail: str = ""):
        if account_id in self.account_states:
            self.account_states[account_id]["status"] = status
            self.account_states[account_id]["detail"] = detail

        self.sip_engine.log_sys_event(
            f"Registration [{account_id}]: {status} - {detail}", category="REG"
        )

        for cb in self.status_callbacks:
            try:
                cb(account_id, status, detail)
            except Exception as e:
                print(f"[RegistrationManager] Callback error: {e}")

    def start_all(self, accounts: List[Dict[str, Any]]):
        self.running = True
        for acc in accounts:
            if acc.get("enabled", True) and acc.get("register_on_startup", True):
                self.register_account(acc)

    def stop_all(self):
        self.running = False

    def register_account(self, account: Dict[str, Any]):
        acc_id = account.get("id", account.get("username", "account"))
        generation = self.account_generations.get(acc_id, 0) + 1
        self.account_generations[acc_id] = generation
        self.running = True
        self.account_states[acc_id] = {
            "account": account,
            "status": RegistrationStatus.REGISTERING,
            "detail": "Sending REGISTER...",
            "last_cseq": 1,
            "call_id": "",
            "response_event": threading.Event(),
            "attempt": 0,
            "challenge_count": 0,
            "terminal_failure": False,
        }
        self._notify_status(acc_id, RegistrationStatus.REGISTERING, "Initiating registration...")

        t = threading.Thread(
            target=self._registration_loop, args=(account, generation), daemon=True
        )
        self.threads[acc_id] = t
        t.start()

    def unregister_account(self, account_id: str):
        self.account_generations[account_id] = self.account_generations.get(account_id, 0) + 1
        state = self.account_states.get(account_id, {})
        account = state.get("account", {})
        username = account.get("username")
        if username in self.sip_engine.registered_users:
            self.sip_engine.registered_users.remove(username)
        if account_id in self.account_states:
            self._notify_status(account_id, RegistrationStatus.UNREGISTERED, "Registration stopped")

    def _registration_loop(self, account: Dict[str, Any], generation: int):
        acc_id = account.get("id", account.get("username", "account"))
        domain = account["domain"]
        configured_port = int(account.get("port", 5060))
        transport = account.get("transport", "UDP").upper()
        expires = int(account.get("expires", 3600))
        outbound_proxy = account.get("outbound_proxy", "")
        retry_interval = max(5, int(account.get("retry_interval", 30)))
        transaction_timeout = 10

        cseq = 1
        attempt = 0
        start_time = time.time()
        while self.running and self.account_generations.get(acc_id) == generation:
            established_account = bool(account.get("has_registered_once", False))
            attempt += 1
            target_host, target_port, discovery = resolve_sip_target(
                domain, configured_port, transport
            )
            self.account_states[acc_id]["resolved_target"] = f"{target_host}:{target_port}"
            self.account_states[acc_id]["discovery"] = discovery
            self.account_states[acc_id]["attempt"] = attempt
            self.account_states[acc_id]["challenge_count"] = 0
            self.account_states[acc_id]["terminal_failure"] = False
            response_event = self.account_states[acc_id]["response_event"]
            response_event.clear()

            max_initial_attempts = 3
            if attempt <= max_initial_attempts:
                attempt_label = f"attempt {attempt} of {max_initial_attempts}"
            else:
                elapsed_min = int((time.time() - start_time) / 60)
                attempt_label = f"retry attempt {attempt} ({elapsed_min}m elapsed)"

            self._notify_status(
                acc_id, RegistrationStatus.REGISTERING, f"{attempt_label}: {discovery}"
            )
            raw_reg, call_id = self.sip_engine.build_register(account, cseq=cseq, expires=expires)
            self.account_states[acc_id]["call_id"] = call_id
            self.account_states[acc_id]["last_cseq"] = cseq
            self.sip_engine.log_sys_event(
                f"REGISTER [{acc_id}] sending {attempt_label} to {target_host}:{target_port} over {transport}",
                category="REG",
            )
            sent = self.sip_engine.send_sip_message(
                raw_reg,
                target_host,
                target_port,
                outbound_proxy=outbound_proxy,
                transport=transport,
                tls_verify=account.get("tls_verify_cert", True),
            )
            if sent is False:
                self._notify_status(
                    acc_id,
                    RegistrationStatus.FAILED,
                    self.sip_engine.last_send_error or "SIP transport send failed",
                )
                response_event.set()
            response_event.wait(transaction_timeout)
            if not self.running or self.account_generations.get(acc_id) != generation:
                break
            curr_status = self.account_states[acc_id].get("status")
            if curr_status == RegistrationStatus.REGISTERED:
                if (
                    account.get("username")
                    and account.get("username") not in self.sip_engine.registered_users
                ):
                    self.sip_engine.registered_users.append(account.get("username"))
                account["has_registered_once"] = True
                attempt = 0
                start_time = time.time()
                refresh_sleep = max(10, expires - 30)
                self.sip_engine.log_sys_event(
                    f"REGISTER [{acc_id}] successful; refresh scheduled in {refresh_sleep} seconds",
                    category="REG",
                )
                self._interruptible_wait(acc_id, generation, refresh_sleep)
                cseq += 1
            else:
                if curr_status != RegistrationStatus.FAILED:
                    failure_detail = f"No REGISTER response within {transaction_timeout} seconds"
                    self._notify_status(acc_id, RegistrationStatus.FAILED, failure_detail)
                else:
                    failure_detail = self.account_states[acc_id].get(
                        "detail", "Registration failed"
                    )

                if not established_account and attempt >= 3:
                    terminal_detail = (
                        f"HALTED: New account failed after 3 attempts. {failure_detail}"
                    )
                    self.account_states[acc_id]["terminal_failure"] = True
                    self._notify_status(acc_id, RegistrationStatus.FAILED, terminal_detail)
                    self.sip_engine.log_sys_event(
                        f"REGISTER [{acc_id}] halted after 3 failed attempts (new account)",
                        category="REG",
                        level="ERROR",
                    )
                    break
                elif established_account and (time.time() - start_time) > 300:
                    terminal_detail = (
                        f"HALTED: Established account retry limit (5m) reached. {failure_detail}"
                    )
                    self.account_states[acc_id]["terminal_failure"] = True
                    self._notify_status(acc_id, RegistrationStatus.FAILED, terminal_detail)
                    self.sip_engine.log_sys_event(
                        f"REGISTER [{acc_id}] halted after 5 minutes of retries (established account)",
                        category="REG",
                        level="ERROR",
                    )
                    break
                else:
                    self.sip_engine.log_sys_event(
                        f"REGISTER [{acc_id}] failed: {failure_detail}; retrying in 30s...",
                        category="REG",
                        level="WARN",
                    )
                    self._interruptible_wait(acc_id, generation, 30)
                    cseq += 1

    def _interruptible_wait(self, account_id: str, generation: int, seconds: int):
        deadline = time.time() + seconds
        while (
            self.running
            and self.account_generations.get(account_id) == generation
            and time.time() < deadline
        ):
            time.sleep(min(0.25, max(0, deadline - time.time())))

    def _on_sip_log(self, entry: SIPLogEntry):
        if entry.direction not in ("RX", "RECV") or not entry.message or entry.message.is_request:
            return

        cseq_hdr = entry.message.get_header("CSeq")
        if "REGISTER" not in cseq_hdr:
            return

        call_id = entry.message.get_header("Call-ID")

        matching_acc_id = ""
        for acc_id, state in self.account_states.items():
            if state.get("call_id") == call_id:
                matching_acc_id = acc_id
                break

        if not matching_acc_id:
            self.sip_engine.log_sys_event(
                f"Unmatched REGISTER response: {entry.summary} Call-ID={call_id}",
                category="REG",
                level="WARN",
            )
            return

        state = self.account_states[matching_acc_id]
        account = state["account"]
        status_code = entry.message.status_code

        if status_code == 200:
            account["has_registered_once"] = True
            self._notify_status(
                matching_acc_id,
                RegistrationStatus.REGISTERED,
                f"200 OK - Registered to {account['domain']}",
            )
            state["response_event"].set()

        elif status_code in (401, 407):
            if state.get("challenge_count", 0) >= 1:
                self._notify_status(
                    matching_acc_id,
                    RegistrationStatus.FAILED,
                    f"{status_code} Digest authentication rejected by server",
                )
                self.sip_engine.log_sys_event(
                    f"REGISTER [{matching_acc_id}] server rejected authenticated request with {status_code}",
                    category="REG",
                    level="ERROR",
                )
                state["response_event"].set()
                return
            state["challenge_count"] = state.get("challenge_count", 0) + 1
            auth_header_name = "WWW-Authenticate" if status_code == 401 else "Proxy-Authenticate"
            challenge = entry.message.get_header(auth_header_name)

            if challenge:
                parsed_challenge = self.sip_engine.parse_auth_challenge(challenge)
                realm = parsed_challenge.get("realm", account["domain"])
                nonce = parsed_challenge.get("nonce", "")
                qop_options = parsed_challenge.get("qop", "")
                qop = "auth" if "auth" in qop_options.lower() else ""
                opaque = parsed_challenge.get("opaque", "")
                algorithm = parsed_challenge.get("algorithm", "MD5").upper()

                if not nonce:
                    self._notify_status(
                        matching_acc_id,
                        RegistrationStatus.FAILED,
                        "Digest challenge did not include a nonce",
                    )
                    state["response_event"].set()
                    return
                if algorithm not in ("MD5", ""):
                    self._notify_status(
                        matching_acc_id,
                        RegistrationStatus.FAILED,
                        f"Unsupported digest algorithm: {algorithm}",
                    )
                    state["response_event"].set()
                    return

                username = account["username"]
                auth_user = account.get("auth_user", username) or username
                password = account["password"]
                uri = f"sip:{account['domain']}"
                method = "REGISTER"

                cnonce = uuid.uuid4().hex[:16]
                nc = "00000001"
                digest_resp = self.sip_engine.calculate_digest_response(
                    auth_user, password, realm, nonce, uri, method, qop=qop, nc=nc, cnonce=cnonce
                )

                if qop:
                    auth_val = (
                        f'Digest username="{auth_user}", realm="{realm}", nonce="{nonce}", '
                        f'uri="{uri}", response="{digest_resp}", qop={qop}, nc={nc}, cnonce="{cnonce}"'
                    )
                else:
                    auth_val = (
                        f'Digest username="{auth_user}", realm="{realm}", nonce="{nonce}", '
                        f'uri="{uri}", response="{digest_resp}"'
                    )
                if opaque:
                    auth_val += f', opaque="{opaque}"'
                auth_val += ", algorithm=MD5"

                next_cseq = state.get("last_cseq", 1) + 1
                state["last_cseq"] = next_cseq

                authed_reg, authenticated_call_id = self.sip_engine.build_register(
                    account,
                    cseq=next_cseq,
                    auth_header=auth_val,
                    expires=account.get("expires", 3600),
                    call_id=state.get("call_id", ""),
                    auth_header_name="Proxy-Authorization"
                    if status_code == 407
                    else "Authorization",
                )
                state["call_id"] = authenticated_call_id
                target_host, target_port, _ = resolve_sip_target(
                    account["domain"],
                    int(account.get("port", 5060)),
                    account.get("transport", "UDP"),
                )
                self._notify_status(
                    matching_acc_id,
                    RegistrationStatus.REGISTERING,
                    "Sending Authenticated REGISTER...",
                )
                self.sip_engine.log_sys_event(
                    f"REGISTER [{matching_acc_id}] accepted {status_code} digest challenge; sending authenticated request",
                    category="REG",
                )
                self.sip_engine.send_sip_message(
                    authed_reg,
                    target_host,
                    target_port,
                    outbound_proxy=account.get("outbound_proxy", ""),
                    transport=account.get("transport", "UDP"),
                    tls_verify=account.get("tls_verify_cert", True),
                )
            else:
                self._notify_status(
                    matching_acc_id,
                    RegistrationStatus.FAILED,
                    f"{status_code} response had no digest challenge",
                )
                state["response_event"].set()

        elif status_code >= 400:
            self._notify_status(
                matching_acc_id,
                RegistrationStatus.FAILED,
                f"{status_code} {entry.message.reason_phrase}",
            )
            state["response_event"].set()
