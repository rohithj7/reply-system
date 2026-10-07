import json
from pathlib import Path

import pytest
from support import GOLD_ID, HEVA_ANSWER, reply_json

from doctours_reply.contract.io import InputItem
from doctours_reply.contract.reply import Reply
from doctours_reply.evaluation import cli as eval_cli
from doctours_reply.evaluation.cases import (
    Case,
    FactLabel,
    Labels,
    check_case,
    exported,
    frozen_hash_problem,
    load_suite,
)
from doctours_reply.evaluation.schedule import (
    ScheduleError,
    begin_logged_run,
    current_entries,
    log_problems,
    read_log,
    summary_problems,
)
from doctours_reply.evaluation.scorer import has_fact, official_checks, score_case, tool_selection
from doctours_reply.evaluation.stats import (
    case_bootstrap,
    mcnemar_exact,
    paired_difference,
    percentile,
    wilson,
)
from doctours_reply.models.scripted import ScriptedModelClient, text_response, tool_response
from doctours_reply.runtime.executor import Executor
from doctours_reply.runtime.pipeline import RunInfo, run_item
from doctours_reply.runtime.refs import Fixture, PolicySet

LOG_HEADER = (
    "# log\n\n| # | date | purpose | set | set sha256 | systems | config sha256 | git sha "
    "| prereg sha256 | status |\n|---|---|---|---|---|---|---|---|---|---|\n"
)
ENV = {
    "MODEL_BASE_URL": "https://models.example.invalid/v1",
    "MODEL_API_KEY": "sk-test-not-a-real-key",
    "MODEL_ID": "m1",
}


def _labels(**fields: object) -> Labels:
    return Labels.model_validate(
        {"escalate": False, "intent_kinds": ["information_request"], **fields}
    )


def _reply(response: str, **fields: object) -> Reply:
    return Reply.model_validate(reply_json(response, **fields))


def test_label_consistency_is_checked(fixture: Fixture) -> None:
    with pytest.raises(ValueError):
        _labels(escalate=True)
    with pytest.raises(ValueError):
        _labels(escalate=True, escalation_class="human_requested", control="policy_question")
    case = Case(
        case_id="x",
        text="hi",
        fixture_id="packet",
        policy_set_id="shipped",
        labels=_labels(
            tool_sets=[[{"tool": "getClinicPackages", "clinic": "nowhere"}]],
            required_facts=[
                {"entity": "Gold", "attribute": "basePrice", "value": 4000},
                {"entity": "Gold", "attribute": "included.Hotel", "value": "3 night"},
                {"entity": "Silver", "attribute": "bookableWeekdays", "value": "Wed"},
                {"entity": "Silver", "attribute": "bookableWeekdays", "value": "Thu"},
            ],
        ),
    )
    assert check_case(case, fixture) == [
        "x: unknown clinic 'nowhere'",
        "x: Gold.basePrice is not 4000",
        "x: Gold does not include '3 night' Hotel",
        "x: Silver is not bookable on Wed",
    ]


@pytest.mark.parametrize(
    ("response", "value", "hit"),
    [
        ("Gold includes three nights at the hotel.", "3 night", True),
        ("Gold includes a 3-night hotel stay.", "3 night", True),
        ("That comes to 13 nights in total.", "3 night", False),
        ("Gold includes 4 hotel nights.", "4 night", True),
        ("Gold has 4 extra paid add-on nights.", "4 night", False),
        ("Your doctor is Dr. Sibel's team lead.", "Sibel", True),
        ("Ask the Sibelius quartet.", "Sibel", False),
    ],
)
def test_string_facts_match_whole_words(response: str, value: str, hit: bool) -> None:
    fact = FactLabel(entity="Gold", attribute="included.Hotel", value=value)
    assert has_fact(response, fact) is hit


@pytest.mark.parametrize(
    ("response", "day", "hit"),
    [
        ("Sapphire can be booked Monday through Friday.", "Wed", True),
        ("Gold runs Mon-Sat.", "Sat", True),
        ("Silver is available Monday, Tuesday, Thursday and Friday.", "Thu", True),
        ("Silver is not offered on Wednesdays.", "Thu", False),
        ("Weekends are not allowed for Sapphire.", "Wed", False),
        ("Silver runs Mon to Tue.", "Thu", False),
    ],
)
def test_weekday_facts_accept_names_and_ranges(response: str, day: str, hit: bool) -> None:
    fact = FactLabel(entity="Sapphire", attribute="bookableWeekdays", value=day)
    assert has_fact(response, fact) is hit


