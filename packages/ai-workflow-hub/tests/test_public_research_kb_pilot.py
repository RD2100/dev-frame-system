import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from typer.main import get_command
from typer.testing import CliRunner

from ai_workflow_hub.cli import app
from ai_workflow_hub.context_layer.adapters import public_research_kb_pilot as pilot_module
from ai_workflow_hub.context_layer.adapters.public_research_kb_pilot import (
    build_public_research_kb_pilot_report,
    _arxiv_search_query,
    _download_public_arxiv_pdfs,
    _fetch_arxiv_metadata,
    _fetch_openalex_metadata,
    _generate_obsidian_note,
    PROFILE,
    SCHEMA_VERSION,
    TASK_ID,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "paper_public_research_kb_pilot_report.schema.json"


def _command_option_names(*command_path: str) -> set[str]:
    command = get_command(app)
    for name in command_path:
        command = command.get_command(None, name)
        assert command is not None, f"missing command path: {' '.join(command_path)}"
    return {
        opt
        for param in command.params
        for opt in getattr(param, "opts", [])
        if opt.startswith("--")
    }


FAKE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Deep Learning for Image Classification</title>
    <summary>  This paper presents a novel approach to image classification
    using deep convolutional neural networks.  </summary>
    <published>2023-01-01T00:00:00Z</published>
    <updated>2023-01-02T00:00:00Z</updated>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2301.00001v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2301.00001v1" rel="related" type="application/pdf"/>
    <link title="doi" href="http://dx.doi.org/10.1234/test.1" rel="related"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2302.00002v1</id>
    <title>Reinforcement Learning for Robotic Control</title>
    <summary>  We explore reinforcement learning techniques for continuous
    robotic control tasks with high-dimensional state spaces.  </summary>
    <published>2023-02-15T00:00:00Z</published>
    <updated>2023-02-16T00:00:00Z</updated>
    <author><name>Carol Davis</name></author>
    <arxiv:primary_category term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2302.00002v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2302.00002v1" rel="related" type="application/pdf"/>
  </entry>
</feed>"""


FAKE_OPENALEX_JSON = {
    "meta": {"count": 1},
    "results": [
        {
            "id": "https://openalex.org/W1234567890",
            "doi": "https://doi.org/10.5555/openalex.education",
            "display_name": "Computer Science Education with Large Language Models",
            "publication_year": 2024,
            "publication_date": "2024-05-01",
            "updated_date": "2024-05-02T00:00:00.000000",
            "abstract_inverted_index": {
                "This": [0],
                "study": [1],
                "examines": [2],
                "computing": [3],
                "education": [4],
            },
            "authorships": [
                {"author": {"display_name": "Dana Educator"}},
                {"author": {"display_name": "Evan Researcher"}},
            ],
            "topics": [
                {"display_name": "Computer science education"},
                {"display_name": "Artificial intelligence in education"},
            ],
            "primary_location": {
                "source": {"display_name": "Journal of Computing Education"},
                "pdf_url": "https://example.org/not-arxiv.pdf",
            },
            "ids": {"doi": "https://doi.org/10.5555/openalex.education"},
            "type": "article",
        }
    ],
}


FAKE_OPENALEX_WITH_ARXIV_JSON = {
    "meta": {"count": 1},
    "results": [
        {
            "id": "https://openalex.org/W9999999999",
            "doi": "https://doi.org/10.5555/openalex.arxiv",
            "display_name": "OpenAlex Record with Public arXiv Evidence",
            "publication_year": 2024,
            "publication_date": "2024-06-01",
            "updated_date": "2024-06-02T00:00:00.000000",
            "abstract_inverted_index": {
                "This": [0],
                "paper": [1],
                "links": [2],
                "OpenAlex": [3],
                "metadata": [4],
                "to": [5],
                "arXiv": [6],
                "evidence": [7],
            },
            "authorships": [
                {"author": {"display_name": "Open Researcher"}},
            ],
            "topics": [
                {"display_name": "Computer science"},
            ],
            "primary_location": {
                "source": {"display_name": "arXiv"},
                "pdf_url": "https://arxiv.org/pdf/2401.00001v1",
            },
            "ids": {
                "arxiv": "https://arxiv.org/abs/2401.00001v1",
                "doi": "https://doi.org/10.5555/openalex.arxiv",
            },
            "type": "preprint",
        }
    ],
}


def _fake_fetcher(_query: str) -> bytes:
    return FAKE_ARXIV_XML.encode("utf-8")


def _fake_openalex_fetcher(_query: str) -> bytes:
    return json.dumps(FAKE_OPENALEX_JSON).encode("utf-8")


def _fake_openalex_with_arxiv_fetcher(_query: str) -> bytes:
    return json.dumps(FAKE_OPENALEX_WITH_ARXIV_JSON).encode("utf-8")


def _fake_fetcher_empty(_query: str) -> bytes:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>0</opensearch:totalResults>
</feed>""".encode("utf-8")


def _fake_fetcher_raises(_query: str) -> bytes:
    raise TimeoutError("public source unavailable")


def _fake_pdf_fetcher(paper: dict) -> bytes:
    return b"%PDF-1.4\n% fake public arxiv pdf\n" + str(paper["arxiv_id"]).encode("utf-8")


def _fake_rag_builder(**kwargs):
    target = Path(kwargs["target_folder"])
    index_root = Path(kwargs["runtime_dir"]) / "index"
    index_root.mkdir(parents=True, exist_ok=True)
    chunk_records = []
    for idx, note_path in enumerate(sorted(target.glob("*.md"))):
        note_hash = f"sha256:{hashlib.sha256(note_path.read_bytes()).hexdigest()}"
        chunk_id = f"doc{idx:04d}-chunk0000"
        chunk_fingerprint = f"sha256:{hashlib.sha256((note_hash + chunk_id).encode('utf-8')).hexdigest()}"
        chunk_records.append({
            "chunk_id": chunk_id,
            "chunk_fingerprint": chunk_fingerprint,
            "source_fingerprint": note_hash,
            "raw_text_persisted": False,
        })
    (index_root / "chunks.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in chunk_records) + "\n",
        encoding="utf-8",
    )
    return {
        "pipeline_status": "PASS_LOCAL_RAG_PIPELINE",
        "pdf_count": int(kwargs.get("pdf_limit", 0)),
        "markdown_note_count": 2,
        "chunk_count": len(chunk_records),
        "retrieval_query_count": len(kwargs.get("queries") or []),
        "retrieval_success_count": len(chunk_records),
        "retrieved_chunk_fingerprints": [record["chunk_fingerprint"] for record in chunk_records],
        "index_reused": False,
    }


def _fake_partial_rag_builder(**kwargs):
    target = Path(kwargs["target_folder"])
    index_root = Path(kwargs["runtime_dir"]) / "index"
    index_root.mkdir(parents=True, exist_ok=True)
    chunk_records = []
    for idx, note_path in enumerate(sorted(target.glob("*.md"))):
        note_hash = f"sha256:{hashlib.sha256(note_path.read_bytes()).hexdigest()}"
        chunk_id = f"doc{idx:04d}-chunk0000"
        chunk_fingerprint = f"sha256:{hashlib.sha256((note_hash + chunk_id).encode('utf-8')).hexdigest()}"
        chunk_records.append({
            "chunk_id": chunk_id,
            "chunk_fingerprint": chunk_fingerprint,
            "source_fingerprint": note_hash,
            "raw_text_persisted": False,
        })
    (index_root / "chunks.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in chunk_records) + "\n",
        encoding="utf-8",
    )
    return {
        "pipeline_status": "PASS_LOCAL_RAG_PIPELINE",
        "pdf_count": int(kwargs.get("pdf_limit", 0)),
        "markdown_note_count": 2,
        "chunk_count": len(chunk_records),
        "retrieval_query_count": len(kwargs.get("queries") or []),
        "retrieval_success_count": 1,
        "retrieved_chunk_fingerprints": [chunk_records[0]["chunk_fingerprint"]],
        "index_reused": False,
    }


class _FakeRestResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeObsidianRestHttpClient:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": dict(kwargs.get("headers") or {}),
        })
        if method == "PUT":
            return _FakeRestResponse(204)
        if method == "POST":
            return _FakeRestResponse(204)
        return _FakeRestResponse(200)


