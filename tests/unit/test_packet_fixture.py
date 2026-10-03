import hashlib
import json
import re
from pathlib import Path
from types import ModuleType

from doctours_reply.runtime.refs import resolve_fixture

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "resources" / "fixtures"
LEGACY = REPO_ROOT / "src" / "doctours_reply" / "prompts" / "legacy"
PACKET_SHA256 = "d06e044a4e3e13b4bc72343593c15cf05196cd51c8eee671c9d05a2cfc6e7436"
PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}")


def test_packet_copy_is_verbatim() -> None:
    packet = REPO_ROOT / "docs" / "assignment" / "pre-deposit-respond-packet.md"
    assert hashlib.sha256(packet.read_bytes()).hexdigest() == PACKET_SHA256


def test_extracted_files_match_the_packet(packet_extract: ModuleType) -> None:
    assert packet_extract.stale_files(packet_extract.read_packet()) == []


def test_constants_equal_the_packet_constants(packet_extract: ModuleType) -> None:
    packet = packet_extract.read_packet()
    expected = packet_extract.parse_constants(packet_extract.fenced_block(packet, "### Constants"))
    constants = json.loads((FIXTURES / "packet" / "constants.json").read_text("utf-8"))
    assert constants == expected
    assert list(constants) == list(expected)
    assert len(constants) == 42
    assert constants["ESTIMATED_GRAFTS"] == 2800
    assert constants["KLARNA_PAYPAL_FINANCING_ELIGIBLE"] is True
    assert constants["PROMO_OFFER"] is None
    assert constants["BOOKINGS"] == []
    assert constants["PATIENT_SUMMARY"].startswith("- Tier: pre_deposit\n")


def test_legacy_templates_match_the_packet_byte_for_byte(packet_extract: ModuleType) -> None:
    packet = packet_extract.read_packet()
    for name, heading in (
        ("system_prompt.txt", "### System prompt"),
        ("user_message.txt", "### User message"),
    ):
        expected = packet_extract.fenced_block(packet, heading).encode("utf-8")
        assert (LEGACY / name).read_bytes() == expected


def test_only_clinic_slug_remains_after_filling_constants() -> None:
    constants = resolve_fixture("packet").constants

    def fill(template: str, values: dict[str, object]) -> str:
        def value(match: re.Match[str]) -> str:
            name = match.group(0)[2:-2]
            if name not in values:
                return match.group(0)
            item = values[name]
            return item if isinstance(item, str) else json.dumps(item)

        return PLACEHOLDER.sub(value, template)

    system = fill((LEGACY / "system_prompt.txt").read_text("utf-8"), dict(constants))
    assert set(PLACEHOLDER.findall(system)) == {"{{clinic.slug}}"}
    user = fill(
        (LEGACY / "user_message.txt").read_text("utf-8"),
        {"HUMAN_MESSAGE": "Hello", **constants},
    )
    assert PLACEHOLDER.findall(user) == []


def test_manifest_hashes_the_packet_fixture_files() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text("utf-8"))
    (entry,) = [f for f in manifest["fixtures"] if f["fixture_id"] == "packet"]
    assert entry["derived_from"] == "packet"
    assert {f["role"]: f["path"] for f in entry["files"]} == {
        "constants": "packet/constants.json",
        "tool_data": "packet/tool_data.json",
    }
    for f in entry["files"]:
        assert hashlib.sha256((FIXTURES / f["path"]).read_bytes()).hexdigest() == f["sha256"]
