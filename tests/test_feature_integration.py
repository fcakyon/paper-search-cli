"""Cross-feature coverage for CLI operations, source gates, and caching.

All provider calls are mocked. This does not certify external entitlements.
"""
import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from paper_search_cli import cli, config
from paper_search_cli import operations as server
from paper_search_cli.academic_platforms.scopus import ScopusSearcher
from paper_search_cli.academic_platforms.wos import WebOfScienceSearcher
from paper_search_cli.search_cache import CacheSettings, SearchCache, search_key

@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("NETRC", str(tmp_path / "absent.netrc"))
    monkeypatch.setattr(config, "_ENV_LOADED", True)
    for key in ("WOS_API_KEY", "SCOPUS_API_KEY", "SCOPUS_INST_TOKEN", "OPENALEX_API_KEY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("PAPER_SEARCH_MCP_" + key, raising=False)
    monkeypatch.setattr(server, "_SEARCH_CACHE", SearchCache(CacheSettings(path=tmp_path / "disabled.sqlite3")))
    monkeypatch.setattr(cli, "SEARCHERS", {})


def tool(*arguments):
    args = cli.build_parser().parse_args(["tool", *arguments])
    return asyncio.run(cli.cmd_tool(args))


@pytest.mark.parametrize("source,options,expected", [
    ("openreview", [], {}),
    ("wos", ["--db", "MEDLINE"], {"db": "MEDLINE"}),
    ("scopus", ["--view", "COMPLETE", "--sort", "coverDate", "--field", "TITLE", "--date", "2020-2024"],
     {"view": "COMPLETE", "sort": "coverDate", "field": "TITLE", "date": "2020-2024"}),
])
def test_added_search_tools_dispatch_to_the_actual_connector(source, options, expected, monkeypatch, capsys):
    search = Mock(return_value=[])
    if source == "openreview":
        monkeypatch.setattr(server.openreview_searcher, "search", search)
    else:
        cls = WebOfScienceSearcher if source == "wos" else ScopusSearcher
        monkeypatch.setattr(cls, "search", search)
    assert tool("search_" + source, "query", "--max-results", "3", *options) == 0
    assert json.loads(capsys.readouterr().out) == []
    search.assert_called_once_with("query", max_results=3, **expected)


@pytest.mark.parametrize("name,method", [("download_openreview", "download_pdf"), ("read_openreview_paper", "read_paper")])
def test_openreview_file_tools_preserve_explicit_destination(name, method, monkeypatch, capsys):
    run = Mock(return_value="local result")
    monkeypatch.setattr(server.openreview_searcher, method, run)
    assert tool(name, "public-note", "--save-path", "explicit-directory") == 0
    assert capsys.readouterr().out == "local result\n"
    run.assert_called_once_with("public-note", "explicit-directory")


@pytest.mark.parametrize("options,enabled", [([], False), (["--full-text"], True), (["--no-full-text"], False)])
def test_scopus_tool_never_enables_full_text_implicitly(options, enabled, monkeypatch, capsys):
    read = Mock(return_value={"status": "abstract_only", "reason": "fixture", "abstract": "text"})
    monkeypatch.setattr(ScopusSearcher, "read_paper", read)
    assert tool("read_scopus_paper", "12345", *options) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "abstract_only"
    read.assert_called_once_with("12345", full_text=enabled)


@pytest.mark.parametrize("name,method", [("get_citing_papers", "get_citations"), ("get_referenced_papers", "get_references")])
def test_relation_tools_preserve_all_budgets(name, method, monkeypatch, capsys):
    lookup = Mock(return_value={"papers": [], "truncated": False})
    monkeypatch.setattr(server.openalex_searcher, method, lookup)
    assert tool(name, "W123", "--max-results", "3", "--filter", "publication_year:2024",
                "--max-pages", "2", "--max-requests", "4", "--timeout-seconds", "2.5") == 0
    assert json.loads(capsys.readouterr().out)["papers"] == []
    lookup.assert_called_once_with("W123", max_results=3, filter="publication_year:2024",
                                 max_pages=2, max_requests=4, timeout_seconds=2.5)


@pytest.mark.parametrize("source,options,expected", [
    ("openreview", [], {}),
    ("wos", ["--wos-db", "MEDLINE"], {"db": "MEDLINE"}),
    ("scopus", ["--scopus-view", "COMPLETE", "--scopus-sort", "coverDate", "--scopus-field", "TITLE", "--scopus-date", "2020-2024"],
     {"view": "COMPLETE", "sort": "coverDate", "field": "TITLE", "date": "2020-2024"}),
])
def test_ordinary_cli_still_honors_source_specific_options(source, options, expected, monkeypatch, capsys):
    searcher = Mock()
    searcher.search.return_value = []
    monkeypatch.setattr(cli, "_get_searcher", Mock(return_value=searcher))
    args = cli.build_parser().parse_args(["search", "query", "-s", source, "-n", "3", *options])
    assert asyncio.run(cli.cmd_search(args)) == 0
    assert json.loads(capsys.readouterr().out)["sources_used"] == [source]
    searcher.search.assert_called_once_with("query", max_results=3, **expected)


def test_default_sources_and_institutional_credentials_remain_independent(monkeypatch):
    monkeypatch.setenv("PAPER_SEARCH_MCP_WOS_API_KEY", "fixture")
    monkeypatch.setenv("PAPER_SEARCH_MCP_SCOPUS_API_KEY", "fixture")
    for preset in ("all", "fast", "fastest"):
        assert {"wos", "scopus", "scihub"}.isdisjoint(cli._parse_sources(preset))
    assert {"wos", "scopus", "scihub"}.isdisjoint(server._parse_sources("all"))
    assert "openreview" in cli._parse_sources("all")
    assert "openreview" in server._parse_sources("all")
    assert cli._parse_sources("scopus,wos") == ["scopus", "wos"]
    assert server._parse_sources("scopus,wos") == ["scopus", "wos"]


@pytest.mark.parametrize("source", ["wos", "scopus"])
def test_missing_institutional_keys_are_errors_and_never_cached(source, capsys):
    assert tool("search_" + source, "query") == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert "API_KEY" in result["message"]
    searcher = WebOfScienceSearcher() if source == "wos" else ScopusSearcher()
    assert search_key(searcher, "query", 3, {}) is None


def test_shared_cli_tool_cache_and_clear_do_not_touch_pdf_files(monkeypatch, tmp_path, capsys):
    from paper_search_cli.academic_platforms.openalex import OpenAlexSearcher
    cache = SearchCache(CacheSettings(enabled=True, path=tmp_path / "cache.sqlite3"))
    monkeypatch.setattr(server, "_SEARCH_CACHE", cache)
    searcher = OpenAlexSearcher(api_key="", email="")
    searcher.search = Mock(return_value=[SimpleNamespace(to_dict=lambda: {"paper_id": "W1", "title": "Public"})])
    monkeypatch.setattr(server, "openalex_searcher", searcher)
    for _ in range(2):
        assert tool("search_openalex", "query") == 0
        assert json.loads(capsys.readouterr().out)[0]["paper_id"] == "W1"
    searcher.search.assert_called_once()
    assert tool("get_search_cache_status") == 0
    status = json.loads(capsys.readouterr().out)
    assert status["enabled"] and status["entries"] == 1
    assert "query" not in status
    pdf = tmp_path / "existing.pdf"
    pdf.write_bytes(b"existing user file")
    assert tool("clear_search_cache") == 0
    assert json.loads(capsys.readouterr().out)["cleared"] == 1
    assert pdf.read_bytes() == b"existing user file"
    assert cache.status()["entries"] == 0


@pytest.mark.parametrize("location", [".netrc", "_netrc", "custom"])
def test_ambient_netrc_auth_never_enters_the_public_cache(location, monkeypatch, tmp_path):
    from paper_search_cli.academic_platforms.openalex import OpenAlexSearcher
    import requests
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NETRC", raising=False)
    if location == "custom":
        monkeypatch.setenv("NETRC", str(tmp_path / location))
    searcher = OpenAlexSearcher(api_key="", email="")
    assert search_key(searcher, "query", 1, {}) is not None
    (tmp_path / location).write_text("# Fixture location only, no stored credentials\n")
    monkeypatch.setattr("requests.sessions.get_netrc_auth", lambda url: ("fixture-user", "fixture-password"))
    prepared = searcher.session.prepare_request(requests.Request("GET", searcher.BASE_URL))
    assert prepared.headers.get("Authorization", "").startswith("Basic ")
    assert search_key(searcher, "query", 1, {}) is None


def test_pr_and_release_workflows_cover_every_added_deterministic_suite():
    from pathlib import Path
    import re
    root = Path(__file__).resolve().parents[1]
    expected = {
        "test_cli_tools.py", "test_feature_integration.py", "test_semantic_pdf_validation.py",
        "test_wos.py", "test_scopus.py", "test_institutional_http.py", "test_openreview.py",
        "test_ssrn_openalex.py", "test_ieee.py", "test_openalex_relations.py",
        "test_search_cache.py", "test_sections.py",
        "test_skill_zip_builder.py", "test_skill_archive_docs.py",
    }
    selections = []
    for filename in ("ci.yml", "publish.yml"):
        text = (root / ".github" / "workflows" / filename).read_text()
        selected = re.findall(r"^          (tests/\S+)", text, re.MULTILINE)
        assert len(selected) == len(set(selected))
        assert expected <= {Path(item.split("::", 1)[0]).name for item in selected}
        assert "tests/test_sci_hub.py" not in selected
        assert "tests/test_semantic.py" not in selected
        selections.append(selected)
    assert selections[0] == selections[1]