class TestFetchArxivMetadata:
    def test_plain_query_is_wrapped_as_all_search(self):
        assert _arxiv_search_query("machine learning education") == "all:machine learning education"

    def test_advanced_query_is_preserved(self):
        assert _arxiv_search_query("cat:cs.CY AND all:education") == "cat:cs.CY AND all:education"

    def test_parses_valid_atom_response(self):
        papers = _fetch_arxiv_metadata("test", max_results=5, fetcher=_fake_fetcher)
        assert len(papers) == 2
        assert papers[0]["arxiv_id"] == "2301.00001v1"
        assert papers[0]["title"] == "Deep Learning for Image Classification"
        assert papers[0]["authors"] == ["Alice Smith", "Bob Jones"]
        assert papers[0]["doi"] == "10.1234/test.1"
        assert papers[0]["primary_category"] == "cs.CV"
        assert papers[0]["updated"] == "2023-01-02T00:00:00Z"
        assert papers[0]["pdf_url"] == "https://arxiv.org/pdf/2301.00001v1"
        assert "cs.CV" in papers[0]["categories"]
        assert "cs.LG" in papers[0]["categories"]
        assert papers[0]["source_level"] == "VERIFIED_SOURCE"
        assert papers[0]["source_type"] == "arxiv_public_metadata"

        assert papers[1]["arxiv_id"] == "2302.00002v1"
        assert papers[1]["authors"] == ["Carol Davis"]
        assert papers[1]["doi"] == ""
        assert papers[1]["primary_category"] == "cs.RO"

    def test_empty_feed_returns_empty_list(self):
        papers = _fetch_arxiv_metadata("nonexistent", max_results=5, fetcher=_fake_fetcher_empty)
        assert papers == []

    def test_http_fetch_uses_user_agent_and_retries_429(self, monkeypatch):
        calls = []

        class FakeResponse:
            def __init__(self, status_code: int, content: bytes):
                self.status_code = status_code
                self.content = content

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"http {self.status_code}")

        class FakeHttpx:
            @staticmethod
            def get(url, **kwargs):
                calls.append({"url": url, **kwargs})
                if len(calls) == 1:
                    return FakeResponse(429, b"")
                return FakeResponse(200, FAKE_ARXIV_XML.encode("utf-8"))

        monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
        monkeypatch.setattr(pilot_module.time, "sleep", lambda _seconds: None)

        papers = _fetch_arxiv_metadata("test", max_results=1)

        assert len(papers) == 2
        assert len(calls) == 2
        assert calls[0]["headers"]["User-Agent"] == pilot_module.ARXIV_USER_AGENT


