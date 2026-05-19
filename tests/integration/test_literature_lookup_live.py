"""Opt-in live checks for official literature metadata APIs.

Run with ``AIDD_INTERN_LIVE_LITERATURE_TESTS=1``. These tests do not use model
APIs or credentials; they call public arXiv and bioRxiv/medRxiv metadata APIs.
"""

from __future__ import annotations

import os

import pytest

from agent.tools.literature_lookup_tool import literature_lookup_handler


def _skip_without_live_flag() -> None:
    if os.environ.get("AIDD_INTERN_LIVE_LITERATURE_TESTS") != "1":
        pytest.skip("set AIDD_INTERN_LIVE_LITERATURE_TESTS=1 to run live API checks")


@pytest.mark.asyncio
async def test_live_arxiv_details_and_medrxiv_doi_lookup():
    _skip_without_live_flag()

    print("STEP 1: Fetch arXiv metadata through export.arxiv.org API")
    arxiv_output, arxiv_ok = await literature_lookup_handler(
        {"operation": "details", "identifier": "1605.08386", "source": "arxiv"}
    )
    print(arxiv_output[:800])
    assert arxiv_ok
    assert "arXiv API" in arxiv_output
    assert "1605.08386" in arxiv_output

    print("STEP 2: Fetch medRxiv DOI through api.biorxiv.org details endpoint")
    medrxiv_output, medrxiv_ok = await literature_lookup_handler(
        {
            "operation": "details",
            "identifier": "10.1101/2020.09.09.20191205",
            "source": "medrxiv",
        }
    )
    print(medrxiv_output[:800])
    assert medrxiv_ok
    assert "medrxiv API" in medrxiv_output
    assert "Evolution of immunity to SARS-CoV-2" in medrxiv_output
