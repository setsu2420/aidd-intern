import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from agent.core.memu import MemUClient
from agent.core.tools import create_builtin_tools


# ==================== Synchronous Client Tests ====================


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


def test_memu_validate_conversation_pads_short():
    client = MemUClient(api_key="test_key")
    short = [{"role": "user", "content": "hi"}]
    padded = client._validate_conversation(short)
    assert len(padded) >= 3
    assert padded[0]["content"] == "hi"


def test_memu_validate_conversation_empty():
    client = MemUClient(api_key="test_key")
    padded = client._validate_conversation([])
    assert len(padded) == 3


def test_memu_validate_conversation_already_valid():
    client = MemUClient(api_key="test_key")
    convo = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    result = client._validate_conversation(convo)
    assert len(result) == 3
    assert result[0]["content"] == "a"


@patch("agent.core.memu.httpx.Client")
def test_memu_memorize(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "task_id": "task_123",
        "status": "PENDING",
        "message": "Memorization task registered successfully",
    }
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request.return_value = mock_response
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    convo = [
        {"role": "user", "content": "I enjoy coding"},
        {"role": "assistant", "content": "Great!"},
        {"role": "user", "content": "Yes indeed"},
    ]
    res = client.memorize(convo, user_id="user_123", agent_id="agent_456")

    assert res["task_id"] == "task_123"
    assert res["status"] == "PENDING"
    mock_client_instance.request.assert_called_once()
    call_kwargs = mock_client_instance.request.call_args
    assert call_kwargs[1]["json"]["user_id"] == "user_123"


@patch("agent.core.memu.httpx.Client")
def test_memu_get_status(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "task_id": "task_123",
        "status": "SUCCESS",
    }
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request.return_value = mock_response
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = client.get_memorize_status("task_123")

    assert res["status"] == "SUCCESS"


@patch("agent.core.memu.httpx.Client")
def test_memu_categories(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "categories": [{"name": "personal", "summary": "Likes coding"}]
    }
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request.return_value = mock_response
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = client.list_categories("user_123", "agent_456")

    assert len(res["categories"]) == 1
    assert res["categories"][0]["name"] == "personal"


@patch("agent.core.memu.httpx.Client")
def test_memu_retrieve(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "rewritten_query": "What are user's hobbies?",
        "items": [{"memory_type": "preference", "content": "Plays tennis"}],
    }
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request.return_value = mock_response
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = client.retrieve("user_123", "agent_456", query="hobbies")

    assert res["rewritten_query"] == "What are user's hobbies?"
    assert res["items"][0]["content"] == "Plays tennis"


@patch("agent.core.memu.httpx.Client")
def test_memu_delete(mock_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = "Memories deleted successfully"
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request.return_value = mock_response
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = client.delete_memories("user_123", "agent_456")

    assert res == "Memories deleted successfully"


def test_memu_not_configured_returns_failed(monkeypatch):
    monkeypatch.delenv("MEMU_API_KEY", raising=False)
    client = MemUClient()
    res = client.memorize([], user_id="u", agent_id="a")
    assert res["status"] == "FAILED"
    res2 = client.get_memorize_status("t")
    assert res2["status"] == "FAILED"
    res3 = client.list_categories("u", "a")
    assert res3 == {"categories": []}
    res4 = client.retrieve("u", "a", "q")
    assert res4["items"] == []
    res5 = client.delete_memories("u")
    assert res5 == "MemU API Key is not configured."


# ==================== Async Client Tests ====================


@pytest.mark.asyncio
@patch("agent.core.memu.httpx.AsyncClient")
async def test_amemorize(mock_async_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"task_id": "t1", "status": "PENDING"}

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.request = AsyncMock(return_value=mock_response)
    mock_async_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    convo = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]
    res = await client.amemorize(convo, user_id="u1", agent_id="a1")
    assert res["task_id"] == "t1"
    assert res["status"] == "PENDING"