class TestFetchOpenAlexMetadata:
    def test_parses_valid_openalex_response(self):
        papers = _fetch_openalex_metadata(
            "computer science education",
            max_results=5,
            fetcher=_fake_openalex_fetcher,
        )

        assert len(papers) == 1
        paper = papers[0]
        assert paper["openalex_id"] == "W1234567890"
        assert paper["arxiv_id"] == ""
        assert paper["title"] == "Computer Science Education with Large Language Models"
        assert paper["authors"] == ["Dana Educator", "Evan Researcher"]
        assert paper["doi"] == "10.5555/openalex.education"
        assert paper["published"] == "2024-05-01"
        assert paper["primary_category"] == "Computer science education"
        assert "Artificial intelligence in education" in paper["categories"]
        assert paper["summary"] == "This study examines computing education"
        assert paper["venue"] == "Journal of Computing Education"
        assert paper["source_url"] == "https://openalex.org/W1234567890"
        assert paper["source_type"] == "openalex_public_metadata"
        assert paper["source_level"] == "VERIFIED_SOURCE"


class TestGenerateObsidianNote:
    def test_creates_valid_markdown_note(self, tmp_path):
        paper = {
            "arxiv_id": "2301.00001v1",
            "title": "Deep Learning for Image Classification",
            "authors": ["Alice Smith", "Bob Jones"],
            "summary": "A novel approach.",
            "published": "2023-01-01T00:00:00Z",
            "updated": "2023-01-02T00:00:00Z",
            "categories": ["cs.CV", "cs.LG"],
            "primary_category": "cs.CV",
            "doi": "10.1234/test.1",
            "links": ["http://arxiv.org/abs/2301.00001v1"],
            "pdf_url": "http://arxiv.org/pdf/2301.00001v1",
            "source_level": "VERIFIED_SOURCE",
            "source_type": "arxiv_public_metadata",
        }
        target = tmp_path / "notes"
        note_path = _generate_obsidian_note(
            paper,
            target,
            vault_name="Research Vault",
            relative_path="notes/arxiv-2301.00001v1.md",
        )

        assert note_path.exists()
        assert note_path.name == "arxiv-2301.00001v1.md"
        content = note_path.read_text(encoding="utf-8")

        assert "---" in content
        assert 'note_id: "arxiv-2301.00001v1"' in content
        assert 'schema_type: "research_paper"' in content
        assert 'schema_name: "devframe.paper.research_paper"' in content
        assert 'title: "Deep Learning for Image Classification"' in content
        assert 'paper_id: "arxiv:2301.00001v1"' in content
        assert 'Alice Smith, Bob Jones' in content
        assert 'author_list: ["Alice Smith", "Bob Jones"]' in content
        assert 'arxiv_id: "2301.00001v1"' in content
        assert 'year: "2023"' in content
        assert 'doi: "10.1234/test.1"' in content
        assert 'source_url: "https://arxiv.org/abs/2301.00001v1"' in content
        assert 'pdf_url: "http://arxiv.org/pdf/2301.00001v1"' in content
        assert 'status: "source_verified"' in content
        assert 'kb_status: "captured"' in content
        assert 'read_status: "unread"' in content
        assert 'review_status: "needs_review"' in content
        assert 'evidence_refs: []' in content
        assert 'cs.CV' in content
        assert 'source_type: "arxiv_public_metadata"' in content
        assert 'source_level: "VERIFIED_SOURCE"' in content
        assert "obsidian://open?" in content
        assert "vault=Research%20Vault" in content
        assert "file=notes%2Farxiv-2301.00001v1.md" in content
        assert "<!-- devframe:paper-metadata:start -->" in content
        assert "<!-- devframe:paper-metadata:end -->" in content
        assert "## Abstract" in content
        assert "A novel approach." in content

    def test_idempotent_update_preserves_user_notes(self, tmp_path):
        paper = {
            "arxiv_id": "2301.00001v1",
            "title": "Deep Learning for Image Classification",
            "authors": ["Alice Smith", "Bob Jones"],
            "summary": "A novel approach.",
            "published": "2023-01-01T00:00:00Z",
            "updated": "2023-01-02T00:00:00Z",
            "categories": ["cs.CV", "cs.LG"],
            "primary_category": "cs.CV",
            "doi": "10.1234/test.1",
            "links": ["http://arxiv.org/abs/2301.00001v1"],
            "pdf_url": "http://arxiv.org/pdf/2301.00001v1",
            "source_level": "VERIFIED_SOURCE",
            "source_type": "arxiv_public_metadata",
        }
        target = tmp_path / "notes"
        note_path = _generate_obsidian_note(paper, target)
        note_path.write_text(
            note_path.read_text(encoding="utf-8")
            + "\n## My Reading Notes\n\nThis human note must survive.\n",
            encoding="utf-8",
        )

        updated = dict(paper)
        updated["summary"] = "Updated managed abstract."
        _generate_obsidian_note(updated, target)

        content = note_path.read_text(encoding="utf-8")
        assert "This human note must survive." in content
        assert "Updated managed abstract." in content
        assert content.count("<!-- devframe:paper-metadata:start -->") == 1
        assert content.count("<!-- devframe:paper-metadata:end -->") == 1

    def test_creates_openalex_markdown_note(self, tmp_path):
        paper = _fetch_openalex_metadata(
            "computer science education",
            fetcher=_fake_openalex_fetcher,
        )[0]
        target = tmp_path / "notes"

        note_path = _generate_obsidian_note(
            paper,
            target,
            vault_name="Research Vault",
            relative_path="notes/openalex-W1234567890.md",
        )

        assert note_path.name == "openalex-W1234567890.md"
        content = note_path.read_text(encoding="utf-8")
        assert 'note_id: "openalex-W1234567890"' in content
        assert 'paper_id: "openalex:W1234567890"' in content
        assert 'source_id: "W1234567890"' in content
        assert 'openalex_id: "W1234567890"' in content
        assert 'source_type: "openalex_public_metadata"' in content
        assert 'source_url: "https://openalex.org/W1234567890"' in content
        assert "**OpenAlex ID**: [W1234567890](https://openalex.org/W1234567890)" in content
        assert "Computer science education" in content


