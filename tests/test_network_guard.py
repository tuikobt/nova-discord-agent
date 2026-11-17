"""The network guard permits asyncio's socketpair, but no service connections."""

import asyncio
import socket

import pytest


@pytest.mark.parametrize("host", ["127.0.0.1", "192.0.2.1"])
@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_direct_connections_remain_blocked(host, method):
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="must not connect"):
            getattr(connection, method)((host, 443))


def test_create_connection_remains_blocked():
    with pytest.raises(AssertionError, match="must not connect"):
        socket.create_connection(("192.0.2.1", 443))


def test_socketpair_works_and_does_not_allow_later_loopback_connections():
    reader, writer = socket.socketpair()
    try:
        reader.settimeout(1)
        writer.sendall(b"local wakeup")
        assert reader.recv(32) == b"local wakeup"
    finally:
        reader.close()
        writer.close()
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="must not connect"):
            connection.connect(("127.0.0.1", 443))


def test_asyncio_can_create_and_close_multiple_event_loops():
    async def scenario():
        await asyncio.sleep(0)
        return 42

    assert asyncio.run(scenario()) == 42
    assert asyncio.run(scenario()) == 42
