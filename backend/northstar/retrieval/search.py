"""Reusable retrieval independent of support decisions and model execution."""

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from northstar.config import RetrievalSettings
from northstar.domain import DomainError
from northstar.retrieval import representation
from northstar.retrieval.models import Document, RetrievalIndex, Section
from northstar.retrieval.service import eligible_documents

logger = logging.getLogger("northstar")


class RetrievalFailure(DomainError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 503)


class Evidence(BaseModel):
    section_id: str
    document_id: str
    policy_id: str
    version: int
    filename: str
    source: str
    ordinal: int
    text: str
    score: float
    semantic_score: float
    keyword_score: float
    coverage: float


class RetrievalResult(BaseModel):
    status: Literal["matched", "ambiguous", "insufficient_evidence", "no_matches"]
    query: str
    effective_at: datetime
    reason: str | None
    evidence: list[Evidence]
    context: str
    context_chars: int
    result_count: int
    budget_limited: bool
    query_expansions: list[str]
    settings: dict
    model_id: str
    index_generation: str
    index_status: str
    indexed_sections: int
    duration_ms: float


class RetrievalService:
    def __init__(self, sessions: sessionmaker[Session], settings: RetrievalSettings | None = None):
        self.sessions = sessions
        self.settings = settings or RetrievalSettings()
        self.model_id = (
            f"{representation.MODEL_ID}:d{self.settings.dimensions}:v{self.settings.max_vocabulary}"
        )

    def _sources(self, session: Session, at: datetime) -> list[dict]:
        ids = eligible_documents(at).with_only_columns(Document.id)
        query = (
            select(
                Section.id.label("section_id"),
                Section.document_id,
                Section.ordinal,
                Section.source,
                Section.text,
                Document.policy_id,
                Document.version,
                Document.filename,
            )
            .join(Document)
            .where(Document.id.in_(ids))
            .order_by(Document.policy_id, Document.version, Section.ordinal)
            .limit(self.settings.max_sections + 1)
        )
        rows = [dict(row) for row in session.execute(query).mappings()]
        if len(rows) > self.settings.max_sections:
            raise RetrievalFailure(
                "corpus_limit", "Active corpus exceeds the configured index limit."
            )
        # C03 READY documents must have sections; missing sources are not empty evidence.
        missing = session.scalar(
            select(Document.id)
            .where(
                Document.id.in_(ids),
                ~select(Section.id).where(Section.document_id == Document.id).exists(),
            )
            .limit(1)
        )
        if missing:
            raise RetrievalFailure(
                "source_inconsistent", "An active document has no extracted sections."
            )
        return rows

    def _synchronize(self, session: Session, at: datetime, force: bool = False):
        index = session.scalar(
            select(RetrievalIndex).where(RetrievalIndex.id == "active").with_for_update()
        )
        sources = self._sources(session, at)
        source_hash = representation.digest(sources)
        if index is None:
            index = RetrievalIndex(id="active")
            session.add(index)
        if (
            force
            or index.status != "READY"
            or index.model_id != self.model_id
            or index.source_hash != source_hash
        ):
            try:
                payload = representation.train(
                    [s["text"] for s in sources],
                    [s["section_id"] for s in sources],
                    self.settings.dimensions,
                    self.settings.max_vocabulary,
                )
                representation.validate(payload, [s["section_id"] for s in sources])
                payload_hash = representation.digest(payload)
            except Exception:
                raise RetrievalFailure(
                    "representation_unavailable", "Semantic index generation failed."
                ) from None
            index.status, index.model_id = "READY", self.model_id
            index.generation, index.source_hash = str(uuid4()), source_hash
            index.payload, index.payload_hash = payload, payload_hash
            session.flush()
        try:
            if representation.digest(index.payload) != index.payload_hash:
                raise ValueError("Checksum mismatch")
            representation.validate(index.payload, [s["section_id"] for s in sources])
        except (ValueError, TypeError, KeyError, IndexError):
            raise RetrievalFailure(
                "index_corrupt", "Index is incomplete or corrupt; rebuild it."
            ) from None
        return index, sources

    @staticmethod
    def _at(at: datetime | None) -> datetime:
        if at is not None and at.tzinfo is None:
            raise DomainError(
                "invalid_retrieval_time", "Retrieval time must include a timezone.", 422
            )
        return at.astimezone(UTC) if at else datetime.now(UTC)

    def synchronize(self, *, at: datetime | None = None, force: bool = False) -> dict:
        """Rebuild explicitly or synchronize lazily; all vectors commit as one snapshot."""
        at = self._at(at)
        try:
            with self.sessions.begin() as session:
                index, sources = self._synchronize(session, at, force)
                return {
                    "status": index.status,
                    "generation": index.generation,
                    "model_id": index.model_id,
                    "indexed_sections": len(sources),
                }
        except SQLAlchemyError:
            raise RetrievalFailure(
                "index_unavailable", "Retrieval storage is unavailable; retry after recovery."
            ) from None

    def search(self, query: str, *, at: datetime | None = None) -> RetrievalResult:
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > self.settings.query_chars
        ):
            raise DomainError(
                "invalid_retrieval_query",
                "Supply a nonempty query within the configured length limit.",
                422,
            )
        start = perf_counter()
        at = self._at(at)
        try:
            with self.sessions.begin() as session:
                index, sources = self._synchronize(session, at)
                try:
                    ranked, expansions = representation.rank(
                        query,
                        [s["text"] for s in sources],
                        index.payload,
                        self.settings.candidate_limit,
                    )
                except Exception:
                    raise RetrievalFailure(
                        "representation_unavailable", "Query representation or ranking failed."
                    ) from None
                candidates = [r for r in ranked if r["score"] >= self.settings.min_score]
                evidence, context, budget_limited = [], "", False
                for row in candidates[: self.settings.result_limit]:
                    source = sources[row["position"]]
                    header = (
                        f"[{source['section_id']}] {source['policy_id']} v{source['version']} "
                        f"{source['filename']} ({source['source']})\n"
                    )
                    block = header + source["text"] + "\n\n"
                    if (
                        len(source["text"]) > self.settings.section_chars
                        or len(context) + len(block) > self.settings.context_chars
                    ):
                        budget_limited = True
                        continue
                    evidence.append(
                        Evidence(**source, **{k: v for k, v in row.items() if k != "position"})
                    )
                    context += block
                status, reason = "matched", None
                if not evidence:
                    status = "insufficient_evidence" if budget_limited else "no_matches"
                    reason = (
                        "context_budget"
                        if budget_limited
                        else ("no_active_documents" if not sources else "no_relevant_sections")
                    )
                elif budget_limited or candidates[0]["coverage"] < 0.5:
                    status, reason = (
                        "insufficient_evidence",
                        "context_budget" if budget_limited else "low_query_coverage",
                    )
                elif len(candidates) > 1:
                    first, second = candidates[:2]
                    if (
                        sources[first["position"]]["policy_id"]
                        != sources[second["position"]]["policy_id"]
                        and first["score"] - second["score"] <= self.settings.ambiguity_margin
                    ):
                        status, reason = "ambiguous", "similar_policy_scores"
                # Catch lifecycle changes committed while representations were being computed.
                if representation.digest(self._sources(session, at)) != index.source_hash:
                    raise RetrievalFailure(
                        "index_changed", "Policies changed during retrieval; retry."
                    )
                result = RetrievalResult(
                    status=status,
                    query=query,
                    effective_at=at,
                    reason=reason,
                    evidence=evidence,
                    context=context,
                    context_chars=len(context),
                    result_count=len(evidence),
                    budget_limited=budget_limited,
                    query_expansions=expansions,
                    settings=self.settings.model_dump(),
                    model_id=index.model_id,
                    index_generation=index.generation,
                    index_status=index.status,
                    indexed_sections=len(sources),
                    duration_ms=round((perf_counter() - start) * 1000, 3),
                )
            logger.info("retrieval_completed", extra={"duration_ms": result.duration_ms})
            return result
        except SQLAlchemyError:
            logger.warning("retrieval_failed", extra={"error_category": "index_unavailable"})
            raise RetrievalFailure(
                "index_unavailable", "Retrieval storage is unavailable; retry after recovery."
            ) from None
        except RetrievalFailure as exc:
            logger.warning("retrieval_failed", extra={"error_category": exc.code})
            raise
