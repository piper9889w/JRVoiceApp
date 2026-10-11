import socket
import threading
import time
import struct
import re
import os
from dataclasses import dataclass
from typing import Any, List, Dict, Optional, Callable
from jrvoiceapp.telephony.sipapp_core.secure_media import SRTPSessionPair, SecureMediaError

try:
    import sounddevice as sd
except ImportError:
    sd = None

RTP_FRAME_SAMPLES = 160


@dataclass(frozen=True)
class RTPAudioPacket:
    sequence: int
    timestamp: int
    ssrc: int
    payload_type: int
    pcm: bytes


class RTPJitterBuffer:
    """Small bounded G.711 jitter buffer with deterministic loss-time preservation."""

    def __init__(self, reorder_window: int = 3) -> None:
        self.reorder_window = max(2, int(reorder_window))
        self._packets: Dict[int, RTPAudioPacket] = {}
        self.expected: Optional[int] = None
        self.started = False
        self.duplicates = 0
        self.lost = 0
        self.ssrc: Optional[int] = None
        self.expected_timestamp: Optional[int] = None

    @staticmethod
    def _distance(sequence: int, base: int) -> int:
        return (sequence - base) & 0xFFFF

    def push(self, packet: RTPAudioPacket) -> List[Optional[RTPAudioPacket]]:
        if self.ssrc is None:
            self.ssrc = packet.ssrc
        elif packet.ssrc != self.ssrc:
            self._packets.clear()
            self.expected = None
            self.expected_timestamp = None
            self.started = False
            self.ssrc = packet.ssrc
        if packet.sequence in self._packets:
            self.duplicates += 1
            return []
        if self.expected is not None and self._distance(packet.sequence, self.expected) >= 0x8000:
            self.duplicates += 1
            return []
        self._packets[packet.sequence] = packet
        if not self.started:
            if len(self._packets) < self.reorder_window:
                return []
            self.expected = min(self._packets.values(), key=lambda item: item.timestamp).sequence
            self.started = True
        return self._drain()

    def _drain(self) -> List[Optional[RTPAudioPacket]]:
        output: List[Optional[RTPAudioPacket]] = []
        consecutive_loss = 0
        while self.expected is not None:
            packet = self._packets.pop(self.expected, None)
            if packet is not None:
                if self.expected_timestamp is not None:
                    timestamp_gap = (packet.timestamp - self.expected_timestamp) & 0xFFFFFFFF
                    if 0 < timestamp_gap < 0x80000000:
                        missing_frames = min(
                            self.reorder_window, timestamp_gap // RTP_FRAME_SAMPLES
                        )
                        output.extend([None] * missing_frames)
                        self.lost += missing_frames
                output.append(packet)
                consecutive_loss = 0
                self.expected_timestamp = (
                    packet.timestamp + max(1, len(packet.pcm) // 2)
                ) & 0xFFFFFFFF
                self.expected = (self.expected + 1) & 0xFFFF
                continue
            if not self._packets:
                break
            furthest = max(self._distance(seq, self.expected) for seq in self._packets)
            if furthest < self.reorder_window - 1:
                break
            output.append(None)
            self.lost += 1
            consecutive_loss += 1
            if self.expected_timestamp is not None:
                self.expected_timestamp = (self.expected_timestamp + RTP_FRAME_SAMPLES) & 0xFFFFFFFF
            self.expected = (self.expected + 1) & 0xFFFF
            if consecutive_loss >= self.reorder_window and self._packets:
                self.expected = min(
                    self._packets, key=lambda seq: self._distance(seq, self.expected)
                )
                consecutive_loss = 0
        return output

    def flush(self) -> List[Optional[RTPAudioPacket]]:
        if not self.started and self._packets:
            self.expected = min(self._packets.values(), key=lambda item: item.timestamp).sequence
            self.started = True
        output: List[Optional[RTPAudioPacket]] = []
        consecutive_loss = 0
        while self._packets and self.expected is not None:
            packet = self._packets.pop(self.expected, None) if self.expected is not None else None
            output.append(packet)
            if packet is None:
                self.lost += 1
                consecutive_loss += 1
            else:
                consecutive_loss = 0
            self.expected = ((self.expected or 0) + 1) & 0xFFFF
            if consecutive_loss >= self.reorder_window and self._packets:
                self.expected = min(
                    self._packets, key=lambda seq: self._distance(seq, self.expected)
                )
                consecutive_loss = 0
        return output


class AudioEngine:
    """
    Pure Python Audio Engine for SIPApp.
    Handles device enumeration, G.711 codec configuration, and RTP media streaming.
    """

    AVAILABLE_CODECS = ["PCMU (G.711u)", "PCMA (G.711a)"]

    def __init__(
        self,
        input_device: str = "Default Microphone",
        output_device: str = "Default Speaker",
        selected_codecs: Optional[List[str]] = None,
    ):
        self.input_device = input_device
        self.output_device = output_device
        self.selected_codecs = selected_codecs or ["PCMU (G.711u)", "PCMA (G.711a)"]

        self.is_streaming = False
        self.rtp_socket: Optional[socket.socket] = None
        self.rtp_thread: Optional[threading.Thread] = None
        self.rx_thread: Optional[threading.Thread] = None
        self.sequence_number = 0
        self.timestamp = 0
        self.ssrc = 0x12345678
        self.remote_ip = ""
        self.remote_port = 0
        self.local_rtp_port = 0
        self.bind_ip = "0.0.0.0"
        self.advertised_ip = ""
        self.advertised_port = 0
        self.nat_status = "Disabled"
        self.symmetric_rtp = False
        self.symmetric_source_learned = False
        self.muted = False
        self.mic_volume = 0.8
        self.speaker_volume = 0.8
        self._rtp_stats_lock = threading.Lock()
        self.rtp_packets_sent = 0
        self.rtp_packets_received = 0
        self.input_stream = None
        self.output_stream = None
        self.audio_error = ""
        self.active_input_device = ""
        self.active_output_device = ""
        self.input_sample_rate = 8000
        self.output_sample_rate = 8000
        self.input_block_frames = 160
        self.audio_tap_callback: Optional[Callable[[str, bytes, int], None]] = None
        self.srtp: Optional[SRTPSessionPair] = None
        self.require_srtp = False
        self.srtp_errors = 0
        self.negotiated_codec = self._configured_codecs()[0]
        self.payload_types = {"PCMU": 0, "PCMA": 8}
        self.jitter_buffer = RTPJitterBuffer()
        self._tx_media_frame = 0
        self._rx_media_frame: Optional[int] = None

    def set_audio_tap(self, callback: Optional[Callable[[str, bytes, int], None]]) -> None:
        """Receive decoded 8 kHz PCM16 audio for recording (TX and RX)."""
        self.audio_tap_callback = callback

    @staticmethod
    def get_audio_devices() -> Dict[str, Any]:
        """Enumerate actual PortAudio input/output devices."""
        input_devices = ["Default Microphone"]
        output_devices = ["Default Speaker"]
        error = ""
        device_count = 0
        if sd is not None:
            try:
                queried_devices = sd.query_devices()
                device_count = len(queried_devices)
                for index, device in enumerate(queried_devices):
                    label = f"{index}: {device['name']}"
                    if device["max_input_channels"] > 0:
                        input_devices.append(label)
                    if device["max_output_channels"] > 0:
                        output_devices.append(label)
            except Exception as exc:
                error = str(exc)
                print(f"[AudioEngine] Audio enumeration error: {exc}")

        return {
            "inputs": input_devices,
            "outputs": output_devices,
            "available": sd is not None and not error and device_count > 0,
            "error": error
            or (
                "sounddevice is not installed"
                if sd is None
                else "CoreAudio reported no devices to this process"
                if device_count == 0
                else ""
            ),
        }

    def start_rtp_stream(
        self,
        local_port: int,
        remote_ip: str,
        remote_port: int,
        on_audio_rx_callback: Optional[Callable] = None,
        bind_ip: str = "0.0.0.0",
        stun_server: str = "",
        symmetric_rtp: bool = False,
        srtp_outbound_key: bytes = b"",
        srtp_inbound_key: bytes = b"",
        require_srtp: bool = False,
    ) -> int:
        """Start RTP audio transmission and reception socket loops."""
        self.stop_rtp_stream()
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.bind_ip = bind_ip or "0.0.0.0"
        self.advertised_ip = self.bind_ip
        self.advertised_port = 0
        self.symmetric_rtp = symmetric_rtp
        self.symmetric_source_learned = False
        self.require_srtp = require_srtp
        self.srtp = (
            SRTPSessionPair(srtp_outbound_key, srtp_inbound_key or None) if require_srtp else None
        )
        self.srtp_errors = 0
        self.jitter_buffer = RTPJitterBuffer()
        self._tx_media_frame = 0
        self._rx_media_frame = None
        self.nat_status = "Symmetric RTP" if symmetric_rtp else "Disabled"
        self.is_streaming = True
        self.sequence_number = 1000
        self.timestamp = 160000
        with self._rtp_stats_lock:
            self.rtp_packets_sent = 0
            self.rtp_packets_received = 0
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        bound_port = 0
        for attempt_port in range(local_port, local_port + 50, 2):
            try:
                self.rtp_socket.bind((self.bind_ip, attempt_port))
                bound_port = attempt_port
                break
            except Exception:
                continue
        if not bound_port:
            self.is_streaming = False
            self.rtp_socket.close()
            self.rtp_socket = None
            raise OSError(
                f"Could not bind a UDP RTP socket on ports {local_port}-{local_port + 48}"
            )
        self.local_rtp_port = bound_port
        self.advertised_port = bound_port
        if stun_server:
            mapped = self._discover_stun_mapping(stun_server)
            if mapped:
                self.advertised_ip, self.advertised_port = mapped
                self.nat_status = f"STUN mapped {self.advertised_ip}:{self.advertised_port}"
            else:
                self.nat_status = f"STUN failed ({stun_server}); using local address"
        self._open_audio_streams()

        self.rtp_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self.rx_thread = threading.Thread(
            target=self._rx_loop, args=(on_audio_rx_callback,), daemon=True
        )
        self.rtp_thread.start()
        self.rx_thread.start()

        print(
            f"[AudioEngine] RTP stream active on {self.bind_ip}:{bound_port} -> {remote_ip}:{remote_port}"
        )
        return self.advertised_port

    def stop_rtp_stream(self):
        """Stop active RTP audio stream."""
        self.is_streaming = False
        self._deliver_rx_frames(self.jitter_buffer.flush())
        self.srtp = None
        self.require_srtp = False
        for stream_name in ("input_stream", "output_stream"):
            stream = getattr(self, stream_name)
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                setattr(self, stream_name, None)
        if self.rtp_socket:
            try:
                self.rtp_socket.close()
            except Exception:
                pass
            self.rtp_socket = None

    @staticmethod
    def _device_id(selection: str) -> Optional[int]:
        match = re.match(r"^(\d+):", selection or "")
        return int(match.group(1)) if match else None

    @staticmethod
    def _split_host_port(server: str, default_port: int = 3478) -> tuple[str, int]:
        host, separator, port_text = (server or "").strip().rpartition(":")
        if separator and host and port_text.isdigit():
            return host, int(port_text)
        return server.strip(), default_port

    def _discover_stun_mapping(self, server: str) -> Optional[tuple[str, int]]:
        """Perform an RFC 5389 Binding request on the bound RTP UDP socket."""
        if not self.rtp_socket:
            return None
        host, port = self._split_host_port(server)
        if not host:
            return None
        cookie = 0x2112A442
        transaction_id = os.urandom(12)
        request = struct.pack("!HHI12s", 0x0001, 0, cookie, transaction_id)
        previous_timeout = self.rtp_socket.gettimeout()
        try:
            stun_ip = socket.gethostbyname(host)
            self.rtp_socket.settimeout(1.5)
            self.rtp_socket.sendto(request, (stun_ip, port))
            response, _ = self.rtp_socket.recvfrom(2048)
            return self._parse_stun_binding_response(response, cookie, transaction_id)
        except (OSError, ValueError):
            return None
        finally:
            self.rtp_socket.settimeout(previous_timeout)
        return None

    @staticmethod
    def _parse_stun_binding_response(
        response: bytes, cookie: int, transaction_id: bytes
    ) -> Optional[tuple[str, int]]:
        if len(response) < 20:
            return None
        message_type, message_length, response_cookie, response_id = struct.unpack(
            "!HHI12s", response[:20]
        )
        if message_type != 0x0101 or response_cookie != cookie or response_id != transaction_id:
            return None
        offset = 20
        end = min(len(response), 20 + message_length)
        while offset + 4 <= end:
            attribute_type, attribute_length = struct.unpack("!HH", response[offset : offset + 4])
            value = response[offset + 4 : offset + 4 + attribute_length]
            if attribute_type in (0x0020, 0x0001) and len(value) >= 8 and value[1] == 0x01:
                mapped_port = struct.unpack("!H", value[2:4])[0]
                address_value = struct.unpack("!I", value[4:8])[0]
                if attribute_type == 0x0020:
                    mapped_port ^= cookie >> 16
                    address_value ^= cookie
                mapped_ip = socket.inet_ntoa(struct.pack("!I", address_value))
                return mapped_ip, mapped_port
            offset += 4 + ((attribute_length + 3) & ~3)
        return None

    def _open_audio_streams(self) -> None:
        self.audio_error = ""
        self.active_input_device = self.input_device
        self.active_output_device = self.output_device
        if sd is None:
            self.audio_error = "sounddevice is not installed; run pip install -r requirements.txt"
            return
        errors = []
        input_id = self._device_id(self.input_device)
        output_id = self._device_id(self.output_device)
        try:
            input_info = sd.query_devices(input_id, "input")
            self.input_sample_rate = int(input_info["default_samplerate"] or 8000)
            self.input_block_frames = max(1, round(self.input_sample_rate * 0.02))
            self.input_stream = sd.RawInputStream(
                samplerate=self.input_sample_rate,
                blocksize=self.input_block_frames,
                device=input_id,
                channels=1,
                dtype="int16",
                latency="low",
            )
            self.input_stream.start()
            self.active_input_device = input_info["name"]
        except Exception as exc:
            errors.append(f"microphone: {exc}")
            if self.input_stream:
                try:
                    self.input_stream.close()
                except Exception:
                    pass
                self.input_stream = None
        try:
            output_info = sd.query_devices(output_id, "output")
            self.output_sample_rate = int(output_info["default_samplerate"] or 8000)
            self.output_stream = sd.RawOutputStream(
                samplerate=self.output_sample_rate,
                blocksize=max(1, round(self.output_sample_rate * 0.02)),
                device=output_id,
                channels=1,
                dtype="int16",
                latency="low",
            )
            self.output_stream.start()
            self.active_output_device = output_info["name"]
        except Exception as exc:
            errors.append(f"speaker: {exc}")
            if self.output_stream:
                try:
                    self.output_stream.close()
                except Exception:
                    pass
                self.output_stream = None
        self.audio_error = "; ".join(errors)

    @staticmethod
    def parse_sdp_audio_target(sdp: str, fallback_ip: str = "") -> tuple[str, int]:
        """Extract the IPv4 connection address and audio port from an SDP offer/answer."""
        remote_ip = fallback_ip
        remote_port = 0
        for raw_line in sdp.replace("\r\n", "\n").split("\n"):
            line = raw_line.strip()
            connection = re.fullmatch(r"c=IN\s+IP4\s+([^\s/]+)(?:/\d+)?", line, re.IGNORECASE)
            if connection:
                remote_ip = connection.group(1)
            media = re.match(r"m=audio\s+(\d+)\s+", line, re.IGNORECASE)
            if media:
                remote_port = int(media.group(1))
        return remote_ip, remote_port

    def set_remote_rtp_target(self, remote_ip: str, remote_port: int) -> None:
        """Update the RTP destination after SIP/SDP negotiation completes."""
        if remote_ip:
            self.remote_ip = remote_ip
        if remote_port > 0:
            self.remote_port = remote_port

    def _configured_codecs(self) -> List[str]:
        codecs = []
        for label in self.selected_codecs:
            codec = "PCMA" if "PCMA" in label.upper() else "PCMU" if "PCMU" in label.upper() else ""
            if codec and codec not in codecs:
                codecs.append(codec)
        return codecs or ["PCMU", "PCMA"]

    @staticmethod
    def parse_sdp_codecs(sdp: str) -> List[tuple[str, int]]:
        mappings: Dict[int, str] = {0: "PCMU", 8: "PCMA"}
        payloads: List[int] = []
        for raw_line in sdp.replace("\r\n", "\n").split("\n"):
            line = raw_line.strip()
            media = re.match(r"m=audio\s+\d+\s+\S+\s+(.+)$", line, re.IGNORECASE)
            if media:
                payloads = [int(value) for value in media.group(1).split() if value.isdigit()]
            mapping = re.match(r"a=rtpmap:(\d+)\s+(PCMU|PCMA)/8000", line, re.IGNORECASE)
            if mapping:
                mappings[int(mapping.group(1))] = mapping.group(2).upper()
        return [(mappings[payload], payload) for payload in payloads if payload in mappings]

    def negotiate_codec(self, sdp: str) -> str:
        configured = self._configured_codecs()
        for codec, payload_type in self.parse_sdp_codecs(sdp):
            if codec in configured:
                self.negotiated_codec = codec
                self.payload_types[codec] = payload_type
                return codec
        raise ValueError("Peer SDP has no supported PCMU/PCMA audio codec.")

    def set_negotiated_codec(self, codec: str, payload_type: Optional[int] = None) -> None:
        codec = codec.upper()
        if codec not in ("PCMU", "PCMA") or codec not in self._configured_codecs():
            raise ValueError(f"Unsupported negotiated codec: {codec}")
        self.negotiated_codec = codec
        if payload_type is not None:
            self.payload_types[codec] = int(payload_type)

    def set_srtp_inbound_key(self, key: bytes) -> None:
        if not self.require_srtp or self.srtp is None:
            raise SecureMediaError("SRTP was not required for this media stream")
        self.srtp.set_inbound_key(key)

    def set_muted(self, muted: bool):
        self.muted = muted

    def set_mic_volume(self, percent: float) -> None:
        self.mic_volume = max(0.0, min(1.0, float(percent) / 100.0))

    def set_speaker_volume(self, percent: float) -> None:
        self.speaker_volume = max(0.0, min(1.0, float(percent) / 100.0))

    @staticmethod
    def _apply_gain(pcm: bytes, gain: float) -> bytes:
        if gain == 1.0:
            return pcm
        samples = (
            max(-32768, min(32767, round(sample[0] * gain)))
            for sample in struct.iter_unpack("<h", pcm)
        )
        values = list(samples)
        return struct.pack(f"<{len(values)}h", *values) if values else b""

    def get_rtp_stats(self) -> Dict[str, Any]:
        """Return an atomic snapshot of successfully sent/received RTP packets."""
        with self._rtp_stats_lock:
            return {
                "packets_sent": self.rtp_packets_sent,
                "packets_received": self.rtp_packets_received,
                "streaming": self.is_streaming,
                "local_port": self.local_rtp_port,
                "bind_ip": self.bind_ip,
                "advertised_ip": self.advertised_ip,
                "advertised_port": self.advertised_port,
                "remote_ip": self.remote_ip,
                "remote_port": self.remote_port,
                "nat_status": self.nat_status,
                "input_device": self.active_input_device,
                "output_device": self.active_output_device,
                "audio_error": self.audio_error,
                "media_security": "SDES-SRTP" if self.require_srtp else "RTP",
                "srtp_errors": self.srtp_errors,
                "jitter_duplicates": self.jitter_buffer.duplicates,
                "jitter_lost": self.jitter_buffer.lost,
            }

    @staticmethod
    def _linear_to_ulaw(pcm: bytes) -> bytes:
        encoded = bytearray()
        for (sample,) in struct.iter_unpack("<h", pcm):
            sign = 0x80 if sample < 0 else 0
            magnitude = min(abs(sample), 32635) + 0x84
            exponent = 7
            mask = 0x4000
            while exponent > 0 and not magnitude & mask:
                exponent -= 1
                mask >>= 1
            mantissa = (magnitude >> (exponent + 3)) & 0x0F
            encoded.append((~(sign | (exponent << 4) | mantissa)) & 0xFF)
        return bytes(encoded)

    @staticmethod
    def _resample_pcm16(
        pcm: bytes, source_rate: int, target_rate: int, target_frames: int = 0
    ) -> bytes:
        """Linearly resample mono signed 16-bit PCM without a NumPy dependency."""
        samples = [sample[0] for sample in struct.iter_unpack("<h", pcm)]
        if not samples:
            return b""
        output_count = target_frames or max(1, round(len(samples) * target_rate / source_rate))
        if len(samples) == output_count:
            return pcm
        if output_count == 1 or len(samples) == 1:
            output = [samples[0]] * output_count
        else:
            scale = (len(samples) - 1) / (output_count - 1)
            output = []
            for index in range(output_count):
                position = index * scale
                left = int(position)
                right = min(left + 1, len(samples) - 1)
                fraction = position - left
                output.append(round(samples[left] + ((samples[right] - samples[left]) * fraction)))
        return struct.pack(f"<{len(output)}h", *output)

    @staticmethod
    def _ulaw_to_linear(payload: bytes) -> bytes:
        decoded = bytearray()
        for value in payload:
            value = (~value) & 0xFF
            magnitude = (((value & 0x0F) << 3) + 0x84) << ((value >> 4) & 0x07)
            sample = magnitude - 0x84
            if value & 0x80:
                sample = -sample
            decoded.extend(struct.pack("<h", max(-32768, min(32767, sample))))
        return bytes(decoded)

    @staticmethod
    def _linear_to_alaw(pcm: bytes) -> bytes:
        encoded = bytearray()
        for (sample,) in struct.iter_unpack("<h", pcm):
            sign = 0x80 if sample >= 0 else 0x00
            magnitude = min(abs(sample), 32767)
            if magnitude < 256:
                compressed = magnitude >> 4
            else:
                exponent = min(7, magnitude.bit_length() - 8)
                compressed = (exponent << 4) | ((magnitude >> (exponent + 3)) & 0x0F)
            encoded.append((compressed ^ (sign ^ 0x55)) & 0xFF)
        return bytes(encoded)

    @staticmethod
    def _alaw_to_linear(payload: bytes) -> bytes:
        decoded = bytearray()
        for value in payload:
            value ^= 0x55
            magnitude = (value & 0x0F) << 4
            exponent = (value & 0x70) >> 4
            magnitude += 8 if exponent == 0 else 0x108
            if exponent > 1:
                magnitude <<= exponent - 1
            sample = magnitude if value & 0x80 else -magnitude
            decoded.extend(struct.pack("<h", max(-32768, min(32767, sample))))
        return bytes(decoded)

    def _create_rtp_packet(self, payload: bytes) -> bytes:
        """Build standard RFC 3550 RTP Header (12 bytes) + Payload."""
        version = 2
        padding = 0
        extension = 0
        csrc_count = 0
        marker = 0
        payload_type = 0  # Default PCMU Type 0

        if self.negotiated_codec == "PCMA":
            payload_type = self.payload_types["PCMA"]
        else:
            payload_type = self.payload_types["PCMU"]

        first_byte = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
        second_byte = (marker << 7) | payload_type

        header = struct.pack(
            "!BBHII", first_byte, second_byte, self.sequence_number, self.timestamp, self.ssrc
        )
        self.sequence_number = (self.sequence_number + 1) % 65536
        self.timestamp = (self.timestamp + 160) % 0xFFFFFFFF

        return header + payload

    def _tx_loop(self):
        """Audio transmission loop."""
        while self.is_streaming and self.rtp_socket:
            try:
                if not self.input_stream:
                    time.sleep(0.1)
                    continue
                pcm, overflowed = self.input_stream.read(self.input_block_frames)
                pcm_bytes = self._resample_pcm16(bytes(pcm), self.input_sample_rate, 8000, 160)
                pcm_bytes = self._apply_gain(pcm_bytes, self.mic_volume)
                if self.muted:
                    pcm_bytes = b"\x00" * 320
                if self.remote_ip and self.remote_port > 0:
                    if self.audio_tap_callback:
                        self.audio_tap_callback("tx", pcm_bytes, self._tx_media_frame)
                    self._tx_media_frame += 1
                    if self.negotiated_codec == "PCMA":
                        payload = self._linear_to_alaw(pcm_bytes)
                    else:
                        payload = self._linear_to_ulaw(pcm_bytes)
                    rtp_packet = self._create_rtp_packet(payload)
                    if self.require_srtp:
                        if self.srtp is None:
                            raise SecureMediaError("SRTP protection is not configured")
                        rtp_packet = self.srtp.protect(rtp_packet)
                    self.rtp_socket.sendto(rtp_packet, (self.remote_ip, self.remote_port))
                    with self._rtp_stats_lock:
                        self.rtp_packets_sent += 1
            except Exception:
                break

    def _rx_loop(self, callback: Optional[Callable]):
        """Audio reception loop."""
        while self.is_streaming and self.rtp_socket:
            try:
                self.rtp_socket.settimeout(0.5)
                data, addr = self.rtp_socket.recvfrom(2048)
                if self.require_srtp:
                    try:
                        if self.srtp is None:
                            raise SecureMediaError("SRTP unprotection is not configured")
                        data = self.srtp.unprotect(data)
                    except SecureMediaError:
                        with self._rtp_stats_lock:
                            self.srtp_errors += 1
                        continue
                if len(data) >= 12 and data[0] >> 6 == 2:
                    if self.symmetric_rtp and not self.symmetric_source_learned:
                        self.remote_ip, self.remote_port = addr[0], addr[1]
                        self.symmetric_source_learned = True
                        self.nat_status = f"Symmetric RTP learned {addr[0]}:{addr[1]}"
                    with self._rtp_stats_lock:
                        self.rtp_packets_received += 1
                    csrc_count = data[0] & 0x0F
                    header_length = 12 + (csrc_count * 4)
                    if data[0] & 0x10 and len(data) >= header_length + 4:
                        extension_words = struct.unpack(
                            "!H", data[header_length + 2 : header_length + 4]
                        )[0]
                        header_length += 4 + (extension_words * 4)
                    payload = data[header_length:]
                    if data[0] & 0x20 and payload:
                        payload = payload[: -payload[-1]]
                    payload_type = data[1] & 0x7F
                    if payload:
                        if (
                            payload_type == self.payload_types.get("PCMU")
                            and self.negotiated_codec == "PCMU"
                        ):
                            pcm = self._ulaw_to_linear(payload)
                        elif (
                            payload_type == self.payload_types.get("PCMA")
                            and self.negotiated_codec == "PCMA"
                        ):
                            pcm = self._alaw_to_linear(payload)
                        else:
                            pcm = b""
                        if pcm:
                            pcm = self._apply_gain(pcm, self.speaker_volume)
                            sequence = struct.unpack("!H", data[2:4])[0]
                            timestamp = struct.unpack("!I", data[4:8])[0]
                            ssrc = struct.unpack("!I", data[8:12])[0]
                            packet = RTPAudioPacket(sequence, timestamp, ssrc, payload_type, pcm)
                            self._deliver_rx_frames(self.jitter_buffer.push(packet))
                    if callback:
                        callback(payload, addr)
            except socket.timeout:
                continue
            except Exception:
                break

    def _deliver_rx_frames(self, frames: List[Optional[RTPAudioPacket]]) -> None:
        """Deliver ordered audio/silence to recording independently of speakers."""
        for ready in frames:
            ready_pcm = ready.pcm if ready else b"\x00\x00" * RTP_FRAME_SAMPLES
            if self._rx_media_frame is None:
                self._rx_media_frame = self._tx_media_frame
            if self.audio_tap_callback:
                self.audio_tap_callback("rx", ready_pcm, self._rx_media_frame)
            self._rx_media_frame += 1
            if self.output_stream:
                self.output_stream.write(
                    self._resample_pcm16(ready_pcm, 8000, self.output_sample_rate)
                )
