"""test_rag.py — TDD tests for rag.py (RAG 2.0 experience retrieval pipeline).

Run: /opt/homebrew/bin/python3.11 -m pytest test_rag.py -v
"""

import json
import math
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Import under test ──────────────────────────────────────────────────────────
from rag import (
    Chunk,
    extract_chunks,
    embed_chunks,
    VectorStore,
    rerank,
    format_for_injection,
)


# ── Fixtures ────────────────────────────────────────────────────────────────────

SAMPLE_EXPLORATION_LOG = {
    "project_fingerprint": {"languages": ["python"], "has_migrations": True},
    "phases": {
        "explore": {
            "timestamp": "2026-04-01T10:00:00Z",
            "outcome_quality": 0.8,
            "patterns_found": [
                "All routes use @auth_required decorator",
                "Repository pattern for data access",
            ],
            "gaps": ["Missing rate limiting on public endpoints"],
            "failed_approaches": [
                "Tried using raw SQL — bypasses ORM events in this codebase"
            ],
            "discoveries": ["auth middleware is injected via DI container"],
        },
        "architect": {
            "timestamp": "2026-04-01T10:30:00Z",
            "outcome_quality": 0.75,
            "decisions_made": [
                "Use Decimal for all monetary fields",
                "All data access through repository classes",
            ],
            "patterns_escalated": ["Decorator pattern widely used for cross-cutting concerns"],
        },
        "review": {
            "timestamp": "2026-04-01T11:00:00Z",
            "outcome_quality": 0.9,
            "feedback": [
                "Missing input validation on POST /users endpoint",
                "Consider adding index on created_at column",
            ],
            "patterns_escalated": ["Security reviews should check all user-facing endpoints"],
        },
    },
}


def make_chunk(**overrides) -> Chunk:
    defaults = dict(
        text="some pattern discovered",
        source_phase="explore",
        source_type="patterns_found",
        timestamp="2026-04-01T10:00:00Z",
        project_fingerprint={"languages": ["python"]},
        outcome_quality=0.8,
    )
    defaults.update(overrides)
    return Chunk(**defaults)


# ── Chunk dataclass ─────────────────────────────────────────────────────────────

class TestChunk:
    def test_chunk_has_required_fields(self):
        c = Chunk(
            text="raw sql bypasses ORM",
            source_phase="explore",
            source_type="failed_approaches",
            timestamp="2026-04-01T10:00:00Z",
            project_fingerprint={"languages": ["python"]},
            outcome_quality=0.8,
        )
        assert c.text == "raw sql bypasses ORM"
        assert c.source_phase == "explore"
        assert c.source_type == "failed_approaches"
        assert c.timestamp == "2026-04-01T10:00:00Z"
        assert c.project_fingerprint == {"languages": ["python"]}
        assert c.outcome_quality == 0.8

    def test_chunk_is_dataclass(self):
        from dataclasses import fields
        field_names = {f.name for f in fields(Chunk)}
        assert field_names == {
            "text", "source_phase", "source_type",
            "timestamp", "project_fingerprint", "outcome_quality",
        }


# ── extract_chunks ──────────────────────────────────────────────────────────────