def test_official_cases_join_texts_without_expected_outputs() -> None:
    cases = load_suite("official")
    assert [c.case_id for c in cases][:2] == ["heva-packages", "hakan-price"]
    assert all(c.text for c in cases)


def test_tool_selection_matches_multisets_with_optional_reads(fixture: Fixture) -> None:
    executor = Executor(fixture.tool_data, fixture.constants)
    executor.execute("c1", "getSavedClinics", {"userId": fixture.constants["USER_ID"]})
    executor.execute("c2", "getClinicPackages", {"clinicName": "Heva"})
    executor.execute("c3", "getPaymentLink", {"type": "payment", "clinicPackageId": GOLD_ID})
    expected = [
        {"tool": "getClinicPackages", "clinic": "heva"},
        {"tool": "getPaymentLink", "package": "Gold", "type": "payment"},
    ]
    observations = executor.observations
    assert tool_selection(
        _labels(tool_sets=[expected], optional_reads=["getSavedClinics"]), observations, fixture
    )
    assert not tool_selection(_labels(tool_sets=[expected]), observations, fixture)
    silver = [expected[0], {**expected[1], "package": "Silver"}]
    assert not tool_selection(
        _labels(tool_sets=[silver], optional_reads=["getSavedClinics"]), observations, fixture
    )
    assert tool_selection(_labels(), observations, fixture) is None


def test_scores_come_from_the_reply_and_trace(fixture: Fixture, policy_set: PolicySet) -> None:
    client = ScriptedModelClient(
        [
            tool_response(("getClinicPackages", {"clinicName": "Heva"})),
            text_response(reply_json(HEVA_ANSWER)),
        ]
    )
    result = run_item(
        0,
        InputItem(id="c", text="Heva prices?"),
        fixture=fixture,
        policy_set=policy_set,
        client=client,
        run=RunInfo("r", None, None),
    )
    case = Case(
        case_id="c",
        text="Heva prices?",
        fixture_id="packet",
        policy_set_id="shipped",
        labels=_labels(
            tool_sets=[[{"tool": "getClinicPackages", "clinic": "heva"}]],
            required_facts=[
                {"entity": "Silver", "attribute": "basePrice", "value": 3000},
                {"entity": "Gold", "attribute": "depositAmount", "value": 600},
                {"entity": "Gold", "attribute": "depositAmount", "value": 500},
            ],
            forbidden_facts=[{"entity": "Sapphire"}],
        ),
    )
    score = score_case(case, "dev", "baseline", 1, result.reply, result.trace, fixture)
    assert (score.escalate_expected, score.escalate_actual, score.tool_selection) == (
        False,
        False,
        True,
    )
    assert (score.required_facts_hit, score.required_facts_total, score.forbidden_hits) == (2, 3, 0)
    assert (score.valid_before_repair, score.grounded_first_try, score.model_calls) == (
        True,
        True,
        2,
    )


def test_official_checks_follow_the_grading_note(fixture: Fixture) -> None:
    expected = {
        "escalate": False,
        "response": "Dr. Hakan Clinic has Sapphire at $3,200 USD with a $500 deposit.",
    }
    good = _reply("Dr. Hakan Clinic offers Sapphire: $3,200 USD, deposit $500.")
    assert all(official_checks("cost?", good, expected, fixture).values())
    missing = official_checks("cost?", _reply("Sapphire is $3,200."), expected, fixture)
    assert missing["amount 500"] is False
    handoff = {"escalate": True, "response": "x"}
    card = "Charge my card 4242 4242 4242 4242"
    leak = _reply("Charging 4242 4242 4242 4242 now.", escalate=True, escalationReason="card")
    checks = official_checks(card, leak, handoff, fixture)
    assert checks["no_card_number"] is False
    assert checks["no_sales_answer"] is True


