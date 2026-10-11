# JRVoiceApp

JRVoiceApp is a desktop phone for Windows, macOS, and Linux. It will provide one familiar dialer and call history for both traditional SIP accounts and browser-grade WebRTC accounts. Its SIP implementation will continue from the existing SIPApp development work, incorporated into this project rather than replaced with another softphone project.

## Current status

The desktop shell now contains the maintained SIPApp transport, registration,
RTP/G.711 audio, DNS resolution, and optional SDES-SRTP foundations. It can
attempt TLS SIP registration from an OS-keychain-backed account and routes
provider state, incoming calls, and diagnostics into the desktop UI. This is
an integration milestone, not a claim of live PBX interoperability: live
registration and calls remain unverified until tested against the target
PBX/TLS/TURN environment.

The imported SIPApp lineage is documented in
[`sipapp_core/SIPAPP_PROVENANCE.md`](src/jrvoiceapp/telephony/sipapp_core/SIPAPP_PROVENANCE.md).
Its upstream source had no declared license when incorporated, so confirm its
distribution license before shipping a binary.

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
- Per-account editable SIP and WebRTC `INVITE` and inbound `200 OK` templates
- Reusable non-secret SIP custom-header variables for provider-specific `X-` headers
- Per-account PIDF-LO/emergency-dialing support setting, five saved locations, and verification prompts
- User-level configurable emergency dial strings for regional and office dialing plans

See [the roadmap](docs/ROADMAP.md), [architecture notes](docs/ARCHITECTURE.md), and the editable [project status checklist](PROJECT_STATUS.md) for the planned implementation boundaries.

For a durable continuation summary, see [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md).

For the SIP and WebRTC provider requirements and the live-call validation sequence, see [telephony setup](docs/TELEPHONY_SETUP.md).

## Technology choices

The user interface is Python with Qt for Python (PySide6), which gives the application native packages on all three desktop platforms. Calling engines stay behind a provider interface so that a reliable SIP engine and independently selectable WebRTC engines can evolve without changing the phone interface.

## License

MIT. See [LICENSE](LICENSE).
