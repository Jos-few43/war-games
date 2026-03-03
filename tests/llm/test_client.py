import pytest
from unittest.mock import AsyncMock, patch
from wargames.llm.client import LLMClient
from wargames.models import TeamSettings

@pytest.fixture
def team_settings():
    return TeamSettings(
        name="Test Team",
        model="http://localhost:4000/v1",
        model_name="test-model",
        temperature=0.7,
    )

@pytest.mark.asyncio
async def test_chat_sends_correct_request(team_settings):
    client = LLMClient(team_settings)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello from LLM"}}]
    }
    mock_response.raise_for_status = lambda: None
    with patch.object(client._http, "post", return_value=mock_response) as mock_post:
        result = await client.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello from LLM"
        call_args = mock_post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert body["model"] == "test-model"
        assert body["temperature"] == 0.7
        assert body["messages"] == [{"role": "user", "content": "Hi"}]

@pytest.mark.asyncio
async def test_chat_with_system_prompt(team_settings):
    client = LLMClient(team_settings)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "response"}}]
    }
    mock_response.raise_for_status = lambda: None
    with patch.object(client._http, "post", return_value=mock_response) as mock_post:
        result = await client.chat(
            [{"role": "user", "content": "attack"}],
            system="You are a red team agent.",
        )
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["messages"][0] == {"role": "system", "content": "You are a red team agent."}
        assert body["messages"][1] == {"role": "user", "content": "attack"}

@pytest.mark.asyncio
async def test_chat_raises_on_error(team_settings):
    client = LLMClient(team_settings)
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("Server error")
    with patch.object(client._http, "post", return_value=mock_response):
        with pytest.raises(Exception, match="Server error"):
            await client.chat([{"role": "user", "content": "Hi"}])
