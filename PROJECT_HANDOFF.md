# JRVoiceApp continuation handoff

**Prepared:** 2026-10-12
**Repository:** `piper9889w/JRVoiceApp`  
**Branch:** `main`  
**Latest commit:** `81a2a1c Expand contacts history and routing UI`
**Repository state:** clean and pushed to `origin/main`

## Read before changing anything

1. Run `git status -sb` and update `main` with `git pull --ff-only`.
2. Read `PROJECT_STATUS.md` first; it is the authoritative tracker.
3. Read `README.md`, `docs/ARCHITECTURE.md`, and `docs/TELEPHONY_SETUP.md`.
4. Preserve the SIP architectural decision: continue only from the maintained
   SIPApp code in `src/jrvoiceapp/telephony/sipapp_core/`. Do not substitute
   Baresip, another softphone, or an unrelated SIP repository.

## Current implementation

- The PySide6 desktop shell has accounts, OS-keychain password/provisioning
  storage, tray behavior, incoming-call UI, signaling templates, VoiceAdmin
  provisioning, contacts, unified history, active-call status, audio preferences,
  default routing, and safe diagnostics.
- SIPApp source is maintained in-tree from upstream commit
  `8464088e4b88761bf1fcfd6a34689f83081e32ba`. Its upstream repository had no
  declared license; see `src/jrvoiceapp/telephony/sipapp_core/SIPAPP_PROVENANCE.md`.
- `SipAppProvider` uses that code for TLS SIP registration, call state, RTP/G.711
  audio, diagnostics, and UI events. No live PBX call has been validated.
- Active-call controls construct SIP INFO DTMF, SIP UPDATE hold/resume, blind
  SIP REFER transfer, and use the SIPApp audio engine for mute/speaker/device
  choice. They are unit-tested only.
- The diagnostics panel intentionally shows only redacted, summary-level data.
  Never put passwords, authorization data, raw SIP content, or media keys into
  UI logs or settings.
- The embedded WebEngine WebRTC runtime loads SIP.js or JsSIP and returns safe
  lifecycle summaries. It is not live WSS/TURN/media validated.
- PIDF-LO XML and a Geolocation header are constructed after location confirmation,
  but are not transmitted or carrier validated.

## Suggested next work without a PBX

1. Test SIP and WebRTC end-to-end against the target staging infrastructure.
2. Finish WebRTC runtime registration/call event wiring and bundle approved JS
   assets rather than relying on CDN runtime loading.
3. Add a per-call account picker and richer contact/history search.
4. Transmit PIDF-LO only after carrier/PBX requirements are known and test it.

## Verification baseline

Use a Python 3.11+ environment. The current baseline is:

```bash
PYTHONPATH=src .venv311/bin/python -m ruff format --check .
PYTHONPATH=src .venv311/bin/python -m ruff check .
PYTHONPATH=src .venv311/bin/python -m pytest -q
git diff --check
```

At this handoff, formatting and lint pass and **22 tests pass**. An offscreen
Qt smoke test may depend on local Qt platform-plugin setup; do not report it as
passing unless it actually initializes in the current environment.

## Non-negotiable validation boundary

Do not claim SIP/WebRTC calling, DTMF, hold, transfer, PIDF-LO, TLS behavior,
or emergency location delivery is complete until it is tested against the
actual PBX/WSS/TURN/carrier environment. Keep `PROJECT_STATUS.md` truthful and
update it in the same commit as implementation work.
