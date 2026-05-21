import json
import pytest
from unittest.mock import MagicMock, patch

from agent.core.memu import MemUClient
from agent.core.tools import create_builtin_tools


def test_memu_client_initialization_no_key(monkeypatch):
    monkeypatch.delenv("MEMU_API_KEY", raising=False)
    client = MemUClient()
    assert client.api_key == ""
    assert client.is_configured() is False


def test_memu_client_initialization_with_key():
    client = MemUClient(api_key="test_key")
    assert client.api_key == "test_key"
    assert client.is_configured() is True
    assert client.headers["Authorization"] == "Bearer test_key"


@patch("requests.post")
def test_memu_memorize(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "task_id": "task_123",
        "status": "PENDING",
        "message": "Memorization task registered successfully",
    }
    mock_post.return_value = mock_response

    client = MemUClient(api_key="test_key")
    convo = [{"role": "user", "content": "I enjoy coding"}]
    res = client.memorize(convo, user_id="user_123", agent_id="agent_456")

    assert res["task_id"] == "task_123"
    assert res["status"] == "PENDING"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["user_id"] == "user_123"
    assert kwargs["json"]["agent_id"] == "agent_456"


@patch("requests.get")
def test_memu_get_status(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "task_id": "task_123",
        "status": "SUCCESS",
    }
    mock_get.return_value = mock_response

    client = MemUClient(api_key="test_key")
    res = client.get_memorize_status("task_123")

    assert res["status"] == "SUCCESS"
    mock_get.assert_called_once_with(
        "https://api.memu.so/api/v3/memory/memorize/status/task_123",
        headers=client.headers,
        timeout=15,
    )


@patch("requests.post")
def test_memu_categories(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "categories": [{"name": "personal", "summary": "Likes coding"}]
    }
    mock_post.return_value = mock_response

    client = MemUClient(api_key="test_key")
    res = client.list_categories("user_123", "agent_456")

    assert len(res["categories"]) == 1
    assert res["categories"][0]["name"] == "personal"


@patch("requests.post")
def test_memu_retrieve(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "rewritten_query": "What are user's hobbies?",
        "items": [{"memory_type": "preference", "content": "Plays tennis"}],
    }
    mock_post.return_value = mock_response

    client = MemUClient(api_key="test_key")
    res = client.retrieve("user_123", "agent_456", query="hobbies")

    assert res["rewritten_query"] == "What are user's hobbies?"
    assert res["items"][0]["content"] == "Plays tennis"


@patch("requests.post")
def test_memu_delete(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = "Memories deleted successfully"
    mock_post.return_value = mock_response

    client = MemUClient(api_key="test_key")
    res = client.delete_memories("user_123", "agent_456")

    assert res == "Memories deleted successfully"


def test_memu_tools_registration():
    tools = create_builtin_tools(local_mode=True)
    specs = {t.name: t for t in tools}

    assert "memu_retrieve_memories" in specs
    assert "memu_memorize_session" in specs

    assert "query" in specs["memu_retrieve_memories"].parameters["properties"]
    assert "conversation" in specs["memu_memorize_session"].parameters["properties"]


@pytest.mark.asyncio
@patch("agent.core.memu.MemUClient.retrieve")
async def test_memu_retrieve_handler_works(mock_retrieve, monkeypatch):
    monkeypatch.setenv("MEMU_API_KEY", "dummy")
    mock_retrieve.return_value = {"items": [{"content": "Retrieved"}]}

    tools = create_builtin_tools(local_mode=True)
    memu_retrieve = [t for t in tools if t.name == "memu_retrieve_memories"][0]

    output, ok = await memu_retrieve.handler({"query": "test query"})
    assert ok is True
    data = json.loads(output)
    assert data["items"][0]["content"] == "Retrieved"


@pytest.mark.asyncio
@patch("agent.core.memu.MemUClient.memorize")
async def test_memu_memorize_handler_works(mock_memorize, monkeypatch):
    monkeypatch.setenv("MEMU_API_KEY", "dummy")
    mock_memorize.return_value = {"status": "SUCCESS", "task_id": "123"}

    tools = create_builtin_tools(local_mode=True)
    memu_memorize = [t for t in tools if t.name == "memu_memorize_session"][0]

    convo = [{"role": "user", "content": "hello"}]
    output, ok = await memu_memorize.handler({"conversation": convo})
    assert ok is True
    data = json.loads(output)
    assert data["status"] == "SUCCESS"
