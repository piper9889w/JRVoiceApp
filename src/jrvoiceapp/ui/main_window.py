"""The desktop shell shown before protocol engines are connected."""

from keyring.errors import KeyringError
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from jrvoiceapp.accounts import AccountStore
from jrvoiceapp.models import SAMPLE_RECENT_CALLS
from jrvoiceapp.records import CallRecord, RecordsStore
from jrvoiceapp.telephony.controller import TelephonyController
from jrvoiceapp.telephony.sipapp import SipAppProvider
from jrvoiceapp.ui.account_dialog import AccountDialog
from jrvoiceapp.ui.diagnostics_dialog import DiagnosticsDialog
from jrvoiceapp.ui.emergency_dialog import EmergencyLocationDialog
from jrvoiceapp.ui.incoming_call import IncomingCallDialog


class MainWindow(QMainWindow):
    provider_event = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self.provider_event.connect(self._on_provider_event)
        self.setWindowTitle("Global Voice")
        self.resize(1280, 790)
        self.setMinimumSize(780, 600)
        self.store = AccountStore()
        self.accounts = self.store.load()
        self.user_emergency_settings = self.store.load_user_emergency_settings()
        self.audio_settings = self.store.load_audio_settings()
        self.default_account_id = self.store.load_default_account_id()
        self.records_store = RecordsStore()
        self.contacts, self.call_history = self.records_store.load()
        self.controller = TelephonyController()
        self.provider = None
        self.active_call_details: dict[str, str] = {}
        self.pending_dial_destination = ""
        self.dial_input = QLineEdit()
        self.dial_input.setAccessibleName("Dial a name or number")
        self.dial_input.setPlaceholderText("Name or number")

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.sidebar = self._sidebar()
        layout.addWidget(self.sidebar)
        layout.addWidget(self._dialer(), 1)
        self.right_column = self._right_column()
        layout.addWidget(self.right_column)
        self.setCentralWidget(root)
        self._quitting = False
        self._build_tray()
        self._refresh_account_label()
        self.active_line_timer = QTimer(self)
        self.active_line_timer.timeout.connect(self._refresh_active_line)
        self.active_line_timer.start(1000)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon), self
        )
        self.tray.setToolTip("Global Voice")
        menu = QMenu(self)
        show = QAction("Show Global Voice", self)
        show.triggered.connect(self.restore_window)
        test = QAction("Test incoming call", self)
        test.triggered.connect(self.show_incoming_call)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addActions([show, test])
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self.restore_window()
                if reason == QSystemTrayIcon.ActivationReason.Trigger
                else None
            )
        )
        self.tray.show()

    def _sidebar(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 28, 18, 24)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        title = QLabel("Global")
        title.setObjectName("brand")
        voice = QLabel("Voice")
        voice.setObjectName("brandAccent")
        brand.addWidget(title)
        brand.addWidget(voice)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(24)
        self.account_label = QLabel()
        self.account_label.setAccessibleName("Current account")
        layout.addWidget(self.account_label)
        self.registration_status = QLabel()
        self.registration_status.setAccessibleName("Registration status")
        layout.addWidget(self.registration_status)
        layout.addSpacing(26)

        for label in ("☎  Phone", "♙  Contacts", "◷  Recent calls", "✉  Voicemail", "▤  Messages"):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setChecked(label.endswith("Phone"))
            if label.endswith("Contacts"):
                button.clicked.connect(self.manage_contacts)
            if label.endswith("Recent calls"):
                button.clicked.connect(self.show_history)
            layout.addWidget(button)
        settings = QPushButton("⚙  Settings")
        settings.setObjectName("nav")
        settings.clicked.connect(self.open_account_dialog)
        settings.setAccessibleName("Account settings")
        layout.addWidget(settings)
        routing = QPushButton("⇄  Default account")
        routing.setObjectName("nav")
        routing.clicked.connect(self.choose_default_account)
        layout.addWidget(routing)
        diagnostics = QPushButton("⌁  Diagnostics")
        diagnostics.setObjectName("nav")
        diagnostics.clicked.connect(self.open_diagnostics)
        diagnostics.setAccessibleName("Call diagnostics")
        layout.addWidget(diagnostics)
        self.register_button = QPushButton("↻  Register / retry")
        self.register_button.setObjectName("nav")
        self.register_button.setAccessibleName("Register or retry account")
        self.register_button.clicked.connect(self.register_or_retry)
        layout.addWidget(self.register_button)
        layout.addStretch()

        secure = QFrame()
        secure.setObjectName("panel")
        secure_layout = QVBoxLayout(secure)
        secure_layout.addWidget(QLabel("▣  Connection security"))
        self.connection_security = QLabel("No active account")
        self.connection_security.setObjectName("subtle")
        secure_layout.addWidget(self.connection_security)
        layout.addWidget(secure)
        return panel

    def _dialer(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(54, 40, 54, 30)
        layout.setSpacing(18)
        identity = QHBoxLayout()
        avatar = QLabel("♙")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(76, 76)
        avatar.setStyleSheet("background:#20334c;border-radius:38px;font-size:38px;")
        identity.addWidget(avatar)
        words = QVBoxLayout()
        heading = QLabel("Extension 1001")
        heading.setObjectName("heading")
        words.addWidget(heading)
        self.identity_registration_status = QLabel()
        self.identity_registration_status.setAccessibleName("Registration status")
        words.addWidget(self.identity_registration_status)
        identity.addLayout(words)
        identity.addStretch()
        layout.addLayout(identity)
        layout.addSpacing(12)
        layout.addWidget(self.dial_input)

        grid = QGridLayout()
        grid.setHorizontalSpacing(26)
        grid.setVerticalSpacing(12)
        for index, value in enumerate(
            (
                "1",
                "2\nABC",
                "3\nDEF",
                "4\nGHI",
                "5\nJKL",
                "6\nMNO",
                "7\nPQRS",
                "8\nTUV",
                "9\nWXYZ",
                "*",
                "0\n+",
                "#",
            )
        ):
            button = QPushButton(value)
            button.setObjectName("dial")
            button.setAccessibleName("Dial " + value[0])
            button.clicked.connect(
                lambda _checked=False, digit=value[0]: self.dial_input.insert(digit)
            )
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addStretch()
        actions = QHBoxLayout()
        actions.addWidget(QPushButton("▣  Video"))
        self.call_button = QPushButton("☎")
        self.call_button.setObjectName("call")
        self.call_button.setAccessibleName("Call")
        self.call_button.setToolTip(
            "Connects the configured account, then dials the entered destination."
        )
        self.call_button.clicked.connect(self.place_call)
        actions.addWidget(self.call_button)
        devices = QPushButton("◉  Devices")
        devices.clicked.connect(self.configure_audio_devices)
        actions.addWidget(devices)
        layout.addLayout(actions)
        return panel

    def _right_column(self) -> QWidget:
        column = QWidget()
        column.setMinimumWidth(300)
        column.setMaximumWidth(350)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 18, 0)
        layout.setSpacing(16)
        layout.addWidget(self._recents(), 3)
        layout.addWidget(self._active_line(), 2)
        return column

    def _recents(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        title = QHBoxLayout()
        label = QLabel("Recent calls")
        label.setObjectName("section")
        title.addWidget(label)
        title.addStretch()
        title.addWidget(QLabel("See all  ›"))
        layout.addLayout(title)
        records = self.call_history[:5]
        for call in records or SAMPLE_RECENT_CALLS:
            if isinstance(call, CallRecord):
                caller = next(
                    (item.name for item in self.contacts if item.address == call.address),
                    call.address,
                )
                initials = "".join(word[0] for word in caller.split()[:2]).upper() or "?"
                direction, when, accent = (
                    call.direction,
                    call.occurred_at[:16].replace("T", " "),
                    "#3478f6",
                )
            else:
                caller, initials, direction, when, accent = (
                    call.caller,
                    call.initials,
                    call.direction,
                    call.time_label,
                    call.accent,
                )
            row = QHBoxLayout()
            avatar = QLabel(initials)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFixedSize(42, 42)
            avatar.setStyleSheet(f"background:{accent};border-radius:21px;font-weight:700;")
            row.addWidget(avatar)
            info = QVBoxLayout()
            info.addWidget(QLabel(caller))
            detail = QLabel(direction)
            detail.setObjectName("subtle")
            info.addWidget(detail)
            row.addLayout(info, 1)
            when_label = QLabel(when)
            when_label.setObjectName("subtle")
            row.addWidget(when_label)
            layout.addLayout(row)
        return panel

    def _active_line(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel("Active line")
        title.setObjectName("section")
        layout.addWidget(title)
        self.active_line_name = QLabel("No active call")
        self.active_line_name.setObjectName("heading")
        self.active_line_name.setWordWrap(True)
        layout.addWidget(self.active_line_name)
        self.active_line_status = QLabel("No active call")
        self.active_line_status.setObjectName("online")
        self.active_line_status.setWordWrap(True)
        layout.addWidget(self.active_line_status)
        controls = QGridLayout()
        for index, label in enumerate(
            ("♩\nMute", "⠿\nKeypad", "◖\nSpeaker", "⇄\nTransfer", "Ⅱ\nHold", "☎\nEnd call")
        ):
            button = QPushButton(label)
            button.setAccessibleName(label.replace("\n", " "))
            if label.endswith("End call"):
                button.setObjectName("end")
                button.clicked.connect(self.end_call)
            elif label.endswith("Mute"):
                button.setCheckable(True)
                button.clicked.connect(self.toggle_mute)
            elif label.endswith("Keypad"):
                button.clicked.connect(self.send_dtmf)
            elif label.endswith("Speaker"):
                button.clicked.connect(self.change_speaker_volume)
            elif label.endswith("Transfer"):
                button.clicked.connect(self.transfer_call)
            elif label.endswith("Hold"):
                button.setCheckable(True)
                button.clicked.connect(self.toggle_hold)
            controls.addWidget(button, index // 3, index % 3)
        for column in range(3):
            controls.setColumnStretch(column, 1)
        layout.addLayout(controls)
        return panel

    def resizeEvent(self, event) -> None:
        self.right_column.setVisible(self.width() >= 980)
        self.sidebar.setVisible(self.width() >= 820)
        super().resizeEvent(event)

    def open_account_dialog(self) -> None:
        account = self.accounts[0] if self.accounts else None
        credentials = (
            self.store.provisioning_credentials_for(account.identifier) if account else ("", "")
        )
        dialog = AccountDialog(account, self.user_emergency_settings, credentials, self)
        if dialog.exec() != AccountDialog.DialogCode.Accepted:
            return
        result = dialog.result_account()
        try:
            if self.accounts:
                self.accounts[0] = result
            else:
                self.accounts.append(result)
            self.store.save(self.accounts)
            self.user_emergency_settings = dialog.user_emergency_settings
            self.store.save_user_emergency_settings(self.user_emergency_settings)
            if dialog.password_input.text():
                self.store.save_password(result.identifier, dialog.password_input.text())
            if result.provisioning_server:
                self.store.save_provisioning_credentials(
                    result.identifier, *dialog.provisioning_credentials
                )
        except (KeyringError, OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not save account", str(error))
            return
        self._refresh_account_label()

    def open_diagnostics(self) -> None:
        if self.provider and hasattr(self.provider, "diagnostics"):
            dialog = DiagnosticsDialog(self.provider.diagnostics, self)
        else:
            dialog = DiagnosticsDialog(
                lambda: {"provider_state": "No SIP provider is connected."}, self
            )
        dialog.exec()

    def _refresh_account_label(self) -> None:
        if self.accounts:
            account = self.accounts[0]
            self.account_label.setText(f"{account.label}\n    {account.username}")
            if account.connection_kind.value == "SIP":
                if account.sip_transport.value == "TLS":
                    self.connection_security.setText("SIP signaling: TLS configured")
                    self.connection_security.setObjectName("subtle")
                else:
                    self.connection_security.setText(
                        f"SIP signaling: {account.sip_transport.value} (not encrypted)"
                    )
                    self.connection_security.setObjectName("subtle")
            else:
                self.connection_security.setText("WebRTC signaling: WSS configured")
                self.connection_security.setObjectName("subtle")
            self.connection_security.style().unpolish(self.connection_security)
            self.connection_security.style().polish(self.connection_security)
        else:
            self.account_label.setText("No account configured")
            self.connection_security.setText("No active account")
        self._refresh_registration_status()

    def _refresh_registration_status(self) -> None:
        """Only call an account online after its provider confirms registration."""
        if not self.accounts:
            text, style = "○  No account configured", "subtle"
        elif self.provider is None or self.provider.state.value == "idle":
            text, style = "○  Not registered", "subtle"
        elif self.provider.state.value == "registered":
            text, style = "●  Online — registered", "online"
        elif self.provider.state.value == "error":
            text, style = "●  Registration failed — retry", "offline"
        else:
            text, style = "◌  Registering…", "subtle"
        self.registration_status.setText(text)
        self.registration_status.setObjectName(style)
        self.identity_registration_status.setText(text)
        self.identity_registration_status.setObjectName(style)
        for label in (self.registration_status, self.identity_registration_status):
            label.style().unpolish(label)
            label.style().polish(label)

    def _start_provider_for(self, destination: str = "") -> None:
        account = self.controller.route_outbound(
            self.accounts, destination, self.default_account_id
        )
        password = self.store.password_for(account.identifier)
        self.provider = self.controller.provider_for(account, password)
        if isinstance(self.provider, SipAppProvider):
            self.provider.audio.input_device = self.audio_settings["input"]
            self.provider.audio.output_device = self.audio_settings["output"]
        # SIP registration runs on a worker; Qt queues this signal safely onto
        # the window's UI thread before labels, dialogs, or history are changed.
        self.provider.add_event_callback(
            lambda event, details: self.provider_event.emit(event, details)
        )
        self.provider.start()

    def register_or_retry(self) -> None:
        if not self.accounts:
            self.open_account_dialog()
            return
        try:
            if self.provider is None:
                self._start_provider_for()
            elif isinstance(self.provider, SipAppProvider):
                self.provider.retry_registration()
            else:
                self.provider.stop()
                self.provider = None
                self._start_provider_for()
            self._refresh_registration_status()
            self.statusBar().showMessage("Registration started.", 5000)
        except (KeyringError, OSError, RuntimeError, ValueError) as error:
            self._refresh_registration_status()
            self.statusBar().showMessage(str(error), 8000)

    def place_call(self) -> None:
        if not self.accounts:
            self.open_account_dialog()
            return
        try:
            started_now = False
            if self.provider is None:
                self._start_provider_for(self.dial_input.text())
                started_now = True
            if (
                self._is_emergency_dial(self.dial_input.text())
                and not self._confirm_emergency_location()
            ):
                return
            if self.provider.state.value != "registered":
                self.pending_dial_destination = self.dial_input.text().strip()
                if isinstance(self.provider, SipAppProvider) and not started_now:
                    self.provider.retry_registration()
                self._refresh_registration_status()
                self.statusBar().showMessage(
                    "Registering account; the call will start after registration succeeds.", 8000
                )
                return
            self.provider.dial(self.dial_input.text())
            self._record_call(self.dial_input.text(), "Outgoing", "Dialing")
        except (KeyringError, OSError, RuntimeError, ValueError) as error:
            self.statusBar().showMessage(str(error), 8000)

    def end_call(self) -> None:
        if self.provider and isinstance(self.provider, SipAppProvider):
            self.provider.hangup()

    def toggle_mute(self, muted: bool) -> None:
        if isinstance(self.provider, SipAppProvider):
            self.provider.set_muted(muted)
            self.statusBar().showMessage(
                "Microphone muted." if muted else "Microphone unmuted.", 3000
            )

    def send_dtmf(self) -> None:
        digit, accepted = QInputDialog.getText(self, "Send DTMF", "Digit (0–9, *, #, A–D):")
        if accepted and digit:
            try:
                if isinstance(self.provider, SipAppProvider):
                    self.provider.send_dtmf(digit.upper())
            except (RuntimeError, ValueError) as error:
                self.statusBar().showMessage(str(error), 6000)

    def change_speaker_volume(self) -> None:
        volume, accepted = QInputDialog.getInt(self, "Speaker volume", "Volume:", 80, 0, 100)
        if accepted and isinstance(self.provider, SipAppProvider):
            self.provider.set_speaker_volume(volume)

    def toggle_hold(self, held: bool) -> None:
        try:
            if isinstance(self.provider, SipAppProvider):
                self.provider.set_hold(held)
        except RuntimeError as error:
            self.statusBar().showMessage(str(error), 6000)

    def transfer_call(self) -> None:
        destination, accepted = QInputDialog.getText(self, "Transfer call", "Destination:")
        if accepted and destination:
            try:
                if isinstance(self.provider, SipAppProvider):
                    self.provider.transfer(destination)
            except RuntimeError as error:
                self.statusBar().showMessage(str(error), 6000)

    def configure_audio_devices(self) -> None:
        if not isinstance(self.provider, SipAppProvider):
            self.statusBar().showMessage(
                "Connect the SIP account before selecting call devices.", 5000
            )
            return
        devices = self.provider.available_audio_devices()
        inputs = devices["inputs"]
        outputs = devices["outputs"]
        input_device, accepted = QInputDialog.getItem(
            self, "Microphone", "Input device:", inputs, editable=False
        )
        if not accepted:
            return
        output_device, accepted = QInputDialog.getItem(
            self, "Speaker", "Output device:", outputs, editable=False
        )
        if accepted:
            self.provider.audio.input_device = input_device
            self.provider.audio.output_device = output_device
            self.audio_settings = {"input": input_device, "output": output_device}
            self.store.save_audio_settings(input_device, output_device)
            self.statusBar().showMessage(
                "Call devices will be used on the next media connection.", 6000
            )

    def _on_provider_event(self, event: str, details: dict[str, str]) -> None:
        if event == "registration":
            self.statusBar().showMessage(details.get("detail", "SIP registration update"), 8000)
            self._refresh_registration_status()
            if details.get("status") == "REGISTERED":
                self._prompt_emergency_location_on_registration()
                if self.pending_dial_destination and self.provider:
                    destination = self.pending_dial_destination
                    self.pending_dial_destination = ""
                    try:
                        self.provider.dial(destination)
                        self._record_call(destination, "Outgoing", "Dialing")
                    except (OSError, RuntimeError, ValueError) as error:
                        self.statusBar().showMessage(str(error), 8000)
            return
        if event == "diagnostic":
            self.statusBar().showMessage(details.get("summary", "SIP diagnostic"), 5000)
            return
        if event == "call-state" and details.get("state") == "INCOMING_CALL":
            caller = details.get("caller", "Unknown caller")
            self._record_call(details.get("from", caller), "Incoming", "Ringing")
            self.show_incoming_call(caller, details.get("from", ""), live=True)
            return
        if event == "call-state":
            state = details.get("state", "Call update")
            if state == "DIALING":
                self.active_call_details = details
            elif state == "CONNECTED":
                self.active_call_details.update(details)
            elif state == "TERMINATED":
                self.active_call_details = {}
                self.active_line_name.setText("No active call")
                self.active_line_status.setText("No active call")
            self._refresh_active_line()
            if details.get("state") in {"CONNECTED", "TERMINATED"} and self.accounts:
                self.call_history = self.records_store.update_latest(
                    self.contacts,
                    self.call_history,
                    self.accounts[0].identifier,
                    details["state"].title(),
                )
            self.statusBar().showMessage(details.get("state", "Call update"), 5000)
        if event == "media":
            self._refresh_active_line()

    def _refresh_active_line(self) -> None:
        """Render live, non-secret SIP call and media state in the active-line card."""
        if not isinstance(self.provider, SipAppProvider) or not self.active_call_details:
            return
        state = self.active_call_details.get("state", "Call update")
        if state not in {"CONNECTED", "HELD"}:
            self.active_line_status.setText(state)
            return
        from_header = self.active_call_details.get("from", "")
        request_uri = self.active_call_details.get("request_uri") or self.active_call_details.get(
            "target", ""
        )
        self.active_line_name.setText(from_header or request_uri or "Active call")
        report = self.provider.diagnostics()
        destination = request_uri or "—"
        signaling = report.get("signaling_destination", "—")
        packets = report.get("rtp_packets", "TX 0 / RX 0")
        packet_rate = report.get("rtp_packet_rate", "TX 0/s / RX 0/s")
        rtp_local = report.get("rtp_local", "—")
        rtp_remote = report.get("rtp_remote", "—")
        rtp_bound = report.get("rtp_bound", "—")
        endpoint_match = report.get("rtp_endpoint_match", "—")
        self.active_line_status.setText(
            f"{state}\nRURI: {destination}\nSignaling: {signaling}\n"
            f"RTP: {rtp_local} → {rtp_remote}\nBound: {rtp_bound} (SDP match: {endpoint_match})\n"
            f"Packets: {packet_rate} ({packets})"
        )

    def manage_contacts(self) -> None:
        choices = ["Add", "Dial", "Edit", "Delete"]
        action, accepted = QInputDialog.getItem(
            self, "Contacts", "Action:", choices, editable=False
        )
        if not accepted:
            return
        if action != "Add":
            names = [f"{item.name} — {item.address}" for item in self.contacts]
            selected, accepted = QInputDialog.getItem(
                self, "Contacts", "Contact:", names, editable=False
            )
            if not accepted:
                return
            index = names.index(selected)
            if action == "Dial":
                self.dial_input.setText(self.contacts[index].address)
                return
            if action == "Delete":
                self.contacts.pop(index)
                self.records_store.save(self.contacts, self.call_history)
                return
        name, accepted = QInputDialog.getText(
            self,
            "Add contact" if action == "Add" else "Edit contact",
            "Name:",
            text="" if action == "Add" else self.contacts[index].name,
        )
        if not accepted or not name.strip():
            return
        address, accepted = QInputDialog.getText(
            self,
            "Contact",
            "Number or SIP address:",
            text="" if action == "Add" else self.contacts[index].address,
        )
        if not accepted or not address.strip():
            return
        from jrvoiceapp.records import Contact

        self.contacts = (
            [*self.contacts, Contact(name.strip(), address.strip())]
            if action == "Add"
            else [
                *self.contacts[:index],
                Contact(name.strip(), address.strip()),
                *self.contacts[index + 1 :],
            ]
        )
        self.records_store.save(self.contacts, self.call_history)
        self.dial_input.setText(address.strip())

    def show_history(self) -> None:
        QMessageBox.information(
            self,
            "Call history",
            "\n".join(
                f"{call.occurred_at[:16]}  {call.direction}  {call.address}  {call.status}"
                for call in self.call_history
            )
            or "No calls recorded yet.",
        )

    def choose_default_account(self) -> None:
        labels = [f"{account.label} — {account.username}" for account in self.accounts]
        choice, accepted = QInputDialog.getItem(
            self, "Default outbound account", "Account:", labels, editable=False
        )
        if accepted:
            self.default_account_id = self.accounts[labels.index(choice)].identifier
            self.store.save_default_account_id(self.default_account_id)

    def _record_call(self, address: str, direction: str, status: str) -> None:
        if not address.strip() or not self.accounts:
            return
        self.call_history = self.records_store.add_call(
            self.contacts,
            self.call_history,
            CallRecord(
                address.strip(),
                direction,
                status,
                self.records_store.now(),
                self.accounts[0].identifier,
            ),
        )

    def show_incoming_call(
        self, caller: str = "Marcus Chen", number: str = "Extension 1002", live: bool = False
    ) -> None:
        self.restore_window()
        self.tray.showMessage(
            "Incoming call", f"{caller} is calling", QSystemTrayIcon.MessageIcon.Information, 8000
        )
        dialog = IncomingCallDialog(caller, number or "Unknown number", self)
        dialog.answer_requested.connect(lambda: self._answer_incoming(live))
        dialog.ignore_requested.connect(lambda: self._ignore_incoming(live, voicemail=False))
        dialog.voicemail_requested.connect(lambda: self._ignore_incoming(live, voicemail=True))
        self.incoming_dialog = dialog
        dialog.show()
        dialog.raise_()

    def _answer_incoming(self, live: bool) -> None:
        if live and isinstance(self.provider, SipAppProvider):
            self.provider.answer()
        self.statusBar().showMessage("Incoming call answered.", 5000)

    def _ignore_incoming(self, live: bool, voicemail: bool) -> None:
        if live and isinstance(self.provider, SipAppProvider):
            self.provider.ignore(voicemail)
        self.statusBar().showMessage(
            "Incoming call sent to voicemail." if voicemail else "Incoming call ignored.", 5000
        )

    def _is_emergency_dial(self, destination: str) -> bool:
        return destination.strip() in self.user_emergency_settings.numbers()

    def _confirm_emergency_location(self) -> bool:
        if not self.accounts or not self.accounts[0].emergency.enabled:
            return True
        dialog = EmergencyLocationDialog(self.accounts[0].emergency, self)
        if dialog.exec() != EmergencyLocationDialog.DialogCode.Accepted:
            return False
        location = dialog.selected_location()
        if not location:
            self.statusBar().showMessage("Emergency calling requires a verified location.", 8000)
            return False
        if isinstance(self.provider, SipAppProvider):
            self.provider.set_emergency_location(location)
        return True

    def _prompt_emergency_location_on_registration(self) -> None:
        if not self.accounts or not self.accounts[0].emergency.enabled:
            return
        self._confirm_emergency_location()

    def restore_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Treat the window-manager X as a full, graceful application exit."""
        self._shutdown()
        event.accept()
        app = QApplication.instance()
        if app:
            app.quit()

    def quit_application(self) -> None:
        self._shutdown()
        self.close()

    def _shutdown(self) -> None:
        """Release phone resources exactly once before the process exits."""
        if self._quitting:
            return
        self._quitting = True
        self.active_line_timer.stop()
        if self.provider:
            try:
                self.provider.stop()
            except (OSError, RuntimeError):
                # A shutdown must still complete if a peer has already gone away.
                pass
        self.tray.hide()
