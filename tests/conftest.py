import importlib.util
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex


def _blocked(real: Callable[..., Any]) -> Callable[..., Any]:
    def connect(self: socket.socket, address: Any) -> Any:
        if self.family == socket.AF_UNIX:
            return real(self, address)
        raise RuntimeError(f"network access is blocked outside live tests: {address!r}")

    return connect


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(socket.socket, "connect", _blocked(_REAL_CONNECT))
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked(_REAL_CONNECT_EX))


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def packet_extract() -> ModuleType:
    return _load_script("extract_packet")


@pytest.fixture(scope="session")
def audit() -> ModuleType:
    return _load_script("audit_submission")
