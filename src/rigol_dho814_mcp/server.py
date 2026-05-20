from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import RigolConfig, RigolDHO814
from .docs import DOCS_DIR, load_command_catalog, read_doc, search_commands, search_docs


mcp = FastMCP(
    "rigol-dho814",
    instructions=(
        "Control a Rigol DHO814 oscilloscope over LAN. Prefer high-level tools for common "
        "changes, use scpi_query/scpi_write for full SCPI coverage, and consult the bundled "
        "programming/user guide resources before changing unfamiliar settings."
    ),
)


def scope() -> RigolDHO814:
    return RigolDHO814(
        RigolConfig(
            host=os.getenv("RIGOL_HOST", "192.168.1.34"),
            scpi_port=int(os.getenv("RIGOL_SCPI_PORT", "5555")),
            http_port=int(os.getenv("RIGOL_HTTP_PORT", "80")),
            timeout=float(os.getenv("RIGOL_TIMEOUT", "8")),
            storage_dir=Path(os.getenv("RIGOL_STORAGE_DIR", "storage")),
        )
    )


@mcp.tool()
def identify() -> dict[str, Any]:
    """Return *IDN? plus the web welcome fields from the DHO814."""
    dev = scope()
    return {"scpi": dev.idn(), "web": dev.welcome_info()}


@mcp.tool()
def network_status() -> dict[str, Any]:
    """Return network status parsed from the Rigol web interface."""
    return scope().network_info()


@mcp.tool()
def get_scope_state() -> dict[str, Any]:
    """Collect a broad state snapshot: acquisition, trigger, timebase, and all channels."""
    return scope().state_snapshot()


@mcp.tool()
def scpi_query(command: str, max_bytes: int = 2_000_000) -> str:
    """Send any SCPI query and return the text response. Use for full command coverage."""
    return scope().query(command, max_bytes=max_bytes)


@mcp.tool()
def scpi_write(command: str) -> dict[str, Any]:
    """Send any SCPI command that does not return a response. Use for full parameter control."""
    return scope().write(command)


@mcp.tool()
def scpi_binary_query(command: str, save_as: str | None = None, max_bytes: int = 80_000_000) -> dict[str, Any]:
    """Send a binary SCPI query and optionally save the payload under the MCP storage directory."""
    payload = scope().binary_query(command, max_bytes=max_bytes)
    result: dict[str, Any] = {"bytes": len(payload)}
    if save_as:
        storage = Path(os.getenv("RIGOL_STORAGE_DIR", "storage"))
        storage.mkdir(parents=True, exist_ok=True)
        path = storage / save_as
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        result["path"] = str(path.resolve())
    else:
        result["preview_hex"] = payload[:256].hex()
    return result


@mcp.tool()
def run() -> dict[str, Any]:
    """Start continuous acquisition."""
    return scope().write(":RUN")


@mcp.tool()
def stop() -> dict[str, Any]:
    """Stop acquisition."""
    return scope().write(":STOP")


@mcp.tool()
def single() -> dict[str, Any]:
    """Arm a single acquisition."""
    return scope().write(":SINGle")


@mcp.tool()
def force_trigger() -> dict[str, Any]:
    """Force a trigger event."""
    return scope().write(":TFORce")


@mcp.tool()
def autoset() -> dict[str, Any]:
    """Run Rigol autoset."""
    return scope().write(":AUToset")


@mcp.tool()
def set_channel(
    channel: int,
    display: bool | None = None,
    scale: float | None = None,
    offset: float | None = None,
    coupling: str | None = None,
    probe: str | None = None,
    invert: bool | None = None,
    bandwidth_limit: str | None = None,
) -> dict[str, Any]:
    """Set channel display, volts/div scale, offset, coupling, probe ratio, invert, or bandwidth limit."""
    return scope().set_channel(channel, display, scale, offset, coupling, probe, invert, bandwidth_limit)


@mcp.tool()
def set_timebase(scale: float | None = None, offset: float | None = None, mode: str | None = None) -> dict[str, Any]:
    """Set horizontal timebase mode, seconds/div scale, or horizontal offset."""
    return scope().set_timebase(scale=scale, offset=offset, mode=mode)


@mcp.tool()
def set_trigger(
    source: str | None = None,
    level: float | None = None,
    sweep: str | None = None,
    mode: str | None = "EDGE",
    slope: str | None = None,
) -> dict[str, Any]:
    """Set common edge-trigger parameters. Use scpi_write for advanced trigger modes."""
    return scope().set_trigger(source=source, level=level, sweep=sweep, mode=mode, slope=slope)


@mcp.tool()
def measure(item: str, source: str = "CHAN1") -> dict[str, Any]:
    """Enable/read one automatic measurement item, e.g. VPP, FREQuency, PERiod, VAVG, VRMS."""
    return scope().measure(item=item, source=source)


