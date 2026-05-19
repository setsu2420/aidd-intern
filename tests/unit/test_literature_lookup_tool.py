from agent.tools import literature_lookup_tool as lit


def test_normalizes_real_identifiers():
    assert lit._normalize_doi("https://doi.org/10.1101/2020.09.09.20191205") == (
        "10.1101/2020.09.09.20191205"
    )
    assert lit._normalize_doi("DOI:10.3389/fimmu.2025.1571371") == (
        "10.3389/fimmu.2025.1571371"
    )
    assert lit._looks_like_arxiv_id("arXiv:1605.08386")
    assert lit._normalize_arxiv_id("https://arxiv.org/pdf/1605.08386.pdf") == (
        "1605.08386"
    )


def test_source_aliases_include_bioarxiv_typo_and_preprint_sources():
    assert lit._parse_sources("bioArxiv, medrxiv, pmc") == {
        "biorxiv",
        "medrxiv",
        "pmc",
    }
    assert "preprints" in lit._parse_sources(["PPR"])


def test_biorxiv_collection_is_formatted_as_api_metadata():
    records = lit._parse_biorxiv_collection(
        [
            {
                "title": "Evolution of immunity to SARS-CoV-2",
                "authors": "Wheatley, A. K.; Kent, S. J.",
                "doi": "10.1101/2020.09.09.20191205",
                "date": "2020-09-10",
                "server": "medRxiv",
                "category": "infectious diseases",
                "abstract": "The immune response to SARS-CoV-2 changes over time.",
                "jatsxml": (
                    "https://www.medrxiv.org/content/early/2020/09/10/"
                    "2020.09.09.20191205.source.xml"
                ),
            }
        ],
        source_label="medrxiv API",
    )

    assert records[0]["source"] == "medrxiv"
    assert records[0]["doi"] == "10.1101/2020.09.09.20191205"
    assert records[0]["url"] == "https://doi.org/10.1101/2020.09.09.20191205"
    assert records[0]["links"][0]["site"] == "JATS XML"
