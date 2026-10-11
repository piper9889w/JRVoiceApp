# JRVoiceApp roadmap

## 1. Foundation and product spec — complete in this milestone

- Python package, quality checks, and packaging baseline
- Product, architecture, and security boundaries
- A small domain model that future calling providers will implement

## 2. Desktop shell and mockup-based interface — complete in this milestone

- Three-panel Global Voice-style phone window
- Dial pad, recent-call list, active-line area, and connection indicators
- Keyboard and button interactions for the local UI

## 3. Background operation and incoming calls

- System-tray presence and minimize-to-tray behavior
- Native notifications and an actionable incoming-call dialog
- Answer, ignore, and send-to-voicemail actions

## 4. Accounts and secure configuration

- Manual account setup and provisioning enrollment
- Operating-system keychain storage
- Connection type and WebRTC-engine selector

## 5. WebRTC calling

- SIP.js as the recommended WSS/WebRTC engine
- JsSIP as a selectable alternative
- Experimental aiortc path, clearly marked as not a complete SIP-over-WebSocket engine

## 6. Traditional SIP calling

- SIP TLS/TCP/UDP, registration, audio devices, DTMF, hold, and transfer

## 7–10. Unified experience, provisioning, release packaging, and polish

See the repository issues and releases once those milestones are opened.
