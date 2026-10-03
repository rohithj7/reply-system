"""Extract the packet fixture constants, legacy prompts and TypeScript tool reference.

Usage:
    uv run python scripts/extract_packet.py          # write the extracted files
    uv run python scripts/extract_packet.py --check  # fail if any file differs from the packet

Standard library only. The tests import this module to parse the packet.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKET = REPO_ROOT / "docs" / "assignment" / "pre-deposit-respond-packet.md"

_OPEN_FENCE = re.compile(r"^```[a-z]*\n", re.MULTILINE)
_CLOSE_FENCE = re.compile(r"^```$", re.MULTILINE)
_CONST = re.compile(r"const ([A-Z][A-Z0-9_]*) = ")
_TS_STRING_FIELD = re.compile(r'(\w+):\s*("(?:[^"\\\n]|\\.)*")')


def read_packet() -> str:
    return PACKET.read_text(encoding="utf-8")


def fenced_block(packet: str, heading: str) -> str:
    """Return the body of the first fenced block after `heading`, without the fences."""
    start = packet.index(f"\n{heading}\n")
    opening = _OPEN_FENCE.search(packet, start)
    if opening is None:
        raise ValueError(f"no fenced block after {heading!r}")
    closing = _CLOSE_FENCE.search(packet, opening.end())
    if closing is None:
        raise ValueError(f"unclosed fenced block after {heading!r}")
    return packet[opening.end() : closing.start() - 1]


def parse_constants(block: str) -> dict[str, Any]:
    """Parse `const NAME = <template literal | JSON>;` statements, in order."""
    decoder = json.JSONDecoder()
    constants: dict[str, Any] = {}
    pos = 0
    while match := _CONST.search(block, pos):
        if block[pos : match.start()].strip():
            raise ValueError(f"unexpected text before {match.group(1)}")
        name, pos = match.group(1), match.end()
        value: Any
        if block[pos] == "`":
            end = block.index("`", pos + 1)
            value = block[pos + 1 : end]
            if "\\" in value or "${" in value:
                raise ValueError(f"{name}: template escapes or interpolation are not supported")
            pos = end + 1
        else:
            value, pos = decoder.raw_decode(block, pos)
        if block[pos] != ";":
            raise ValueError(f"{name}: expected ';'")
        pos += 1
        constants[name] = value
    if block[pos:].strip():
        raise ValueError("unexpected text after the last constant")
    return constants


def ts_string_fields(block: str) -> list[tuple[str, str]]:
    """Return `(key, value)` for every `key: "string"` property in a TypeScript literal."""
    return [(key, json.loads(literal)) for key, literal in _TS_STRING_FIELD.findall(block)]


def extracted_files(packet: str) -> dict[Path, str]:
    constants = parse_constants(fenced_block(packet, "### Constants"))
    legacy = REPO_ROOT / "src" / "doctours_reply" / "prompts" / "legacy"
    return {
        REPO_ROOT / "resources" / "fixtures" / "packet" / "constants.json": (
            json.dumps(constants, ensure_ascii=False, indent=2) + "\n"
        ),
        legacy / "system_prompt.txt": fenced_block(packet, "### System prompt"),
        legacy / "user_message.txt": fenced_block(packet, "### User message"),
        REPO_ROOT / "tests" / "conformance" / "reference" / "packet_tools.ts": fenced_block(
            packet, "### Tools"
        ),
    }


def stale_files(packet: str) -> list[Path]:
    """Return the extracted files that are missing or differ from the packet."""
    return [
        path
        for path, content in extracted_files(packet).items()
        if not path.is_file() or path.read_text(encoding="utf-8") != content
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args()
    packet = read_packet()
    if args.check:
        stale = stale_files(packet)
        for path in stale:
            print(f"stale: {path.relative_to(REPO_ROOT)}")
        return 1 if stale else 0
    for path, content in extracted_files(packet).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
