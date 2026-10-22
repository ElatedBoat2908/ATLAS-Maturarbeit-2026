from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import traceback

from atlas.agents.knowledge_agent import KnowledgeAgent
from atlas.agents.market_analyst import MarketAnalyst
from atlas.agents.quant_validator import QuantValidator
from atlas.agents.strategy_engineer import StrategyEngineer
from atlas.core.agent_registry import AgentRegistry
from atlas.core.decision_log import DecisionLog
from atlas.research.regime_trade_analyzer import RegimeTradeAnalyzer
from atlas.research.tournament import ResearchTournament
from atlas.adaptation.orchestrator import AdaptiveResearchOrchestrator
from atlas.brain.brain_router import BrainRouter
from atlas.brain.research_plan_executor import ResearchPlanExecutor
from atlas.execution.task_executor import SafeTaskExecutor
from atlas.execution.task_queue import PersistentTaskQueue
from atlas.execution.task_registry import TaskRegistry
from atlas.cognitive import CognitiveMemory, ExplanationEngine, ResearchJournal
from atlas.missions import (
    MissionLifecycleManager,
    MissionScheduler,
    MissionStatus,
)
from atlas.events import EventEngine


class AtlasSupervisor:
    """
    Central orchestration layer for ATLAS.

    The Supervisor coordinates specialized agents and research engines.
    It does not perform quantitative calculations itself.

    Current responsibilities:
    - track agent states
    - coordinate workflows
    - run market and regime analysis
    - generate strategy candidates
    - run candidate validation
    - run variant tournaments
    - inspect research knowledge
    - write structured decision records
    """

    def __init__(
        self,
        project_root: Path,
    ):
        self.project_root = project_root
        self.memory_dir = (
            project_root / "atlas" / "memory"
        )
        self.memory_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.market_analyst = MarketAnalyst(
            project_root=project_root,
        )

        self.strategy_engineer = StrategyEngineer(
            project_root=project_root,
        )

        self.quant_validator = QuantValidator(
            project_root=project_root,
        )

        self.knowledge_agent = KnowledgeAgent(
            project_root=project_root,
        )

        self.tournament = ResearchTournament(
            project_root=project_root,
        )

        self.regime_analyzer = RegimeTradeAnalyzer(
            project_root=project_root,
        )

        self.registry = AgentRegistry(
            project_root=project_root,
        )

        self.decision_log = DecisionLog(
            project_root=project_root,
        )

        self.adaptive_orchestrator = AdaptiveResearchOrchestrator(
            project_root=project_root,
        )

        self.brain_router = BrainRouter(
            project_root=project_root,
        )

        self.task_queue = PersistentTaskQueue(project_root=project_root)
        self.task_registry = TaskRegistry()
        self.task_executor = SafeTaskExecutor(
            queue=self.task_queue,
            registry=self.task_registry,
        )
        self.research_plan_executor = ResearchPlanExecutor(
            project_root=project_root,
        )
        self._register_research_task_handlers()
        self.cognitive_memory = CognitiveMemory(project_root=project_root)
        self.explanation_engine = ExplanationEngine()
        self.research_journal = ResearchJournal(project_root=project_root)
        self.mission_scheduler = MissionScheduler(project_root=project_root)
        self.mission_lifecycle = MissionLifecycleManager(
            scheduler=self.mission_scheduler
        )
        self.event_engine = EventEngine(
            project_root=project_root,
            mission_scheduler=self.mission_scheduler,
        )

    def plan_next_research_action(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        """Ask the Research Brain what ATLAS should do next.

        v0.5.1 is planning-only: the returned plan is validated and recorded,
        but no agent workflow is executed automatically.
        """
        workflow = "research_brain_planning"

        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message=f"Research Brain is planning the next action for {symbol} {timeframe}.",
        )

        try:
            plan = self.brain_router.plan_next_action(
                symbol=symbol,
                timeframe=timeframe,
            )
            preview = self.research_plan_executor.preview(plan)

            if preview.get("status") != "valid":
                raise RuntimeError(
                    "; ".join(preview.get("errors") or ["Brain plan is invalid."])
                )

            result = {
                "status": "complete",
                "workflow": workflow,
                "plan": plan,
                "execution_preview": preview,
                "message": (
                    "Research Brain created a safe planning-only recommendation. "
                    "No agent workflow or live trade was executed."
                ),
            }

            self.registry.mark_complete(
                "supervisor",
                message=plan.get("reason"),
                recommendation=plan.get("recommended_action"),
                metadata={
                    "plan_id": plan.get("plan_id"),
                    "priority": plan.get("priority"),
                    "goal": (plan.get("goal") or {}).get("goal_id"),
                    "required_agents": plan.get("required_agents", []),
                    "execution_mode": "preview_only",
                },
            )

            self.decision_log.record(
                workflow=workflow,
                market=symbol,
                timeframe=timeframe,
                regime=(
                    (plan.get("evidence") or {}).get("market_intelligence", {})
                    .get("regime", {})
                    .get("primary")
                ),
                decision=plan.get("recommended_action"),
                reason=plan.get("reason", "Research Brain plan created."),
                confidence=None,
                live_deployment_allowed=False,
                evidence={
                    "brain_plan": plan,
                    "execution_preview": preview,
                },
                metadata={
                    "plan_id": plan.get("plan_id"),
                    "priority": plan.get("priority"),
                    "planning_only": True,
                },
            )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )



    def run_autonomous_cycle(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        """Refresh context, detect events and create safe missions.

        This cycle never executes a mission and never authorizes live trading.
        """
        workflow = "autonomous_event_cycle"
        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message=f"Running autonomous event cycle for {symbol} {timeframe}.",
        )
        try:
            market_refresh = self.analyze_market(
                symbol=symbol,
                timeframe=timeframe,
            )
            intelligence = self._load_latest_intelligence()
            adaptive = self._load_json_file(
                self.memory_dir / "latest_adaptive_decision.json"
            )
            event_result = self.event_engine.run_cycle(
                intelligence=intelligence,
                adaptive_decision=adaptive,
            )
            result = {
                "status": "complete",
                "workflow": workflow,
                "market_refresh": market_refresh,
                "event_cycle": event_result,
                "mission_queue": self.mission_scheduler.queue_snapshot(),
            "event_state": self.event_engine.store.snapshot(),
                "live_trading_allowed": False,
                "message": (
                    "Autonomous cycle refreshed market context, detected "
                    "events and created only permitted research missions."
                ),
            }
            self.registry.mark_complete(
                "supervisor",
                message=result["message"],
                recommendation=(
                    "EXECUTE_CURRENT_MISSION"
                    if event_result.get("created_missions")
                    else "WAIT_FOR_MEANINGFUL_CHANGE"
                ),
                metadata={
                    "detected_events": event_result.get("detected_events", 0),
                    "suppressed_events": event_result.get("suppressed_events", 0),
                    "created_missions": len(event_result.get("created_missions") or []),
                },
            )
            self.decision_log.record(
                workflow=workflow,
                market=symbol,
                timeframe=timeframe,
                decision="AUTONOMOUS_EVENT_CYCLE_COMPLETE",
                reason=result["message"],
                confidence=None,
                live_deployment_allowed=False,
                evidence={"event_cycle": event_result},
                metadata={
                    "created_mission_ids": [
                        item.get("mission_id")
                        for item in event_result.get("created_missions") or []
                    ],
                },
            )
            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )
        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )

    def create_next_mission(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        """Create one queued mission from the current Research Brain state."""
        workflow = "mission_creation"
        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message=f"Creating the next mission for {symbol} {timeframe}.",
        )
        try:
            plan = self.brain_router.plan_next_action(
                symbol=symbol,
                timeframe=timeframe,
            )
            preview = self.research_plan_executor.preview(plan)
            if preview.get("status") != "valid":
                raise RuntimeError(
                    "; ".join(
                        preview.get("errors") or ["Brain plan is invalid."]
                    )
                )

            mission = self.mission_scheduler.create_from_plan(plan)
            result = {
                "status": "complete",
                "workflow": workflow,
                "mission": mission.to_dict(),
                "plan": plan,
                "live_trading_allowed": False,
                "message": (
                    "Research Brain plan was converted into a queued mission."
                ),
            }
            self.registry.mark_complete(
                "supervisor",
                message=result["message"],
                recommendation="EXECUTE_CURRENT_MISSION",
                metadata={
                    "mission_id": mission.mission_id,
                    "mission_type": mission.mission_type.value,
                    "priority": mission.priority.name,
                    "plan_id": mission.plan_id,
                },
            )
            self.decision_log.record(
                workflow=workflow,
                market=symbol,
                timeframe=timeframe,
                decision="MISSION_CREATED",
                reason=mission.goal,
                confidence=None,
                live_deployment_allowed=False,
                evidence={
                    "mission": mission.to_dict(),
                    "brain_plan": plan,
                },
                metadata={
                    "mission_id": mission.mission_id,
                    "plan_id": mission.plan_id,
                    "decision_id": mission.decision_id,
                },
            )
            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )
        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )


    def reconcile_missions(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        """Revalidate queued missions against the latest Brain decision."""
        workflow = "mission_reconciliation"
        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message=f"Reconciling missions for {symbol} {timeframe}.",
        )
        try:
            plan = self.brain_router.plan_next_action(
                symbol=symbol,
                timeframe=timeframe,
            )
            preview = self.research_plan_executor.preview(plan)
            if preview.get("status") != "valid":
                raise RuntimeError(
                    "; ".join(preview.get("errors") or ["Brain plan is invalid."])
                )
            reconciliation = self.mission_lifecycle.reconcile(plan)
            result = {
                "status": "complete",
                "workflow": workflow,
                "plan": plan,
                "reconciliation": reconciliation,
                "mission_queue": self.mission_scheduler.queue_snapshot(),
                "live_trading_allowed": False,
                "message": reconciliation.get(
                    "message",
                    "Mission reconciliation completed.",
                ),
            }
            self.registry.mark_complete(
                "supervisor",
                message=result["message"],
                recommendation=reconciliation.get("decision"),
                metadata={
                    "latest_action": reconciliation.get("latest_action"),
                    "superseded_missions": reconciliation.get("superseded_missions", []),
                    "replacement_mission_id": (
                        reconciliation.get("replacement_mission") or {}
                    ).get("mission_id"),
                },
            )
            self.decision_log.record(
                workflow=workflow,
                market=symbol,
                timeframe=timeframe,
                decision=reconciliation.get("decision", "MISSION_RECONCILED"),
                reason=result["message"],
                confidence=None,
                live_deployment_allowed=False,
                evidence={
                    "brain_plan": plan,
                    "reconciliation": reconciliation,
                },
                metadata={
                    "superseded_missions": reconciliation.get("superseded_missions", []),
                    "replacement_mission_id": (
                        reconciliation.get("replacement_mission") or {}
                    ).get("mission_id"),
                },
            )
            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )
        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )

    def show_current_mission(self) -> dict[str, Any]:
        mission = self.mission_scheduler.current_mission()
        return {
            "status": "complete",
            "mission": mission.to_dict() if mission else None,
            "message": (
                "Current mission loaded."
                if mission
                else "No active or queued mission is available."
            ),
        }

    def show_mission_queue(self) -> dict[str, Any]:
        snapshot = self.mission_scheduler.queue_snapshot()
        current = self.mission_scheduler.current_mission()
        snapshot["current_mission"] = (
            current.to_dict() if current else None
        )
        return snapshot

    def execute_current_mission(self) -> dict[str, Any]:
        """Execute the highest-priority mission via the safe task queue."""
        workflow = "mission_execution"
        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message=(
                "Executing the current mission through the controlled task queue."
            ),
        )
        mission = None
        try:
            reconciliation_envelope = self.reconcile_missions()
            reconciliation_result = reconciliation_envelope.get("result", {})
            if reconciliation_result.get("status") != "complete":
                raise RuntimeError(
                    reconciliation_result.get(
                        "message",
                        "Mission reconciliation failed before execution.",
                    )
                )
            mission = self.mission_scheduler.claim_next()
            if mission is None:
                raise RuntimeError(
                    "No executable mission is currently available."
                )

            plan = dict((mission.payload or {}).get("plan") or {})
            if not plan:
                raise RuntimeError(
                    "Mission does not contain a Research Brain plan."
                )

            queued = self.research_plan_executor.enqueue(plan)
            if queued.get("status") != "queued":
                raise RuntimeError(
                    "; ".join(
                        queued.get("errors")
                        or ["Mission tasks could not be queued."]
                    )
                )

            mission.task_ids = [
                str(item.get("task_id"))
                for item in queued.get("tasks", [])
                if item.get("task_id")
            ]
            self.mission_scheduler.store.update(
                mission,
                event="TASKS_CREATED",
            )

            execution = self.task_executor.run_until_idle(max_tasks=20)
            queue_state = self.task_queue.snapshot(
                plan_id=str(plan.get("plan_id"))
            )
            counts = queue_state.get("counts") or {}
            failed = int(counts.get("FAILED", 0))
            blocked = int(counts.get("BLOCKED", 0))
            retrying = int(counts.get("RETRYING", 0))

            mission_result = {
                "execution": execution,
                "queue_state": queue_state,
                "live_trading_allowed": False,
            }
            if failed or blocked:
                completed = self.mission_scheduler.block(
                    mission.mission_id,
                    (
                        "Mission stopped because one or more tasks "
                        "failed or were blocked."
                    ),
                )
                status = "review_required"
            elif retrying:
                completed = self.mission_scheduler.fail(
                    mission.mission_id,
                    "A mission task requires a retry.",
                )
                status = "retry_queued"
            else:
                completed = self.mission_scheduler.complete(
                    mission.mission_id,
                    mission_result,
                )
                status = "complete"

            result = {
                "status": status,
                "workflow": workflow,
                "mission": completed.to_dict(),
                "reconciliation": reconciliation_result.get("reconciliation"),
                "execution": execution,
                "queue_state": queue_state,
                "live_trading_allowed": False,
                "message": (
                    "Mission completed through the controlled task queue."
                    if status == "complete"
                    else "Mission requires review or retry."
                ),
            }
            self.registry.mark_complete(
                "supervisor",
                message=result["message"],
                recommendation=(
                    "CREATE_NEXT_MISSION"
                    if status == "complete"
                    else "REVIEW_MISSION"
                ),
                metadata={
                    "mission_id": completed.mission_id,
                    "mission_status": completed.status.value,
                    "task_counts": counts,
                    "live_trading_allowed": False,
                },
            )
            self.decision_log.record(
                workflow=workflow,
                market=completed.symbol,
                timeframe=completed.timeframe,
                decision="MISSION_EXECUTED",
                reason=result["message"],
                confidence=None,
                live_deployment_allowed=False,
                evidence={
                    "mission": completed.to_dict(),
                    "reconciliation": reconciliation_result.get("reconciliation"),
                    "task_queue": queue_state,
                },
                metadata={
                    "mission_id": completed.mission_id,
                    "plan_id": completed.plan_id,
                },
            )
            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )
        except Exception as exc:
            if mission is not None and mission.status == MissionStatus.RUNNING:
                try:
                    self.mission_scheduler.fail(
                        mission.mission_id,
                        str(exc),
                    )
                except Exception:
                    pass
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )

    def explain_latest_research_decision(self) -> dict[str, Any]:
        """Explain the latest Research Brain decision from stored evidence."""
        return self.explanation_engine.explain(self.cognitive_memory.load_latest())

    def execute_brain_plan(
        self,
    ) -> dict[str, Any]:
        """Queue and execute the latest Research Brain plan safely.

        Only explicitly registered research handlers can run. Live trading,
        order placement and risk-limit changes are not part of this executor.
        """
        workflow = "research_brain_execution"
        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message="Executing the latest Research Brain plan through the safe task queue.",
        )

        try:
            plan = self.brain_router.latest_plan()
            if not plan:
                raise RuntimeError(
                    "No Research Brain plan is available. Run 'plan next research action' first."
                )

            queued = self.research_plan_executor.enqueue(plan)
            if queued.get("status") != "queued":
                raise RuntimeError(
                    "; ".join(queued.get("errors") or ["Brain plan could not be queued."])
                )

            execution = self.task_executor.run_until_idle(max_tasks=20)
            queue_state = self.task_queue.snapshot(plan_id=str(plan.get("plan_id")))
            failed = queue_state.get("counts", {}).get("FAILED", 0)
            blocked = queue_state.get("counts", {}).get("BLOCKED", 0)
            result_status = "complete" if not failed and not blocked else "review_required"

            result = {
                "status": result_status,
                "workflow": workflow,
                "plan": plan,
                "queued": queued,
                "execution": execution,
                "queue_state": queue_state,
                "live_trading_allowed": False,
                "message": (
                    "Research Brain plan executed through the controlled task queue."
                    if result_status == "complete"
                    else "Research Brain execution stopped because a task failed or was blocked."
                ),
            }

            self.registry.mark_complete(
                "supervisor",
                message=result["message"],
                recommendation=(
                    "REVIEW_TASK_FAILURES"
                    if result_status != "complete"
                    else "BUILD_NEXT_BRAIN_PLAN"
                ),
                metadata={
                    "plan_id": plan.get("plan_id"),
                    "executed_tasks": execution.get("executed", 0),
                    "queue_counts": queue_state.get("counts", {}),
                    "live_trading_allowed": False,
                },
            )

            self.decision_log.record(
                workflow=workflow,
                market=plan.get("symbol"),
                timeframe=plan.get("timeframe"),
                decision="BRAIN_PLAN_EXECUTED",
                reason=result["message"],
                confidence=None,
                live_deployment_allowed=False,
                evidence={
                    "plan": plan,
                    "queue_state": queue_state,
                    "execution": execution,
                },
                metadata={
                    "plan_id": plan.get("plan_id"),
                    "controlled_execution": True,
                },
            )

            self.research_journal.append({
                "event": "research_plan_executed",
                "plan_id": plan.get("plan_id"),
                "decision_id": plan.get("cognitive_decision_id"),
                "chosen_action": plan.get("recommended_action"),
                "executed_tasks": execution,
                "outcome": result_status.upper(),
                "queue_state": queue_state,
                "live_trading_allowed": False,
            })
            return self._save_supervisor_result(workflow=workflow, result=result)

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )

    def get_task_queue_state(self) -> dict[str, Any]:
        return self.task_queue.snapshot()

    def _register_research_task_handlers(self) -> None:
        self.task_registry.register(
            "REFRESH_MARKET_INTELLIGENCE",
            self._task_refresh_market_intelligence,
        )
        self.task_registry.register(
            "RUN_ADAPTIVE_SELECTION",
            self._task_adaptive_selection,
        )
        self.task_registry.register(
            "MONITOR_CHAMPION",
            self._task_adaptive_selection,
        )
        self.task_registry.register(
            "PREPARE_CHALLENGER",
            self._task_prepare_challenger,
        )
        self.task_registry.register(
            "VALIDATE_CANDIDATE",
            self._task_validate_candidate,
        )
        self.task_registry.register(
            "RUN_TOURNAMENT",
            self._task_run_tournament,
        )
        self.task_registry.register(
            "BLOCK_AND_REVIEW",
            self._task_block_and_review,
        )

    def _task_refresh_market_intelligence(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.analyze_market(
            symbol=str(payload.get("symbol") or "USTEC.c"),
            timeframe=str(payload.get("timeframe") or "M5"),
        )

    def _task_adaptive_selection(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.adapt_to_market(
            symbol=str(payload.get("symbol") or "USTEC.c"),
            timeframe=str(payload.get("timeframe") or "M5"),
        )

    def _task_prepare_challenger(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.improve_strategy()

    def _task_validate_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.validate_candidate()

    def _task_run_tournament(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.run_tournament()

    def _task_block_and_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "complete",
            "action": "BLOCK_AND_REVIEW",
            "plan_id": payload.get("plan_id"),
            "live_trading_allowed": False,
            "message": "Research activity remains blocked pending manual review.",
        }

    def analyze_market(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        workflow = "market_analysis"

        self.registry.mark_running(
            "market_analyst",
            workflow=workflow,
            message=(
                f"Analyzing {symbol} {timeframe}."
            ),
        )

        try:
            result = (
                self.market_analyst
                .analyze_current_market(
                    symbol=symbol,
                    timeframe=timeframe,
                )
            )

            if result.get("status") == "complete":
                self.registry.mark_complete(
                    "market_analyst",
                    message=result.get(
                        "summary"
                    ),
                    confidence=result.get(
                        "confidence"
                    ),
                    recommendation=(
                        "Use this market context as research input."
                    ),
                    metadata={
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "regime": result.get(
                            "trend_regime"
                        ),
                        "freshness": result.get(
                            "freshness_status"
                        ),
                        "intelligence_id": result.get(
                            "intelligence_id"
                        ),
                    },
                )

                self.decision_log.record(
                    workflow=workflow,
                    market=symbol,
                    timeframe=timeframe,
                    regime=result.get(
                        "trend_regime"
                    ),
                    decision="MARKET_CONTEXT_UPDATED",
                    reason=result.get(
                        "summary",
                        "Market analysis completed.",
                    ),
                    confidence=result.get(
                        "confidence"
                    ),
                    live_deployment_allowed=False,
                    evidence=result,
                    metadata={
                        "intelligence_id": result.get("intelligence_id"),
                    },
                )

            else:
                self.registry.mark_failed(
                    "market_analyst",
                    error=result.get(
                        "message",
                        "Market analysis failed.",
                    ),
                )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="market_analyst",
                error=exc,
            )

    def adapt_to_market(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        """Build market context and choose a safe adaptive research action."""
        workflow = "adaptive_strategy_intelligence"
        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message="Selecting the best strategy for the current market context.",
        )
        try:
            market_result = self.market_analyst.analyze_current_market(
                symbol=symbol,
                timeframe=timeframe,
            )

            intelligence = (
                market_result.get("market_intelligence")
                or market_result.get("intelligence")
                or {}
            )

            if market_result.get("status") != "complete":
                raise RuntimeError(
                    market_result.get(
                        "message",
                        "Market analysis failed."
                    )
                )
    
            if not intelligence:
                raise RuntimeError(
                    "Market analysis completed, but no market-intelligence "
                "snapshot was returned."
            )

            result = self.adaptive_orchestrator.run(intelligence)
            selected = (result.get("selection") or {}).get("selected_strategy") or {}
            self.registry.mark_complete(
                "supervisor",
                message=result.get("recommendation"),
                confidence=selected.get("compatibility_score"),
                recommendation=result.get("action"),
                metadata={
                    "intelligence_id": result.get("intelligence_id"),
                    "strategy": selected.get("strategy_name"),
                    "action": result.get("action"),
                },
            )
            self.decision_log.record(
                workflow=workflow,
                market=symbol,
                timeframe=timeframe,
                regime=result.get("regime"),
                strategy=selected.get("strategy_name"),
                decision=result.get("action"),
                reason=result.get("recommendation", "Adaptive research decision completed."),
                confidence=selected.get("compatibility_score"),
                live_deployment_allowed=False,
                evidence=result,
            )
            return self._save_supervisor_result(workflow=workflow, result=result)
        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )

    def analyze_regimes(
        self,
    ) -> dict[str, Any]:
        workflow = "regime_analysis"

        self.registry.mark_running(
            "market_analyst",
            workflow=workflow,
            message=(
                "Analyzing strategy performance by regime."
            ),
        )

        try:
            result = self.regime_analyzer.analyze()

            if result.get("status") == "complete":
                latest_regime = result.get(
                    "latest_regime",
                    {},
                )

                interpretation = result.get(
                    "interpretation",
                    [],
                )

                recommendation = (
                    interpretation[0]
                    if interpretation
                    else "Review regime analysis."
                )

                self.registry.mark_complete(
                    "market_analyst",
                    message=(
                        "Historical regime analysis completed."
                    ),
                    confidence=latest_regime.get(
                        "confidence"
                    ),
                    recommendation=recommendation,
                    metadata={
                        "latest_regime": (
                            latest_regime.get(
                                "combined_regime"
                            )
                        ),
                        "trades_analyzed": result.get(
                            "trades_analyzed"
                        ),
                    },
                )

                self.decision_log.record(
                    workflow=workflow,
                    market="USTEC.c",
                    timeframe="M5",
                    regime=latest_regime.get(
                        "combined_regime"
                    ),
                    strategy=result.get(
                        "source_strategy"
                    ),
                    decision="REGIME_PROFILE_UPDATED",
                    reason=(
                        "Historical strategy performance was "
                        "grouped by trend, volatility and momentum."
                    ),
                    confidence=latest_regime.get(
                        "confidence"
                    ),
                    live_deployment_allowed=False,
                    evidence={
                        "best_regimes": result.get(
                            "best_regimes",
                            [],
                        ),
                        "worst_regimes": result.get(
                            "worst_regimes",
                            [],
                        ),
                    },
                )

            else:
                self.registry.mark_failed(
                    "market_analyst",
                    error=(
                        "Regime analysis did not complete."
                    ),
                )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="market_analyst",
                error=exc,
            )

    def improve_strategy(
        self,
    ) -> dict[str, Any]:
        workflow = "strategy_improvement"

        self.registry.mark_running(
            "strategy_engineer",
            workflow=workflow,
            message=(
                "Analyzing the current strategy and generating "
                "a controlled candidate."
            ),
        )

        try:
            result = (
                self.strategy_engineer
                .generate_candidate()
            )

            if result.get("status") == "complete":
                generated = result.get(
                    "generated_strategy",
                    {},
                )

                self.registry.mark_complete(
                    "strategy_engineer",
                    message=result.get(
                        "message"
                    ),
                    recommendation=(
                        "Validate the generated strategy candidate."
                    ),
                    metadata={
                        "candidate": generated.get(
                            "strategy_name"
                        ),
                        "file_path": generated.get(
                            "file_path"
                        ),
                    },
                )

                self.decision_log.record(
                    workflow=workflow,
                    strategy=generated.get(
                        "strategy_name"
                    ),
                    decision="CANDIDATE_GENERATED",
                    reason=(
                        "The Strategy Engineer generated a "
                        "controlled research candidate."
                    ),
                    confidence=0.70,
                    live_deployment_allowed=False,
                    evidence={
                        "analysis": result.get(
                            "analysis",
                            {},
                        ),
                        "prior_knowledge": result.get(
                            "relevant_knowledge",
                            {},
                        ),
                    },
                )

            else:
                self.registry.mark_failed(
                    "strategy_engineer",
                    error=result.get(
                        "message",
                        "Strategy generation failed.",
                    ),
                )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="strategy_engineer",
                error=exc,
            )

    def validate_candidate(
        self,
    ) -> dict[str, Any]:
        workflow = "candidate_validation"

        self.registry.mark_running(
            "quant_validator",
            workflow=workflow,
            message=(
                "Validating the latest generated candidate."
            ),
        )

        try:
            result = (
                self.quant_validator
                .validate_latest_candidate()
            )

            validation = result.get(
                "validation",
                {},
            )

            if validation.get("status") == "complete":
                verdict = validation.get(
                    "verdict",
                    "REVIEW",
                )

                candidate = validation.get(
                    "candidate_strategy",
                    {},
                )

                candidate_name = candidate.get(
                    "name"
                )

                self.registry.mark_complete(
                    "quant_validator",
                    message=(
                        f"Candidate validation completed: {verdict}."
                    ),
                    recommendation=(
                        self._validation_recommendation(
                            verdict
                        )
                    ),
                    metadata={
                        "candidate": candidate_name,
                        "verdict": verdict,
                    },
                )

                self.decision_log.record(
                    workflow=workflow,
                    strategy=candidate_name,
                    decision=verdict,
                    reason=(
                        self._validation_recommendation(
                            verdict
                        )
                    ),
                    confidence=self._verdict_confidence(
                        verdict
                    ),
                    live_deployment_allowed=False,
                    evidence=validation,
                )

            else:
                errors = validation.get(
                    "errors",
                    [],
                )

                self.registry.mark_failed(
                    "quant_validator",
                    error=(
                        "; ".join(errors)
                        if errors
                        else "Candidate validation failed."
                    ),
                )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="quant_validator",
                error=exc,
            )

    def run_tournament(
        self,
    ) -> dict[str, Any]:
        workflow = "variant_tournament"

        self.registry.mark_running(
            "tournament_engine",
            workflow=workflow,
            message=(
                "Generating, testing and ranking controlled variants."
            ),
        )

        try:
            result = self.tournament.run()

            if result.get("status") == "complete":
                winner = result.get(
                    "winner",
                    {},
                )

                recommendation = result.get(
                    "recommendation",
                    "Manual review required.",
                )

                self.registry.mark_complete(
                    "tournament_engine",
                    message=(
                        "Variant tournament completed."
                    ),
                    recommendation=recommendation,
                    metadata={
                        "experiment_id": result.get(
                            "experiment_id"
                        ),
                        "winner": winner.get(
                            "strategy_name"
                        ),
                        "score": winner.get(
                            "score"
                        ),
                    },
                )

                self.decision_log.record(
                    workflow=workflow,
                    strategy=winner.get(
                        "strategy_name"
                    ),
                    decision="TOURNAMENT_WINNER_SELECTED",
                    reason=recommendation,
                    confidence=self._score_confidence(
                        winner.get("score")
                    ),
                    live_deployment_allowed=False,
                    evidence={
                        "winner": winner,
                        "leaderboard": result.get(
                            "leaderboard",
                            [],
                        ),
                    },
                )

            else:
                self.registry.mark_failed(
                    "tournament_engine",
                    error=(
                        "No successful tournament result was produced."
                    ),
                )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="tournament_engine",
                error=exc,
            )

    def inspect_knowledge(
        self,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        workflow = "knowledge_inspection"

        self.registry.mark_running(
            "knowledge_agent",
            workflow=workflow,
            message=(
                "Inspecting stored ATLAS research knowledge."
            ),
        )

        try:
            result = {
                "status": "complete",
                "agent": "knowledge_agent",
                "stats": self.knowledge_agent.get_stats(),
                "knowledge": (
                    self.knowledge_agent
                    .summarize_for_strategy_engineer(
                        tags=tags,
                        limit=10,
                    )
                ),
            }

            self.registry.mark_complete(
                "knowledge_agent",
                message=(
                    "Research knowledge inspection completed."
                ),
                recommendation=(
                    "Use stored lessons during candidate generation."
                ),
                metadata=result.get(
                    "stats",
                    {},
                ),
            )

            return self._save_supervisor_result(
                workflow=workflow,
                result=result,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="knowledge_agent",
                error=exc,
            )

    def run_strategy_research_loop(
        self,
        symbol: str = "USTEC.c",
        timeframe: str = "M5",
    ) -> dict[str, Any]:
        workflow = "strategy_research_loop"

        self.registry.mark_running(
            "supervisor",
            workflow=workflow,
            message=(
                "Coordinating the complete research loop."
            ),
        )

        try:
            market_envelope = self.analyze_market(
                symbol=symbol,
                timeframe=timeframe,
            )

            market_result = market_envelope.get(
                "result",
                {},
            )

            regime_envelope = self.analyze_regimes()

            regime_result = regime_envelope.get(
                "result",
                {},
            )

            engineering_envelope = (
                self.improve_strategy()
            )

            engineering_result = (
                engineering_envelope.get(
                    "result",
                    {},
                )
            )

            if engineering_result.get(
                "status"
            ) != "complete":
                raise RuntimeError(
                    "Strategy Engineer could not generate a candidate."
                )

            validation_envelope = (
                self.validate_candidate()
            )

            validation_result = (
                validation_envelope.get(
                    "result",
                    {},
                )
            )

            validation = validation_result.get(
                "validation",
                {},
            )

            verdict = validation.get(
                "verdict",
                "REVIEW",
            )

            tournament_result = None

            if verdict in {
                "REVIEW_RISK_IMPROVEMENT",
                "REVIEW",
            }:
                tournament_envelope = (
                    self.run_tournament()
                )

                tournament_result = (
                    tournament_envelope.get(
                        "result",
                        {},
                    )
                )

            recommendation = (
                self._build_research_loop_recommendation(
                    validation=validation,
                    tournament=tournament_result,
                )
            )

            combined = {
                "status": "complete",
                "workflow": workflow,
                "market_analysis": market_result,
                "regime_analysis": regime_result,
                "strategy_engineering": engineering_result,
                "candidate_validation": validation_result,
                "tournament": tournament_result,
                "recommendation": recommendation,
                "live_deployment_allowed": False,
            }

            self.registry.mark_complete(
                "supervisor",
                message=(
                    "Complete research loop finished."
                ),
                recommendation=recommendation,
                metadata={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "verdict": verdict,
                    "tournament_ran": (
                        tournament_result is not None
                    ),
                },
            )

            latest_regime = regime_result.get(
                "latest_regime",
                {},
            )

            self.decision_log.record(
                workflow=workflow,
                market=symbol,
                timeframe=timeframe,
                regime=latest_regime.get(
                    "combined_regime"
                ),
                strategy=(
                    validation
                    .get(
                        "candidate_strategy",
                        {},
                    )
                    .get("name")
                ),
                decision="KEEP_IN_RESEARCH",
                reason=recommendation,
                confidence=0.80,
                live_deployment_allowed=False,
                evidence={
                    "validation": validation,
                    "tournament": tournament_result,
                },
            )

            return self._save_supervisor_result(
                workflow=workflow,
                result=combined,
            )

        except Exception as exc:
            return self._handle_failure(
                workflow=workflow,
                agent_name="supervisor",
                error=exc,
            )

    def get_system_state(
        self,
    ) -> dict[str, Any]:
        return {
            "status": "complete",
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "agents": self.registry.all_states(),
            "recent_decisions": (
                self.decision_log.read_recent(
                    limit=10
                )
            ),
            "latest_market_intelligence": self._load_latest_intelligence(),
            "latest_brain_plan": self.brain_router.latest_plan(),
            "brain_task_queue": self.task_queue.snapshot(),
            "mission_queue": self.mission_scheduler.queue_snapshot(),
            "current_mission": (
                self.mission_scheduler.current_mission().to_dict()
                if self.mission_scheduler.current_mission()
                else None
            ),
        }



    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _load_latest_intelligence(
        self,
    ) -> dict[str, Any] | None:
        path = self.memory_dir / "latest_market_intelligence.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _build_research_loop_recommendation(
        self,
        validation: dict[str, Any],
        tournament: dict[str, Any] | None,
    ) -> str:
        verdict = validation.get(
            "verdict",
            "REVIEW",
        )

        if tournament:
            return tournament.get(
                "recommendation",
                "Review the tournament winner.",
            )

        return self._validation_recommendation(
            verdict
        )

    def _validation_recommendation(
        self,
        verdict: str,
    ) -> str:
        recommendations = {
            "ACCEPT_FOR_WALK_FORWARD": (
                "Advance the candidate to Monte Carlo and "
                "walk-forward validation."
            ),
            "REVIEW_RISK_IMPROVEMENT": (
                "Generate and test less aggressive strategy variants."
            ),
            "REVIEW": (
                "Keep the candidate in research and run a variant tournament."
            ),
            "REJECT": (
                "Reject the candidate and preserve the original strategy."
            ),
            "ERROR": (
                "Resolve validation errors before continuing."
            ),
        }

        return recommendations.get(
            verdict,
            "Manual quantitative review is required.",
        )

    def _verdict_confidence(
        self,
        verdict: str,
    ) -> float:
        values = {
            "ACCEPT_FOR_WALK_FORWARD": 0.85,
            "REVIEW_RISK_IMPROVEMENT": 0.75,
            "REVIEW": 0.60,
            "REJECT": 0.85,
            "ERROR": 0.20,
        }

        return values.get(
            verdict,
            0.50,
        )

    def _score_confidence(
        self,
        score: Any,
    ) -> float | None:
        if score is None:
            return None

        try:
            value = float(score)
        except (
            TypeError,
            ValueError,
        ):
            return None

        return min(
            1.0,
            max(0.0, value / 100.0),
        )

    def _save_supervisor_result(
        self,
        workflow: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        envelope = {
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "supervisor": "atlas_supervisor",
            "workflow": workflow,
            "result": result,
            "agent_states": (
                self.registry.all_states()
            ),
        }

        path = (
            self.memory_dir
            / "latest_supervisor_result.json"
        )

        path.write_text(
            json.dumps(
                envelope,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        return envelope

    def _handle_failure(
        self,
        workflow: str,
        agent_name: str,
        error: Exception,
    ) -> dict[str, Any]:
        error_message = str(error)

        self.registry.mark_failed(
            agent_name,
            error=error_message,
            message=(
                f"Workflow '{workflow}' failed."
            ),
            metadata={
                "traceback": traceback.format_exc(),
            },
        )

        self.decision_log.record(
            workflow=workflow,
            decision="WORKFLOW_FAILED",
            reason=error_message,
            confidence=0.0,
            live_deployment_allowed=False,
            evidence={
                "agent": agent_name,
                "traceback": traceback.format_exc(),
            },
        )

        result = {
            "status": "failed",
            "workflow": workflow,
            "agent": agent_name,
            "message": error_message,
            "traceback": traceback.format_exc(),
        }

        return self._save_supervisor_result(
            workflow=workflow,
            result=result,
        )