class TestExtractChunks:
    def test_extracts_patterns_found(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "All routes use @auth_required decorator" in texts
        assert "Repository pattern for data access" in texts

    def test_extracts_gaps(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "Missing rate limiting on public endpoints" in texts

    def test_extracts_failed_approaches(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "Tried using raw SQL — bypasses ORM events in this codebase" in texts

    def test_extracts_discoveries(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "auth middleware is injected via DI container" in texts

    def test_extracts_decisions_made(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "Use Decimal for all monetary fields" in texts

    def test_extracts_patterns_escalated(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "Decorator pattern widely used for cross-cutting concerns" in texts
        assert "Security reviews should check all user-facing endpoints" in texts

    def test_extracts_review_feedback(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        texts = [c.text for c in chunks]
        assert "Missing input validation on POST /users endpoint" in texts

    def test_chunk_source_phase_is_set(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        by_type = {c.text: c.source_phase for c in chunks}
        assert by_type["All routes use @auth_required decorator"] == "explore"
        assert by_type["Use Decimal for all monetary fields"] == "architect"
        assert by_type["Missing input validation on POST /users endpoint"] == "review"

    def test_chunk_source_type_is_set(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        by_text = {c.text: c.source_type for c in chunks}
        assert by_text["Tried using raw SQL — bypasses ORM events in this codebase"] == "failed_approaches"
        assert by_text["Use Decimal for all monetary fields"] == "decisions_made"
        assert by_text["Missing input validation on POST /users endpoint"] == "feedback"

    def test_chunk_fingerprint_propagated(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        for c in chunks:
            assert c.project_fingerprint == {"languages": ["python"], "has_migrations": True}

    def test_chunk_outcome_quality_from_phase(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        by_text = {c.text: c.outcome_quality for c in chunks}
        assert by_text["All routes use @auth_required decorator"] == 0.8
        assert by_text["Use Decimal for all monetary fields"] == 0.75

    def test_returns_list_of_chunks(self):
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        assert isinstance(chunks, list)
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_empty_log_returns_empty_list(self):
        assert extract_chunks({}) == []
        assert extract_chunks({"phases": {}}) == []

    def test_total_chunk_count(self):
        # 2 patterns + 1 gap + 1 failed + 1 discovery (explore=5)
        # + 2 decisions + 1 escalated (architect=3)
        # + 2 feedback + 1 escalated (review=3)  → 11 total
        chunks = extract_chunks(SAMPLE_EXPLORATION_LOG)
        assert len(chunks) == 11


# ── embed_chunks ────────────────────────────────────────────────────────────────

class TestEmbedChunks:
    def test_returns_list_of_vectors(self):
        chunks = [make_chunk(text=f"chunk {i}") for i in range(3)]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536) for _ in range(3)]
        )
        with patch("rag.openai.OpenAI", return_value=mock_client):
            vectors = embed_chunks(chunks, api_key="sk-test")
        assert len(vectors) == 3
        assert all(len(v) == 1536 for v in vectors)

    def test_calls_correct_model(self):
        chunks = [make_chunk()]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.0] * 1536)]
        )
        with patch("rag.openai.OpenAI", return_value=mock_client):
            embed_chunks(chunks, api_key="sk-test")
        call_kwargs = mock_client.embeddings.create.call_args
        assert call_kwargs.kwargs.get("model") == "text-embedding-3-small"

    def test_passes_texts_as_input(self):
        texts = ["alpha", "beta", "gamma"]
        chunks = [make_chunk(text=t) for t in texts]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.0] * 1536) for _ in texts]
        )
        with patch("rag.openai.OpenAI", return_value=mock_client):
            embed_chunks(chunks, api_key="sk-test")
        call_kwargs = mock_client.embeddings.create.call_args
        assert call_kwargs.kwargs.get("input") == texts

    def test_returns_floats(self):
        chunks = [make_chunk()]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.5] * 1536)]
        )
        with patch("rag.openai.OpenAI", return_value=mock_client):
            vectors = embed_chunks(chunks, api_key="sk-test")
        assert all(isinstance(x, float) for x in vectors[0])


# ── VectorStore ─────────────────────────────────────────────────────────────────

