from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.markets.intelligence_scanner import (
    MultiMarketIntelligenceScanner,
)


class GlobalMarketObserver:
    """Read-only ATLAS agent for multi-market observation."""

    def __init__(self, project_root: Path):
        self.scanner = MultiMarketIntelligenceScanner(
            project_root
        )

    def observe(
        self,
        *,
        profile_name: str,
        timeframe: str = "M5",
        limit: int = 20,
        count: int = 1500,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        result = self.scanner.scan(
            profile_name=profile_name,
            timeframe=timeframe,
            limit=limit,
            count=count,
            symbols=symbols,
        )
        return {
            "status": "complete",
            "agent": "global_market_observer",
            "scan": result,
            "live_trading_allowed": False,
        }
