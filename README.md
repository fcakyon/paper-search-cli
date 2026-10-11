<p align="center">
  <img src="docs/images/logo.svg" width="80" height="80" alt="Paper Search CLI logo">
</p>

<h1 align="center">Paper Search CLI</h1>

<p align="center">Search papers, download PDFs, and follow citations from your terminal.</p>

![80 to 16 packages, 75.5 to 12.7 MB installed, 113 to 38 ms startup, and 366 to 0 MB background RAM between commands](docs/images/cli-comparison.webp)

<details>
<summary>How we measured</summary>

Fresh installs on macOS arm64, Python 3.13.7, 11 October 2026: [upstream cab1b5c](https://github.com/openags/paper-search-mcp/commit/cab1b5c) versus this fork's 0.2.0 wheel. Counts include the app, exclude development tools. Size is installed file bytes in decimal MB. Startup is the median of five `--help` launches. Search latency depends on providers.

Background RAM is a separate deployment comparison on macOS 27.0.1 arm64 with Apple container 1.5.0. The idle MCP server completed initialization using `mcp/paper-search` at image digest `sha256:19d0af269a5531403fbb042aad8277d1a9ec2315c972769c7ca8efb3a76eca34` (upstream c8b6421). Its macOS VM process RSS was 357,040 KiB, rounded to 366 MB. This includes guest memory; it is not Docker Desktop memory or total runtime overhead. The CLI exits after each command, leaving 0 MB of background process memory; running commands still use RAM. Upstream also supports running without a container.

</details>

## Get started

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv tool install 'git+https://github.com/fcakyon/paper-search-cli'
paper-search search 'object detection' -s fast -n 5
```

Requires Python 3.10+. Search results are JSON.

## Everyday commands

| Task | Command |
| --- | --- |
| Download a PDF | `paper-search download arxiv 1706.03762` |
| Read its text | `paper-search read arxiv 1706.03762` |
| Look up a DOI | `paper-search tool get_crossref_paper_by_doi 10.1038/nature12373` |
| Find citing papers | `paper-search tool get_citing_papers 10.1038/nature12373` |
| List sources | `paper-search sources` |
| Explore all operations | `paper-search tool --help` |

## Choose your sources

Start with `-s fast`, or choose sources such as `-s arxiv,openalex,pubmed`.

<details>
<summary>Search options and API keys</summary>

| Option | What it does |
| --- | --- |
| `-s fastest` | OpenAlex + Crossref |
| `-s fast` | Adds arXiv, PubMed, Europe PMC and configured Semantic Scholar |
| `-s all` | Broad search, also the default |
| `-n 5` | Up to five results per source |
| `--sort date` | Newest first among retrieved results |
| `--source-timeout 45` | Limit each source to 45 seconds |

Check the JSON `errors` field for partial failures.

Set keys in `~/.config/paper-search-mcp/.env` using [.env.example](.env.example). IEEE, Scopus and Web of Science require credentials. Unpaywall needs an email. Metadata access does not guarantee a downloadable PDF.

[Institutional sources](docs/INSTITUTIONAL_CONNECTORS.md) · [IEEE](docs/IEEE_METADATA.md)

</details>

<details>
<summary>References, PDF sections, and cache</summary>

```bash
paper-search tool get_referenced_papers 10.1038/nature12373
paper-search tool download_with_fallback arxiv 1706.03762
paper-search tool extract_sections 1706.03762.pdf
paper-search tool get_search_cache_status
```

PDF section extraction requires supported POSIX resource limits and has a known macOS limitation. Ordinary PDF download and reading work independently. Caching is off by default.

[PDF sections](docs/PDF_SECTIONS.md) · [Citation limits](docs/OPENALEX_RELATIONSHIPS.md) · [Cache setup](docs/SEARCH_CACHE.md)

</details>

<details>
<summary>Development and skill packaging</summary>

### Development

```bash
uv sync --extra dev
uv run pytest tests/test_cli_contracts.py tests/test_cli_tools.py tests/test_scopus.py
```

#### Skill ZIP uploads and other Claude runtimes

From a checkout, package the agent instructions:

```python
from zipfile import ZIP_DEFLATED, ZipFile

with ZipFile("paper-search-skill.zip", "w", compression=ZIP_DEFLATED) as archive:
    archive.write("claude-code/SKILL.md", arcname="paper-search/SKILL.md")
```

The receiving runtime needs CLI execution and network access.

</details>

[Agent skill](claude-code/SKILL.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE) · Forked from [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp)
