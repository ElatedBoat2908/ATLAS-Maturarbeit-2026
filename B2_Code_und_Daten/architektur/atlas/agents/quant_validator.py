from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.agents.knowledge_agent import KnowledgeAgent
from atlas.research.candidate_validator import CandidateValidator
from atlas.research.research_pipeline import ResearchPipeline


class QuantValidator:
    """
    ATLAS quantitative-validation agent.

    Responsibilities:
    - validate generated candidates
    - run complete research cycles
    - transfer validated lessons into research memory
    - never approve direct live deployment
    """

    def __init__(
        self,
        project_root: Path,
    ):
        self.project_root = project_root

        self.candidate_validator = CandidateValidator(
            project_root=project_root,
        )

        self.research_pipeline = ResearchPipeline(
            project_root=project_root,
        )

        self.knowledge_agent = KnowledgeAgent(
            project_root=project_root,
        )

    def validate_latest_candidate(
        self,
    ) -> dict[str, Any]:
        validation = (
            self.candidate_validator
            .validate_latest()
        )

        knowledge_result = (
            self.knowledge_agent
            .learn_from_candidate_validation(
                validation
            )
        )

        return {
            "status": validation.get(
                "status",
                "failed",
            ),
            "agent": "quant_validator",
            "validation": validation,
            "knowledge_result": knowledge_result,
        }

    def run_full_research_cycle(
        self,
        command: str,
    ) -> dict[str, Any]:
        report = self.research_pipeline.run_full_cycle(
            command
        )

        return {
            "status": report.get(
                "status",
                "failed",
            ),
            "agent": "quant_validator",
            "research_report": report,
        }