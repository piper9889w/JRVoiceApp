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

## Active SIP-call controls

The active-line panel exposes mute, speaker volume, current-session device
selection, SIP INFO DTMF, SIP UPDATE hold/resume, blind SIP REFER transfer,
and hangup. Mute and speaker volume directly use the SIPApp audio engine;
DTMF, hold, and transfer construct standards-oriented in-dialog messages.
These controls are unit-tested for message construction only and must be
validated against the target PBX before they are treated as interoperable.

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

## Emergency dialing and PIDF-LO

**Emergency dialing and location…** in Account Settings stores a per-account
provider-support flag, up to five non-secret saved locations, and a default
location. Emergency dial strings (default `911`) are app-wide and accept a
comma-separated list such as `911, 112, 999`; this supports regional and
office-specific dial plans. When a PIDF-LO-enabled account registers, the app
asks the user to confirm the default or another saved location, or to provide
a temporary location for the current session. An emergency call similarly
requires that confirmation.

This is a safety UI/configuration foundation only. The current SIPApp transport
does **not** yet construct or transmit a standards-compliant PIDF-LO body or
Geolocation header. Do not rely on it for emergency location delivery until
that protocol work has been implemented and validated with the carrier/PBX.

## WebRTC requirements

WebRTC accounts use a valid `wss://` endpoint. SIP.js is the intended default and JsSIP is a selectable alternative. Both require an embedded Chromium runtime, microphone permission, a trusted TLS certificate, and ICE/TURN configuration appropriate for the user’s network.

`aiortc` remains an experimental future option. It is not a complete SIP-over-WSS replacement and the application rejects it for production registration.
