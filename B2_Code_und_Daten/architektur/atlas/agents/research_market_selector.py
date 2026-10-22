from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.markets.market_selector import ResearchMarketSelector


class ResearchMarketSelectorAgent:
    """Agent wrapper for controlled market selection."""

    def __init__(self, project_root: Path):
        self.selector = ResearchMarketSelector(project_root)

    def select_market(
        self,
        *,
        minimum_score: float = 55.0,
        create_mission: bool = True,
    ) -> dict[str, Any]:
        result = self.selector.select_latest(
            minimum_score=minimum_score,
            create_mission=create_mission,
        )
        return {
            "status": "complete",
            "agent": "research_market_selector",
            "selection": result,
            "live_trading_allowed": False,
        }
