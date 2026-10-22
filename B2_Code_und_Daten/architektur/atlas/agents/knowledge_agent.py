from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid


class KnowledgeAgent:
    """
    Persistent research-memory agent for ATLAS.

    This first version stores structured observations in one JSON file.
    It does not use an LLM and does not invent conclusions.

    Responsibilities:
    - store lessons from completed experiments
    - search previous lessons by tags
    - summarize relevant knowledge for other agents
    - preserve evidence and source references
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.memory_dir = project_root / "atlas" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.knowledge_path = (
            self.memory_dir / "research_knowledge.json"
        )

        self.latest_path = (
            self.memory_dir / "latest_knowledge_result.json"
        )

    def record_observation(
        self,
        observation: str,
        tags: list[str],
        source: str,
        confidence: float,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        knowledge = self._load_knowledge()

        normalized_confidence = min(
            1.0,
            max(0.0, float(confidence)),
        )

        item = {
            "knowledge_id": str(uuid.uuid4()),
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "observation": observation,
            "tags": sorted(
                {
                    str(tag).strip().lower()
                    for tag in tags
                    if str(tag).strip()
                }
            ),
            "source": source,
            "confidence": normalized_confidence,
            "evidence": evidence or {},
        }

        knowledge["observations"].append(item)
        knowledge["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        self._save_knowledge(knowledge)
        self._save_latest(
            {
                "status": "complete",
                "action": "record_observation",
                "observation": item,
            }
        )

        return item

    def learn_from_candidate_validation(
        self,
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        if validation.get("status") != "complete":
            result = {
                "status": "skipped",
                "reason": (
                    "Candidate validation did not complete successfully."
                ),
            }

            self._save_latest(result)
            return result

        original = validation.get(
            "original_strategy",
            {},
        )
        candidate = validation.get(
            "candidate_strategy",
            {},
        )

        original_metrics = original.get(
            "metrics",
            {},
        )
        candidate_metrics = candidate.get(
            "metrics",
            {},
        )

        comparison = validation.get(
            "comparison",
            {},
        )

        verdict = validation.get(
            "verdict",
            "REVIEW",
        )

        original_name = original.get(
            "name",
            "unknown_original",
        )
        candidate_name = candidate.get(
            "name",
            "unknown_candidate",
        )

        pf_change = (
            comparison
            .get("profit_factor", {})
            .get("absolute_change")
        )

        pnl_change = (
            comparison
            .get("total_pnl", {})
            .get("absolute_change")
        )

        drawdown_change = (
            comparison
            .get("max_drawdown_pct", {})
            .get("absolute_change")
        )

        trades_change = (
            comparison
            .get("trades", {})
            .get("absolute_change")
        )

        observations: list[dict[str, Any]] = []

        if (
            pf_change is not None
            and drawdown_change is not None
            and pnl_change is not None
            and pf_change > 0
            and drawdown_change > 0
            and pnl_change < 0
        ):
            observation = (
                f"Candidate {candidate_name} improved profit factor and "
                f"drawdown versus {original_name}, but reduced total PnL. "
                "Aggressive filtering may improve risk quality while "
                "removing too many profitable trades."
            )

            observations.append(
                self.record_observation(
                    observation=observation,
                    tags=[
                        "strategy_improvement",
                        "risk_quality",
                        "drawdown",
                        "profit_factor",
                        "pnl_retention",
                        "filtering",
                    ],
                    source="candidate_validation",
                    confidence=0.85,
                    evidence={
                        "verdict": verdict,
                        "original_strategy": original_name,
                        "candidate_strategy": candidate_name,
                        "profit_factor_change": pf_change,
                        "pnl_change": pnl_change,
                        "drawdown_change": drawdown_change,
                        "trades_change": trades_change,
                        "original_metrics": original_metrics,
                        "candidate_metrics": candidate_metrics,
                    },
                )
            )

        if verdict == "ACCEPT_FOR_WALK_FORWARD":
            observations.append(
                self.record_observation(
                    observation=(
                        f"Candidate {candidate_name} improved enough "
                        "in-sample to justify walk-forward validation."
                    ),
                    tags=[
                        "candidate",
                        "walk_forward",
                        "accepted",
                    ],
                    source="candidate_validation",
                    confidence=0.90,
                    evidence={
                        "verdict": verdict,
                        "candidate_strategy": candidate_name,
                        "candidate_metrics": candidate_metrics,
                    },
                )
            )

        if verdict == "REJECT":
            observations.append(
                self.record_observation(
                    observation=(
                        f"Candidate {candidate_name} failed the in-sample "
                        "acceptance criteria and should not replace "
                        f"{original_name}."
                    ),
                    tags=[
                        "candidate",
                        "rejected",
                        "strategy_improvement",
                    ],
                    source="candidate_validation",
                    confidence=0.90,
                    evidence={
                        "verdict": verdict,
                        "candidate_strategy": candidate_name,
                        "candidate_metrics": candidate_metrics,
                    },
                )
            )

        if not observations:
            observations.append(
                self.record_observation(
                    observation=(
                        f"Candidate {candidate_name} produced a mixed result "
                        f"with verdict {verdict}. More controlled variants "
                        "are required before a conclusion is made."
                    ),
                    tags=[
                        "candidate",
                        "review",
                        "mixed_result",
                    ],
                    source="candidate_validation",
                    confidence=0.70,
                    evidence={
                        "verdict": verdict,
                        "original_strategy": original_name,
                        "candidate_strategy": candidate_name,
                        "comparison": comparison,
                    },
                )
            )

        result = {
            "status": "complete",
            "action": "learn_from_candidate_validation",
            "observations_recorded": len(observations),
            "observations": observations,
        }

        self._save_latest(result)
        return result

    def search(
        self,
        tags: list[str] | None = None,
        text: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        knowledge = self._load_knowledge()
        observations = knowledge.get(
            "observations",
            [],
        )

        requested_tags = {
            str(tag).strip().lower()
            for tag in (tags or [])
            if str(tag).strip()
        }

        requested_text = (
            text.strip().lower()
            if text
            else None
        )

        matches = []

        for item in observations:
            item_tags = set(
                item.get("tags", [])
            )
            observation_text = str(
                item.get("observation", "")
            ).lower()

            tags_match = (
                not requested_tags
                or requested_tags.intersection(item_tags)
            )

            text_match = (
                requested_text is None
                or requested_text in observation_text
            )

            if tags_match and text_match:
                matches.append(item)

        matches.sort(
            key=lambda item: (
                float(item.get("confidence", 0)),
                item.get("created_at", ""),
            ),
            reverse=True,
        )

        return matches[: max(1, int(limit))]

    def summarize_for_strategy_engineer(
        self,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        matches = self.search(
            tags=tags,
            limit=limit,
        )

        if not matches:
            return {
                "status": "complete",
                "knowledge_count": 0,
                "summary": (
                    "No relevant prior research knowledge was found."
                ),
                "observations": [],
            }

        lines = []

        for item in matches:
            confidence = float(
                item.get("confidence", 0)
            )

            lines.append(
                f"- {item.get('observation')} "
                f"(confidence {confidence:.0%})"
            )

        return {
            "status": "complete",
            "knowledge_count": len(matches),
            "summary": "\n".join(lines),
            "observations": matches,
        }

    def get_stats(self) -> dict[str, Any]:
        knowledge = self._load_knowledge()
        observations = knowledge.get(
            "observations",
            [],
        )

        tag_counts: dict[str, int] = {}

        for item in observations:
            for tag in item.get("tags", []):
                tag_counts[tag] = (
                    tag_counts.get(tag, 0) + 1
                )

        return {
            "status": "complete",
            "observation_count": len(observations),
            "tag_counts": dict(
                sorted(
                    tag_counts.items(),
                    key=lambda pair: pair[1],
                    reverse=True,
                )
            ),
            "updated_at": knowledge.get(
                "updated_at"
            ),
        }

    def _load_knowledge(self) -> dict[str, Any]:
        if not self.knowledge_path.exists():
            return {
                "version": "1.0",
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "observations": [],
            }

        try:
            data = json.loads(
                self.knowledge_path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError:
            backup_path = (
                self.memory_dir
                / "research_knowledge_corrupt.json"
            )

            backup_path.write_text(
                self.knowledge_path.read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            return {
                "version": "1.0",
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "observations": [],
            }

        data.setdefault("version", "1.0")
        data.setdefault("observations", [])

        return data

    def _save_knowledge(
        self,
        knowledge: dict[str, Any],
    ) -> None:
        self.knowledge_path.write_text(
            json.dumps(
                knowledge,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    def _save_latest(
        self,
        result: dict[str, Any],
    ) -> None:
        self.latest_path.write_text(
            json.dumps(
                result,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )