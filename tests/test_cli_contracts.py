"""Exercise command output through real parsers with offline HTTP responses."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def command(tmp_path):
    """Run a fresh CLI process without replacing providers or dispatch."""
    script = '''
import importlib.abc
import json
import os
import runpy
import sys
from urllib.parse import urlsplit
import requests

class WithoutMCP(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mcp', 'fastmcp', 'joserfc'}:
            raise ModuleNotFoundError('CLI requires optional dependency: ' + fullname)

if os.environ.get('TEST_WITHOUT_MCP'):
    sys.meta_path.insert(0, WithoutMCP())

def send(self, request, **kwargs):
    response = requests.Response()
    response.status_code = 200
    response.url = request.url
    response.request = request
    host = urlsplit(request.url).hostname
    if host == 'api.crossref.org':
        item = {'DOI': '10.1234/fixture', 'title': ['Fixture paper'],
                'author': [{'given': 'Ada', 'family': 'Example'}],
                'published': {'date-parts': [[2026, 10, 1]]},
                'type': 'journal-article', 'is-referenced-by-count': 7}
        message = {'items': [item]} if urlsplit(request.url).path == '/works' else item
        response._content = json.dumps({'status': 'ok', 'message': message}).encode()
    else:
        raise AssertionError('Unexpected network request: ' + request.url)
    return response

requests.Session.send = send
runpy.run_module('paper_search_mcp.cli', run_name='__main__')
'''
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('PAPER_SEARCH', 'TEST_WITHOUT_MCP'))}
    env['PAPER_SEARCH_MCP_ENV_FILE'] = str(tmp_path / 'absent.env')
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])

    def run(*args, without_mcp=False):
        return subprocess.run(
            [sys.executable, '-c', script, *args], cwd=tmp_path,
            env={**env, **({'TEST_WITHOUT_MCP': '1'} if without_mcp else {})},
            text=True, capture_output=True, timeout=20,
        )

    return run


@pytest.mark.parametrize('without_mcp', [False, True])
@pytest.mark.parametrize('args', [
    ('search', 'fixture', '-s', 'crossref', '-n', '1'),
    ('tool', 'search_crossref', 'fixture', '--max-results', '1'),
    ('tool', 'get_crossref_paper_by_doi', '10.1234/fixture'),
])
def test_search_and_lookup_preserve_metadata(command, without_mcp, args):
    """Keep real provider normalization reachable from an MCP-free CLI."""
    result = command(*args, without_mcp=without_mcp)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    if args[0] == 'search':
        assert payload['sources_used'] == ['crossref']
        assert payload['errors'] == {}
        paper, = payload['papers']
    elif args[1] == 'search_crossref':
        paper, = payload
    else:
        paper = payload
    assert paper['title'] == 'Fixture paper'
    assert paper['doi'] == '10.1234/fixture'
    assert paper['authors'] == 'Ada Example'
    assert paper['published_date'] == '2026-10-01T00:00:00'
    assert paper['citations'] == 7


@pytest.mark.parametrize('without_mcp', [False, True])
def test_tool_validation_rejects_invalid_limits_before_read(command, without_mcp):
    """Preserve strict PDF limits when transport validation is removed."""
    result = command('tool', 'extract_sections', 'missing.pdf', '--max-pages', '0',
                     without_mcp=without_mcp)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload['status'] == 'error'
    assert 'greater than or equal to 1' in payload['message']


@pytest.mark.parametrize('without_mcp', [False, True])
def test_read_limitations_remain_plain_text(command, without_mcp):
    """Preserve a metadata source's honest full-text limitation."""
    result = command('tool', 'read_crossref_paper', '10.1234/fixture', without_mcp=without_mcp)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'CrossRef papers cannot be read directly' in result.stdout
    assert not result.stdout.startswith(('{', '['))