class TestVectorStore:
    def test_creates_empty_store_if_missing(self, tmp_path):
        store = VectorStore(tmp_path)
        assert store.size == 0

    def test_size_increases_after_add(self, tmp_path):
        store = VectorStore(tmp_path)
        chunks = [make_chunk(text=f"chunk {i}") for i in range(5)]
        vectors = [np.random.randn(1536).tolist() for _ in range(5)]
        store.add(chunks, vectors)
        assert store.size == 5

    def test_persists_to_disk(self, tmp_path):
        store = VectorStore(tmp_path)
        chunks = [make_chunk(text="persisted chunk")]
        vectors = [np.random.randn(1536).tolist()]
        store.add(chunks, vectors)
        # Reload from disk
        store2 = VectorStore(tmp_path)
        assert store2.size == 1
        assert store2._index[0]["text"] == "persisted chunk"

    def test_index_json_written(self, tmp_path):
        store = VectorStore(tmp_path)
        chunks = [make_chunk(text="hello")]
        store.add(chunks, [np.random.randn(1536).tolist()])
        assert (tmp_path / "index.json").exists()
        data = json.loads((tmp_path / "index.json").read_text())
        assert len(data) == 1
        assert data[0]["text"] == "hello"

    def test_embeddings_npy_written(self, tmp_path):
        store = VectorStore(tmp_path)
        chunks = [make_chunk()]
        store.add(chunks, [np.random.randn(1536).tolist()])
        assert (tmp_path / "embeddings.npy").exists()
        arr = np.load(tmp_path / "embeddings.npy")
        assert arr.shape == (1, 1536)

    def test_add_multiple_batches(self, tmp_path):
        store = VectorStore(tmp_path)
        for i in range(3):
            store.add([make_chunk(text=f"chunk {i}")], [np.random.randn(1536).tolist()])
        assert store.size == 3

    def test_query_returns_top_k(self, tmp_path):
        store = VectorStore(tmp_path)
        chunks = [make_chunk(text=f"chunk {i}") for i in range(10)]
        vectors = [np.random.randn(1536).tolist() for _ in range(10)]
        store.add(chunks, vectors)
        query = np.random.randn(1536).tolist()
        results = store.query(query, top_k=5)
        assert len(results) == 5

    def test_query_returns_chunk_score_pairs(self, tmp_path):
        store = VectorStore(tmp_path)
        chunks = [make_chunk(text="test")]
        vectors = [np.random.randn(1536).tolist()]
        store.add(chunks, vectors)
        results = store.query(vectors[0], top_k=1)
        assert len(results) == 1
        chunk, score = results[0]
        assert isinstance(chunk, Chunk)
        assert isinstance(score, float)

    def test_query_cosine_similarity_ordering(self, tmp_path):
        """The query vector itself should match with near-perfect similarity."""
        store = VectorStore(tmp_path)
        target = np.random.randn(1536)
        target_norm = (target / np.linalg.norm(target)).tolist()
        other_vectors = [np.random.randn(1536).tolist() for _ in range(9)]
        all_vectors = [target_norm] + other_vectors
        all_chunks = [make_chunk(text=f"c{i}") for i in range(10)]
        store.add(all_chunks, all_vectors)
        results = store.query(target_norm, top_k=1)
        assert results[0][0].text == "c0"
        assert results[0][1] > 0.99

    def test_query_on_empty_store_returns_empty(self, tmp_path):
        store = VectorStore(tmp_path)
        results = store.query(np.random.randn(1536).tolist(), top_k=5)
        assert results == []

    def test_query_top_k_capped_to_store_size(self, tmp_path):
        store = VectorStore(tmp_path)
        store.add([make_chunk()], [np.random.randn(1536).tolist()])
        results = store.query(np.random.randn(1536).tolist(), top_k=20)
        assert len(results) == 1


# ── rerank ──────────────────────────────────────────────────────────────────────

