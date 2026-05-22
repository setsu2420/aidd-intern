"""
MemU Client for AI Agent Memory Layer
Wraps api.memu.so endpoints for storing and retrieving memories semantically.
Fully supports synchronous and asynchronous calls, automatic tenacity retries,
and robust validation.
"""

from __future__ import annotations

import logging
import os
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

BASE_URL = "https://api.memu.so"


class MemUClient:
    """Client for interacting with the MemU Agentic Memory API."""

    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL):
        self.api_key = api_key or os.environ.get("MEMU_API_KEY", "")
        self.base_url = base_url.rstrip("/")

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

        for attempt in Retrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                with httpx.Client(timeout=timeout) as client:
                    response = client.request(
                        method, url, headers=self.headers, **kwargs
                    )
                    if response.status_code >= 500:
                        response.raise_for_status()
                    return response

    async def _send_request_async(
        self, method: str, path: str, timeout: float = 15.0, **kwargs
    ) -> httpx.Response:
        """Send an asynchronous request with tenacity retry for connection/timeout and 5xx errors."""
        url = f"{self.base_url}{path}"

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method, url, headers=self.headers, **kwargs
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
    ) -> Dict[str, Any]:
        """Retrieve memories using semantic search."""
        if not self.is_configured():
            logger.warning("MemU API Key not configured. Returning empty retrieval.")
            return {
                "rewritten_query": str(query),
                "categories": [],
                "items": [],
                "resources": [],
            }

        path = "/api/v3/memory/retrieve"
        payload = {"user_id": user_id, "agent_id": agent_id, "query": query}
        try:
            response = self._send_request("POST", path, json=payload, timeout=20.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU retrieve failed: {response.status_code} {response.text}"
                )
                return {
                    "rewritten_query": str(query),
                    "categories": [],
                    "items": [],
                    "resources": [],
                }
        except Exception as e:
            logger.error(f"MemU retrieve exception: {e}")
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
    ) -> Dict[str, Any]:
        """Retrieve memories asymptotically using semantic search."""
        if not self.is_configured():
            logger.warning("MemU API Key not configured. Returning empty retrieval.")
            return {
                "rewritten_query": str(query),
                "categories": [],
                "items": [],
                "resources": [],
            }

        path = "/api/v3/memory/retrieve"
        payload = {"user_id": user_id, "agent_id": agent_id, "query": query}
        try:
            response = await self._send_request_async(
                "POST", path, json=payload, timeout=20.0
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"MemU retrieve async failed: {response.status_code} {response.text}"
                )
                return {
                    "rewritten_query": str(query),
                    "categories": [],
                    "items": [],
                    "resources": [],
                }
        except Exception as e:
            logger.error(f"MemU retrieve async exception: {e}")
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
