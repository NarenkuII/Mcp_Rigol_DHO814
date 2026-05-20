# Rigol DHO814 MCP

MCP server for controlling a Rigol DHO814 oscilloscope over LAN.

The server targets the scope at `192.168.1.34` by default and uses:

- Raw SCPI over TCP port `5555` for full instrument control.
- Rigol web endpoints on port `80` for welcome/network metadata.
- SCPI `:DISPlay:DATA? PNG` for screenshots.
- Optional web-control touch events over WebSocket port `9002`.
- Bundled DHO800/DHO900 programming guide, DHO800 user guide, and DHO800 datasheet as MCP resources plus searchable tools.

## MCP Tools

Core control:

- `identify`
- `network_status`
- `get_scope_state`
- `run`
- `stop`
- `single`
- `force_trigger`
- `autoset`

Full SCPI access:

- `scpi_query`
- `scpi_write`
- `scpi_binary_query`
- `search_scpi_commands`
- `list_scpi_commands`

High-level helpers:

- `set_channel`
- `set_timebase`
- `set_trigger`
- `measure`
- `measure_many`
- `capture_screenshot`
- `save_waveform`
- `web_touch`
- `search_scope_docs`

Resources:

- `rigol://docs/programming-guide`
- `rigol://docs/user-guide`
- `rigol://docs/datasheet`
- `rigol://commands/catalog`
- `rigol://screenshot/latest`

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .
$env:RIGOL_HOST = "192.168.1.34"
$env:RIGOL_STORAGE_DIR = "storage"
.\.venv\Scripts\rigol-dho814-mcp
```

## Docker

```bash
docker build -t rigol-dho814-mcp:latest .
docker run --rm -i \
  -e RIGOL_HOST=192.168.1.34 \
  -e RIGOL_STORAGE_DIR=/data \
  -v rigol-dho814-data:/data \
  rigol-dho814-mcp:latest
```

For Codex MCP configuration, use a stdio command similar to:

```toml
[mcp_servers.rigol-dho814]
command = "docker"
args = ["run", "--rm", "-i", "-e", "RIGOL_HOST=192.168.1.34", "-v", "rigol-dho814-data:/data", "rigol-dho814-mcp:latest"]
enabled = true
```

## Safety

`scpi_write` can change any exposed instrument setting. Use `search_scope_docs` or `search_scpi_commands` before unfamiliar commands, and prefer the high-level helpers for common setup changes.

