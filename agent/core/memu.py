"""
MemU Client for AI Agent Memory Layer
Wraps api.memu.so endpoints for storing and retrieving memories semantically.
Fully supports synchronous and asynchronous calls, automatic tenacity retries,
and robust validation.
"""

from __future__ import annotations

import logging
import os
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Union
import httpx
from tenacity import (
    AsyncRetrying,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

LOCAL_MEMORIES_FALLBACK_PATH = Path(
    "~/.gemini/antigravity-cli/local_memories_fallback.json"
).expanduser()


try:
    from aidd_intern_core import (
        read_file_utf8,
        json_dumps_sorted,
        save_json_atomic,
    )

    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False


def _load_local_fallback_cache(user_id: str, agent_id: str) -> Dict[str, Any] | None:
    """Load user-agent specific memory cache from local fallback storage, using Rust if available."""
    try:
        if LOCAL_MEMORIES_FALLBACK_PATH.exists():
            if _RUST_AVAILABLE:
                try:
                    # 使用 Rust 原生高效 UTF-8 文件读取
                    content = read_file_utf8(str(LOCAL_MEMORIES_FALLBACK_PATH))
                except Exception as re:
                    logger.warning("Rust read_file_utf8 failed, falling back: %s", re)
                    with open(LOCAL_MEMORIES_FALLBACK_PATH, "r", encoding="utf-8") as f:
                        content = f.read()
            else:
                with open(LOCAL_MEMORIES_FALLBACK_PATH, "r", encoding="utf-8") as f:
                    content = f.read()

            if content:
                data = json.loads(content)
                key = f"{user_id}:{agent_id}"
                if isinstance(data, dict) and key in data:
                    return data[key]
    except Exception as e:
        logger.warning("Failed to load local fallback memory cache: %s", e)
    return None


def _save_local_fallback_cache(
    user_id: str, agent_id: str, raw_res: Dict[str, Any]
) -> None:
    """Save user-agent specific memory cache to local fallback storage, using Rust if available."""
    try:
        LOCAL_MEMORIES_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if LOCAL_MEMORIES_FALLBACK_PATH.exists():
            try:
                # 尽量用 Rust 读取已有数据
                if _RUST_AVAILABLE:
                    try:
                        content = read_file_utf8(str(LOCAL_MEMORIES_FALLBACK_PATH))
                    except Exception:
                        with open(
                            LOCAL_MEMORIES_FALLBACK_PATH, "r", encoding="utf-8"
                        ) as f:
                            content = f.read()
                else:
                    with open(LOCAL_MEMORIES_FALLBACK_PATH, "r", encoding="utf-8") as f:
                        content = f.read()
                if content:
                    data = json.loads(content)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        key = f"{user_id}:{agent_id}"
        data[key] = raw_res

        # 序列化为 JSON 字符串并原子级写盘
        if _RUST_AVAILABLE:
            try:
                # 使用 Rust 极速无 GIL 锁的 JSON 转换
                json_str = json_dumps_sorted(data)
                # 使用 Rust 的原子级原子写（tempfile + rename，安全高防灾）
                save_json_atomic(
                    str(LOCAL_MEMORIES_FALLBACK_PATH), json_str.encode("utf-8")
                )
                return
            except Exception as we:
                logger.warning(
                    "Rust JSON serialization/write failed, falling back: %s", we
                )

        # 纯 Python 兜底持久化
        with open(LOCAL_MEMORIES_FALLBACK_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save local fallback memory cache: %s", e)


BASE_URL = "https://api.memu.so"


class MemUClient:
    """Client for interacting with the MemU Agentic Memory API."""

    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL):
        self.api_key = api_key or os.environ.get("MEMU_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self._cache: Dict[Any, tuple[float, Any]] = {}
        self._client: httpx.Client | None = None
        self._aclient: httpx.AsyncClient | None = None

    def get_client(self) -> httpx.Client:
        """Get or create the reusable synchronous HTTPX client connection pool."""
        if self._client is None:
            self._client = httpx.Client()
        return self._client

    def get_aclient(self) -> httpx.AsyncClient:
        """Get or create the reusable asynchronous HTTPX client connection pool."""
        if self._aclient is None:
            self._aclient = httpx.AsyncClient()
        return self._aclient

    def _add_to_cache(self, key: Any, val: Any) -> None:
        """Add to cache with a hard limit of 128 items to prevent memory leak."""
        if len(self._cache) >= 128:
            try:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key, None)
            except (StopIteration, RuntimeError):
                pass
        self._cache[key] = (time.time(), val)

    def _get_cache_key(self, user_id: str, agent_id: str, query: Any) -> Any:
        """Helper to build a hashable immutable cache key for MemU query."""
        if isinstance(query, list):
            flat = []
            for item in query:
                if isinstance(item, dict):
                    flat.append(tuple(sorted(item.items())))
                else:
                    flat.append(item)
            query_key = tuple(flat)
        else:
            query_key = query
        return (user_id, agent_id, query_key)

    @property
    def headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_configured(self) -> bool:
        """Check if API Key is configured."""
        return bool(self.api_key)

    def _send_request(
        self, method: str, path: str, timeout: float = 15.0, **kwargs
    ) -> httpx.Response:
        """Send a synchronous request with tenacity retry for connection/timeout and 5xx errors."""
        url = f"{self.base_url}{path}"
        client = self.get_client()

        for attempt in Retrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                response = client.request(
                    method, url, headers=self.headers, timeout=timeout, **kwargs
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                return response

    async def _send_request_async(
        self, method: str, path: str, timeout: float = 15.0, **kwargs
    ) -> httpx.Response:
        """Send an asynchronous request with tenacity retry for connection/timeout and 5xx errors."""
        url = f"{self.base_url}{path}"
        client = self.get_aclient()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                response = await client.request(
                    method, url, headers=self.headers, timeout=timeout, **kwargs
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                return response

    def _validate_conversation(
        self, conversation: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Defensively validate and pad conversations to satisfy the 3-message minimum API requirement."""
        if not conversation:
            return [
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."},
                {"role": "user", "content": "..."},
            ]

        valid_convo = list(conversation)
        while len(valid_convo) < 3:
            last_role = valid_convo[-1].get("role", "user")
            next_role = "assistant" if last_role == "user" else "user"
            valid_convo.append({"role": next_role, "content": "..."})
        return valid_convo

    # ==================== Synchronous API ====================

    def memorize(
        self,
        conversation: List[Dict[str, Any]],
        user_id: str,
        agent_id: str,
        user_name: str | None = None,
        agent_name: str | None = None,
        session_date: str | None = None,
    ) -> Dict[str, Any]:
        """Register a memorization task to extract and store memories from a conversation."""
        if not self.is_configured():
            logger.warning("MemU API Key is not configured.")
            return {"status": "FAILED", "message": "MemU API Key is not configured."}

        conversation = self._validate_conversation(conversation)
        path = "/api/v3/memory/memorize"
        payload: Dict[str, Any] = {
            "conversation": conversation,
            "user_id": user_id,
            "agent_id": agent_id,
        }
        if user_name:
            payload["user_name"] = user_name
        if agent_name:
            payload["agent_name"] = agent_name
        if session_date:
            payload["session_date"] = session_date

        try:
            response = self._send_request("POST", path, json=payload, timeout=30.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU memorize failed: {response.status_code} {response.text}"
                )
                return {
                    "status": "FAILED",
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
        except Exception as e:
            logger.error(f"MemU memorize exception: {e}")
            return {"status": "FAILED", "message": str(e)}

    def get_memorize_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a memorization task."""
        if not self.is_configured():
            return {"status": "FAILED", "message": "MemU API Key is not configured."}

        path = f"/api/v3/memory/memorize/status/{task_id}"
        try:
            response = self._send_request("GET", path, timeout=15.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU status failed: {response.status_code} {response.text}"
                )
                return {
                    "status": "FAILED",
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
        except Exception as e:
            logger.error(f"MemU status exception: {e}")
            return {"status": "FAILED", "message": str(e)}

    def list_categories(self, user_id: str, agent_id: str) -> Dict[str, Any]:
        """Retrieve all memory categories for a user/agent combination."""
        if not self.is_configured():
            return {"categories": []}

        path = "/api/v3/memory/categories"
        payload = {"user_id": user_id, "agent_id": agent_id}
        try:
            response = self._send_request("POST", path, json=payload, timeout=15.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU categories failed: {response.status_code} {response.text}"
                )
                return {"categories": []}
        except Exception as e:
            logger.error(f"MemU categories exception: {e}")
            return {"categories": []}

    def retrieve(
        self,
        user_id: str,
        agent_id: str,
        query: Union[str, List[Dict[str, Any]]],
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        """Retrieve memories using semantic search, with local fallback cache."""
        if not self.is_configured():
            logger.warning("MemU API Key not configured. Loading local fallback cache.")
            cached = _load_local_fallback_cache(user_id, agent_id)
            if cached:
                return cached
            return {
                "rewritten_query": str(query),
                "categories": [],
                "items": [],
                "resources": [],
            }

        cache_key = self._get_cache_key(user_id, agent_id, query)
        now = time.time()
        if cache_key in self._cache:
            ts, val = self._cache[cache_key]
            if now - ts < 300.0:  # 5 minutes TTL
                logger.info("MemU retrieve semantic cache hit!")
                return val

        path = "/api/v3/memory/retrieve"
        payload = {"user_id": user_id, "agent_id": agent_id, "query": query}
        try:
            response = self._send_request("POST", path, json=payload, timeout=timeout)
            if response.status_code == 200:
                res = response.json()
                self._add_to_cache(cache_key, res)
                _save_local_fallback_cache(user_id, agent_id, res)
                return res
            else:
                logger.error(
                    f"MemU retrieve failed (HTTP {response.status_code}): {response.text}"
                )
        except Exception as e:
            logger.error(f"MemU retrieve exception: {e}")

        # Fallback to local cache on request failure
        cached = _load_local_fallback_cache(user_id, agent_id)
        if cached:
            logger.info("Successfully fell back to local memory cache.")
            return cached

        return {
            "rewritten_query": str(query),
            "categories": [],
            "items": [],
            "resources": [],
        }

    def delete_memories(
        self, user_id: str, agent_id: str | None = None
    ) -> Union[str, Dict[str, Any]]:
        """Delete memories for a user."""
        if not self.is_configured():
            return "MemU API Key is not configured."

        path = "/api/v3/memory/delete"
        payload: Dict[str, Any] = {"user_id": user_id}
        if agent_id:
            payload["agent_id"] = agent_id

        try:
            response = self._send_request("POST", path, json=payload, timeout=15.0)
            if response.status_code == 200:
                self._cache.clear()
                return response.json()
            else:
                logger.error(
                    f"MemU delete failed: {response.status_code} {response.text}"
                )
                return {
                    "status": "FAILED",
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
        except Exception as e:
            logger.error(f"MemU delete exception: {e}")
            return {"status": "FAILED", "message": str(e)}

    # ==================== Asynchronous API ====================

    async def amemorize(
        self,
        conversation: List[Dict[str, Any]],
        user_id: str,
        agent_id: str,
        user_name: str | None = None,
        agent_name: str | None = None,
        session_date: str | None = None,
    ) -> Dict[str, Any]:
        """Register a memorization task asymptotically."""
        if not self.is_configured():
            logger.warning("MemU API Key is not configured.")
            return {"status": "FAILED", "message": "MemU API Key is not configured."}

        conversation = self._validate_conversation(conversation)
        path = "/api/v3/memory/memorize"
        payload: Dict[str, Any] = {
            "conversation": conversation,
            "user_id": user_id,
            "agent_id": agent_id,
        }
        if user_name:
            payload["user_name"] = user_name
        if agent_name:
            payload["agent_name"] = agent_name
        if session_date:
            payload["session_date"] = session_date

        try:
            response = await self._send_request_async(
                "POST", path, json=payload, timeout=30.0
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU memorize async failed: {response.status_code} {response.text}"
                )
                return {
                    "status": "FAILED",
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
        except Exception as e:
            logger.error(f"MemU memorize async exception: {e}")
            return {"status": "FAILED", "message": str(e)}

    async def aget_memorize_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a memorization task asymptotically."""
        if not self.is_configured():
            return {"status": "FAILED", "message": "MemU API Key is not configured."}

        path = f"/api/v3/memory/memorize/status/{task_id}"
        try:
            response = await self._send_request_async("GET", path, timeout=15.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU status async failed: {response.status_code} {response.text}"
                )
                return {
                    "status": "FAILED",
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
        except Exception as e:
            logger.error(f"MemU status async exception: {e}")
            return {"status": "FAILED", "message": str(e)}

    async def alist_categories(self, user_id: str, agent_id: str) -> Dict[str, Any]:
        """Retrieve all memory categories asymptotically."""
        if not self.is_configured():
            return {"categories": []}

        path = "/api/v3/memory/categories"
        payload = {"user_id": user_id, "agent_id": agent_id}
        try:
            response = await self._send_request_async(
                "POST", path, json=payload, timeout=15.0
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU categories async failed: {response.status_code} {response.text}"
                )
                return {"categories": []}
        except Exception as e:
            logger.error(f"MemU categories async exception: {e}")
            return {"categories": []}

    async def aretrieve(
        self,
        user_id: str,
        agent_id: str,
        query: Union[str, List[Dict[str, Any]]],
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        """Retrieve memories asymptotically using semantic search, with local fallback cache."""
        if not self.is_configured():
            logger.warning("MemU API Key not configured. Loading local fallback cache.")
            cached = _load_local_fallback_cache(user_id, agent_id)
            if cached:
                return cached
            return {
                "rewritten_query": str(query),
                "categories": [],
                "items": [],
                "resources": [],
            }

        cache_key = self._get_cache_key(user_id, agent_id, query)
        now = time.time()
        if cache_key in self._cache:
            ts, val = self._cache[cache_key]
            if now - ts < 300.0:  # 5 minutes TTL
                logger.info("MemU retrieve async semantic cache hit!")
                return val

        path = "/api/v3/memory/retrieve"
        payload = {"user_id": user_id, "agent_id": agent_id, "query": query}
        try:
            response = await self._send_request_async(
                "POST", path, json=payload, timeout=timeout
            )
            if response.status_code == 200:
                res = response.json()
                self._add_to_cache(cache_key, res)
                _save_local_fallback_cache(user_id, agent_id, res)
                return res
            else:
                logger.error(
                    f"MemU retrieve async failed (HTTP {response.status_code}): {response.text}"
                )
        except Exception as e:
            logger.error(f"MemU retrieve async exception: {e}")

        # Fallback to local cache on request failure
        cached = _load_local_fallback_cache(user_id, agent_id)
        if cached:
            logger.info("Successfully fell back to local memory cache.")
            return cached

        return {
            "rewritten_query": str(query),
            "categories": [],
            "items": [],
            "resources": [],
        }

    async def adelete_memories(
        self, user_id: str, agent_id: str | None = None
    ) -> Union[str, Dict[str, Any]]:
        """Delete memories asymptotically for a user."""
        if not self.is_configured():
            return "MemU API Key is not configured."

        path = "/api/v3/memory/delete"
        payload: Dict[str, Any] = {"user_id": user_id}
        if agent_id:
            payload["agent_id"] = agent_id

        try:
            response = await self._send_request_async(
                "POST", path, json=payload, timeout=15.0
            )
            if response.status_code == 200:
                self._cache.clear()
                return response.json()
            else:
                logger.error(
                    f"MemU delete async failed: {response.status_code} {response.text}"
                )
                return {
                    "status": "FAILED",
                    "message": f"HTTP {response.status_code}: {response.text}",
                }
        except Exception as e:
            logger.error(f"MemU delete async exception: {e}")
            return {"status": "FAILED", "message": str(e)}