@mcp.tool()
def measure_many(source: str = "CHAN1") -> dict[str, Any]:
    """Read a broad set of common automatic measurements for a source."""
    return scope().all_measurements(source=source)


@mcp.tool()
def capture_screenshot(name: str | None = None, include_base64: bool = False) -> dict[str, Any]:
    """Capture the oscilloscope screen as PNG, save it, and update rigol://screenshot/latest."""
    return scope().screenshot(name=name, include_base64=include_base64)


@mcp.tool()
def capture_screenshot_burst(
    count: int = 10,
    interval_s: float = 0.2,
    name: str | None = None,
    include_base64_latest: bool = False,
) -> dict[str, Any]:
    """Capture a timed burst of screenshots as individual PNG frames."""
    return scope().capture_burst(
        count=count,
        interval_s=interval_s,
        name=name,
        include_base64_latest=include_base64_latest,
    )


@mcp.tool()
def record_screen_gif(
    duration_s: float = 3.0,
    fps: float = 5.0,
    name: str | None = None,
    keep_frames: bool = True,
) -> dict[str, Any]:
    """Record the oscilloscope display by repeated SCPI screenshots and save an animated GIF."""
    return scope().record_screen_gif(
        duration_s=duration_s,
        fps=fps,
        name=name,
        keep_frames=keep_frames,
    )


@mcp.tool()
def save_waveform(source: str = "CHAN1", points: str = "MAX", fmt: str = "BYTE", name: str | None = None) -> dict[str, Any]:
    """Download waveform data, save raw binary plus converted CSV and metadata."""
    return scope().save_waveform(source=source, points=points, fmt=fmt, name=name)


@mcp.tool()
def web_touch(event_type: str, x: float, y: float) -> dict[str, Any]:
    """Send a web-control touch/mouse event to the screen at native 1024x600 coordinates."""
    return scope().touch(event_type=event_type, x=x, y=y)


@mcp.tool()
def configure_waveform_recording(
    enable: bool | None = True,
    frames: int | None = None,
    interval_s: float | None = None,
    prompt: bool | None = None,
) -> dict[str, Any]:
    """Configure the oscilloscope internal waveform recorder (:RECord:WRECord:*)."""
    return scope().configure_waveform_recording(
        enable=enable,
        frames=frames,
        interval_s=interval_s,
        prompt=prompt,
    )


@mcp.tool()
def waveform_recording_control(operate: str) -> dict[str, Any]:
    """Start or stop the oscilloscope internal waveform recorder. operate=RUN/START or STOP."""
    return scope().waveform_recording_control(operate=operate)


@mcp.tool()
def waveform_recording_status() -> dict[str, Any]:
    """Read internal waveform recording/playback status and frame settings."""
    return scope().waveform_recording_status()


@mcp.tool()
def save_to_scope_storage(
    kind: str,
    path: str,
    overwrite: bool = True,
    image_format: str | None = None,
) -> dict[str, Any]:
    """Save image/setup/waveform to the oscilloscope storage, e.g. C:/cap.png or D:/wave.csv."""
    return scope().save_to_scope_storage(
        kind=kind,
        path=path,
        overwrite=overwrite,
        image_format=image_format,
    )


@mcp.tool()
def search_scope_docs(query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Search the bundled Rigol programming guide, user guide, and datasheet."""
    return search_docs(query=query, limit=limit)


@mcp.tool()
def search_scpi_commands(query: str, limit: int = 25) -> list[dict[str, str]]:
    """Search the generated SCPI command catalog extracted from the programming guide."""
    return search_commands(query=query, limit=limit)


@mcp.tool()
def list_scpi_commands(limit: int = 200) -> list[dict[str, str]]:
    """List the extracted SCPI command catalog."""
    return load_command_catalog()[:limit]


@mcp.resource("rigol://docs/programming-guide")
def programming_guide() -> str:
    """Rigol DHO800/DHO900 Programming Guide text."""
    return read_doc("programming")


@mcp.resource("rigol://docs/user-guide")
def user_guide() -> str:
    """Rigol DHO800 Series User Guide text."""
    return read_doc("userguide")


@mcp.resource("rigol://docs/datasheet")
def datasheet() -> str:
    """Rigol DHO800 datasheet text."""
    return read_doc("datasheet")


@mcp.resource("rigol://commands/catalog")
def command_catalog() -> str:
    """Generated JSON catalog of SCPI commands extracted from the programming guide."""
    return (DOCS_DIR / "command_catalog.json").read_text(encoding="utf-8")


@mcp.resource("rigol://screenshot/latest", mime_type="image/png")
def latest_screenshot() -> bytes:
    """Most recent captured screenshot as PNG."""
    path = Path(os.getenv("RIGOL_STORAGE_DIR", "storage")) / "screenshots" / "latest.png"
    if not path.exists():
        return b""
    return path.read_bytes()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
