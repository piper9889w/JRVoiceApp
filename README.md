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

## Run and test locally

Requires Python 3.11 or newer. From the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/jrvoiceapp
```

On Windows use `.venv\\Scripts\\python -m pip install -e ".[dev]"` and
`.venv\\Scripts\\jrvoiceapp`. The first run may prompt the OS keychain for
permission to save account or provisioning credentials.

### Quick local smoke plan

1. Start the app and confirm the dial pad, tray icon, and **Test incoming call** tray action work.
2. Open **Settings** and create a SIP TLS account with a non-production test endpoint; confirm passwords never appear in the account fields after saving.
3. Under **Contacts**, add, edit, dial, and delete a contact. Check **Recent calls** shows locally recorded activity.
4. Use **Default account** to persist an account preference. A SIP URI with an explicit matching domain takes precedence over that default.
5. In the active call panel, choose **Devices** after connecting a SIP account and confirm the choice survives an app restart.
6. Optionally configure a WebRTC WSS account and open **Diagnostics**. Runtime/endpoint summaries may appear, but do not treat this as a completed WebRTC call test.

Run the automated checks with:

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

### Live telephony test boundary

Live testing needs a staging PBX/WSS/TURN/carrier environment and non-production
credentials. Validate registration, calls, audio, DTMF, hold, transfer, TLS,
WebRTC media, and emergency-location delivery there. Never use this application
as the sole means of placing an emergency call until carrier validation is complete.

## Product direction

- One account-aware dialer for SIP and WebRTC
- A selectable WebRTC engine per account: SIP.js (recommended), JsSIP, or experimental aiortc
- Native-looking desktop behavior on Windows, macOS, and Linux
- A background/tray mode and actionable incoming-call notification
- Secure account credentials through each operating system's keychain
- Per-account editable SIP and WebRTC `INVITE` and inbound `200 OK` templates
- Reusable non-secret SIP custom-header variables for provider-specific `X-` headers
- Per-account PIDF-LO/emergency-dialing support setting, five saved locations, and verification prompts
- VoiceAdmin version-1 profile download and refresh, with provisioning credentials stored in the OS keychain
- User-level configurable emergency dial strings for regional and office dialing plans

See [the roadmap](docs/ROADMAP.md), [architecture notes](docs/ARCHITECTURE.md), and the editable [project status checklist](PROJECT_STATUS.md) for the planned implementation boundaries.

For a durable continuation summary, see [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md).

For the SIP and WebRTC provider requirements and the live-call validation sequence, see [telephony setup](docs/TELEPHONY_SETUP.md).

## Technology choices

The user interface is Python with Qt for Python (PySide6), which gives the application native packages on all three desktop platforms. Calling engines stay behind a provider interface so that a reliable SIP engine and independently selectable WebRTC engines can evolve without changing the phone interface.

## License

MIT. See [LICENSE](LICENSE).
