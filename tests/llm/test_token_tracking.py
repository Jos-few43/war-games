import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from wargames.llm.client import LLMClient
from wargames.models import TeamSettings
import httpx


@pytest.fixture
def team_settings():
    return TeamSettings(
        name="Token Test Team",
        model="http://localhost:4000/v1",
        model_name="test-model",
        temperature=0.7,
    )


@pytest.fixture
def fallback_settings():
    return TeamSettings(
        name="Fallback Token Team",
        model="http://cloud:4002/v1",
        model_name="cloud-model",
        temperature=0.7,
        fallback_model="http://localhost:11434/v1",
        fallback_model_name="qwen3:4b",
    )


def _ok_response(content="Hello from LLM", prompt_tokens=10, completion_tokens=5):
    """Create a mock httpx.Response with usage data."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    resp.raise_for_status.return_value = None
    return resp


def _ok_response_no_usage(content="No usage response"):
    """Create a mock httpx.Response without usage field."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.asyncio
async def test_initial_token_state(team_settings):
    """New client starts with zero tokens and correct model name."""
    client = LLMClient(team_settings)
    usage = client.get_usage()
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0
    assert usage["model_used"] == "test-model"


@pytest.mark.asyncio
async def test_tokens_accumulated_after_chat(team_settings):
    """Tokens from a response are accumulated in the client."""
    client = LLMClient(team_settings)
    mock_response = _ok_response(prompt_tokens=20, completion_tokens=8)
    with patch.object(client._http, "post", return_value=mock_response):
        await client.chat([{"role": "user", "content": "Hi"}])

    usage = client.get_usage()
    assert usage["prompt_tokens"] == 20
    assert usage["completion_tokens"] == 8
    assert usage["model_used"] == "test-model"


@pytest.mark.asyncio
async def test_tokens_accumulate_across_multiple_calls(team_settings):
    """Multiple chat calls accumulate tokens additively."""
    client = LLMClient(team_settings)
    resp1 = _ok_response(prompt_tokens=10, completion_tokens=5)
    resp2 = _ok_response(prompt_tokens=15, completion_tokens=7)
    resp3 = _ok_response(prompt_tokens=8, completion_tokens=3)

    with patch.object(client._http, "post", side_effect=[resp1, resp2, resp3]):
        await client.chat([{"role": "user", "content": "First"}])
        await client.chat([{"role": "user", "content": "Second"}])
        await client.chat([{"role": "user", "content": "Third"}])

    usage = client.get_usage()
    assert usage["prompt_tokens"] == 33   # 10 + 15 + 8
    assert usage["completion_tokens"] == 15  # 5 + 7 + 3


@pytest.mark.asyncio
async def test_get_usage_reset_clears_counters(team_settings):
    """get_usage(reset=True) returns current values then zeros them."""
    client = LLMClient(team_settings)
    resp = _ok_response(prompt_tokens=25, completion_tokens=12)

    with patch.object(client._http, "post", return_value=resp):
        await client.chat([{"role": "user", "content": "Hi"}])

    usage = client.get_usage(reset=True)
    assert usage["prompt_tokens"] == 25
    assert usage["completion_tokens"] == 12

    # After reset, counters should be zero
    usage_after = client.get_usage()
    assert usage_after["prompt_tokens"] == 0
    assert usage_after["completion_tokens"] == 0


@pytest.mark.asyncio
async def test_get_usage_without_reset_does_not_clear(team_settings):
    """get_usage() without reset preserves counters."""
    client = LLMClient(team_settings)
    resp = _ok_response(prompt_tokens=30, completion_tokens=10)

    with patch.object(client._http, "post", return_value=resp):
        await client.chat([{"role": "user", "content": "Hi"}])

    client.get_usage()  # read without reset
    usage = client.get_usage()  # read again
    assert usage["prompt_tokens"] == 30
    assert usage["completion_tokens"] == 10


@pytest.mark.asyncio
async def test_missing_usage_field_does_not_crash(team_settings):
    """Responses without a 'usage' field result in zero token accumulation."""
    client = LLMClient(team_settings)
    mock_response = _ok_response_no_usage()

    with patch.object(client._http, "post", return_value=mock_response):
        result = await client.chat([{"role": "user", "content": "Hi"}])

    assert result == "No usage response"
    usage = client.get_usage()
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0


@pytest.mark.asyncio
async def test_accumulation_mixed_usage_and_no_usage(team_settings):
    """Mix of responses with and without usage fields accumulates correctly."""
    client = LLMClient(team_settings)
    resp_with_usage = _ok_response(prompt_tokens=10, completion_tokens=5)
    resp_no_usage = _ok_response_no_usage()

    with patch.object(client._http, "post", side_effect=[resp_with_usage, resp_no_usage]):
        await client.chat([{"role": "user", "content": "First"}])
        await client.chat([{"role": "user", "content": "Second"}])

    usage = client.get_usage()
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 5


@pytest.mark.asyncio
async def test_fallback_model_usage_tracked(fallback_settings):
    """When fallback is used, model_used reflects fallback model name."""
    client = LLMClient(fallback_settings)
    fb_response = _ok_response("fallback reply", prompt_tokens=18, completion_tokens=9)

    with patch.object(
        client._http, "post",
        side_effect=httpx.ReadTimeout("timeout"),
    ), patch.object(
        client._fallback_http, "post",
        return_value=fb_response,
    ), patch("wargames.llm.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client.chat([{"role": "user", "content": "Hi"}])

    assert result == "fallback reply"
    usage = client.get_usage()
    assert usage["prompt_tokens"] == 18
    assert usage["completion_tokens"] == 9
    assert usage["model_used"] == "qwen3:4b"
    await client.close()


@pytest.mark.asyncio
async def test_primary_model_usage_tracked_correctly(fallback_settings):
    """When primary succeeds, model_used reflects primary model name."""
    client = LLMClient(fallback_settings)
    primary_response = _ok_response("primary reply", prompt_tokens=12, completion_tokens=6)

    with patch.object(client._http, "post", return_value=primary_response):
        result = await client.chat([{"role": "user", "content": "Hi"}])

    assert result == "primary reply"
    usage = client.get_usage()
    assert usage["model_used"] == "cloud-model"
    await client.close()


@pytest.mark.asyncio
async def test_reset_after_accumulation_then_new_calls(team_settings):
    """After reset, new calls accumulate from zero."""
    client = LLMClient(team_settings)
    resp1 = _ok_response(prompt_tokens=50, completion_tokens=20)
    resp2 = _ok_response(prompt_tokens=5, completion_tokens=2)

    with patch.object(client._http, "post", side_effect=[resp1, resp2]):
        await client.chat([{"role": "user", "content": "Before reset"}])
        client.get_usage(reset=True)
        await client.chat([{"role": "user", "content": "After reset"}])

    usage = client.get_usage()
    assert usage["prompt_tokens"] == 5
    assert usage["completion_tokens"] == 2
