"""
MemU Client for AI Agent Memory Layer
Wraps api.memu.so endpoints for storing and retrieving memories semantically.
"""

from __future__ import annotations

import logging
import os
import requests
from typing import Any, Dict, List, Union

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

    def memorize(
        self,
        conversation: List[Dict[str, Any]],
        user_id: str,
        agent_id: str,
        user_name: str | None = None,
        agent_name: str | None = None,
        session_date: str | None = None,
    ) -> Dict[str, Any]:
        """
        Register a memorization task to extract and store memories from a conversation.
        Requires at least 3 messages in the conversation.
        """
        if not self.is_configured():
            logger.warning("MemU API Key is not configured.")
            return {"status": "FAILED", "message": "MemU API Key is not configured."}

        url = f"{self.base_url}/api/v3/memory/memorize"
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
            response = requests.post(
                url, json=payload, headers=self.headers, timeout=30
            )
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

        url = f"{self.base_url}/api/v3/memory/memorize/status/{task_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
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

        url = f"{self.base_url}/api/v3/memory/categories"
        payload = {
            "user_id": user_id,
            "agent_id": agent_id,
        }
        try:
            response = requests.post(
                url, json=payload, headers=self.headers, timeout=15
            )
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
        """
        Retrieve memories using semantic search.
        query can be a search string or a message list with query rewriting.
        """
        if not self.is_configured():
            logger.warning("MemU API Key not configured. Returning empty retrieval.")
            return {
                "rewritten_query": str(query),
                "categories": [],
                "items": [],
                "resources": [],
            }

        url = f"{self.base_url}/api/v3/memory/retrieve"
        payload = {
            "user_id": user_id,
            "agent_id": agent_id,
            "query": query,
        }
        try:
            response = requests.post(
                url, json=payload, headers=self.headers, timeout=20
            )
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
        """Delete memories for a user. If agent_id is provided, delete only that agent's memories."""
        if not self.is_configured():
            return "MemU API Key is not configured."

        url = f"{self.base_url}/api/v3/memory/delete"
        payload: Dict[str, Any] = {"user_id": user_id}
        if agent_id:
            payload["agent_id"] = agent_id

        try:
            response = requests.post(
                url, json=payload, headers=self.headers, timeout=15
            )
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
