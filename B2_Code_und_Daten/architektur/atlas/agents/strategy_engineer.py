from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.agents.knowledge_agent import KnowledgeAgent
from atlas.research.strategy_analyzer import StrategyAnalyzer
from atlas.research.strategy_improver import StrategyImprover


class StrategyEngineer:
    """
    ATLAS strategy-engineering agent.

    It orchestrates:
    - StrategyAnalyzer
    - StrategyImprover
    - KnowledgeAgent

    The Knowledge Agent provides previous research lessons.
    The current StrategyImprover remains deterministic and controlled.
    """

    def __init__(
        self,
        project_root: Path,
    ):
        self.project_root = project_root

        self.analyzer = StrategyAnalyzer(
            project_root=project_root,
        )

        self.improver = StrategyImprover(
            project_root=project_root,
        )

        self.knowledge_agent = KnowledgeAgent(
            project_root=project_root,
        )

    def analyze_best_strategy(
        self,
    ) -> dict[str, Any]:
        analysis = self.analyzer.analyze_best_strategy()

        knowledge = (
            self.knowledge_agent
            .summarize_for_strategy_engineer(
                tags=[
                    "strategy_improvement",
                    "filtering",
                    "risk_quality",
                ],
                limit=5,
            )
        )

        return {
            "status": analysis.get(
                "status",
                "failed",
            ),
            "agent": "strategy_engineer",
            "analysis": analysis,
            "relevant_knowledge": knowledge,
        }

    def generate_candidate(
        self,
    ) -> dict[str, Any]:
        analysis = self.analyzer.analyze_best_strategy()

        if analysis.get("status") != "complete":
            return {
                "status": "failed",
                "agent": "strategy_engineer",
                "analysis": analysis,
                "message": analysis.get(
                    "message",
                    "Strategy analysis failed.",
                ),
            }

        relevant_knowledge = (
            self.knowledge_agent
            .summarize_for_strategy_engineer(
                tags=[
                    "strategy_improvement",
                    "filtering",
                    "risk_quality",
                    "pnl_retention",
                ],
                limit=5,
            )
        )

        generated = (
            self.improver
            .create_improved_strategy(analysis)
        )

        return {
            "status": generated.get(
                "status",
                "failed",
            ),
            "agent": "strategy_engineer",
            "analysis": analysis,
            "relevant_knowledge": relevant_knowledge,
            "generated_strategy": generated,
            "message": (
                "Strategy Engineer analyzed the current leader, reviewed "
                "prior research knowledge and generated one controlled "
                "candidate."
            ),
        }