class TestRerank:
    def _make_candidates(self, n=10):
        now = datetime.now(timezone.utc)
        candidates = []
        for i in range(n):
            c = make_chunk(
                text=f"chunk {i}",
                source_phase="explore",
                project_fingerprint={"languages": ["python"], "has_migrations": True},
                timestamp=(now - timedelta(days=i * 5)).isoformat(),
                outcome_quality=0.5 + i * 0.03,
            )
            score = 0.9 - i * 0.05
            candidates.append((c, score))
        return candidates

    def test_returns_top_5(self):
        candidates = self._make_candidates(10)
        result = rerank(candidates, {"languages": ["python"]}, "explore",
                        datetime.now(timezone.utc))
        assert len(result) == 5

    def test_returns_chunks(self):
        candidates = self._make_candidates(10)
        result = rerank(candidates, {"languages": ["python"]}, "explore",
                        datetime.now(timezone.utc))
        for item in result:
            assert isinstance(item, Chunk)

    def test_fewer_than_5_candidates(self):
        candidates = self._make_candidates(3)
        result = rerank(candidates, {"languages": ["python"]}, "explore",
                        datetime.now(timezone.utc))
        assert len(result) == 3

    def test_phase_match_boosts_same_phase(self):
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        fp = {"languages": ["python"]}
        # Two candidates: one matching phase, one not
        c_same = make_chunk(source_phase="explore", timestamp=ts, outcome_quality=0.5)
        c_diff = make_chunk(source_phase="review", timestamp=ts, outcome_quality=0.5)
        # Give them identical similarity so phase_match is the tiebreaker
        candidates = [(c_same, 0.8), (c_diff, 0.8)]
        result = rerank(candidates, fp, "explore", now)
        assert result[0].source_phase == "explore"

    def test_recent_chunks_ranked_higher_when_equal_otherwise(self):
        now = datetime.now(timezone.utc)
        fp = {"languages": ["python"]}
        c_recent = make_chunk(
            source_phase="explore",
            timestamp=now.isoformat(),
            outcome_quality=0.5,
        )
        c_old = make_chunk(
            source_phase="explore",
            timestamp=(now - timedelta(days=100)).isoformat(),
            outcome_quality=0.5,
        )
        candidates = [(c_old, 0.8), (c_recent, 0.8)]
        result = rerank(candidates, fp, "explore", now)
        assert result[0].timestamp == c_recent.timestamp

    def test_fingerprint_match_uses_jaccard(self):
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        c_match = make_chunk(
            project_fingerprint={"languages": ["python"], "has_migrations": True},
            timestamp=ts, source_phase="explore", outcome_quality=0.5,
        )
        c_no_match = make_chunk(
            project_fingerprint={"languages": ["javascript"]},
            timestamp=ts, source_phase="explore", outcome_quality=0.5,
        )
        candidates = [(c_no_match, 0.8), (c_match, 0.8)]
        result = rerank(candidates, {"languages": ["python"], "has_migrations": True}, "explore", now)
        assert result[0].project_fingerprint == {"languages": ["python"], "has_migrations": True}

    def test_empty_candidates_returns_empty(self):
        result = rerank([], {}, "explore", datetime.now(timezone.utc))
        assert result == []


# ── format_for_injection ────────────────────────────────────────────────────────

class TestFormatForInjection:
    def test_includes_prior_experience_header(self):
        chunks = [make_chunk(text="use repository pattern")]
        output = format_for_injection(chunks)
        assert "PRIOR EXPERIENCE" in output

    def test_includes_chunk_text(self):
        chunks = [make_chunk(text="never use raw SQL here")]
        output = format_for_injection(chunks)
        assert "never use raw SQL here" in output

    def test_includes_source_metadata(self):
        chunks = [make_chunk(source_phase="explore", source_type="failed_approaches")]
        output = format_for_injection(chunks)
        assert "explore" in output
        assert "failed_approaches" in output

    def test_multiple_chunks_all_present(self):
        chunks = [make_chunk(text=f"insight {i}") for i in range(5)]
        output = format_for_injection(chunks)
        for i in range(5):
            assert f"insight {i}" in output

    def test_empty_chunks_returns_empty_string(self):
        assert format_for_injection([]) == ""

    def test_returns_string(self):
        chunks = [make_chunk()]
        assert isinstance(format_for_injection(chunks), str)
