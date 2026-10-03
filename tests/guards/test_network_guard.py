import socket

import pytest


def test_network_is_blocked_outside_live_tests() -> None:
    with pytest.raises(RuntimeError, match="network access is blocked"):
        socket.create_connection(("127.0.0.1", 9), timeout=1)