@pytest.mark.asyncio
@patch("agent.core.memu.httpx.AsyncClient")
async def test_aretrieve(mock_async_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "rewritten_query": "hobbies?",
        "items": [{"memory_type": "fact", "content": "Likes Python"}],
        "categories": [],
        "resources": [],
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.request = AsyncMock(return_value=mock_response)
    mock_async_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = await client.aretrieve("u1", "a1", query="hobbies")
    assert res["items"][0]["content"] == "Likes Python"


@pytest.mark.asyncio
async def test_amemorize_not_configured(monkeypatch):
    monkeypatch.delenv("MEMU_API_KEY", raising=False)
    client = MemUClient()
    res = await client.amemorize([], user_id="u", agent_id="a")
    assert res["status"] == "FAILED"


@pytest.mark.asyncio
async def test_aretrieve_not_configured(monkeypatch):
    monkeypatch.delenv("MEMU_API_KEY", raising=False)
    client = MemUClient()
    res = await client.aretrieve("u", "a", "q")
    assert res["items"] == []


@pytest.mark.asyncio
@patch("agent.core.memu.httpx.AsyncClient")
async def test_adelete_memories(mock_async_client_class):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = "Memories deleted successfully"

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.request = AsyncMock(return_value=mock_response)
    mock_async_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = await client.adelete_memories("u1", "a1")
    assert res == "Memories deleted successfully"


# ==================== Tenacity Retry Tests ====================


@patch("agent.core.memu.httpx.Client")
def test_sync_retry_on_500_then_success(mock_client_class):
    """Simulate server returning 500 twice then 200 — tenacity should retry and succeed."""
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.text = "Internal Server Error"
    fail_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=fail_response
        )
    )

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {
        "rewritten_query": "test",
        "items": [],
        "categories": [],
        "resources": [],
    }

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request = MagicMock(
        side_effect=[fail_response, fail_response, ok_response]
    )
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = client.retrieve("u1", "a1", query="test")

    assert res["rewritten_query"] == "test"
    assert mock_client_instance.request.call_count == 3


@patch("agent.core.memu.httpx.Client")
def test_sync_retry_exhausted_returns_fallback(mock_client_class):
    """After 3 retries all fail, the method should return a fallback response."""
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.text = "Internal Server Error"
    fail_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=fail_response
        )
    )

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.request = MagicMock(return_value=fail_response)
    mock_client_class.return_value = mock_client_instance

    client = MemUClient(api_key="test_key")
    res = client.retrieve("u1", "a1", query="test")

    # Should return fallback (empty) rather than raising
    assert res["items"] == []


# ==================== Tool Registration Tests ====================


def test_memu_tools_registration():
    tools = create_builtin_tools(local_mode=True)
    specs = {t.name: t for t in tools}

    assert "memu_retrieve_memories" in specs
    assert "memu_memorize_session" in specs

    assert "query" in specs["memu_retrieve_memories"].parameters["properties"]
    assert "conversation" in specs["memu_memorize_session"].parameters["properties"]


# ==================== Tool Handler Tests ====================


@pytest.mark.asyncio
@patch("agent.core.memu.MemUClient.aretrieve")
async def test_memu_retrieve_handler_works(mock_aretrieve, monkeypatch):
    monkeypatch.setenv("MEMU_API_KEY", "dummy")
    mock_aretrieve.return_value = {
        "items": [{"content": "Retrieved", "memory_type": "fact"}],
        "categories": [],
        "resources": [],
        "rewritten_query": "test",
    }

    tools = create_builtin_tools(local_mode=True)
    memu_retrieve = [t for t in tools if t.name == "memu_retrieve_memories"][0]

    output, ok = await memu_retrieve.handler({"query": "test query"})
    assert ok is True
    data = json.loads(output)
    assert data["items"][0]["content"] == "Retrieved"


@pytest.mark.asyncio
@patch("agent.core.memu.MemUClient.amemorize")
async def test_memu_memorize_handler_works(mock_amemorize, monkeypatch):
    monkeypatch.setenv("MEMU_API_KEY", "dummy")
    mock_amemorize.return_value = {"status": "SUCCESS", "task_id": "123"}

    tools = create_builtin_tools(local_mode=True)
    memu_memorize = [t for t in tools if t.name == "memu_memorize_session"][0]

    convo = [{"role": "user", "content": "hello"}]
    output, ok = await memu_memorize.handler({"conversation": convo})
    assert ok is True
    data = json.loads(output)
    assert data["status"] == "SUCCESS"


# ==================== Reusable Connection Pool and Cache Eviction Tests ====================


def test_memu_client_connection_pooling():
    client = MemUClient(api_key="test_key")
    
    # Verify synchronous client reuse
    c1 = client.get_client()
    c2 = client.get_client()
    assert c1 is c2
    assert isinstance(c1, httpx.Client)

    # Verify asynchronous client reuse
    ac1 = client.get_aclient()
    ac2 = client.get_aclient()
    assert ac1 is ac2
    assert isinstance(ac1, httpx.AsyncClient)


