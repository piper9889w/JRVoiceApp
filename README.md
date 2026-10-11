# JRVoiceApp

JRVoiceApp is a desktop phone for Windows, macOS, and Linux. It will provide one familiar dialer and call history for both traditional SIP accounts and browser-grade WebRTC accounts.

## Current status

The first milestone provides a functional UI shell only. It demonstrates the intended dark desktop-phone experience, but it does **not** yet register accounts or place calls.

## Run the desktop shell

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/jrvoiceapp
```

On Windows, activate the virtual environment with `.venv\\Scripts\\activate` before running the install and app commands.

## Product direction

- One account-aware dialer for SIP and WebRTC
- A selectable WebRTC engine per account: SIP.js (recommended), JsSIP, or experimental aiortc
- Native-looking desktop behavior on Windows, macOS, and Linux
- A background/tray mode and actionable incoming-call notification
- Secure account credentials through each operating system's keychain

See [the roadmap](docs/ROADMAP.md), [architecture notes](docs/ARCHITECTURE.md), and the editable [project status checklist](PROJECT_STATUS.md) for the planned implementation boundaries.

## Technology choices

The user interface is Python with Qt for Python (PySide6), which gives the application native packages on all three desktop platforms. Calling engines stay behind a provider interface so that a reliable SIP engine and independently selectable WebRTC engines can evolve without changing the phone interface.

## License

MIT. See [LICENSE](LICENSE).
