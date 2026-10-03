import pytest
from support import GOLD_ID, HEVA_ID, SILVER_ID, USER_ID

from doctours_reply.runtime.executor import Executor, ExecutorClosedError
from doctours_reply.runtime.refs import Fixture


def _executor(fixture: Fixture, max_calls: int = 8) -> Executor:
    return Executor(fixture.tool_data, fixture.constants, max_calls)


def _selection(clinic: str = HEVA_ID, package: str = GOLD_ID) -> dict[str, object]:
    return {
        "userId": USER_ID,
        "clinicSelection": {"selectedClinicId": clinic, "selectedPackageId": package},
    }


def test_ids_must_come_from_a_tool_result_this_turn(fixture: Fixture) -> None:
    executor = _executor(fixture)
    before = executor.execute("c1", "getClinicPackages", {"clinicId": HEVA_ID})
    assert before.status == "rejected"
    assert "clinicId" in (before.reason or "")
    assert executor.execute("c2", "getAllClinics", {}).status == "ok"
    after = executor.execute("c3", "getClinicPackages", {"clinicId": HEVA_ID})
    assert after.status == "ok"
    assert after.result is not None


def test_patient_ids_must_be_trusted_constants(fixture: Fixture) -> None:
    executor = _executor(fixture)
    assert executor.execute("c1", "getPatientContext", {"userId": USER_ID}).status == "ok"
    foreign = executor.execute("c2", "getPatientContext", {"userId": "someone-else"})
    assert foreign.status == "rejected"


def test_requests_are_validated_and_recorded(fixture: Fixture) -> None:
    executor = _executor(fixture)
    assert executor.execute("c1", "bookFlight", {}).reason == "unknown tool"
    assert executor.execute("c2", "getAllClinics", "{not json").reason == "arguments not an object"
    assert executor.execute("c3", "getAllClinics", {"extra": 1}).status == "rejected"
    alias = executor.execute("c4", "getAllClinicsTool", "")
    assert (alias.tool, alias.status) == ("getAllClinics", "ok")
    assert [o.call_id for o in executor.observations] == ["c1", "c2", "c3", "c4"]


def test_a_seen_but_wrong_id_yields_a_null_result(fixture: Fixture) -> None:
    executor = _executor(fixture)
    executor.execute("c1", "getClinicPackages", {"clinicName": "Heva"})
    wrong = executor.execute("c2", "getClinicPackages", {"clinicId": SILVER_ID})
    assert (wrong.status, wrong.result) == ("null_result", None)
    preferences = executor.execute(
        "c3", "updateUserClinicPreferences", _selection(clinic=SILVER_ID)
    )
    assert preferences.status == "null_result"
    assert preferences.executed


def test_a_failing_tool_becomes_an_error_observation(fixture: Fixture) -> None:
    broken = fixture.tool_data.model_copy(update={"clinics": [{"id": HEVA_ID}]})
    executor = Executor(broken, fixture.constants)
    failed = executor.execute("c1", "getClinicPackages", {"clinicName": "Heva"})
    assert failed.status == "error"
    assert failed.reason is not None and failed.reason.startswith("KeyError")
    assert executor.execute("c2", "getAllClinics", {}).status == "ok"


def test_a_repeated_write_executes_once_rc_w_6(fixture: Fixture) -> None:
    executor = _executor(fixture)
    executor.execute("c1", "getClinicPackages", {"clinicName": "Heva"})
    first = executor.execute("c2", "updateUserClinicPreferences", _selection())
    again = executor.execute("c3", "updateUserClinicPreferences", _selection())
    assert first.status == "ok"
    assert (again.status, again.result) == ("duplicate_write", first.result)
    assert not again.executed
    other = executor.execute("c4", "updateUserClinicPreferences", _selection(package=SILVER_ID))
    assert other.status == "ok"
    assert executor.executed_writes == ("c2", "c4")


def test_working_memory_is_written_at_most_once_per_item(fixture: Fixture) -> None:
    executor = _executor(fixture)
    first = executor.execute("c1", "updateWorkingMemory", {"memory": {"patientName": "Jo"}})
    second = executor.execute("c2", "updateWorkingMemory", {"memory": {"keyConcerns": "cost"}})
    assert first.status == "ok"
    assert first.result == {"success": True}
    assert second.status == "duplicate_write"
    assert executor.executed_writes == ("c1",)


def test_the_call_budget_is_bounded(fixture: Fixture) -> None:
    executor = _executor(fixture, max_calls=2)
    executor.execute("c1", "getAllClinics", {})
    executor.execute("c2", "getSavedClinics", {"userId": USER_ID})
    third = executor.execute("c3", "getAllClinics", {})
    assert (third.status, third.reason) == ("rejected", "tool call budget used up")


def test_no_tool_runs_after_close(fixture: Fixture) -> None:
    executor = _executor(fixture)
    executor.close()
    with pytest.raises(ExecutorClosedError):
        executor.execute("c1", "getAllClinics", {})
    assert executor.observations == []


def test_results_do_not_alias_the_fixture(fixture: Fixture) -> None:
    executor = _executor(fixture)
    result = executor.execute("c1", "getAllClinics", {}).result
    assert isinstance(result, dict)
    result["clinics"].clear()
    assert fixture.tool_data.clinics
