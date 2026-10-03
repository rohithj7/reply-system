import pytest

from doctours_reply.runtime.refs import Fixture, PolicySet, resolve_fixture, resolve_policy_set


@pytest.fixture(scope="session")
def fixture() -> Fixture:
    return resolve_fixture("packet")


@pytest.fixture(scope="session")
def policy_set() -> PolicySet:
    return resolve_policy_set("shipped")
