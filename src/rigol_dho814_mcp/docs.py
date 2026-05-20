from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
_default_docs = Path.cwd() / "docs"
if not _default_docs.exists():
    _default_docs = ROOT / "docs"
DOCS_DIR = Path(os.getenv("RIGOL_DOCS_DIR", _default_docs))

DOC_FILES = {
    "programming": "DHO800900_ProgrammingGuide_EN.txt",
    "userguide": "DHO800-Series_userguide_EN.txt",
    "datasheet": "DHO800_DataSheet_EN.txt",
}


def read_doc(name: str, limit: int | None = None) -> str:
    if name not in DOC_FILES:
        raise ValueError(f"Unknown doc {name!r}. Use one of: {', '.join(DOC_FILES)}")
    text = (DOCS_DIR / DOC_FILES[name]).read_text(encoding="utf-8", errors="replace")
    return text[:limit] if limit else text


def search_docs(query: str, limit: int = 12, context_lines: int = 2) -> list[dict[str, Any]]:
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_:*?<>.-]+", query) if t]
    if not terms:
        return []
    results: list[dict[str, Any]] = []
    for doc_name, filename in DOC_FILES.items():
        path = DOCS_DIR / filename
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines):
            hay = line.lower()
            if all(term in hay for term in terms):
                start = max(0, idx - context_lines)
                end = min(len(lines), idx + context_lines + 1)
                results.append(
                    {
                        "doc": doc_name,
                        "line": idx + 1,
                        "text": line.strip(),
                        "context": "\n".join(lines[start:end]).strip(),
                    }
                )
                if len(results) >= limit:
                    return results
    return results


def load_command_catalog() -> list[dict[str, str]]:
    path = DOCS_DIR / "command_catalog.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def search_commands(query: str, limit: int = 25) -> list[dict[str, str]]:
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_:*?<>.-]+", query) if t]
    commands = load_command_catalog()
    if not terms:
        return commands[:limit]
    matches = []
    for item in commands:
        hay = " ".join(str(v) for v in item.values()).lower()
        if all(term in hay for term in terms):
            matches.append(item)
            if len(matches) >= limit:
                break
    return matches
