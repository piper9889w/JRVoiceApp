# JRVoiceApp project status

Last updated: 2026-10-11

This is the shared working checklist for the project. Update it in the same pull request or commit as the work it describes. Use `[x]` only for work that has been implemented and verified; use `[~]` for active work; use `[ ]` for planned work.

## Current snapshot

| Area | Status | What exists now |
| --- | --- | --- |
| Project foundation | Complete | Python package, documentation, license, lint/test workflow, and packaging baseline. |
| Desktop interface | Complete | Mockup-inspired responsive dark phone window with accessible controls, dialer, connection status, recents, and call controls. |
| SIP calling | In progress; live validation pending | SIPApp source is maintained in-tree; provider registration, call-state, RTP/G.711 audio, UI/tray events, and non-secret diagnostics are integrated but not live-PBX verified. |
| WebRTC calling | In progress; live validation pending | SIP.js/JsSIP provider boundary, embedded WebEngine runtime loader, and secure-WSS validation are implemented; real WSS/TURN registration and media remain unverified. |
| Tray and incoming calls | Complete foundation | Minimize-to-tray, restore, native notification, and actionable demo incoming-call prompt. |
| Accounts and secure configuration | Complete foundation | Account editor, OS-keychain password/provisioning-secret boundary, VoiceAdmin profile refresh, and SIP/WebRTC engine settings. |
| Releases | Planned | No installers have been built. |

## Delivery checklist

### 1. Foundation and product specification

- [x] Create the public `piper9889w/JRVoiceApp` repository.
- [x] Create the Python package and local application entry point.
- [x] Add README, license, roadmap, architecture, and this status file.
- [x] Add a Windows/macOS/Linux quality-check workflow.
- [x] Define protocol-provider and security boundaries.

### 2. Desktop shell and mockup-based interface

- [x] Build the initial Global Voice-style dark phone window.
- [x] Add dial pad input, extension status, security indicators, recents, and active-line controls.
- [x] Keep the application independent of a particular SIP/WebRTC provider.
- [x] Add responsive layout behavior and accessible names for primary controls.
- [ ] Create visual regression screenshots.

### 3. Background operation and incoming calls

- [x] Add minimize-to-tray and restore behavior.
- [x] Add an incoming-call popup with caller identity.
- [x] Add **Answer**, **Ignore**, and **Send to voicemail** actions in the UI foundation.
- [x] Add native notifications.
- [ ] Add optional launch-at-login.

### 4. Accounts and secure configuration

- [x] Add the initial account add/edit flow.
- [~] Add manual setup and provisioning-server enrollment (VoiceAdmin version-1 download, mapping, refresh, retry, and safe errors are implemented; target VoiceAdmin deployment validation remains).
- [x] Store secrets in the operating-system keychain, never plaintext settings.
- [x] Add connection type selection: SIP or WebRTC.
- [x] Add WebRTC-engine selection: SIP.js, JsSIP, or experimental aiortc.
- [~] Add per-account PIDF-LO support/location preferences and user-level emergency dial strings (saved locations, verification prompt, and temporary session location are implemented; PIDF-LO SIP transmission and carrier validation remain).

### 5. WebRTC calling

- [~] Implement SIP.js as the recommended WSS/WebRTC engine (embedded runtime loader and event boundary are implemented; WSS/TURN registration and media are not live-validated).
- [~] Implement JsSIP as an alternate selectable engine (embedded runtime loader and event boundary are implemented; WSS/TURN registration and media are not live-validated).
- [x] Document and enforce the limited experimental aiortc path.
- [ ] Add microphone, speaker, codec, ICE, and TURN diagnostics.

### 6. Traditional SIP calling

- [x] Record the SIP implementation decision: continue from SIPApp source in this project.
- [x] Bring the approved SIPApp source into JRVoiceApp and create the maintained integration boundary (source commit `8464088`; no upstream license declaration, recorded in provenance).
- [~] Add SIP TLS/TCP/UDP registration and call setup using that SIPApp lineage (TLS registration/call adapter is implemented; target-PBX validation and TCP/UDP account selection remain).
- [~] Add audio-device selection, DTMF, hold, transfer, and voicemail (SIPApp RTP/G.711 audio and voicemail dialing are integrated; desktop controls now issue SIP INFO DTMF, UPDATE hold/resume, and REFER transfer, plus mute/speaker/device selection. All require target-PBX validation.)
- [~] Add certificate validation and useful network error reporting (TLS verification, a redacted desktop diagnostics panel, RTP/jitter/audio metrics, and recent SIP-event summaries are wired; real certificate/network scenarios remain to be tested).

### 7. Unified experience

- [~] Combine SIP and WebRTC history, contacts, dialer, and presence (persisted local unified history/contact store and dialer integration are implemented; contact-management UI and live-provider completion states remain).
- [ ] Display account, codec, encryption, and call-quality status.
- [ ] Define deterministic account-routing rules for outbound calls.
- [~] Add per-account editable SIP/WebRTC INVITE and 200 OK templates plus reusable custom-header variables (SIPApp adapter applies SIP templates; WebRTC bridge configuration is ready pending runtime integration).

### 8. Provisioning integration

- [~] Implement the existing VoiceAdmin HTTP Basic profile download flow (version-1 profile download, account mapping, refresh, bounded retry, and safe errors are implemented; target VoiceAdmin deployment validation remains).

### 9. Packaging and verification

- [ ] Produce Windows installer, signed macOS app, and Linux package.
- [ ] Test inbound/outbound SIP and WebRTC calls on all supported operating systems.
- [ ] Verify tray notifications, sleep/wake recovery, and credential handling.

### 10. Polish and release readiness

- [ ] Refine the interface against the approved visual direction.
- [ ] Add user/admin documentation and troubleshooting guides.
- [ ] Publish a versioned release process.

## How to add work

Add new tasks under the closest numbered phase. Give each item a short, testable description. If a request spans multiple phases, add it to the earliest phase and link to its later dependency in parentheses. Keep this file honest: do not mark an item complete until it is implemented and verified.
