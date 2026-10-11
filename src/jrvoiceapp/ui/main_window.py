"""The desktop shell shown before protocol engines are connected."""

from keyring.errors import KeyringError
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
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
from jrvoiceapp.ui.account_dialog import AccountDialog
from jrvoiceapp.ui.incoming_call import IncomingCallDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Global Voice")
        self.resize(1280, 790)
        self.setMinimumSize(780, 600)
        self.store = AccountStore()
        self.accounts = self.store.load()
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
        online = QLabel("     Online")
        online.setObjectName("online")
        layout.addWidget(online)
        layout.addSpacing(26)

        for label in ("☎  Phone", "♙  Contacts", "◷  Recent calls", "✉  Voicemail", "▤  Messages"):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setChecked(label.endswith("Phone"))
            layout.addWidget(button)
        settings = QPushButton("⚙  Settings")
        settings.setObjectName("nav")
        settings.clicked.connect(self.open_account_dialog)
        settings.setAccessibleName("Account settings")
        layout.addWidget(settings)
        layout.addStretch()

        secure = QFrame()
        secure.setObjectName("panel")
        secure_layout = QVBoxLayout(secure)
        secure_layout.addWidget(QLabel("▣  Secure connection"))
        for connection in ("✓  SIP TLS", "✓  WebRTC WSS"):
            chip = QLabel(connection)
            chip.setObjectName("online")
            secure_layout.addWidget(chip)
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
        online = QLabel("●  Online")
        online.setObjectName("online")
        words.addWidget(online)
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
        call = QPushButton("☎")
        call.setObjectName("call")
        call.setAccessibleName("Call")
        call.setToolTip("Calling will be enabled when an account is configured.")
        actions.addWidget(call)
        actions.addWidget(QPushButton("◉  Devices"))
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
        for call in SAMPLE_RECENT_CALLS:
            row = QHBoxLayout()
            avatar = QLabel(call.initials)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFixedSize(42, 42)
            avatar.setStyleSheet(f"background:{call.accent};border-radius:21px;font-weight:700;")
            row.addWidget(avatar)
            info = QVBoxLayout()
            info.addWidget(QLabel(call.caller))
            detail = QLabel(call.direction)
            detail.setObjectName("subtle")
            info.addWidget(detail)
            row.addLayout(info, 1)
            when = QLabel(call.time_label)
            when.setObjectName("subtle")
            row.addWidget(when)
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
        name = QLabel("Marcus Chen")
        name.setObjectName("heading")
        layout.addWidget(name)
        timer = QLabel("00:02:18     ▂▄▆█  Opus · Encrypted")
        timer.setObjectName("online")
        layout.addWidget(timer)
        controls = QGridLayout()
        for index, label in enumerate(
            ("♩\nMute", "⠿\nKeypad", "◖\nSpeaker", "⇄\nTransfer", "Ⅱ\nHold", "☎\nEnd call")
        ):
            button = QPushButton(label)
            button.setAccessibleName(label.replace("\n", " "))
            if label.endswith("End call"):
                button.setObjectName("end")
            controls.addWidget(button, index // 3, index % 3)
        layout.addLayout(controls)
        return panel

    def resizeEvent(self, event) -> None:
        self.right_column.setVisible(self.width() >= 980)
        self.sidebar.setVisible(self.width() >= 820)
        super().resizeEvent(event)

    def open_account_dialog(self) -> None:
        account = self.accounts[0] if self.accounts else None
        dialog = AccountDialog(account, self)
        if dialog.exec() != AccountDialog.DialogCode.Accepted:
            return
        result = dialog.result_account()
        try:
            if self.accounts:
                self.accounts[0] = result
            else:
                self.accounts.append(result)
            self.store.save(self.accounts)
            if dialog.password_input.text():
                self.store.save_password(result.identifier, dialog.password_input.text())
        except (KeyringError, OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not save account", str(error))
            return
        self._refresh_account_label()

    def _refresh_account_label(self) -> None:
        if self.accounts:
            account = self.accounts[0]
            self.account_label.setText(f"●  {account.label}\n    {account.username}")
        else:
            self.account_label.setText("●  No account configured")

    def show_incoming_call(self) -> None:
        self.restore_window()
        self.tray.showMessage(
            "Incoming call", "Marcus Chen is calling", QSystemTrayIcon.MessageIcon.Information, 8000
        )
        dialog = IncomingCallDialog("Marcus Chen", "Extension 1002", self)
        dialog.answer_requested.connect(
            lambda: self.statusBar().showMessage("Answer is ready for the call engine.", 5000)
        )
        dialog.ignore_requested.connect(
            lambda: self.statusBar().showMessage("Incoming call ignored.", 5000)
        )
        dialog.voicemail_requested.connect(
            lambda: self.statusBar().showMessage(
                "Voicemail routing is ready for the call engine.", 5000
            )
        )
        self.incoming_dialog = dialog
        dialog.show()
        dialog.raise_()

    def restore_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting or not self.tray.isVisible():
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Global Voice",
            "The phone is still running in the system tray.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def quit_application(self) -> None:
        self._quitting = True
        self.tray.hide()
        self.close()
