import pytest
from wargames.tui.bridge import EventBridge


def test_bridge_push_and_drain():
    bridge = EventBridge()
    bridge.push("attack", {"turn": 1, "success": True})
    bridge.push("defense", {"turn": 1, "blocked": False})
    events = bridge.drain()
    assert len(events) == 2
    assert events[0] == ("attack", {"turn": 1, "success": True})
    assert events[1] == ("defense", {"turn": 1, "blocked": False})


def test_bridge_drain_empty():
    bridge = EventBridge()
    events = bridge.drain()
    assert events == []


def test_bridge_drain_clears():
    bridge = EventBridge()
    bridge.push("attack", {"turn": 1})
    bridge.drain()
    assert bridge.drain() == []


@pytest.mark.asyncio
async def test_bridge_async_push():
    bridge = EventBridge()
    await bridge.async_push("round_complete", {"outcome": "red_win"})
    events = bridge.drain()
    assert len(events) == 1
    assert events[0][0] == "round_complete"


def test_bridge_maxlen():
    bridge = EventBridge(maxlen=3)
    bridge.push("a", {})
    bridge.push("b", {})
    bridge.push("c", {})
    bridge.push("d", {})  # Should drop "a"
    events = bridge.drain()
    assert len(events) == 3
    assert events[0][0] == "b"