class TestBuildPublicResearchKbPilotReport:
    def test_blocked_missing_query(self):
        report = build_public_research_kb_pilot_report(
            query="",
            vault_root="/tmp/vault",
            target_folder="/tmp/vault/notes",
            runtime_dir="/tmp/runtime",
            fetcher=_fake_fetcher,
        )
        assert report["pilot_status"] == "BLOCKED_MISSING_QUERY"
        assert "query_is_empty" in report["reasons"]

    def test_blocked_vault_missing(self, tmp_path):
        nonexistent = tmp_path / "nonexistent_vault"
        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=nonexistent,
            target_folder=nonexistent / "notes",
            runtime_dir=tmp_path / "runtime",
            fetcher=_fake_fetcher,
        )
        assert report["pilot_status"] == "BLOCKED_VAULT_MISSING"
        assert "vault_root_not_present" in report["reasons"]

    def test_blocked_target_outside_vault(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=outside,
            runtime_dir=tmp_path / "runtime",
            fetcher=_fake_fetcher,
        )
        assert report["pilot_status"] == "BLOCKED_TARGET_OUTSIDE_VAULT"
        assert "target_folder_outside_vault" in report["reasons"]

    def test_blocked_runtime_invalid(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=vault / "notes",
            runtime_dir="",
            fetcher=_fake_fetcher,
        )
        assert report["pilot_status"] == "BLOCKED_RUNTIME_INVALID"

    def test_blocked_no_arxiv_results(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher_empty,
        )
        assert report["pilot_status"] == "BLOCKED_NO_ARXIV_RESULTS"
        assert report["arxiv_status"] == "NO_RESULTS"

    def test_blocked_arxiv_unavailable_when_fetch_fails(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher_raises,
        )

        assert report["pilot_status"] == "BLOCKED_ARXIV_UNAVAILABLE"
        assert report["arxiv_status"] == "FAILED"

    def test_full_pipeline_with_fake_data(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="deep learning",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        assert report["profile"] == PROFILE
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["task_id"] == TASK_ID
        assert report["project_id"] == "dev-frame-system"
        assert report["workflow_type"] == "paper"
        assert report["arxiv_status"] == "PASS"
        assert report["paper_count"] == 2
        assert report["note_count"] == 2
        assert report["pdf_download_status"] == "PASS"
        assert report["pdf_count"] == 2
        assert len(report["pdf_fingerprints"]) == 2
        assert len(report["citation_evidence_map"]) == 2
        assert report["citation_evidence_map"][0]["source_level"] == "VERIFIED_SOURCE"
        assert report["citation_evidence_map"][0]["retrieval_hit"] is True
        assert len(report["note_paths"]) == 2
        assert len(report["note_links"]) == 2
        assert report["note_links"][0]["obsidian_uri"].startswith("obsidian://open?")
        assert "file=notes%2Farxiv-2301.00001v1.md" in report["note_links"][0]["obsidian_uri"]
        assert report["dashboard_status"] == "PASS"
        assert report["dashboard_path"] == "notes/_Research KB Dashboard.md"
        assert report["dashboard_uri"].startswith("obsidian://open?")
        assert report["obsidian_rest_status"] == "NOT_RUN"
        assert len(report["paper_fingerprints"]) == 2

        assert report["obsidian_status"] == "PASS"

        note_files = sorted(target.glob("*.md"))
        assert len(note_files) == 3
        dashboard = target / "_Research KB Dashboard.md"
        assert dashboard.exists()
        dashboard_text = dashboard.read_text(encoding="utf-8")
        assert 'schema_type: "research_kb_dashboard"' in dashboard_text
        assert "```dataview" in dashboard_text
        assert 'FROM "notes"' in dashboard_text

        fingerprints = report["paper_fingerprints"]
        assert fingerprints[0]["arxiv_id"] == "2301.00001v1"
        assert fingerprints[0]["authors_count"] == 2
        assert fingerprints[0]["doi"] == "10.1234/test.1"
        assert fingerprints[1]["arxiv_id"] == "2302.00002v1"
        assert fingerprints[1]["authors_count"] == 1

    def test_openalex_source_generates_minimized_research_notes(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="computer science education",
            source="openalex",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_openalex_fetcher,
            rag_builder=_fake_rag_builder,
        )

        assert report["source_kind"] == "openalex_public_api"
        assert report["source_status"] == "PASS"
        assert report["arxiv_status"] == "NOT_RUN"
        assert report["paper_count"] == 1
        assert report["note_count"] == 1
        assert report["note_paths"] == ["notes/openalex-W1234567890.md"]
        assert report["note_links"][0]["source_id"] == "W1234567890"
        assert report["note_links"][0]["openalex_id"] == "W1234567890"
        assert report["paper_fingerprints"][0]["source_id"] == "W1234567890"
        assert report["paper_fingerprints"][0]["source_type"] == "openalex_public_metadata"
        assert report["pdf_download_status"] == "FAILED"
        assert report["pdf_count"] == 0
        assert report["rag_status"] == "BLOCKED"
        assert report["citation_lookup_status"] == "NEEDS_REVIEW"
        assert report["citation_lookup_results"][0]["match_status"] == "VERIFIED_SOURCE"
        assert report["pilot_status"] == "PASS_DEGRADED_PUBLIC_PDF"
        assert report["artifact_minimization"]["source_kind"] == "openalex_public_api"
        assert report["evidence_manifest"]["source_fingerprint_count"] == 1

        note_text = (target / "openalex-W1234567890.md").read_text(encoding="utf-8")
        assert 'schema_type: "research_paper"' in note_text
        assert 'source_type: "openalex_public_metadata"' in note_text

        report_json = json.dumps(report)
        assert "computer science education" not in report_json
        assert "abstract_inverted_index" not in report_json
        assert str(vault) not in report_json

    def test_openalex_with_safe_arxiv_pdf_emits_source_aware_citation_evidence(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="openalex arxiv evidence",
            source="openalex",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_openalex_with_arxiv_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        assert report["source_kind"] == "openalex_public_api"
        assert report["source_status"] == "PASS"
        assert report["pdf_download_status"] == "PASS"
        assert report["rag_status"] == "PASS"
        assert report["citation_lookup_status"] == "PASS"
        assert report["pilot_status"] == "PASS"
        assert report["note_paths"] == ["notes/openalex-W9999999999.md"]
        assert len(report["pdf_fingerprints"]) == 1
        assert report["pdf_fingerprints"][0]["source_id"] == "W9999999999"
        assert report["pdf_fingerprints"][0]["openalex_id"] == "W9999999999"
        assert report["pdf_fingerprints"][0]["arxiv_id"] == "2401.00001v1"

        evidence_rows = report["citation_evidence_map"]
        assert len(evidence_rows) == 1
        evidence = evidence_rows[0]
        assert evidence["citation_id"] == "W9999999999"
        assert evidence["source_id"] == "W9999999999"
        assert evidence["openalex_id"] == "W9999999999"
        assert evidence["source_type"] == "openalex_public_metadata"
        assert evidence["arxiv_id"] == "2401.00001v1"
        assert evidence["retrieval_hit"] is True
        assert evidence["chunk_fingerprint"] in report["rag_report_summary"]["retrieved_chunk_fingerprints"]

    def test_unsupported_source_blocks_without_fetching(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            source="unsupported",
            vault_root=vault,
            target_folder=vault / "notes",
            runtime_dir=tmp_path / "runtime",
            fetcher=_fake_fetcher_raises,
        )

        assert report["pilot_status"] == "BLOCKED_UNSUPPORTED_SOURCE"
        assert report["source_status"] == "BLOCKED"
        assert report["paper_count"] == 0

    def test_privacy_boundary_all_false(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        boundary = report["privacy_boundary"]
        for key in boundary:
            assert boundary[key] is False, f"privacy_boundary.{key} should be False"

    def test_obsidian_rest_sync_writes_notes_and_dashboard(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        fake_rest = _FakeObsidianRestHttpClient()
        monkeypatch.setenv("OBSIDIAN_REST_API_KEY", "secret-value")

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
            obsidian_rest=True,
            obsidian_rest_open=True,
            obsidian_rest_http_client=fake_rest,
        )

        assert report["obsidian_status"] == "PASS"
        assert report["dashboard_status"] == "PASS"
        assert report["obsidian_rest_status"] == "PASS"
        assert report["obsidian_rest_summary"]["write_count"] == 3
        assert report["obsidian_rest_summary"]["open_called"] is True
        assert report["obsidian_rest_summary"]["token_persisted"] is False
        assert report["privacy_boundary"]["obsidian_rest_api_called"] is True
        assert "secret-value" not in json.dumps(report)
        assert [call["method"] for call in fake_rest.calls].count("PUT") == 3
        assert [call["method"] for call in fake_rest.calls].count("POST") == 1

    def test_evidence_manifest_no_sensitive_data(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        manifest = report["evidence_manifest"]
        assert manifest["raw_sensitive_fields_absent"] is True
        assert manifest["contains_raw_pdf_text"] is False
        assert manifest["contains_raw_markdown_body"] is False
        assert manifest["contains_raw_arxiv_response"] is False
        assert manifest["contains_raw_query"] is False
        assert manifest["contains_raw_paths"] is False
        assert manifest["contains_secrets"] is False

    def test_rag_integration_explicit_when_import_fails(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "local_paper_rag_pipeline" in name:
                raise ImportError("RAG not available")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
        )

        assert report["rag_status"] == "FAILED_IMPORT"
        assert report["rag_report_summary"]["error"] == "local_paper_rag_pipeline module unavailable"

    def test_citation_lookup_runs_with_fake_data(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        assert report["citation_lookup_status"] == "PASS"
        assert len(report["citation_evidence_map"]) == 2
        assert "citation_lookup_results" in report
        assert len(report["citation_lookup_results"]) == 2

    def test_partial_rag_evidence_does_not_pass_all_citations(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_partial_rag_builder,
        )

        assert report["paper_count"] == 2
        assert len(report["citation_lookup_results"]) == 2
        assert len(report["citation_evidence_map"]) < len(report["citation_lookup_results"])
        assert report["citation_lookup_status"] == "NEEDS_REVIEW"
        assert report["pilot_status"] == "DEGRADED_CITATION_LOOKUP"

    def test_pdf_downloader_rejects_non_arxiv_url(self, tmp_path):
        papers = [{
            "arxiv_id": "2301.00001v1",
            "pdf_url": "https://example.com/not-arxiv.pdf",
        }]
        downloaded, fingerprints, failures = _download_public_arxiv_pdfs(
            papers=papers,
            pdf_dir=tmp_path / "pdfs",
            pdf_fetcher=_fake_pdf_fetcher,
        )

        assert downloaded == []
        assert fingerprints == []
        assert failures == ["2301.00001v1:ValueError"]

    def test_pdf_downloader_rejects_too_small_pdf(self, tmp_path):
        papers = [{
            "arxiv_id": "2301.00001v1",
            "pdf_url": "https://arxiv.org/pdf/2301.00001v1",
        }]
        downloaded, fingerprints, failures = _download_public_arxiv_pdfs(
            papers=papers,
            pdf_dir=tmp_path / "pdfs",
            pdf_fetcher=lambda _paper: b"%PDF",
        )

        assert downloaded == []
        assert fingerprints == []
        assert failures == ["2301.00001v1:ValueError"]

    def test_no_private_paths_in_report(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        report_json = json.dumps(report)
        assert "writelab_token" not in report_json
        assert "paragraph_text" not in report_json
        assert "private_local_path_marker" not in report_json
        assert str(vault) not in report_json

    def test_citation_lookup_import_failure_blocks_plain_pass(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "local_paper_rag_pipeline" in name:
                raise ImportError("RAG not available")
            if "citation_metadata_lookup" in name:
                raise ImportError("citation not available")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=_fake_pdf_fetcher,
        )

        assert report["rag_status"] == "FAILED_IMPORT"
        assert report["citation_lookup_status"] == "FAILED_IMPORT"
        assert report["arxiv_status"] == "PASS"
        assert report["obsidian_status"] == "PASS"
        assert report["pilot_status"] == "BLOCKED_CITATION_LOOKUP"
        assert "PASS" not in report["pilot_status"]

    def test_citation_failure_blocks_pdf_degraded_status(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "citation_metadata_lookup" in name:
                raise ImportError("citation not available")
            return original_import(name, *args, **kwargs)

        def partial_pdf_fetcher(paper: dict) -> bytes:
            if paper["arxiv_id"] == "2302.00002v1":
                raise RuntimeError("public PDF unavailable")
            return _fake_pdf_fetcher(paper)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        report = build_public_research_kb_pilot_report(
            query="test",
            vault_root=vault,
            target_folder=target,
            runtime_dir=runtime,
            fetcher=_fake_fetcher,
            pdf_fetcher=partial_pdf_fetcher,
            rag_builder=_fake_rag_builder,
        )

        assert report["pdf_download_status"] == "PARTIAL"
        assert report["citation_lookup_status"] == "FAILED_IMPORT"
        assert report["pilot_status"] == "BLOCKED_CITATION_LOOKUP"
        assert "PASS" not in report["pilot_status"]


def test_schema_validates_report(tmp_path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)

    vault = tmp_path / "vault"
    vault.mkdir()
    target = vault / "notes"
    target.mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    report = build_public_research_kb_pilot_report(
        query="test",
        vault_root=vault,
        target_folder=target,
        runtime_dir=runtime,
        fetcher=_fake_fetcher,
        pdf_fetcher=_fake_pdf_fetcher,
        rag_builder=_fake_rag_builder,
    )

    Draft7Validator(schema).validate(report)


class TestCliPublicResearchKbPilot:
    def test_help_exits_zero(self):
        result = CliRunner().invoke(
            app,
            ["paper", "public-research-kb-pilot", "--help"],
            env={"COLUMNS": "240", "NO_COLOR": "1"},
        )
        assert result.exit_code == 0
        assert "public-research-kb-pilot" in result.stdout
        options = _command_option_names("paper", "public-research-kb-pilot")
        assert {
            "--query",
            "--source",
            "--vault-root",
            "--target-folder",
            "--runtime-dir",
            "--vault-uri-name",
            "--obsidian-rest",
            "--obsidian-rest-token-env",
        }.issubset(options)

    def test_obsidian_rest_probe_help_exits_zero(self):
        result = CliRunner().invoke(
            app,
            ["paper", "obsidian-rest-probe", "--help"],
        )
        assert result.exit_code == 0
        assert "obsidian-rest-probe" in result.stdout
        options = _command_option_names("paper", "obsidian-rest-probe")
        assert {"--token-env", "--write-probe"}.issubset(options)

    def test_cli_missing_required_args(self):
        result = CliRunner().invoke(
            app,
            ["paper", "public-research-kb-pilot"],
        )
        assert result.exit_code != 0

    def test_cli_with_fake_fetcher(self, tmp_path, monkeypatch):
        from ai_workflow_hub.context_layer.adapters import public_research_kb_pilot

        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        monkeypatch.setattr(
            public_research_kb_pilot,
            "_fetch_arxiv_metadata",
            lambda query, max_results=5, fetcher=None: _fetch_arxiv_metadata(
                query, max_results, fetcher=_fake_fetcher
            ),
        )

        monkeypatch.setattr(
            public_research_kb_pilot,
            "build_public_research_kb_pilot_report",
            lambda **kwargs: build_public_research_kb_pilot_report(
                **{
                    **kwargs,
                    "fetcher": _fake_fetcher,
                    "pdf_fetcher": _fake_pdf_fetcher,
                    "rag_builder": _fake_rag_builder,
                }
            ),
        )

        result = CliRunner().invoke(
            app,
            [
                "paper",
                "public-research-kb-pilot",
                "--query", "deep learning",
                "--vault-root", str(vault),
                "--target-folder", str(target),
                "--runtime-dir", str(runtime),
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["profile"] == PROFILE
        assert payload["arxiv_status"] == "PASS"
        assert payload["paper_count"] == 2
        assert payload["note_count"] == 2

    def test_cli_passes_obsidian_rest_options(self, tmp_path, monkeypatch):
        from ai_workflow_hub.context_layer.adapters import public_research_kb_pilot

        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        captured = {}

        def fake_builder(**kwargs):
            captured.update(kwargs)
            return {
                "profile": PROFILE,
                "pilot_status": "PASS",
                "obsidian_rest_status": "PASS",
            }

        monkeypatch.setattr(
            public_research_kb_pilot,
            "build_public_research_kb_pilot_report",
            fake_builder,
        )

        result = CliRunner().invoke(
            app,
            [
                "paper",
                "public-research-kb-pilot",
                "--query", "deep learning",
                "--source", "openalex",
                "--vault-root", str(vault),
                "--target-folder", str(target),
                "--runtime-dir", str(runtime),
                "--obsidian-rest",
                "--obsidian-rest-base-url", "https://127.0.0.1:27124",
                "--obsidian-rest-token-env", "OBSIDIAN_REST_API_KEY",
                "--obsidian-rest-open",
                "--obsidian-rest-verify-tls",
            ],
        )

        assert result.exit_code == 0
        assert captured["source"] == "openalex"
        assert captured["obsidian_rest"] is True
        assert captured["obsidian_rest_base_url"] == "https://127.0.0.1:27124"
        assert captured["obsidian_rest_token_env"] == "OBSIDIAN_REST_API_KEY"
        assert captured["obsidian_rest_open"] is True
        assert captured["obsidian_rest_verify_tls"] is True

    def test_cli_handles_empty_query(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        result = CliRunner().invoke(
            app,
            [
                "paper",
                "public-research-kb-pilot",
                "--query", "",
                "--vault-root", str(vault),
                "--target-folder", str(vault / "notes"),
                "--runtime-dir", str(tmp_path / "runtime"),
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pilot_status"] == "BLOCKED_MISSING_QUERY"

    def test_cli_writes_output_file(self, tmp_path, monkeypatch):
        from ai_workflow_hub.context_layer.adapters import public_research_kb_pilot

        vault = tmp_path / "vault"
        vault.mkdir()
        target = vault / "notes"
        target.mkdir(parents=True)
        runtime = tmp_path / "runtime"
        runtime.mkdir()

        monkeypatch.setattr(
            public_research_kb_pilot,
            "_fetch_arxiv_metadata",
            lambda query, max_results=5, fetcher=None: _fetch_arxiv_metadata(
                query, max_results, fetcher=_fake_fetcher
            ),
        )

        monkeypatch.setattr(
            public_research_kb_pilot,
            "build_public_research_kb_pilot_report",
            lambda **kwargs: build_public_research_kb_pilot_report(
                **{
                    **kwargs,
                    "fetcher": _fake_fetcher,
                    "pdf_fetcher": _fake_pdf_fetcher,
                    "rag_builder": _fake_rag_builder,
                }
            ),
        )

        output_file = tmp_path / "report.json"
        manifest_file = tmp_path / "manifest.json"

        result = CliRunner().invoke(
            app,
            [
                "paper",
                "public-research-kb-pilot",
                "--query", "deep learning",
                "--vault-root", str(vault),
                "--target-folder", str(target),
                "--runtime-dir", str(runtime),
                "--output", str(output_file),
                "--manifest-output", str(manifest_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert manifest_file.exists()

        written = json.loads(output_file.read_text(encoding="utf-8"))
        assert written["profile"] == PROFILE

        manifest_written = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest_written["producer"] == "dev-frame-system"
