"""Opt-in live check for Google Custom Search search results.

Run with ``AIDD_INTERN_LIVE_WEB_SEARCH_TESTS=1``. The test uses real Google
Custom Search credentials when they are available and skips otherwise.
"""

from __future__ import annotations

import os

import pytest

from agent.tools.web_search_tool import execute_web_search


def _skip_without_live_google() -> None:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") or os.environ.get(
        "GOOGLE_API_KEY"
    )
    engine_id = os.environ.get("GOOGLE_SEARCH_ENGINE_ID") or os.environ.get(
        "GOOGLE_CSE_ID"
    )
    if api_key and engine_id:
        return
    pytest.skip("Google Search credentials are not configured")


def test_live_google_custom_search_returns_links_and_recency_flags():
    _skip_without_live_google()

    query = 'site:developers.google.com/custom-search "Custom Search JSON API"'
    print("STEP 1: Running Google Custom Search with recency and date sorting")
    try:
        output = execute_web_search(
            query,
            allowed_domains=["developers.google.com"],
            recent_days=365,
            sort_by_date=True,
        )
    except RuntimeError as exc:
        if "Google Custom Search API returned HTTP 403" in str(exc):
            pytest.skip(f"Google Search API is configured but blocked: {exc}")
        raise
    print(f"STEP 2: Provider = {output['provider']}")
    print(f"STEP 3: recentDays = {output.get('recentDays')}")
    print(f"STEP 4: sortByDate = {output.get('sortByDate')}")
    print(f"STEP 5: Summary = {output['results'][0]}")

    content = next(item for item in output["results"] if isinstance(item, dict))[
        "content"
    ]
    print(f"STEP 6: First result URLs = {[item['url'] for item in content[:3]]}")

    assert output["provider"] == "Google"
    assert output["recentDays"] == 365
    assert output["sortByDate"] is True
    assert content
    assert all("url" in item for item in content)
    assert any("developers.google.com" in item["url"] for item in content)
