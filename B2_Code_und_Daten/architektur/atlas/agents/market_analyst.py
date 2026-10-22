from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

import pandas as pd

from atlas.data_engine.market_data import MarketDataService
from atlas.intelligence.context_builder import MarketIntelligenceContextBuilder
from atlas.intelligence.store import IntelligenceStore


TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


class MarketAnalyst:
    """
    Deterministic ATLAS market-analysis agent.

    Before analyzing the market, this agent refreshes the selected
    symbol/timeframe from MetaTrader 5. It then reads the exact local
    feature database belonging to that symbol and timeframe.

    Responsibilities:
    - refresh MT5 candles
    - load the correct symbol/timeframe dataset
    - detect stale data
    - classify trend, volatility and session
    - save a grounded market analysis
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.memory_dir = project_root / "atlas" / "memory"

        self.market_data_service = MarketDataService(
            project_root=project_root,
        )
        self.intelligence_builder = MarketIntelligenceContextBuilder()
        self.intelligence_store = IntelligenceStore(project_root=project_root)

    def analyze_current_market(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
        refresh_from_mt5: bool = True,
        refresh_count: int = 5_000,
    ) -> dict[str, Any]:
        refresh_result = None

        if refresh_from_mt5:
            refresh_result = self.market_data_service.update_from_mt5(
                symbol=symbol,
                timeframe=timeframe,
                count=refresh_count,
            )

        data_path = self._exact_market_dataset(
            symbol=symbol,
            timeframe=timeframe,
        )

        if data_path is None:
            refresh_message = (
                refresh_result.message
                if refresh_result is not None
                else "No MT5 refresh was requested."
            )

            return self._failure(
                symbol=symbol,
                timeframe=timeframe,
                message=(
                    "ATLAS could not locate an exact local feature dataset "
                    f"for {symbol} {timeframe}. MT5 update result: "
                    f"{refresh_message}"
                ),
            )

        try:
            df = pd.read_parquet(data_path)
        except Exception as exc:
            return self._failure(
                symbol=symbol,
                timeframe=timeframe,
                message=f"Could not read {data_path}: {exc}",
            )

        if df.empty:
            return self._failure(
                symbol=symbol,
                timeframe=timeframe,
                message="The market feature dataset is empty.",
            )

        if "time" not in df.columns:
            return self._failure(
                symbol=symbol,
                timeframe=timeframe,
                message="The market dataset has no 'time' column.",
            )

        df = df.copy()
        df["time"] = pd.to_datetime(
            df["time"],
            utc=True,
            errors="coerce",
        )

        df = (
            df.dropna(subset=["time"])
            .sort_values("time")
            .drop_duplicates(subset=["time"])
            .reset_index(drop=True)
        )

        if df.empty:
            return self._failure(
                symbol=symbol,
                timeframe=timeframe,
                message="No valid timestamps remain after cleaning.",
            )

        last = df.iloc[-1]
        last_candle = pd.Timestamp(last["time"])

        data_age_minutes = self._data_age_minutes(
            last_candle
        )

        freshness_status = self._freshness_status(
            timeframe=timeframe,
            data_age_minutes=data_age_minutes,
        )

        trend_regime = self._detect_trend_regime(df)
        volatility_regime = self._detect_volatility_regime(df)
        session = self._detect_session(last)

        confidence = self._calculate_confidence(
            df=df,
            trend_regime=trend_regime,
            volatility_regime=volatility_regime,
            freshness_status=freshness_status,
        )

        refresh_status = (
            refresh_result.status
            if refresh_result is not None
            else "not_requested"
        )

        refresh_message = (
            refresh_result.message
            if refresh_result is not None
            else "MT5 refresh was not requested."
        )

        intelligence_context = self.intelligence_builder.build(
            symbol=symbol,
            timeframe=timeframe,
            market_data=df,
            freshness_status=freshness_status,
            data_age_minutes=data_age_minutes,
            session=session,
        )
        intelligence = self.intelligence_store.save(
            intelligence_context
        )

        result = {
            "status": "complete",
            "agent": "market_analyst",
            "symbol": symbol,
            "timeframe": timeframe,
            "data_path": str(data_path),
            "rows": int(len(df)),
            "first_candle": str(df.iloc[0]["time"]),
            "last_candle": str(last_candle),
            "last_close": self._safe_float(
                last.get("close")
            ),
            "atr_14": self._safe_float(
                last.get("atr_14")
            ),
            "trend_regime": trend_regime,
            "volatility_regime": volatility_regime,
            "session": session,
            "confidence": confidence,
            "data_age_minutes": round(
                data_age_minutes,
                2,
            ),
            "freshness_status": freshness_status,
            "mt5_refresh_status": refresh_status,
            "mt5_refresh_message": refresh_message,
            "analyzed_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "intelligence_id": intelligence.get("intelligence_id"),
            "market_intelligence": intelligence,
            "summary": self._build_summary(
                symbol=symbol,
                timeframe=timeframe,
                trend_regime=trend_regime,
                volatility_regime=volatility_regime,
                session=session,
                confidence=confidence,
                freshness_status=freshness_status,
                data_age_minutes=data_age_minutes,
            ),
        }

        self._save_result(result)
        return result

    def _exact_market_dataset(
        self,
        symbol: str,
        timeframe: str,
    ) -> Path | None:
        """
        Only use a dataset belonging to the requested symbol and timeframe.

        This intentionally avoids selecting an unrelated or old generic
        feature file from another directory.
        """
        exact_candidates = [
            (
                self.project_root
                / "data"
                / "market"
                / symbol
                / timeframe
                / "features.parquet"
            ),
            (
                self.project_root
                / "data"
                / "processed"
                / f"{symbol}_{timeframe}_features.parquet"
            ),
            (
                self.project_root
                / "data_processed"
                / f"{symbol}_{timeframe}_features.parquet"
            ),
        ]

        symbol_without_suffix = symbol.split(".")[0]

        exact_candidates.extend(
            [
                (
                    self.project_root
                    / "data"
                    / "processed"
                    / f"{symbol_without_suffix}_{timeframe}_features.parquet"
                ),
                (
                    self.project_root
                    / "data_processed"
                    / f"{symbol_without_suffix}_{timeframe}_features.parquet"
                ),
            ]
        )

        for path in exact_candidates:
            if path.exists():
                return path

        return None

    def _detect_trend_regime(
        self,
        df: pd.DataFrame,
    ) -> str:
        last = df.iloc[-1]

        if "trend_regime" in df.columns:
            value = last.get("trend_regime")

            if pd.notna(value):
                return str(value)

        required = {
            "ma_20",
            "ma_50",
            "ma_200",
        }

        if not required.issubset(df.columns):
            return "unknown"

        ma_20 = last.get("ma_20")
        ma_50 = last.get("ma_50")
        ma_200 = last.get("ma_200")

        if not all(
            pd.notna(value)
            for value in [ma_20, ma_50, ma_200]
        ):
            return "unknown"

        if ma_20 > ma_50 > ma_200:
            return "uptrend"

        if ma_20 < ma_50 < ma_200:
            return "downtrend"

        return "neutral"

    def _detect_volatility_regime(
        self,
        df: pd.DataFrame,
    ) -> str:
        last = df.iloc[-1]

        if "volatility_regime" in df.columns:
            value = last.get("volatility_regime")

            if pd.notna(value):
                return str(value)

        if "atr_14" not in df.columns:
            return "unknown"

        atr = df["atr_14"].dropna()

        if len(atr) < 50:
            return "unknown"

        current_atr = float(atr.iloc[-1])
        median_atr = float(
            atr.tail(500).median()
        )

        if median_atr <= 0:
            return "unknown"

        ratio = current_atr / median_atr

        if ratio >= 1.25:
            return "high_volatility"

        if ratio <= 0.75:
            return "low_volatility"

        return "normal"

    def _detect_session(
        self,
        last_row: pd.Series,
    ) -> str:
        value = last_row.get("time")

        if value is None or pd.isna(value):
            return "unknown"

        timestamp = pd.Timestamp(value)
        hour = int(timestamp.hour)

        if 0 <= hour < 7:
            return "asia"

        if 7 <= hour < 13:
            return "europe"

        if 13 <= hour < 21:
            return "united_states"

        return "after_hours"

    def _data_age_minutes(
        self,
        last_candle: pd.Timestamp,
    ) -> float:
        now = pd.Timestamp.now(tz="UTC")

        if last_candle.tzinfo is None:
            last_candle = last_candle.tz_localize(
                "UTC"
            )
        else:
            last_candle = last_candle.tz_convert(
                "UTC"
            )

        age = now - last_candle

        return max(
            0.0,
            age.total_seconds() / 60.0,
        )

    def _freshness_status(
        self,
        timeframe: str,
        data_age_minutes: float,
    ) -> str:
        timeframe_minutes = TIMEFRAME_MINUTES.get(
            timeframe,
            5,
        )

        fresh_limit = max(
            15,
            timeframe_minutes * 3,
        )

        delayed_limit = max(
            60,
            timeframe_minutes * 12,
        )

        if data_age_minutes <= fresh_limit:
            return "fresh"

        if data_age_minutes <= delayed_limit:
            return "delayed"

        return "stale"

    def _calculate_confidence(
        self,
        df: pd.DataFrame,
        trend_regime: str,
        volatility_regime: str,
        freshness_status: str,
    ) -> float:
        score = 40.0

        if trend_regime in {
            "uptrend",
            "downtrend",
            "neutral",
        }:
            score += 15.0

        if volatility_regime in {
            "normal",
            "high_volatility",
            "low_volatility",
        }:
            score += 15.0

        if len(df) >= 1_000:
            score += 10.0

        if {
            "ma_20",
            "ma_50",
            "ma_200",
            "atr_14",
        }.issubset(df.columns):
            score += 10.0

        if freshness_status == "fresh":
            score += 10.0
        elif freshness_status == "delayed":
            score -= 10.0
        else:
            score -= 35.0

        return min(
            100.0,
            max(0.0, round(score, 1)),
        )

    def _build_summary(
        self,
        symbol: str,
        timeframe: str,
        trend_regime: str,
        volatility_regime: str,
        session: str,
        confidence: float,
        freshness_status: str,
        data_age_minutes: float,
    ) -> str:
        base = (
            f"{symbol} {timeframe} is classified as "
            f"{trend_regime}, with {volatility_regime} conditions "
            f"during the {session} session."
        )

        if freshness_status == "fresh":
            freshness_text = (
                f"The latest candle is approximately "
                f"{data_age_minutes:.1f} minutes old."
            )
        else:
            freshness_text = (
                f"Warning: market data is {freshness_status} and the "
                f"latest candle is approximately "
                f"{data_age_minutes:.1f} minutes old."
            )

        return (
            f"{base} {freshness_text} "
            f"Market-analysis confidence is {confidence:.1f}%."
        )

    def _failure(
        self,
        symbol: str,
        timeframe: str,
        message: str,
    ) -> dict[str, Any]:
        result = {
            "status": "failed",
            "agent": "market_analyst",
            "symbol": symbol,
            "timeframe": timeframe,
            "message": message,
            "analyzed_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        self._save_result(result)
        return result

    def _save_result(
        self,
        result: dict[str, Any],
    ) -> None:
        self.memory_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            self.memory_dir
            / "latest_market_agent_analysis.json"
        )

        path.write_text(
            json.dumps(
                result,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    def _safe_float(
        self,
        value,
    ) -> float | None:
        if value is None or pd.isna(value):
            return None

        return float(value)