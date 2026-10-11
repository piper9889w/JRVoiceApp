# Architecture

JRVoiceApp separates the stable desktop experience from protocol-specific calling engines.

```text
Qt desktop UI
    │
    ├── application state and call controller
    │       ├── SIP provider (future native engine)
    │       └── WebRTC provider (future SIP.js, JsSIP, or experimental aiortc)
    │
    ├── OS adapters: keychain, tray, notifications, audio devices
    └── account/provisioning store
```

The user should not have to think about this separation during a call. It exists so that each account can select the safest compatible transport while retaining one dialer, contact list, call history, and incoming-call workflow.

## WebRTC engine selector

The account editor will display three choices:

- **SIP.js — recommended:** mature SIP-over-WSS behavior running in an embedded web runtime.
- **JsSIP:** alternate SIP-over-WSS engine for deployments that need its compatibility profile.
- **aiortc — experimental:** a Python WebRTC media building block. It needs custom SIP signaling, so it will not be advertised as a drop-in replacement for the other two.

## Security boundaries

- Passwords and provisioning secrets must never be written to logs or plaintext configuration files.
- SIP TLS/WSS certificate validation stays enabled by default.
- TURN credentials and logs are treated as sensitive configuration.
- The UI may display account state but must not expose passwords.