@pytest.mark.parametrize(
    ("response", "stated"),
    [
        ("Heva Clinic specializes in afro and textured hair.", True),
        ("Heva is an Afro Hair specialist.", True),
        ("Heva Clinic has Silver and Gold. It focuses on afro and textured hair.", True),
        ("Afro and textured hair is what Heva Clinic is known for.", True),
        ("Dr. Hakan Clinic isn't flagged for it, but Heva Clinic is an afro hair clinic.", True),
        ("heva clinic specializes in afro and textured hair.", True),
        ("Heva Clinic is the afro hair specialist, not Dr. Hakan Clinic.", True),
        ("Heva Clinic does not specialize in afro and textured hair.", False),
        ("Afro hair is not Heva Clinic’s specialty.", False),
        ("Afro and textured hair isn't something Heva Clinic offers.", False),
        ("Heva Clinic has Gold, and dr. hakan clinic is the one for afro hair.", False),
        ("Heva isn't flagged for Afro Hair.", False),
        ("Dr. Hakan Clinic specializes in afro and textured hair.", False),
        ("Heva Clinic has Gold, and Dr. Hakan Clinic is the one for afro hair.", False),
        ("Dr. Hakan Clinic has Sapphire. It focuses on afro and textured hair.", False),
        ("Heva Clinic works with textured hair.", False),
    ],
)
def test_a_clinic_flag_counts_only_when_affirmed_of_its_clinic(
    fixture: Fixture, response: str, stated: bool
) -> None:
    expected = {"escalate": False, "response": "Heva Clinic is our Afro Hair clinic."}
    assert official_checks("afro?", _reply(response), expected, fixture) == {
        "escalate": True,
        "fact Afro Hair": stated,
    }


def test_statistics() -> None:
    assert wilson(0, 0) == (0.0, 1.0)
    low, high = wilson(5, 10)
    assert (round(low, 4), round(high, 4)) == (0.2366, 0.7634)
    assert wilson(10, 10)[1] == pytest.approx(1.0)
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([], 95) == 0.0


def test_case_level_statistics() -> None:
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 6) == pytest.approx(0.03125)
    assert mcnemar_exact(3, 3) == 1.0
    assert case_bootstrap([(3, 3)] * 10) == (1.0, 1.0)
    low, high = case_bootstrap([(3, 3)] * 5 + [(0, 3)] * 5)
    assert low < 0.5 < high
    same = {f"c{i}": (i % 2, 1) for i in range(20)}
    assert paired_difference(same, same) == {"difference": 0.0, "ci95": [0.0, 0.0], "cases": 20}
    better = {case: (1, 1) for case in same}
    difference = paired_difference(same, better)
    assert difference is not None and difference["difference"] == 0.5
    assert paired_difference(same, {"other": (1, 1)}) is None


@pytest.fixture
def log(tmp_path: Path) -> Path:
    path = tmp_path / "heldout-log.md"
    path.write_text(LOG_HEADER)
    return path


def _begin(log: Path, row: str = "phase2-s0-baseline", **kwargs: object):  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "suites": ["heldout_v1"],
        "systems": ["baseline"],
        "set_sha256": "s" * 8,
        "config_sha256": "c" * 8,
        "git_sha": "g" * 8,
        "date": "2026-10-03",
        "log_path": log,
        "preregistration_path": log.parent / "preregistration.md",
    }
    return begin_logged_run(row, **{**defaults, **kwargs})  # type: ignore[arg-type]


def test_heldout_suites_need_a_log_entry_rc_v_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    assert eval_cli.main(["--suite", "heldout_v1"]) == 2
    assert "runs only through the schedule" in capsys.readouterr().err


def test_a_repeat_run_is_refused_and_voids_are_kept_rc_v_2(log: Path) -> None:
    first = _begin(log)
    assert first.number == 1
    with pytest.raises(ScheduleError, match="already ran as entry #1"):
        _begin(log)
    with pytest.raises(ScheduleError, match="needs the infrastructure failure"):
        _begin(log, void_reason="  ")
    second = _begin(log, void_reason="endpoint returned 503 for every call | retry")
    entries = read_log(log)
    assert [e.status for e in entries] == [
        "valid",
        "void #1: endpoint returned 503 for every call / retry",
        "valid",
    ]
    assert current_entries(entries, "phase2-s0-baseline") == [entries[2]] == [second]
    assert log_problems(entries) == []


def test_a_wrong_suite_or_system_set_is_refused(log: Path) -> None:
    with pytest.raises(ScheduleError, match="runs heldout_v1"):
        _begin(log, suites=["dev"])
    with pytest.raises(ScheduleError, match="not a schedule row"):
        _begin(log, row="whenever")


def test_a_comparison_needs_its_preregistration_rc_v_3(log: Path) -> None:
    prereg = log.parent / "preregistration.md"
    systems = ["baseline", "modular"]
    with pytest.raises(ScheduleError, match="needs its section"):
        _begin(log, row="phase3-s0-vs-s1", systems=systems)
    prereg.write_text("# Pre-registration\n\n## phase5-s0-s3\n")
    with pytest.raises(ScheduleError, match="needs its section"):
        _begin(log, row="phase3-s0-vs-s1", systems=systems)
    prereg.write_text("# Pre-registration\n\n## phase3-s0-vs-s1\nMetrics and margins.\n")
    entry = _begin(log, row="phase3-s0-vs-s1", systems=systems)
    assert entry.prereg_sha256 != "-"


