# Telephony setup and continuation decision

## Non-negotiable SIP direction

Continue SIP development from the existing **SIPApp** code. Bring the approved SIPApp source into JRVoiceApp as maintained project code, then adapt it to the account, keychain, tray, notification, and call-control layers already in this repository.

Do **not** replace SIPApp with Baresip, another softphone, or an unrelated SIP repository. JRVoiceApp should have one controlled SIP lineage.

## First task when SIPApp source is available

1. Identify the SIPApp transport, registration, call-state, audio, DTMF, hold, transfer, and voicemail components.
2. Port or incorporate those components into `src/jrvoiceapp/telephony/` while retaining their license notices and tests.
3. Implement `SipAppProvider` using that code, without exposing account secrets outside the OS keychain boundary.
4. Wire provider events to the existing tray alert, incoming-call popup, active-line panel, and diagnostics.
5. Test registration and calls against the target PBX before marking SIP work complete.

## WebRTC requirements

WebRTC accounts use a valid `wss://` endpoint. SIP.js is the intended default and JsSIP is a selectable alternative. Both require an embedded Chromium runtime, microphone permission, a trusted TLS certificate, and ICE/TURN configuration appropriate for the user’s network.

`aiortc` remains an experimental future option. It is not a complete SIP-over-WSS replacement and the application rejects it for production registration.
