import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from wargames.llm.client import LLMClient
from wargames.models import TeamSettings
import httpx

@pytest.fixture
def team_settings():
    return TeamSettings(
        name="Test Team",
        model="http://localhost:4000/v1",
        model_name="test-model",
        temperature=0.7,
    )

def _ok_response(content="Hello from LLM"):
    """Create a mock httpx.Response (sync methods like the real thing)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status.return_value = None
    return resp

@pytest.mark.asyncio
async def test_chat_sends_correct_request(team_settings):
    client = LLMClient(team_settings)
    mock_response = _ok_response()
    with patch.object(client._http, "post", return_value=mock_response) as mock_post:
        result = await client.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello from LLM"
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["model"] == "test-model"
        assert body["temperature"] == 0.7
        assert body["messages"] == [{"role": "user", "content": "Hi"}]

@pytest.mark.asyncio
async def test_chat_with_system_prompt(team_settings):
    client = LLMClient(team_settings)
    mock_response = _ok_response("response")
    with patch.object(client._http, "post", return_value=mock_response) as mock_post:
        result = await client.chat(
            [{"role": "user", "content": "attack"}],
            system="You are a red team agent.",
        )
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["messages"][0] == {"role": "system", "content": "You are a red team agent."}
        assert body["messages"][1] == {"role": "user", "content": "attack"}

@pytest.mark.asyncio
async def test_chat_raises_on_non_retryable_error(team_settings):
    """Non-retryable HTTP errors (e.g. 400, 401) should raise immediately."""
    client = LLMClient(team_settings)
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response,
    )
    with patch.object(client._http, "post", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "Hi"}])

@pytest.mark.asyncio
async def test_chat_retries_on_read_timeout(team_settings):
    client = LLMClient(team_settings)
    mock_success = _ok_response("recovered")
    with patch.object(
        client._http, "post",
        side_effect=[httpx.ReadTimeout("timeout"), mock_success],
    ):
        result = await client.chat([{"role": "user", "content": "Hi"}])
        assert result == "recovered"

@pytest.mark.asyncio
async def test_chat_retries_on_429(team_settings):
    """429 Too Many Requests should trigger retry with backoff."""
    client = LLMClient(team_settings)
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {"retry-after": "0.1"}
    mock_429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate limited", request=MagicMock(), response=mock_429,
    )
    mock_success = _ok_response("after retry")
    with patch.object(
        client._http, "post",
        side_effect=[mock_429, mock_success],
    ):
        result = await client.chat([{"role": "user", "content": "Hi"}])
        assert result == "after retry"

@pytest.mark.asyncio
async def test_chat_sends_auth_header():
    """API key should be sent as Bearer token."""
    settings = TeamSettings(
        name="Auth Test", model="http://localhost:4000/v1",
        model_name="test", temperature=0.5, api_key="sk-test-key",
    )
    client = LLMClient(settings)
    assert client._http.headers.get("authorization") == "Bearer sk-test-key"
    await client.close()
