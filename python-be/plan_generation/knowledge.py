# -*- coding: utf-8 -*-
"""
Utilities to interface the structured knowledge base during plan generation.
"""
from __future__ import annotations

from typing import Iterable, List

from knowledge_base.repository import KnowledgeRepository
from knowledge_base.vector_store import VectorSearchResult


class KnowledgeService:
    def __init__(self) -> None:
        self.repository = KnowledgeRepository()

    def search_guidelines(self, query: str, top_k: int = 5) -> List[VectorSearchResult]:
        """
        Retrieve guidance snippets relevant to the query string.
        """
        return self.repository.search(query, top_k=top_k)

    def guideline_summaries(self, query: str, top_k: int = 3) -> List[str]:
        results = self.search_guidelines(query, top_k=top_k)
        summaries: List[str] = []
        for result in results:
            heading = result.metadata.get("heading") or "General"
            summaries.append(f"{heading}: {result.text}")
        return summaries

    def validate_plan(self, plan: dict) -> dict:
        """
        Run schema and rule validation on a generated plan.
        """
        from .validators import validate_plan_schema, validate_plan_rules

        issues = list(validate_plan_schema(plan)) + list(validate_plan_rules(plan))
        report = self.repository.validation_report(issues)
        return report.model_dump()
