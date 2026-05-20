from __future__ import annotations

import base64
import csv
import json
import os
import re
import socket
import time
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


def _bool(value: bool | int | str) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    text = str(value).strip().upper()
    if text in {"1", "ON", "TRUE", "YES"}:
        return "ON"
    if text in {"0", "OFF", "FALSE", "NO"}:
        return "OFF"
    raise ValueError(f"Expected boolean-like value, got {value!r}")


def _clean_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "capture"


@dataclass
class RigolConfig:
    host: str = os.getenv("RIGOL_HOST", "192.168.1.34")
    scpi_port: int = int(os.getenv("RIGOL_SCPI_PORT", "5555"))
    http_port: int = int(os.getenv("RIGOL_HTTP_PORT", "80"))
    timeout: float = float(os.getenv("RIGOL_TIMEOUT", "8"))
    storage_dir: Path = Path(os.getenv("RIGOL_STORAGE_DIR", "storage"))


class RigolDHO814:
    def __init__(self, config: RigolConfig | None = None):
        self.config = config or RigolConfig()
        self.config.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.config.storage_dir / "screenshots").mkdir(exist_ok=True)
        (self.config.storage_dir / "waveforms").mkdir(exist_ok=True)

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.http_port}"

    def _socket(self) -> socket.socket:
        s = socket.create_connection(
            (self.config.host, self.config.scpi_port),
            timeout=self.config.timeout,
        )
        s.settimeout(self.config.timeout)
        return s

    def write(self, command: str) -> dict[str, Any]:
        command = command.strip()
        with self._socket() as s:
            s.sendall((command + "\n").encode("utf-8"))
        return {"ok": True, "command": command}

    def query(self, command: str, max_bytes: int = 2_000_000) -> str:
        command = command.strip()
        with self._socket() as s:
            s.sendall((command + "\n").encode("utf-8"))
            data = self._read_response(s, max_bytes=max_bytes)
        return data.decode("utf-8", errors="replace").strip()

    def binary_query(self, command: str, max_bytes: int = 80_000_000) -> bytes:
        command = command.strip()
        with self._socket() as s:
            s.sendall((command + "\n").encode("utf-8"))
            first = s.recv(2)
            if first.startswith(b"#") and len(first) == 2 and first[1:2].isdigit():
                digits = int(first[1:2])
                length = int(self._recv_exact(s, digits).decode("ascii"))
                if length > max_bytes:
                    raise ValueError(f"Instrument response is {length} bytes, above max_bytes={max_bytes}")
                payload = self._recv_exact(s, length)
                return payload
            rest = self._read_response(s, initial=first, max_bytes=max_bytes)
            return rest

    def _read_response(self, s: socket.socket, initial: bytes = b"", max_bytes: int = 2_000_000) -> bytes:
        chunks = [initial] if initial else []
        total = len(initial)
        while total < max_bytes:
            try:
                part = s.recv(65536)
            except socket.timeout:
                break
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if part.endswith(b"\n"):
                break
        return b"".join(chunks)

    def _recv_exact(self, s: socket.socket, n: int) -> bytes:
        data = bytearray()
        while len(data) < n:
            part = s.recv(n - len(data))
            if not part:
                raise ConnectionError(f"Socket closed while reading {n} bytes")
            data.extend(part)
        return bytes(data)

    def idn(self) -> dict[str, str]:
        parts = self.query("*IDN?").split(",")
        return {
            "manufacturer": parts[0] if len(parts) > 0 else "",
            "model": parts[1] if len(parts) > 1 else "",
            "serial": parts[2] if len(parts) > 2 else "",
            "firmware": parts[3] if len(parts) > 3 else "",
            "raw": ",".join(parts),
        }

    def web_get(self, path: str) -> str:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = requests.get(url, timeout=self.config.timeout)
        response.raise_for_status()
        return response.text

    def welcome_info(self) -> dict[str, str]:
        items = self.web_get("/welcome.do").split("$")
        data = {f"field_{i}": value for i, value in enumerate(items)}
        data.update(
            {
                "manufacturer": items[0] if len(items) > 0 else "",
                "model": items[1] if len(items) > 1 else "",
                "serial": items[2] if len(items) > 2 else "",
                "firmware": items[3] if len(items) > 3 else "",
                "mac": items[4] if len(items) > 4 else "",
                "ip": items[5] if len(items) > 5 else "",
                "usb": items[6] if len(items) > 6 else "",
                "hostname": items[7] if len(items) > 7 else "",
                "raw": "$".join(items),
            }
        )
        return data

    def network_info(self) -> dict[str, str]:
        items = self.web_get("/network.do").split("$")
        data = {f"field_{i}": value for i, value in enumerate(items)}
        data.update(
            {
                "legacy_ip": items[0] if len(items) > 0 else "",
                "legacy_subnet": items[1] if len(items) > 1 else "",
                "legacy_gateway": items[2] if len(items) > 2 else "",
                "legacy_dns": items[3] if len(items) > 3 else "",
                "legacy_mode": items[4] if len(items) > 4 else "",
                "legacy_status": items[5] if len(items) > 5 else "",
                "legacy_hostname": items[8] if len(items) > 8 else "",
                "raw": "$".join(items),
            }
        )
        return data

    def screenshot(self, name: str | None = None, include_base64: bool = False) -> dict[str, Any]:
        payload = self.binary_query(":DISPlay:DATA? PNG", max_bytes=30_000_000)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        filename = _clean_name(name or f"dho814-{stamp}") + ".png"
        path = self.config.storage_dir / "screenshots" / filename
        path.write_bytes(payload)
        latest = self.config.storage_dir / "screenshots" / "latest.png"
        latest.write_bytes(payload)
        result: dict[str, Any] = {
            "path": str(path.resolve()),
            "latest": str(latest.resolve()),
            "bytes": len(payload),
            "mime_type": "image/png",
        }
        if include_base64:
            result["base64"] = base64.b64encode(payload).decode("ascii")
        return result

    def capture_burst(
        self,
        count: int = 10,
        interval_s: float = 0.2,
        name: str | None = None,
        include_base64_latest: bool = False,
    ) -> dict[str, Any]:
        count = max(1, min(int(count), 200))
        interval_s = max(0.0, float(interval_s))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stem = _clean_name(name or f"burst-{stamp}")
        directory = self.config.storage_dir / "screenshots" / stem
        directory.mkdir(parents=True, exist_ok=True)
        frames = []
        start = time.monotonic()
        latest_payload = b""
        for idx in range(count):
            if idx:
                elapsed_target = start + idx * interval_s
                delay = elapsed_target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            payload = self.binary_query(":DISPlay:DATA? PNG", max_bytes=30_000_000)
            latest_payload = payload
            path = directory / f"frame-{idx + 1:04d}.png"
            path.write_bytes(payload)
            frames.append({"index": idx + 1, "path": str(path.resolve()), "bytes": len(payload)})
        latest = self.config.storage_dir / "screenshots" / "latest.png"
        if latest_payload:
            latest.write_bytes(latest_payload)
        result: dict[str, Any] = {
            "directory": str(directory.resolve()),
            "frames": frames,
            "count": len(frames),
            "interval_s": interval_s,
            "duration_s": time.monotonic() - start,
            "latest": str(latest.resolve()),
        }
        if include_base64_latest and latest_payload:
            result["latest_base64"] = base64.b64encode(latest_payload).decode("ascii")
        return result

    def record_screen_gif(
        self,
        duration_s: float = 3.0,
        fps: float = 5.0,
        name: str | None = None,
        keep_frames: bool = True,
    ) -> dict[str, Any]:
        from PIL import Image

        duration_s = max(0.2, min(float(duration_s), 60.0))
        fps = max(0.2, min(float(fps), 20.0))
        count = max(1, int(round(duration_s * fps)))
        interval_s = 1.0 / fps
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stem = _clean_name(name or f"record-{stamp}")
        directory = self.config.storage_dir / "recordings" / stem
        directory.mkdir(parents=True, exist_ok=True)
        gif_path = directory / f"{stem}.gif"
        frames_info = []
        images = []
        start = time.monotonic()
        latest_payload = b""
        for idx in range(count):
            if idx:
                target = start + idx * interval_s
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            payload = self.binary_query(":DISPlay:DATA? PNG", max_bytes=30_000_000)
            latest_payload = payload
            image = Image.open(BytesIO(payload)).convert("P", palette=Image.ADAPTIVE)
            images.append(image)
            if keep_frames:
                frame_path = directory / f"frame-{idx + 1:04d}.png"
                frame_path.write_bytes(payload)
                frames_info.append({"index": idx + 1, "path": str(frame_path.resolve()), "bytes": len(payload)})
        if not images:
            raise RuntimeError("No frames captured")
        images[0].save(
            gif_path,
            save_all=True,
            append_images=images[1:],
            duration=max(20, int(1000 / fps)),
            loop=0,
            optimize=False,
        )
        latest = self.config.storage_dir / "screenshots" / "latest.png"
        latest.parent.mkdir(exist_ok=True)
        if latest_payload:
            latest.write_bytes(latest_payload)
        return {
            "gif_path": str(gif_path.resolve()),
            "directory": str(directory.resolve()),
            "frames": frames_info,
            "frame_count": len(images),
            "fps": fps,
            "duration_s": time.monotonic() - start,
            "latest": str(latest.resolve()),
        }

    def state_snapshot(self) -> dict[str, Any]:
        queries = {
            "idn": "*IDN?",
            "trigger_status": ":TRIGger:STATus?",
            "timebase_scale": ":TIMebase:MAIN:SCALe?",
            "timebase_offset": ":TIMebase:MAIN:OFFSet?",
            "acquire_type": ":ACQuire:TYPE?",
            "sample_rate": ":ACQuire:SRATe?",
            "memory_depth": ":ACQuire:MDEPth?",
            "waveform_source": ":WAVeform:SOURce?",
        }
        state: dict[str, Any] = {}
        for key, cmd in queries.items():
            try:
                state[key] = self.query(cmd)
            except Exception as exc:
                state[key] = {"error": str(exc), "command": cmd}
        channels = {}
        for n in range(1, 5):
            channels[str(n)] = {}
            for key, cmd in {
                "display": f":CHANnel{n}:DISPlay?",
                "scale": f":CHANnel{n}:SCALe?",
                "offset": f":CHANnel{n}:OFFSet?",
                "coupling": f":CHANnel{n}:COUPling?",
                "probe": f":CHANnel{n}:PROBe?",
            }.items():
                try:
                    channels[str(n)][key] = self.query(cmd)
                except Exception as exc:
                    channels[str(n)][key] = {"error": str(exc)}
        state["channels"] = channels
        return state

    def set_channel(
        self,
        channel: int,
        display: bool | None = None,
        scale: float | None = None,
        offset: float | None = None,
        coupling: str | None = None,
        probe: str | float | None = None,
        invert: bool | None = None,
        bandwidth_limit: str | None = None,
    ) -> dict[str, Any]:
        self._check_channel(channel)
        commands: list[str] = []
        if display is not None:
            commands.append(f":CHANnel{channel}:DISPlay {_bool(display)}")
        if scale is not None:
            commands.append(f":CHANnel{channel}:SCALe {scale}")
        if offset is not None:
            commands.append(f":CHANnel{channel}:OFFSet {offset}")
        if coupling is not None:
            commands.append(f":CHANnel{channel}:COUPling {coupling.upper()}")
        if probe is not None:
            commands.append(f":CHANnel{channel}:PROBe {probe}")
        if invert is not None:
            commands.append(f":CHANnel{channel}:INVert {_bool(invert)}")
        if bandwidth_limit is not None:
            commands.append(f":CHANnel{channel}:BWLimit {bandwidth_limit.upper()}")
        for cmd in commands:
            self.write(cmd)
        return {"ok": True, "commands": commands}

    def set_timebase(self, scale: float | None = None, offset: float | None = None, mode: str | None = None) -> dict[str, Any]:
        commands: list[str] = []
        if mode is not None:
            commands.append(f":TIMebase:MODE {mode.upper()}")
        if scale is not None:
            commands.append(f":TIMebase:MAIN:SCALe {scale}")
        if offset is not None:
            commands.append(f":TIMebase:MAIN:OFFSet {offset}")
        for cmd in commands:
            self.write(cmd)
        return {"ok": True, "commands": commands}

    def set_trigger(self, source: str | None = None, level: float | None = None, sweep: str | None = None, mode: str | None = None, slope: str | None = None) -> dict[str, Any]:
        commands: list[str] = []
        if mode is not None:
            commands.append(f":TRIGger:MODE {mode.upper()}")
        if source is not None:
            commands.append(f":TRIGger:EDGE:SOURce {source.upper()}")
        if slope is not None:
            commands.append(f":TRIGger:EDGE:SLOPe {slope.upper()}")
        if level is not None:
            commands.append(f":TRIGger:EDGE:LEVel {level}")
        if sweep is not None:
            commands.append(f":TRIGger:SWEep {sweep.upper()}")
        for cmd in commands:
            self.write(cmd)
        return {"ok": True, "commands": commands}

    def measure(self, item: str, source: str = "CHAN1") -> dict[str, Any]:
        item = item.upper()
        source = source.upper()
        self.write(f":MEASure:SOURce {source}")
        self.write(f":MEASure:ITEM {item},{source}")
        value = self.query(f":MEASure:ITEM? {item},{source}")
        return {"item": item, "source": source, "value": value}

    def all_measurements(self, source: str = "CHAN1") -> dict[str, Any]:
        items = [
            "VMAX", "VMIN", "VPP", "VTOP", "VBASe", "VAMP", "VAVG", "VRMS",
            "OVERshoot", "PREShoot", "PERiod", "FREQuency", "RTIMe", "FTIMe",
            "PWIDth", "NWIDth", "PDUTy", "NDUTy", "AREA", "PAREA", "NAREA",
        ]
        values = {}
        for item in items:
            try:
                values[item] = self.measure(item, source)["value"]
            except Exception as exc:
                values[item] = {"error": str(exc)}
        return {"source": source.upper(), "measurements": values}

    def save_waveform(self, source: str = "CHAN1", points: str | int = "MAX", fmt: str = "BYTE", name: str | None = None) -> dict[str, Any]:
        source = source.upper()
        fmt = fmt.upper()
        self.write(f":WAVeform:SOURce {source}")
        self.write(f":WAVeform:FORMat {fmt}")
        self.write(f":WAVeform:POINts {points}")
        preamble = {
            "source": source,
            "format": self.query(":WAVeform:FORMat?"),
            "points": self.query(":WAVeform:POINts?"),
            "xincrement": self.query(":WAVeform:XINCrement?"),
            "xorigin": self.query(":WAVeform:XORigin?"),
            "xreference": self.query(":WAVeform:XREFerence?"),
            "yincrement": self.query(":WAVeform:YINCrement?"),
            "yorigin": self.query(":WAVeform:YORigin?"),
            "yreference": self.query(":WAVeform:YREFerence?"),
        }
        raw = self.binary_query(":WAVeform:DATA?", max_bytes=100_000_000)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stem = _clean_name(name or f"{source}-{stamp}")
        bin_path = self.config.storage_dir / "waveforms" / f"{stem}.bin"
        json_path = self.config.storage_dir / "waveforms" / f"{stem}.json"
        csv_path = self.config.storage_dir / "waveforms" / f"{stem}.csv"
        bin_path.write_bytes(raw)
        json_path.write_text(json.dumps(preamble, indent=2), encoding="utf-8")
        self._write_waveform_csv(raw, preamble, csv_path)
        return {
            "source": source,
            "raw_path": str(bin_path.resolve()),
            "metadata_path": str(json_path.resolve()),
            "csv_path": str(csv_path.resolve()),
            "bytes": len(raw),
            "preamble": preamble,
        }

    def _write_waveform_csv(self, raw: bytes, preamble: dict[str, str], path: Path) -> None:
        try:
            xinc = float(preamble["xincrement"])
            xorig = float(preamble["xorigin"])
            xref = float(preamble["xreference"])
            yinc = float(preamble["yincrement"])
            yorig = float(preamble["yorigin"])
            yref = float(preamble["yreference"])
            samples = raw if preamble["format"].upper().startswith("BYTE") else raw
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["index", "time_s", "raw", "voltage_v"])
                for i, y in enumerate(samples):
                    writer.writerow([i, (i - xref) * xinc + xorig, y, (y - yref) * yinc + yorig])
        except Exception as exc:
            path.write_text(f"CSV conversion failed: {exc}\n", encoding="utf-8")

    def touch(self, event_type: str, x: float, y: float) -> dict[str, Any]:
        import asyncio
        import websockets

        async def _send() -> None:
            uri = f"ws://{self.config.host}:9002"
            payload = json.dumps({"type": event_type, "downDelta": 0, "clientX": x, "clientY": y})
            async with websockets.connect(uri, open_timeout=self.config.timeout) as ws:
                await ws.send(payload)

        asyncio.run(_send())
        return {"ok": True, "event_type": event_type, "x": x, "y": y}

    def configure_waveform_recording(
        self,
        enable: bool | None = True,
        frames: int | None = None,
        interval_s: float | None = None,
        prompt: bool | None = None,
    ) -> dict[str, Any]:
        commands: list[str] = []
        if enable is not None:
            commands.append(f":RECord:WRECord:ENABle {_bool(enable)}")
        if frames is not None:
            commands.append(f":RECord:WRECord:FRAMes {max(1, int(frames))}")
        if interval_s is not None:
            commands.append(f":RECord:WRECord:FINTerval {float(interval_s)}")
        if prompt is not None:
            commands.append(f":RECord:WRECord:PROMpt {_bool(prompt)}")
        for cmd in commands:
            self.write(cmd)
        return {"ok": True, "commands": commands, "status": self.waveform_recording_status()}

    def waveform_recording_control(self, operate: str) -> dict[str, Any]:
        op = operate.strip().upper()
        aliases = {"START": "RUN", "ON": "RUN", "RUN": "RUN", "STOP": "STOP", "OFF": "STOP"}
        if op not in aliases:
            raise ValueError("operate must be RUN/START/ON or STOP/OFF")
        command = f":RECord:WRECord:OPERate {aliases[op]}"
        self.write(command)
        return {"ok": True, "command": command, "status": self.waveform_recording_status()}

    def waveform_recording_status(self) -> dict[str, Any]:
        queries = {
            "enabled": ":RECord:WRECord:ENABle?",
            "operate": ":RECord:WRECord:OPERate?",
            "frames": ":RECord:WRECord:FRAMes?",
            "max_frames": ":RECord:WRECord:FMAX?",
            "frame_interval_s": ":RECord:WRECord:FINTerval?",
            "current_frame": ":RECord:WREPlay:FCURrent?",
            "play_mode": ":RECord:WREPlay:MODE?",
        }
        result: dict[str, Any] = {}
        for key, command in queries.items():
            try:
                result[key] = self.query(command)
            except Exception as exc:
                result[key] = {"error": str(exc), "command": command}
        return result

    def save_to_scope_storage(
        self,
        kind: str,
        path: str,
        overwrite: bool = True,
        image_format: str | None = None,
    ) -> dict[str, Any]:
        kind_key = kind.strip().lower().replace("-", "_")
        allowed = {
            "image": ":SAVE:IMAGe",
            "setup": ":SAVE:SETup",
            "screen_waveform": ":SAVE:WAVeform",
            "memory_waveform": ":SAVE:MEMory:WAVeform",
        }
        if kind_key not in allowed:
            raise ValueError(f"kind must be one of {', '.join(allowed)}")
        commands = [f":SAVE:OVERlap {_bool(overwrite)}"]
        if kind_key == "image" and image_format:
            commands.append(f":SAVE:IMAGe:FORMat {image_format.upper()}")
        commands.append(f"{allowed[kind_key]} {path}")
        for cmd in commands:
            self.write(cmd)
        status = None
        for _ in range(20):
            try:
                status = self.query(":SAVE:STATus?")
                if status == "1":
                    break
            except Exception:
                pass
            time.sleep(0.2)
        return {"ok": True, "kind": kind_key, "scope_path": path, "commands": commands, "save_status": status}

    def _check_channel(self, channel: int) -> None:
        if channel not in {1, 2, 3, 4}:
            raise ValueError("DHO814 channels are 1, 2, 3, or 4")