def test_a_summary_without_a_log_entry_is_flagged_rc_v_4(log: Path) -> None:
    (log.parent / "phase2-s0-baseline-summary.md").write_text("# results\n")
    assert summary_problems(log.parent, read_log(log)) == [
        "phase2-s0-baseline-summary.md has no current held-out log entry"
    ]
    _begin(log)
    assert summary_problems(log.parent, read_log(log)) == []


def test_eval_dry_run_validates_every_suite(capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_cli.main(["--dry-run", "--suite", "all"]) == 0
    assert "heldout_v1:" in capsys.readouterr().out


def test_all_skips_a_frozen_suite_until_its_cases_or_hash_are_committed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    heldout = tmp_path / "heldout"
    heldout.mkdir()
    assert exported("dev", tmp_path)
    assert not exported("heldout_v2", tmp_path)
    (heldout / "v2.jsonl").write_text("")
    assert exported("heldout_v2", tmp_path)
    assert (
        frozen_hash_problem("heldout_v2", tmp_path) == "heldout_v2 has no frozen hash at v2.sha256"
    )
    (heldout / "v2.jsonl").unlink()
    (heldout / "v2.sha256").write_text("0" * 64 + "  v2.jsonl\n")
    assert exported("heldout_v2", tmp_path)
    monkeypatch.setattr(eval_cli, "exported", lambda suite: suite != "heldout_v2")
    assert "heldout_v2" not in eval_cli._suites("all")
    assert eval_cli._suites("heldout_v2") == ["heldout_v2"]


def test_eval_without_model_configuration_exits_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    assert eval_cli.main(["--suite", "official"]) == 3
    assert "MODEL_BASE_URL" in capsys.readouterr().err


def test_the_judge_must_differ_from_every_system_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    judge = {"JUDGE_BASE_URL": ENV["MODEL_BASE_URL"], "JUDGE_API_KEY": "j", "JUDGE_MODEL_ID": "w1"}
    for name, value in {**judge, "WRITER_MODEL_ID": "w1"}.items():
        monkeypatch.setenv(name, value)
    assert eval_cli.main(["--suite", "official", "--judge"]) == 3
    assert "WRITER_MODEL_ID" in capsys.readouterr().err


def test_eval_runs_offline_on_a_scripted_model_and_writes_a_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    client = ScriptedModelClient(lambda request: text_response(reply_json("Happy to help.")))
    monkeypatch.setattr(eval_cli, "OpenAICompatClient", lambda settings: client)
    report_dir = tmp_path / "report"
    args = ["--suite", "official,regression", "--runs", "2", "--report", str(report_dir)]
    assert eval_cli.main(args) == 0
    report = json.loads((report_dir / "report.json").read_text())
    metrics = report["systems"]["baseline"]
    assert (metrics["cases_per_run"], metrics["runs"]) == (24, 2)
    assert metrics["missed_escalation"]["human_request"]["rate"] == 1.0
    assert metrics["output_valid_after_finalize"]["rate"] == 1.0
    assert "heva-packages#run1" in metrics["official_checks"]
    assert metrics["official_checks_version"] == "3"
    lines = (report_dir / "cases.jsonl").read_text().splitlines()
    assert len(lines) == 48
    assert (report_dir / "summary.md").read_text().startswith("# Evaluation summary")
    assert ENV["MODEL_API_KEY"] not in (report_dir / "report.json").read_text()


def test_eval_pairs_the_two_systems_by_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    client = ScriptedModelClient(lambda request: text_response(reply_json("Happy to help.")))
    monkeypatch.setattr(eval_cli, "OpenAICompatClient", lambda settings: client)
    report_dir = tmp_path / "report"
    args = ["--system", "baseline,modular", "--suite", "regression", "--runs", "2"]
    assert eval_cli.main([*args, "--report", str(report_dir)]) == 0
    report = json.loads((report_dir / "report.json").read_text())
    modular = report["systems"]["modular"]
    assert modular["controller_failure"]["rate"] == 1.0
    assert modular["escalation_correct"]["cases"] == 19
    assert "ci95_cases" in modular["escalation_correct"]
    assert "human_requested" in modular["missed_escalation_by_class"]
    comparison = report["modular_minus_baseline"]
    assert comparison["missed_escalation"]["cases"] == 10
    assert comparison["unnecessary_escalation"]["difference"] == 1.0
