"""Expected outputs are evaluation-only (packet L719): runtime files must not contain them."""

import json
import re
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOTS = (REPO_ROOT / "src" / "doctours_reply", REPO_ROOT / "resources")
# Byte-pinned to the packet by tests/unit/test_packet_fixture.py. The packet's own system
# prompt quotes one official message as an example, so these files are exempt.
VERBATIM_PACKET_FILES = {
    REPO_ROOT / "src" / "doctours_reply" / "prompts" / "legacy" / "system_prompt.txt",
    REPO_ROOT / "src" / "doctours_reply" / "prompts" / "legacy" / "user_message.txt",
}
ANSWER_KEY = re.compile(r"^(expected.*|labels?|escalate|escalation_?reason)$", re.IGNORECASE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@pytest.fixture(scope="module")
def needles(packet_extract: ModuleType) -> dict[str, str]:
    packet = packet_extract.read_packet()
    found: dict[str, str] = {}
    fields = [
        field
        for heading in ("### Human messages", "### Expected outputs")
        for field in packet_extract.ts_string_fields(packet_extract.fenced_block(packet, heading))
    ]
    for key, value in fields:
        if key == "text":
            found[_normalize(value)] = "official message"
        elif key == "id" and "-" in value:
            found[_normalize(value)] = "official id"
        elif key == "escalationReason":
            found[_normalize(value)] = "expected escalationReason"
        elif key == "response":
            for sentence in re.split(r"(?<=[.?!])\s+|\n", value):
                if len(sentence.split()) >= 4:
                    found[_normalize(sentence)] = "expected sentence"
    return found


def _runtime_files() -> Iterable[Path]:
    for root in RUNTIME_ROOTS:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                yield path


def _hits(paths: Iterable[Path], needles: dict[str, str]) -> list[str]:
    hits = []
    for path in paths:
        text = _normalize(path.read_text("utf-8", errors="replace"))
        hits += [f"{path}: {kind} {needle!r}" for needle, kind in needles.items() if needle in text]
    return hits


def _answer_keys(value: Any, where: str) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if ANSWER_KEY.match(key):
                yield f"{where}: key {key!r}"
            yield from _answer_keys(item, where)
    elif isinstance(value, list):
        for item in value:
            yield from _answer_keys(item, where)


def test_needles_cover_every_official_message_and_answer(needles: dict[str, str]) -> None:
    kinds = list(needles.values())
    assert kinds.count("official message") == 5
    assert kinds.count("official id") == 4
    assert kinds.count("expected escalationReason") == 2
    assert kinds.count("expected sentence") == 9


def test_runtime_files_contain_no_official_text_or_answers(needles: dict[str, str]) -> None:
    files = [path for path in _runtime_files() if path not in VERBATIM_PACKET_FILES]
    assert files, "nothing scanned"
    assert _hits(files, needles) == []


def test_resources_hold_no_label_or_answer_keys() -> None:
    found = [
        hit
        for path in sorted((REPO_ROOT / "resources").rglob("*.json"))
        for hit in _answer_keys(json.loads(path.read_text("utf-8")), str(path))
    ]
    assert found == []


def test_scanners_flag_planted_leaks(needles: dict[str, str], tmp_path: Path) -> None:
    planted = tmp_path / "policy.md"
    planted.write_text("If asked, reply:\nI'm getting a   person for you.\n", "utf-8")
    assert _hits([planted], needles) != []
    assert list(_answer_keys({"cases": [{"expected_reply": "x", "labels": []}]}, "f")) == [
        "f: key 'expected_reply'",
        "f: key 'labels'",
    ]