def test_memu_client_cache_eviction():
    client = MemUClient(api_key="test_key")
    
    # Fill cache up to the 128 limit
    for i in range(128):
        client._add_to_cache(f"key_{i}", f"val_{i}")
    
    assert len(client._cache) == 128
    assert "key_0" in client._cache

    # Add 129th item, which should trigger eviction of "key_0" (the oldest item)
    client._add_to_cache("key_128", "val_128")
    assert len(client._cache) == 128
    assert "key_0" not in client._cache
    assert "key_128" in client._cache
    assert "key_1" in client._cache


# ==================== Fallback Cache and Timeout Tests ====================


def test_memu_fallback_cache_save_and_load(tmp_path, monkeypatch):
    from agent.core import memu
    
    # Override local memories fallback path to a temporary file
    temp_fallback_path = tmp_path / "local_memories_fallback.json"
    monkeypatch.setattr(memu, "LOCAL_MEMORIES_FALLBACK_PATH", temp_fallback_path)
    
    dummy_res = {
        "rewritten_query": "What are hobbies?",
        "categories": [{"name": "sports", "summary": "John plays tennis."}],
        "items": [],
        "resources": [],
    }
    
    # Save cache
    memu._save_local_fallback_cache("user_dummy", "agent_dummy", dummy_res)
    
    # Load cache
    loaded = memu._load_local_fallback_cache("user_dummy", "agent_dummy")
    assert loaded is not None
    assert loaded["rewritten_query"] == "What are hobbies?"
    assert len(loaded["categories"]) == 1
    
    # Load cache for non-existent key
    assert memu._load_local_fallback_cache("other", "other") is None


@patch("agent.core.memu.httpx.Client")
def test_memu_retrieve_fallback_on_network_failure(mock_client_class, tmp_path, monkeypatch):
    from agent.core import memu
    
    temp_fallback_path = tmp_path / "local_memories_fallback.json"
    monkeypatch.setattr(memu, "LOCAL_MEMORIES_FALLBACK_PATH", temp_fallback_path)
    
    # Save a known cache
    dummy_res = {
        "rewritten_query": "hobbies",
        "categories": [{"name": "sports", "summary": "tennis"}],
        "items": [],
        "resources": [],
    }
    memu._save_local_fallback_cache("user_test", "agent_test", dummy_res)
    
    # Mock network client to throw timeout exception
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_instance.request.side_effect = httpx.TimeoutException("Connection timed out")
    mock_client_class.return_value = mock_client_instance
    
    client = MemUClient(api_key="test_key")
    
    # Call retrieve - should catch exception and fallback
    res = client.retrieve("user_test", "agent_test", query="hobbies")
    
    assert res["rewritten_query"] == "hobbies"
    assert res["categories"][0]["summary"] == "tennis"


@pytest.mark.asyncio
@patch("agent.core.memu.httpx.AsyncClient")
async def test_memu_aretrieve_fallback_on_network_failure(mock_aclient_class, tmp_path, monkeypatch):
    from agent.core import memu
    
    temp_fallback_path = tmp_path / "local_memories_fallback.json"
    monkeypatch.setattr(memu, "LOCAL_MEMORIES_FALLBACK_PATH", temp_fallback_path)
    
    # Save a known cache
    dummy_res = {
        "rewritten_query": "hobbies async",
        "categories": [{"name": "sports", "summary": "tennis async"}],
        "items": [],
        "resources": [],
    }
    memu._save_local_fallback_cache("user_test", "agent_test", dummy_res)
    
    # Mock network client to throw error
    mock_aclient_instance = MagicMock()
    mock_aclient_instance.__aenter__ = AsyncMock(return_value=mock_aclient_instance)
    mock_aclient_instance.request.side_effect = httpx.ConnectError("Failed to connect")
    mock_aclient_class.return_value = mock_aclient_instance
    
    client = MemUClient(api_key="test_key")
    
    # Call aretrieve - should catch exception and fallback
    res = await client.aretrieve("user_test", "agent_test", query="hobbies async")
    
    assert res["rewritten_query"] == "hobbies async"
    assert res["categories"][0]["summary"] == "tennis async"


