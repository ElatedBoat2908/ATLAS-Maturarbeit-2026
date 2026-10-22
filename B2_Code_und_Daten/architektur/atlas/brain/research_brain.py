from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .brain_memory import BrainMemory
from .models import BrainAction, BrainGoal, BrainPriority, ResearchPlan
from atlas.cognitive import (
    CognitiveDecision, CognitiveEvidence, CognitiveMemory,
    CognitiveObservation, DecisionOption, EvidenceItem,
    EvidenceStrength, ObservationSource, ResearchJournal,
)


class ResearchBrain:
    """
    Deterministic planning layer for ATLAS.

    The Research Brain decides what should happen next. It does not execute
    agents, place trades, alter risk limits, or approve live deployment.
    Execution remains the Supervisor's responsibility.
    """

    def __init__(self, project_root: Path):
        self.memory = BrainMemory(project_root=project_root)
        self.cognitive_memory = CognitiveMemory(project_root=project_root)
        self.journal = ResearchJournal(project_root=project_root)

    def build_plan(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        intelligence = self.memory.load_latest_intelligence()
        adaptive = self.memory.load_latest_adaptive_decision()
        dashboard = self.memory.load_strategy_dashboard()

        plan = self._decide(
            symbol=symbol,
            timeframe=timeframe,
            intelligence=intelligence,
            adaptive=adaptive,
            dashboard=dashboard,
        )
        plan_payload = self.memory.save_plan(plan)
        cognitive_record = self._record_cognitive_decision(
            plan=plan_payload,
            intelligence=intelligence,
            adaptive=adaptive,
            dashboard=dashboard,
        )
        plan_payload["cognitive_decision_id"] = (
            cognitive_record.get("decision", {}).get("decision_id")
        )
        return plan_payload

    def get_latest_plan(self) -> dict[str, Any] | None:
        return self.memory.load_latest_plan()

    def _record_cognitive_decision(
        self,
        *,
        plan: dict[str, Any],
        intelligence: dict[str, Any] | None,
        adaptive: dict[str, Any] | None,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(plan.get("recommended_action") or "UNKNOWN")
        if "." in action:
            action = action.rsplit(".", 1)[-1]
        observation = CognitiveObservation.create(
            subject="research_plan_context",
            source=ObservationSource.SYSTEM,
            symbol=plan.get("symbol"),
            timeframe=plan.get("timeframe"),
            source_reference=plan.get("plan_id"),
            facts={
                "plan_observation": plan.get("observation"),
                "priority": plan.get("priority"),
                "goal": plan.get("goal"),
                "market_intelligence": intelligence,
                "adaptive_decision": adaptive,
                "strategy_count": len(dashboard.get("strategies", [])),
            },
            valid=True,
        )
        evidence_item = EvidenceItem(
            evidence_id=f"evidence-{plan.get('plan_id')}",
            claim=str(plan.get("reason") or "Research plan selected."),
            value=plan.get("evidence") or {},
            source="research_brain",
            strength=(EvidenceStrength.CRITICAL if str(plan.get("priority")).upper().endswith("CRITICAL") else EvidenceStrength.STRONG),
            supports=(action,),
        )
        evidence = CognitiveEvidence(
            observation_ids=(observation.observation_id,),
            items=(evidence_item,),
            completeness=1.0 if intelligence else 0.5,
            data_freshness_score=0.0 if action == "BLOCK_AND_REVIEW" else 0.8,
        )
        alternatives = ["MONITOR_CHAMPION", "PREPARE_CHALLENGER", "RESEARCH_CHALLENGER", "BLOCK_AND_REVIEW"]
        options = []
        for candidate in alternatives:
            selected = candidate == action
            options.append(DecisionOption(
                action=candidate,
                score=0.90 if selected else 0.25,
                rationale=(str(plan.get("reason")) if selected else f"Rejected because {action} better matches the current evidence."),
                supporting_evidence_ids=(evidence_item.evidence_id,) if selected else (),
                contradicting_evidence_ids=() if selected else (evidence_item.evidence_id,),
            ))
        confidence = 0.9 if action == "BLOCK_AND_REVIEW" else 0.75
        decision = CognitiveDecision.create(
            decision_type="research_plan_selection",
            chosen_action=action,
            confidence=confidence,
            explanation=str(plan.get("reason") or "Research Brain selected this action."),
            observation_ids=(observation.observation_id,),
            options=options,
            restrictions=plan.get("restrictions") or (),
            plan_id=plan.get("plan_id"),
            symbol=plan.get("symbol"),
            timeframe=plan.get("timeframe"),
            metadata={"priority": plan.get("priority"), "goal": plan.get("goal")},
        )
        record = self.cognitive_memory.save(observation, evidence, decision)
        self.journal.append({
            "event": "research_plan_created",
            "plan_id": plan.get("plan_id"),
            "decision_id": decision.decision_id,
            "chosen_action": action,
            "observation": plan.get("observation"),
            "reason": plan.get("reason"),
            "restrictions": plan.get("restrictions") or [],
            "outcome": "PLANNED",
            "next_required_action": action,
        })
        return record

    def _decide(
        self,
        symbol: str,
        timeframe: str,
        intelligence: dict[str, Any] | None,
        adaptive: dict[str, Any] | None,
        dashboard: dict[str, Any],
    ) -> ResearchPlan:
        restrictions = self._base_restrictions()

        if not intelligence:
            return self._plan(
                symbol=symbol,
                timeframe=timeframe,
                priority=BrainPriority.HIGH,
                goal=self._goal_market_context(),
                observation="No current market-intelligence snapshot is available.",
                action=BrainAction.REFRESH_MARKET_INTELLIGENCE,
                reason=(
                    "ATLAS cannot select, generate, validate, or deploy a strategy "
                    "without a current and traceable market context."
                ),
                required_agents=["market_analyst"],
                evidence={"market_intelligence_available": False},
                restrictions=restrictions,
            )

        risk_environment = str(
            intelligence.get("risk_environment", "unknown")
        ).lower()
        data_quality = str(
            intelligence.get("data_quality", "unknown")
        ).lower()

        if risk_environment == "blocked" or data_quality in {
            "invalid",
            "insufficient",
            "blocked",
        }:
            return self._plan(
                symbol=symbol,
                timeframe=timeframe,
                priority=BrainPriority.CRITICAL,
                goal=self._goal_protect_capital(),
                observation=(
                    f"Market context reports risk={risk_environment} and "
                    f"data_quality={data_quality}."
                ),
                action=BrainAction.BLOCK_AND_REVIEW,
                reason=(
                    "Research may continue only after data and risk conditions are "
                    "re-established. Trading must remain blocked."
                ),
                required_agents=["market_analyst", "deployment_guard"],
                evidence={"market_intelligence": intelligence},
                restrictions=restrictions,
            )

        if not adaptive:
            return self._plan(
                symbol=symbol,
                timeframe=timeframe,
                priority=BrainPriority.HIGH,
                goal=self._goal_strategy_coverage(),
                observation=(
                    "Market intelligence exists, but no adaptive strategy decision "
                    "has been recorded for the current research state."
                ),
                action=BrainAction.RUN_ADAPTIVE_SELECTION,
                reason=(
                    "ATLAS must compare the current regime with the validated strategy "
                    "library before generating a new strategy."
                ),
                required_agents=["market_analyst", "supervisor"],
                evidence={
                    "intelligence_id": intelligence.get("intelligence_id"),
                    "strategy_count": len(dashboard.get("strategies", [])),
                },
                restrictions=restrictions,
            )

        adaptive_action = str(adaptive.get("action", "")).upper()
        selection = adaptive.get("selection") or {}
        selected = selection.get("selected_strategy") or {}
        compatibility = self._number(selected.get("compatibility_score"), 0.0)

        if adaptive_action == "GENERATE_CHALLENGER":
            return self._plan(
                symbol=symbol,
                timeframe=timeframe,
                priority=BrainPriority.HIGH,
                goal=self._goal_strategy_coverage(),
                observation=(
                    "No sufficiently compatible validated strategy covers the current "
                    "market environment."
                ),
                action=BrainAction.RESEARCH_CHALLENGER,
                reason=(
                    "A controlled challenger is required, but it must pass the complete "
                    "validation pipeline before paper or live deployment."
                ),
                required_agents=[
                    "knowledge_agent",
                    "strategy_engineer",
                    "quant_validator",
                    "tournament_engine",
                    "deployment_guard",
                ],
                evidence={
                    "intelligence_id": intelligence.get("intelligence_id"),
                    "adaptive_decision": adaptive,
                },
                restrictions=restrictions,
            )

        strategy_name = str(selected.get("strategy_name", "unknown"))

        if compatibility < 0.70:
            return self._plan(
                symbol=symbol,
                timeframe=timeframe,
                priority=BrainPriority.MEDIUM,
                goal=self._goal_champion_health(),
                observation=(
                    f"The selected champion {strategy_name} has only "
                    f"{compatibility:.1%} compatibility with the current market."
                ),
                action=BrainAction.PREPARE_CHALLENGER,
                reason=(
                    "The champion may remain the current research choice, but ATLAS "
                    "should prepare a challenger before compatibility deteriorates further."
                ),
                required_agents=[
                    "knowledge_agent",
                    "strategy_engineer",
                    "quant_validator",
                ],
                evidence={
                    "intelligence_id": intelligence.get("intelligence_id"),
                    "selected_strategy": selected,
                },
                restrictions=restrictions,
            )

        return self._plan(
            symbol=symbol,
            timeframe=timeframe,
            priority=BrainPriority.LOW,
            goal=self._goal_champion_health(),
            observation=(
                f"The selected champion {strategy_name} remains compatible with the "
                f"current market at {compatibility:.1%}."
            ),
            action=BrainAction.MONITOR_CHAMPION,
            reason=(
                "No immediate strategy-generation task is justified. ATLAS should "
                "monitor regime compatibility and performance decay."
            ),
            required_agents=["market_analyst", "quant_validator"],
            evidence={
                "intelligence_id": intelligence.get("intelligence_id"),
                "selected_strategy": selected,
            },
            restrictions=restrictions,
        )

    def _plan(
        self,
        *,
        symbol: str,
        timeframe: str,
        priority: BrainPriority,
        goal: BrainGoal,
        observation: str,
        action: BrainAction,
        reason: str,
        required_agents: list[str],
        evidence: dict[str, Any],
        restrictions: list[str],
    ) -> ResearchPlan:
        return ResearchPlan(
            plan_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol=symbol,
            timeframe=timeframe,
            priority=priority,
            goal=goal,
            observation=observation,
            recommended_action=action,
            reason=reason,
            required_agents=required_agents,
            evidence=evidence,
            restrictions=restrictions,
            live_trading_allowed=False,
        )

    @staticmethod
    def _goal_market_context() -> BrainGoal:
        return BrainGoal(
            goal_id="maintain_current_market_context",
            description="Maintain fresh and traceable market intelligence.",
            success_condition="A valid current intelligence snapshot exists.",
            priority=BrainPriority.HIGH,
        )

    @staticmethod
    def _goal_strategy_coverage() -> BrainGoal:
        return BrainGoal(
            goal_id="maintain_valid_strategy_coverage",
            description="Maintain at least one robust strategy for the current regime.",
            success_condition=(
                "A compatible strategy has passed the required validation pipeline."
            ),
            priority=BrainPriority.HIGH,
        )

    @staticmethod
    def _goal_champion_health() -> BrainGoal:
        return BrainGoal(
            goal_id="protect_champion_quality",
            description="Monitor the current champion for incompatibility and decay.",
            success_condition="The champion remains robust and regime-compatible.",
            priority=BrainPriority.MEDIUM,
        )

    @staticmethod
    def _goal_protect_capital() -> BrainGoal:
        return BrainGoal(
            goal_id="protect_capital",
            description="Prevent trading when data or risk conditions are unsafe.",
            success_condition="Unsafe deployment remains technically blocked.",
            priority=BrainPriority.CRITICAL,
        )

    @staticmethod
    def _base_restrictions() -> list[str]:
        return [
            "Research Brain may not place orders.",
            "Research Brain may not approve live deployment.",
            "Risk limits may not be changed by autonomous agents.",
            "Every promoted strategy must pass the complete validation pipeline.",
            "Deployment Guard and kill-switch rules remain mandatory.",
        ]

    @staticmethod
    def _number(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default