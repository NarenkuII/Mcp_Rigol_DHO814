from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "DHO800900_ProgrammingGuide_EN.txt"
DST = ROOT / "docs" / "command_catalog.json"

TOC_RE = re.compile(r"^\s*(?P<section>\d+(?:\.\d+)+)\s+(?P<command>[:*][A-Za-z0-9:<>\[\]?]+(?:[:][A-Za-z0-9?<>\[\]]+)*)\s+\.{3,}\s*(?P<page>\d+)\s*$")
SIGNATURE_RE = re.compile(r"^\s*(?P<command>[:*][A-Za-z][A-Za-z0-9:<>\[\]?]*(?::[A-Za-z0-9?<>\[\]]+)*)\s*(?P<args><[^>]+>(?:,<[^>]+>)?)?\s*$")


def normalize(cmd: str) -> str:
    return re.sub(r"\s+", "", cmd.strip())


def main() -> None:
    lines = SRC.read_text(encoding="utf-8", errors="replace").splitlines()
    by_command: dict[str, dict[str, str]] = {}

    for line in lines[:900]:
        match = TOC_RE.match(line)
        if not match:
            continue
        command = normalize(match.group("command"))
        by_command.setdefault(command, {"command": command})
        by_command[command].update({"section": match.group("section"), "page": match.group("page")})

    for idx, line in enumerate(lines):
        match = SIGNATURE_RE.match(line)
        if not match:
            continue
        command = normalize(match.group("command"))
        if len(command) < 2 or command in {":", "*"}:
            continue
        item = by_command.setdefault(command, {"command": command})
        if match.group("args"):
            item.setdefault("arguments", match.group("args"))
        if "line" not in item:
            item["line"] = str(idx + 1)

    commands = sorted(by_command.values(), key=lambda item: item["command"].replace("<N>", "<n>").upper())
    DST.write_text(json.dumps(commands, indent=2), encoding="utf-8")
    print(f"Wrote {len(commands)} commands to {DST}")


if __name__ == "__main__":
    main()

