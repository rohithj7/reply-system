import json
from pathlib import Path

import pytest
from support import HEVA_ANSWER, reply_json

from doctours_reply import cli
from doctours_reply.models.client import ModelUnavailableError
from doctours_reply.models.scripted import ScriptedModelClient, Step, text_response, tool_response

ENV = {
    "MODEL_BASE_URL": "https://models.example.invalid/v1",
    "MODEL_API_KEY": "sk-test-not-a-real-key",
    "MODEL_ID": "m1",
}


@pytest.fixture
def no_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def _scripted(monkeypatch: pytest.MonkeyPatch, steps: list[Step]) -> ScriptedModelClient:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    client = ScriptedModelClient(steps)
    monkeypatch.setattr(cli, "OpenAICompatClient", lambda settings: client)
    return client


def _paths(tmp_path: Path, items: object) -> tuple[Path, Path, Path]:
    source = tmp_path / "in.json"
    source.write_text(json.dumps(items))
    return source, tmp_path / "out" / "replies.json", tmp_path / "traces"


def _run(source: Path, output: Path, traces: Path) -> int:
    return cli.main(
        ["run", "--input", str(source), "--output", str(output), "--trace-dir", str(traces)]
    )


def test_replies_and_traces_are_written_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _scripted(
        monkeypatch,
        [
            tool_response(("getClinicPackages", {"clinicName": "Heva"})),
            text_response(reply_json(HEVA_ANSWER)),
            text_response(reply_json("Happy to help.")),
        ],
    )
    source, output, traces = _paths(
        tmp_path, [{"id": "a", "text": "Heva prices?"}, {"id": "b", "text": "thanks"}]
    )
    assert _run(source, output, traces) == 0
    replies = json.loads(output.read_text())
    assert [r["response"] for r in replies] == [HEVA_ANSWER, "Happy to help."]
    assert set(replies[0]) == set(reply_json("x"))
    records = [json.loads(line) for line in (traces / "traces.jsonl").read_text().splitlines()]
    assert sorted(r["item_id"] for r in records) == ["a", "b"]
    assert "observations" not in output.read_text()
    assert ENV["MODEL_API_KEY"] not in (traces / "traces.jsonl").read_text()
    assert [p.name for p in output.parent.iterdir()] == ["replies.json"]


def test_an_empty_array_needs_no_model_configuration(no_model_env: None, tmp_path: Path) -> None:
    source, output, traces = _paths(tmp_path, [])
    assert _run(source, output, traces) == 0
    assert json.loads(output.read_text()) == []


@pytest.mark.parametrize(
    "items",
    [{"id": "a", "text": "hi"}, [{"id": "a"}], [{"id": 1, "text": "hi"}]],
    ids=["not-array", "missing-text", "wrong-type"],
)
def test_invalid_input_exits_2_and_writes_nothing(
    no_model_env: None, tmp_path: Path, items: object
) -> None:
    source, output, traces = _paths(tmp_path, items)
    assert _run(source, output, traces) == 2
    assert not output.exists()


def test_an_unknown_fixture_exits_2(no_model_env: None, tmp_path: Path) -> None:
    source, output, _ = _paths(tmp_path, [])
    args = ["run", "--input", str(source), "--output", str(output), "--fixture-id", "nope"]
    assert cli.main(args) == 2
    assert not output.exists()


def test_missing_model_configuration_exits_3_naming_the_variables(
    no_model_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, output, traces = _paths(tmp_path, [{"id": "a", "text": "hi"}])
    assert _run(source, output, traces) == 3
    assert "MODEL_BASE_URL, MODEL_API_KEY, MODEL_ID" in capsys.readouterr().err
    assert not output.exists()


def test_a_model_failure_exits_4_and_keeps_the_previous_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _scripted(monkeypatch, [ModelUnavailableError("model endpoint failed after 4 attempts")])
    source, output, traces = _paths(tmp_path, [{"id": "a", "text": "hi"}])
    output.parent.mkdir()
    output.write_text("previous")
    assert _run(source, output, traces) == 4
    assert output.read_text() == "previous"
    assert "item 0 ('a') failed" in capsys.readouterr().err
    record = json.loads((traces / "traces.jsonl").read_text())
    assert record["error"].startswith("model endpoint failed")


def test_write_atomic_replaces_the_file_in_one_step(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text("old")
    cli.write_atomic(target, "new")
    assert target.read_text() == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]
