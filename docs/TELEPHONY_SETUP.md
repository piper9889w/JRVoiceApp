# Telephony setup

JRVoiceApp has two provider paths. They share the same account screen, but they have different deployment requirements.

## Traditional SIP: Baresip

The initial native SIP provider uses [Baresip](https://github.com/baresip/baresip), a cross-platform SIP user agent. Install the `baresip` executable on the client machine and ensure it is available on the system path.

When a SIP account starts, JRVoiceApp creates a private, temporary runtime directory and places its generated `accounts` file there with owner-only permissions. The file is removed when the provider stops. The account password comes from the operating-system keychain and must not be committed to this repository or placed in a settings file.

Before live testing, confirm:

- SIP transport: TLS, TCP, or UDP as supported by the target PBX
- Correct registrar/proxy hostname and port
- Authentication username and secret
- Network/RTP reachability and selected codecs
- A Baresip configuration with the desired audio modules for each target operating system

## WebRTC: SIP.js or JsSIP

WebRTC accounts must use a valid `wss://` endpoint. SIP.js is the intended default and JsSIP is a selectable alternative. Both require an embedded Chromium runtime, microphone permission, a trusted TLS certificate, and an ICE/TURN configuration appropriate for the user’s network.

Before live testing, confirm:

- WSS URL and SIP authentication credentials
- Browser-trusted HTTPS/WSS certificate chain
- Kamailio/Asterisk WebSocket and WebRTC media configuration
- TURN credentials for clients outside the local network
- Codec interoperability: Opus for WebRTC and an agreed PBX bridge codec such as PCMU/PCMA

`aiortc` remains visible only as an experimental future option. It is not a complete SIP-over-WSS replacement and the application rejects it for production account registration.

## Live-call test plan

1. Register a SIP account and a WebRTC account to the same PBX.
2. Place calls in both directions between those accounts.
3. Verify inbound notifications, Answer, Ignore, and voicemail routing.
4. Test microphone/speaker selection, DTMF, hold, transfer, and sleep/wake recovery.
5. Repeat from an external network through TURN.
