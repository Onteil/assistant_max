"""Search and formatting helpers for the technical support knowledge base."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import TechSupportKnowledge


TOKEN_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яЁё_\\.-]{3,}")


@dataclass(slots=True)
class KnowledgeSearchResult:
    entry: TechSupportKnowledge
    score: int


def _normalize(value: str) -> str:
    return value.lower().replace("ё", "е")


def _tokenize(text: str) -> list[str]:
    return list(dict.fromkeys(_normalize(token) for token in TOKEN_PATTERN.findall(text)))


def _entry_text(entry: TechSupportKnowledge) -> str:
    return _normalize(
        " ".join(
            value
            for value in (
                entry.title,
                entry.error_text,
                entry.solution_text,
                entry.keywords,
            )
            if value
        )
    )


def _score_entry(entry: TechSupportKnowledge, user_text: str, tokens: list[str]) -> int:
    haystack = _entry_text(entry)
    normalized_user_text = _normalize(user_text)
    score = 0

    if normalized_user_text and normalized_user_text in haystack:
        score += 8

    for token in tokens:
        if token in haystack:
            score += 2
        if entry.keywords and token in _normalize(entry.keywords):
            score += 2
        if token in _normalize(entry.title):
            score += 1
        if token in _normalize(entry.error_text):
            score += 1

    return score


async def search_tech_support_knowledge(
    session: AsyncSession,
    user_text: str,
    *,
    limit: int = 3,
    min_score: int = 4,
) -> list[KnowledgeSearchResult]:
    """Find active knowledge base entries that are relevant to a client message."""
    tokens = _tokenize(user_text)
    if not tokens:
        return []

    searchable_tokens = tokens[:8]
    conditions = []
    for token in searchable_tokens:
        pattern = f"%{token}%"
        conditions.extend(
            (
                TechSupportKnowledge.title.ilike(pattern),
                TechSupportKnowledge.error_text.ilike(pattern),
                TechSupportKnowledge.solution_text.ilike(pattern),
                TechSupportKnowledge.keywords.ilike(pattern),
            )
        )

    result = await session.execute(
        select(TechSupportKnowledge)
        .where(
            TechSupportKnowledge.is_active.is_(True),
            or_(*conditions),
        )
        .order_by(TechSupportKnowledge.updated_at.desc().nullslast(), TechSupportKnowledge.id.desc())
        .limit(25)
    )
    entries = result.scalars().all()

    scored = [
        KnowledgeSearchResult(entry=entry, score=_score_entry(entry, user_text, tokens))
        for entry in entries
    ]
    scored = [result for result in scored if result.score >= min_score]
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


def format_knowledge_answer(result: KnowledgeSearchResult) -> str:
    """Format one knowledge base result for a client-facing AI assistant answer."""
    entry = result.entry
    parts = [
        f"Нашла похожую ошибку: <b>{escape(entry.title)}</b>",
        "",
        "<b>Что означает:</b>",
        escape(entry.error_text),
        "",
        "<b>Что можно сделать:</b>",
        escape(entry.solution_text),
    ]

    if entry.screenshot_url:
        parts.extend(("", f"Скриншот/инструкция: {escape(entry.screenshot_url)}"))

    parts.extend(
        (
            "",
            "Если это не помогло, напишите «нужна техподдержка», и я помогу оформить обращение специалисту.",
        )
    )
    return "\n".join(parts)
