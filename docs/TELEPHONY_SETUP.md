# Telephony setup and continuation decision

## Non-negotiable SIP direction

Continue SIP development from the existing **SIPApp** code. Bring the approved SIPApp source into JRVoiceApp as maintained project code, then adapt it to the account, keychain, tray, notification, and call-control layers already in this repository.

Do **not** replace SIPApp with Baresip, another softphone, or an unrelated SIP repository. JRVoiceApp should have one controlled SIP lineage.

## SIPApp incorporation status

The project incorporates maintained source from `piper9889w/SIPApp` commit
`8464088e4b88761bf1fcfd6a34689f83081e32ba` under
`src/jrvoiceapp/telephony/sipapp_core/`. It contains its SIP transport,
registration manager, RTP/G.711 audio engine, resolver, SRTP helpers, and
credential-store adapter. `SipAppProvider` adapts these modules without
persisting a password: the UI reads it from the OS keychain only at provider
startup and the provider never includes it in events or diagnostics.

SIPApp v1.8 supplies registration, outbound/inbound calls, RTP audio,
voicemail dialing, cancellation/BYE, and session refresh. It does **not**
implement SIP hold, transfer, or DTMF signaling; those controls remain
disabled/pending rather than being represented as working. Its source did not
include a license declaration, which is recorded in `sipapp_core/SIPAPP_PROVENANCE.md`.

Run live registration and inbound/outbound audio tests against the target PBX
before treating any SIP feature as complete. The default TLS certificate and
hostname verification must remain enabled in that testing.

## Signaling templates and custom headers

Each account has **Edit signaling templates…** in Account Settings. It stores
non-secret templates for SIP and WebRTC outbound `INVITE` and inbound-answer
`200 OK` messages. Blank templates use the safe engine default. Changes are
saved with the account and apply to the next call; they do not alter a live
dialog.

Header variables are stored as `name = value`. Use `{name}` anywhere in a
template, and use `{custom_headers}` to emit every defined value as an
`X-name: value` SIP header. Values cannot contain newlines, preventing header
injection. The WebRTC bridge receives the same settings for its future
SIP.js/JsSIP implementation; it is configuration-ready but not live-runtime
validated yet.

## WebRTC requirements

WebRTC accounts use a valid `wss://` endpoint. SIP.js is the intended default and JsSIP is a selectable alternative. Both require an embedded Chromium runtime, microphone permission, a trusted TLS certificate, and ICE/TURN configuration appropriate for the user’s network.

`aiortc` remains an experimental future option. It is not a complete SIP-over-WSS replacement and the application rejects it for production registration.
