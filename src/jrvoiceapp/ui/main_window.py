"""The desktop shell shown before protocol engines are connected."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jrvoiceapp.models import SAMPLE_RECENT_CALLS


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Global Voice")
        self.resize(1280, 790)
        self.setMinimumSize(1080, 680)
        self.dial_input = QLineEdit()
        self.dial_input.setPlaceholderText("Name or number")

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._sidebar())
        layout.addWidget(self._dialer(), 1)
        layout.addWidget(self._right_column())
        self.setCentralWidget(root)

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
        layout.addWidget(QLabel("●  Extension 1001"))
        online = QLabel("     Online")
        online.setObjectName("online")
        layout.addWidget(online)
        layout.addSpacing(26)

        for label in ("☎  Phone", "♙  Contacts", "◷  Recent calls", "✉  Voicemail", "▤  Messages", "⚙  Settings"):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setChecked(label.endswith("Phone"))
            layout.addWidget(button)
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
        for index, value in enumerate(("1", "2\nABC", "3\nDEF", "4\nGHI", "5\nJKL", "6\nMNO", "7\nPQRS", "8\nTUV", "9\nWXYZ", "*", "0\n+", "#")):
            button = QPushButton(value)
            button.setObjectName("dial")
            button.clicked.connect(lambda _checked=False, digit=value[0]: self.dial_input.insert(digit))
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addStretch()
        actions = QHBoxLayout()
        actions.addWidget(QPushButton("▣  Video"))
        call = QPushButton("☎")
        call.setObjectName("call")
        call.setToolTip("Calling will be enabled when an account is configured.")
        actions.addWidget(call)
        actions.addWidget(QPushButton("◉  Devices"))
        layout.addLayout(actions)
        return panel

    def _right_column(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(350)
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
        for index, label in enumerate(("♩\nMute", "⠿\nKeypad", "◖\nSpeaker", "⇄\nTransfer", "Ⅱ\nHold", "☎\nEnd call")):
            button = QPushButton(label)
            if label.endswith("End call"):
                button.setObjectName("end")
            controls.addWidget(button, index // 3, index % 3)
        layout.addLayout(controls)
        return panel
