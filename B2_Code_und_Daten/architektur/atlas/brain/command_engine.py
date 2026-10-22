from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.agents.supervisor import AtlasSupervisor
from atlas.execution.deployment_guard import DeploymentGuard
from atlas.application import IntelligenceActionController


class CommandEngine:
    """
    Clean ATLAS command router.

    Responsibilities:
    - detect executable user intents
    - delegate workflows to AtlasSupervisor
    - format structured results for the Chat UI
    - send deployment requests through DeploymentGuard
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.supervisor = AtlasSupervisor(project_root=project_root)
        self.deployment_guard = DeploymentGuard()
        self.intelligence_actions = IntelligenceActionController(project_root)

    def can_handle(self, command: str) -> bool:
        return any(
            (
                self._is_full_intelligence_cycle_command(command),
                self._is_reconcile_mission_command(command),
                self._is_autonomous_cycle_command(command),
                self._is_execute_mission_command(command),
                self._is_show_mission_queue_command(command),
                self._is_show_current_mission_command(command),
                self._is_create_mission_command(command),
                self._is_brain_evidence_command(command),
                self._is_brain_alternatives_command(command),
                self._is_brain_explanation_command(command),
                self._is_brain_plan_execution_command(command),
                self._is_brain_plan_command(command),
                self._is_adaptive_strategy_command(command),
                self._is_combined_agent_command(command),
                self._is_market_analysis_command(command),
                self._is_regime_analysis_command(command),
                self._is_tournament_command(command),
                self._is_candidate_validation_command(command),
                self._is_strategy_improvement_command(command),
                self._is_knowledge_command(command),
                self._is_current_intelligence_command(command),
                self._is_system_state_command(command),
                self._is_research_command(command),
                self._is_deployment_command(command),
            )
        )

    def execute(self, command: str) -> dict[str, Any]:
        if self._is_full_intelligence_cycle_command(command):
            return self._execute_full_intelligence_cycle()

        if self._is_reconcile_mission_command(command):
            return self._execute_reconcile_missions()

        if self._is_autonomous_cycle_command(command):
            return self._execute_autonomous_cycle()

        if self._is_execute_mission_command(command):
            return self._execute_current_mission()

        if self._is_show_mission_queue_command(command):
            return self._execute_show_mission_queue()

        if self._is_show_current_mission_command(command):
            return self._execute_show_current_mission()

        if self._is_create_mission_command(command):
            return self._execute_create_mission()

        if self._is_brain_evidence_command(command):
            return self._execute_brain_evidence()

        if self._is_brain_alternatives_command(command):
            return self._execute_brain_alternatives()

        if self._is_brain_explanation_command(command):
            return self._execute_brain_explanation()

        if self._is_brain_plan_execution_command(command):
            return self._execute_brain_plan_execution()

        if self._is_brain_plan_command(command):
            return self._execute_brain_plan()

        if self._is_adaptive_strategy_command(command):
            return self._execute_adaptive_strategy()

        if self._is_combined_agent_command(command):
            return self._execute_combined_research()

        if self._is_regime_analysis_command(command):
            return self._execute_regime_analysis()

        if self._is_market_analysis_command(command):
            return self._execute_market_analysis()

        if self._is_tournament_command(command):
            return self._execute_tournament()

        if self._is_candidate_validation_command(command):
            return self._execute_candidate_validation()

        if self._is_strategy_improvement_command(command):
            return self._execute_strategy_improvement()

        if self._is_knowledge_command(command):
            return self._execute_knowledge_inspection()

        if self._is_current_intelligence_command(command):
            return self._execute_current_intelligence()

        if self._is_system_state_command(command):
            return self._execute_system_state()

        if self._is_research_command(command) or self._is_deployment_command(command):
            return self._execute_full_research(command)

        return {
            "handled": False,
            "intent": "unknown",
            "message": "ATLAS does not currently have an executable workflow for that command.",
        }

    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------



    def _execute_full_intelligence_cycle(self) -> dict[str, Any]:
        result = self.intelligence_actions.run_full_cycle(
            profile="GBE Demo",
            timeframe="M5",
            limit=5,
            count=1500,
            top_n=5,
            minimum_score=55.0,
            create_mission=False,
        )
        return {
            "handled": True,
            "intent": "full_intelligence_cycle",
            "intelligence_cycle": result,
            "message": self._format_full_intelligence_cycle(result),
        }

    def _execute_reconcile_missions(self) -> dict[str, Any]:
        envelope = self.supervisor.reconcile_missions()
        result = envelope.get("result", {})
        return {
            "handled": True,
            "intent": "mission_reconciliation",
            "supervisor_result": envelope,
            "message": self._format_mission_reconciliation(result),
        }

    def _execute_autonomous_cycle(self) -> dict[str, Any]:
        envelope = self.supervisor.run_autonomous_cycle()
        result = envelope.get("result", {})
        return {
            "handled": True,
            "intent": "autonomous_event_cycle",
            "supervisor_result": envelope,
            "message": self._format_autonomous_cycle(result),
        }

    def _execute_create_mission(self) -> dict[str, Any]:
        envelope = self.supervisor.create_next_mission()
        result = envelope.get("result", {})
        return {
            "handled": True,
            "intent": "mission_creation",
            "supervisor_result": envelope,
            "message": self._format_mission_created(result),
        }

    def _execute_show_current_mission(self) -> dict[str, Any]:
        result = self.supervisor.show_current_mission()
        return {
            "handled": True,
            "intent": "current_mission",
            "mission": result.get("mission"),
            "message": self._format_current_mission(result),
        }

    def _execute_show_mission_queue(self) -> dict[str, Any]:
        result = self.supervisor.show_mission_queue()
        return {
            "handled": True,
            "intent": "mission_queue",
            "mission_queue": result,
            "message": self._format_mission_queue(result),
        }

    def _execute_current_mission(self) -> dict[str, Any]:
        envelope = self.supervisor.execute_current_mission()
        result = envelope.get("result", {})
        return {
            "handled": True,
            "intent": "mission_execution",
            "supervisor_result": envelope,
            "message": self._format_mission_execution(result),
        }

    def _execute_brain_evidence(self) -> dict[str, Any]:
        result = self.supervisor.explain_latest_research_decision()
        return {
            "handled": True,
            "intent": "research_brain_evidence",
            "cognitive_explanation": result,
            "message": self._format_brain_evidence(result),
        }

    def _execute_brain_alternatives(self) -> dict[str, Any]:
        result = self.supervisor.explain_latest_research_decision()
        return {
            "handled": True,
            "intent": "research_brain_alternatives",
            "cognitive_explanation": result,
            "message": self._format_brain_alternatives(result),
        }

    def _execute_brain_explanation(self) -> dict[str, Any]:
        result = self.supervisor.explain_latest_research_decision()
        return {
            "handled": True,
            "intent": "research_brain_explanation",
            "cognitive_explanation": result,
            "message": self._format_brain_explanation(result),
        }

    def _execute_brain_plan_execution(self) -> dict[str, Any]:
        envelope = self.supervisor.execute_brain_plan()
        result = envelope.get("result", {})
        return {
            "handled": True,
            "intent": "research_brain_execution",
            "supervisor_result": envelope,
            "message": self._format_brain_execution(result),
        }

    def _execute_brain_plan(self) -> dict[str, Any]:
        envelope = self.supervisor.plan_next_research_action()
        result = envelope.get("result", {})
        plan = result.get("plan") or {}

        return {
            "handled": True,
            "intent": "research_brain_planning",
            "supervisor_result": envelope,
            "brain_plan": plan,
            "message": self._format_brain_plan(result),
        }

    def _execute_adaptive_strategy(self) -> dict[str, Any]:
        envelope = self.supervisor.adapt_to_market()
        result = envelope.get("result", {})
        return {
            "handled": True,
            "intent": "adaptive_strategy_intelligence",
            "supervisor_result": envelope,
            "message": self._format_adaptive_strategy(result),
        }

    def _execute_market_analysis(self) -> dict[str, Any]:
        envelope = self.supervisor.analyze_market()
        result = envelope.get("result", {})

        return {
            "handled": True,
            "intent": "market_analysis",
            "supervisor_result": envelope,
            "message": self._format_market_analysis(result),
        }

    def _execute_regime_analysis(self) -> dict[str, Any]:
        envelope = self.supervisor.analyze_regimes()
        result = envelope.get("result", {})

        return {
            "handled": True,
            "intent": "regime_analysis",
            "supervisor_result": envelope,
            "message": self._format_regime_analysis(result),
        }

    def _execute_strategy_improvement(self) -> dict[str, Any]:
        envelope = self.supervisor.improve_strategy()
        result = envelope.get("result", {})

        return {
            "handled": True,
            "intent": "strategy_improvement",
            "supervisor_result": envelope,
            "message": self._format_strategy_improvement(result),
        }

    def _execute_candidate_validation(self) -> dict[str, Any]:
        envelope = self.supervisor.validate_candidate()
        result = envelope.get("result", {})
        validation = result.get("validation", {})
        knowledge_result = result.get("knowledge_result", {})

        return {
            "handled": True,
            "intent": "candidate_validation",
            "supervisor_result": envelope,
            "validation": validation,
            "knowledge_result": knowledge_result,
            "message": self._format_candidate_validation(
                validation=validation,
                knowledge_result=knowledge_result,
            ),
        }

    def _execute_tournament(self) -> dict[str, Any]:
        envelope = self.supervisor.run_tournament()
        result = envelope.get("result", {})

        return {
            "handled": True,
            "intent": "variant_tournament",
            "supervisor_result": envelope,
            "message": self._format_tournament(result),
        }

    def _execute_knowledge_inspection(self) -> dict[str, Any]:
        envelope = self.supervisor.inspect_knowledge()
        result = envelope.get("result", {})

        return {
            "handled": True,
            "intent": "knowledge_inspection",
            "supervisor_result": envelope,
            "message": self._format_knowledge_inspection(
                stats=result.get("stats", {}),
                knowledge=result.get("knowledge", {}),
            ),
        }


    def _execute_current_intelligence(self) -> dict[str, Any]:
        state = self.supervisor.get_system_state()
        intelligence = state.get("latest_market_intelligence")
        return {
            "handled": True,
            "intent": "current_market_intelligence",
            "market_intelligence": intelligence,
            "message": self._format_current_intelligence(intelligence),
        }

    def _execute_system_state(self) -> dict[str, Any]:
        result = self.supervisor.get_system_state()

        return {
            "handled": True,
            "intent": "system_state",
            "system_state": result,
            "message": self._format_system_state(result),
        }

    def _execute_combined_research(self) -> dict[str, Any]:
        envelope = self.supervisor.run_strategy_research_loop()
        result = envelope.get("result", {})

        return {
            "handled": True,
            "intent": "combined_agent_research",
            "supervisor_result": envelope,
            "message": self._format_combined_research(result),
        }

    def _execute_full_research(self, command: str) -> dict[str, Any]:
        deployment_decision = (
            self.deployment_guard.evaluate_live_deployment_request(command)
        )

        wrapper = self.supervisor.quant_validator.run_full_research_cycle(command)
        report = wrapper.get("research_report", {})

        return {
            "handled": True,
            "intent": "full_research_cycle",
            "research_report": report,
            "deployment_guard": {
                "allowed": deployment_decision.allowed,
                "reason": deployment_decision.reason,
                "requires_manual_approval": (
                    deployment_decision.requires_manual_approval
                ),
            },
            "message": self._format_full_research(
                report=report,
                safety_message=deployment_decision.reason,
            ),
        }

    # ------------------------------------------------------------------
    # Intent detection
    # ------------------------------------------------------------------

    @staticmethod
    def _contains(command: str, phrases: list[str]) -> bool:
        lowered = command.lower().strip()
        return any(phrase in lowered for phrase in phrases)



    def _is_full_intelligence_cycle_command(self, command: str) -> bool:
        normalized = " ".join(command.lower().strip().split())
        phrases = {
            "run full cycle",
            "run the full cycle",
            "run full intelligence cycle",
            "run the full intelligence cycle",
            "full intelligence cycle",
            "start full cycle",
        }
        return normalized in phrases

    def _is_reconcile_mission_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "reconcile missions",
                "reconcile current mission",
                "revalidate current mission",
                "check mission validity",
                "replace obsolete mission",
            ],
        )

    def _is_autonomous_cycle_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "run autonomous cycle",
                "run the autonomous cycle",
                "run event cycle",
                "detect events and create missions",
                "autonomous mission cycle",
            ],
        )

    def _is_create_mission_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "create next mission",
                "create the next mission",
                "create research mission",
                "convert brain plan to mission",
                "schedule next mission",
            ],
        )

    def _is_show_current_mission_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "show current mission",
                "current mission",
                "what is the current mission",
                "show active mission",
            ],
        )

    def _is_show_mission_queue_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "show mission queue",
                "mission queue",
                "show queued missions",
                "show all missions",
            ],
        )

    def _is_execute_mission_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "execute current mission",
                "run current mission",
                "execute next mission",
                "run next mission",
            ],
        )

    def _is_brain_evidence_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "what evidence supports your decision",
                "what evidence supports this decision",
                "show supporting evidence",
                "show latest evidence",
                "show decision evidence",
                "show cognitive evidence",
                "what evidence did you use",
                "which evidence did you use",
                "why is this decision supported",
            ],
        )

    def _is_brain_alternatives_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "what alternatives did you consider",
                "which alternatives did you consider",
                "show rejected alternatives",
                "show rejected options",
                "what options did you reject",
                "which options did you reject",
                "show alternative decisions",
            ],
        )

    def _is_brain_explanation_command(self, command: str) -> bool:
        text = command.strip().lower()
        phrases = (
            "why did you choose this research plan",
            "why did atlas choose this research plan",
            "explain the latest research decision",
            "explain your research plan",
            "why this research plan",
        )
        return any(phrase in text for phrase in phrases)

    def _is_brain_plan_execution_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "execute brain plan",
                "execute research brain plan",
                "run latest brain plan",
                "execute latest research plan",
                "run the brain plan",
            ],
        )

    def _is_brain_plan_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "plan next research action",
                "plan the next research action",
                "what should atlas research next",
                "what should i research next",
                "ask the research brain",
                "run research brain",
                "show brain plan",
                "create research plan",
            ],
        )

    def _is_adaptive_strategy_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "adapt to current market",
                "adapt strategy to current market",
                "select strategy for current market",
                "find the best strategy for current market",
                "run adaptive strategy intelligence",
                "improve for the current market",
            ],
        )

    def _is_combined_agent_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "run agent research loop",
                "run strategy research loop",
                "full agent workflow",
                "run all agents",
                "use all agents",
                "complete agent workflow",
                "let the agents improve the strategy",
                "agents improve strategy",
                "analyze generate and validate",
                "analyse generate and validate",
            ],
        )

    def _is_market_analysis_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "analyze current market",
                "analyse current market",
                "current market analysis",
                "describe current market",
                "check current market",
                "what is the current market",
                "current market regime",
            ],
        )

    def _is_regime_analysis_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "run regime analysis",
                "analyze trading regimes",
                "analyse trading regimes",
                "analyze market regimes",
                "analyse market regimes",
                "analyze strategy performance by market regime",
                "analyse strategy performance by market regime",
                "show best market regimes",
                "show worst market regimes",
                "regime performance analysis",
                "historical regime analysis",
            ],
        )

    def _is_tournament_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "run tournament",
                "run strategy tournament",
                "run variant tournament",
                "generate and test strategy variants",
                "test strategy variants",
                "rank strategy variants",
            ],
        )

    def _is_candidate_validation_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "validate latest generated strategy",
                "validate generated strategy",
                "validate latest candidate",
                "validate candidate",
                "test latest generated strategy",
                "backtest latest generated strategy",
                "test the improved strategy",
                "validate the improved strategy",
                "test improved strategy",
                "compare improved strategy",
                "compare candidate",
                "test latest candidate",
            ],
        )

    def _is_strategy_improvement_command(self, command: str) -> bool:
        lowered = command.lower().strip()

        explicit = self._contains(
            command,
            [
                "analyze current best strategy",
                "analyse current best strategy",
                "create a better version",
                "improve strategy",
                "improve the best",
                "create improved strategy",
                "generate improved strategy",
                "give me a better strategy",
                "make the strategy better",
                "find strategy weaknesses",
                "recode the strategy",
            ],
        )

        strategy_words = (
            "strategy",
            "strategies",
            "bot",
            "trading system",
        )
        improvement_words = (
            "improve",
            "improved",
            "better",
            "optimize",
            "optimise",
            "recode",
            "rewrite",
            "enhance",
            "upgrade",
        )

        return explicit or (
            any(word in lowered for word in strategy_words)
            and any(word in lowered for word in improvement_words)
        )

    def _is_knowledge_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "show research knowledge",
                "show atlas knowledge",
                "what has atlas learned",
                "what did atlas learn",
                "inspect knowledge",
                "show knowledge memory",
                "show research memory",
                "what does atlas know",
                "show learned observations",
                "show stored knowledge",
                "knowledge agent",
            ],
        )


    def _is_current_intelligence_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "show current intelligence",
                "show market intelligence",
                "current intelligence snapshot",
                "latest market intelligence",
                "build market intelligence",
            ],
        )

    def _is_system_state_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "show agent states",
                "show system state",
                "show atlas state",
                "agent status",
                "system status",
                "what are the agents doing",
            ],
        )

    def _is_research_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "run full research cycle",
                "full research cycle",
                "research cycle",
                "monte carlo",
                "montecarlo",
                "walk forward",
                "walk-forward",
                "backtest",
                "robustness test",
                "run research",
                "validate strategy",
                "test strategy",
            ],
        )

    def _is_deployment_command(self, command: str) -> bool:
        return self._contains(
            command,
            [
                "deploy",
                "go live",
                "trade live",
                "live trading",
                "start trading",
                "real money",
                "live mt5",
                "prepare mt5",
                "prepare for mt5",
                "deployment package",
            ],
        )

    # ------------------------------------------------------------------
    # Response formatting

    @staticmethod
    def _format_mission_reconciliation(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "ATLAS MISSION RECONCILIATION FAILED\n\n"
                + str(result.get("message") or "Unknown error.")
            )
        reconciliation = result.get("reconciliation") or {}
        replacement = reconciliation.get("replacement_mission") or {}
        superseded = reconciliation.get("superseded_missions") or []
        lines = [
            "ATLAS MISSION RECONCILIATION",
            "",
            f"Decision: {reconciliation.get('decision', 'UNKNOWN')}",
            f"Latest Brain action: {reconciliation.get('latest_action', 'UNKNOWN')}",
            f"Superseded missions: {len(superseded)}",
        ]
        for mission_id in superseded:
            lines.append(f"- {mission_id}")
        if replacement:
            lines.extend([
                "",
                "Replacement mission:",
                f"- ID: {replacement.get('mission_id')}",
                f"- Type: {replacement.get('mission_type')}",
                f"- Priority: {replacement.get('priority')}",
                f"- Status: {replacement.get('status')}",
            ])
        lines.extend([
            "",
            str(reconciliation.get("message") or "Mission reconciliation completed."),
            "",
            "Live trading allowed: NO",
        ])
        return "\n".join(lines)

    @staticmethod
    def _format_autonomous_cycle(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "ATLAS AUTONOMOUS CYCLE FAILED\n\n"
                + str(result.get("message") or "Unknown error.")
            )

        cycle = result.get("event_cycle") or {}
        events = cycle.get("events") or []
        missions = cycle.get("created_missions") or []
        lines = [
            "ATLAS AUTONOMOUS EVENT CYCLE",
            "",
            f"Detected events: {cycle.get('detected_events', 0)}",
            f"Suppressed events: {cycle.get('suppressed_events', 0)}",
            f"Created missions: {len(missions)}",
            "Live trading allowed: NO",
        ]
        if events:
            lines.extend(["", "Events:"])
            for event in events:
                lines.append(
                    f"- {event.get('severity', 'NORMAL')} | "
                    f"{event.get('event_type', 'UNKNOWN')} | "
                    f"{event.get('status', 'UNKNOWN')}"
                )
        if missions:
            lines.extend(["", "Created missions:"])
            for mission in missions:
                lines.append(
                    f"- {mission.get('mission_id')} | "
                    f"{mission.get('priority')} | "
                    f"{mission.get('mission_type')} | "
                    f"{mission.get('status')}"
                )
            lines.extend(["", "Next command: execute current mission"])
        else:
            lines.extend(["", "No new mission was required."])
        return "\n".join(lines)

    @staticmethod
    def _format_mission_created(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "MISSION CREATION FAILED\n\n"
                f"{result.get('message', 'Unknown error.')}"
            )
        mission = result.get("mission") or {}
        return "\n".join([
            "ATLAS MISSION CREATED",
            "",
            f"Mission ID: {mission.get('mission_id', 'n/a')}",
            f"Type: {mission.get('mission_type', 'n/a')}",
            f"Category: {mission.get('category', 'n/a')}",
            f"Priority: {mission.get('priority', 'n/a')}",
            f"Status: {mission.get('status', 'n/a')}",
            (
                f"Market: {mission.get('symbol', 'n/a')} "
                f"{mission.get('timeframe', '')}"
            ).strip(),
            "",
            f"Goal: {mission.get('goal', 'n/a')}",
            f"Trigger: {mission.get('trigger', 'n/a')}",
            "",
            "Live trading allowed: NO",
            "",
            "Next command: execute current mission",
        ])


    @staticmethod
    def _format_full_intelligence_cycle(result: dict[str, Any]) -> str:
        lines = [
            "ATLAS FULL INTELLIGENCE CYCLE",
            "",
            f"Status: {result.get('status', 'UNKNOWN')}",
            f"Profile: {result.get('profile', 'n/a')}",
            f"Timeframe: {result.get('timeframe', 'n/a')}",
            "",
            "Pipeline:",
        ]
        for step in result.get("steps", []):
            icon = "✓" if step.get("status") == "COMPLETE" else "✗"
            lines.append(
                f"{icon} {step.get('name')}: {step.get('summary')} "
                f"({step.get('duration_seconds', 0):.3f}s)"
            )
            if step.get("error"):
                lines.append(f"  Error: {step['error']}")

        selection = result.get("selection") or {}
        lines.extend(
            [
                "",
                f"Selected market: {selection.get('selected_symbol') or 'NONE'}",
                f"Opportunity score: {selection.get('selected_score', 'n/a')}",
                f"Mission created: {selection.get('mission_id') or 'NO'}",
                "Live trading allowed: NO",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_current_mission(result: dict[str, Any]) -> str:
        mission = result.get("mission")
        if not mission:
            return (
                "ATLAS CURRENT MISSION\n\n"
                "No active or queued mission is available."
            )
        return "\n".join([
            "ATLAS CURRENT MISSION",
            "",
            f"Mission ID: {mission.get('mission_id', 'n/a')}",
            f"Type: {mission.get('mission_type', 'n/a')}",
            f"Priority: {mission.get('priority', 'n/a')}",
            f"Status: {mission.get('status', 'n/a')}",
            f"Goal: {mission.get('goal', 'n/a')}",
            (
                f"Attempts: {mission.get('attempts', 0)}/"
                f"{mission.get('max_attempts', 0)}"
            ),
            f"Plan ID: {mission.get('plan_id', 'n/a')}",
            f"Decision ID: {mission.get('decision_id', 'n/a')}",
            "",
            "Live trading allowed: NO",
        ])

    @staticmethod
    def _format_mission_queue(result: dict[str, Any]) -> str:
        counts = result.get("counts") or {}
        missions = result.get("missions") or []
        lines = [
            "ATLAS MISSION QUEUE",
            "",
            f"Total missions: {len(missions)}",
            "Status counts:",
        ]
        if counts:
            lines.extend(
                f"- {name}: {value}"
                for name, value in sorted(counts.items())
            )
        else:
            lines.append("- No missions stored.")
        if missions:
            lines.extend(["", "Missions:"])
            for mission in missions[:10]:
                lines.append(
                    f"- {mission.get('mission_id')} | "
                    f"{mission.get('priority')} | "
                    f"{mission.get('mission_type')} | "
                    f"{mission.get('status')}"
                )
        lines.extend(["", "Live trading allowed: NO"])
        return "\n".join(lines)

    @staticmethod
    def _format_mission_execution(result: dict[str, Any]) -> str:
        if result.get("status") == "failed":
            return (
                "ATLAS MISSION EXECUTION FAILED\n\n"
                f"{result.get('message', 'Unknown error.')}"
            )
        mission = result.get("mission") or {}
        counts = (
            (result.get("queue_state") or {}).get("counts") or {}
        )
        return "\n".join([
            "ATLAS MISSION EXECUTION",
            "",
            f"Mission ID: {mission.get('mission_id', 'n/a')}",
            f"Mission type: {mission.get('mission_type', 'n/a')}",
            f"Mission status: {mission.get('status', 'n/a')}",
            (
                f"Result status: "
                f"{str(result.get('status', 'unknown')).upper()}"
            ),
            "",
            f"Completed tasks: {counts.get('COMPLETED', 0)}",
            f"Failed tasks: {counts.get('FAILED', 0)}",
            f"Blocked tasks: {counts.get('BLOCKED', 0)}",
            "",
            result.get("message", "Mission execution finished."),
            "",
            "Live trading allowed: NO",
        ])

    @staticmethod
    def _format_brain_evidence(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return result.get(
                "message",
                "No cognitive evidence is available.",
            )

        evidence = result.get("supporting_evidence") or []
        observation = result.get("observation") or {}
        lines = [
            "ATLAS COGNITIVE EVIDENCE",
            "",
            f"Decision ID: {result.get('decision_id')}",
            f"Plan ID: {result.get('plan_id')}",
            f"Chosen action: {result.get('chosen_action')}",
            f"Confidence: {float(result.get('confidence') or 0):.1%}",
            "",
            "Supporting evidence:",
        ]

        if evidence:
            for item in evidence:
                lines.append(
                    f"- [{str(item.get('strength', 'unknown')).upper()}] "
                    f"{item.get('claim', 'Unnamed evidence')}"
                )
                if item.get("source"):
                    lines.append(f"  Source: {item.get('source')}")
                if item.get("value") is not None:
                    lines.append(f"  Value: {item.get('value')}")
        else:
            lines.append("- No supporting evidence items were recorded.")

        market = observation.get("market_intelligence") or {}
        if market:
            lines.extend(
                [
                    "",
                    "Observed market context:",
                    f"- Data quality: {market.get('data_quality', 'unknown')}",
                    f"- Risk environment: {market.get('risk_environment', 'unknown')}",
                    f"- Regime: {market.get('combined_regime', 'unknown')}",
                    f"- Market confidence: "
                    f"{float(market.get('confidence') or 0):.1%}",
                ]
            )
            warnings = market.get("warnings") or []
            if warnings:
                lines.append("- Warnings:")
                for warning in warnings:
                    lines.append(
                        f"  - {warning.get('severity', 'warning')}: "
                        f"{warning.get('message', '')}"
                    )

        lines.extend(["", "Live trading allowed: NO"])
        return "\n".join(lines)

    @staticmethod
    def _format_brain_alternatives(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return result.get(
                "message",
                "No cognitive decision is available.",
            )

        rejected = result.get("rejected_options") or []
        lines = [
            "ATLAS DECISION ALTERNATIVES",
            "",
            f"Decision ID: {result.get('decision_id')}",
            f"Chosen action: {result.get('chosen_action')}",
            "",
            "Rejected alternatives:",
        ]

        if rejected:
            for option in rejected:
                lines.append(
                    f"- {option.get('action', 'UNKNOWN')} "
                    f"(score {float(option.get('score') or 0):.1%})"
                )
                lines.append(
                    f"  Reason: {option.get('rationale') or 'No rationale recorded.'}"
                )
        else:
            lines.append("- No rejected alternatives were recorded.")

        lines.extend(["", "Live trading allowed: NO"])
        return "\n".join(lines)

    @staticmethod
    def _format_brain_explanation(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return result.get("message", "No cognitive decision is available.")
        lines = [
            "ATLAS COGNITIVE EXPLANATION",
            "",
            f"Decision ID: {result.get('decision_id')}",
            f"Plan ID: {result.get('plan_id')}",
            f"Chosen action: {result.get('chosen_action')}",
            f"Confidence: {float(result.get('confidence') or 0):.1%}",
            "",
            "Why:",
            str(result.get("explanation") or "No explanation recorded."),
        ]
        rejected = result.get("rejected_options") or []
        if rejected:
            lines.extend(["", "Rejected alternatives:"])
            for option in rejected:
                lines.append(
                    f"- {option.get('action')}: {option.get('rationale')}"
                )
        restrictions = result.get("restrictions") or []
        if restrictions:
            lines.extend(["", "Restrictions:"])
            lines.extend(f"- {item}" for item in restrictions)
        lines.extend(["", "Live trading allowed: NO"])
        return "\n".join(lines)

    @staticmethod
    def _format_brain_execution(result: dict[str, Any]) -> str:
        if result.get("status") == "failed":
            return f"RESEARCH BRAIN EXECUTION FAILED\n\n{result.get('message', 'Unknown error.')}"

        queue_state = result.get("queue_state") or {}
        counts = queue_state.get("counts") or {}
        tasks = queue_state.get("tasks") or []
        lines = [
            "RESEARCH BRAIN EXECUTION",
            "",
            f"Status: {str(result.get('status', 'unknown')).upper()}",
            f"Completed tasks: {counts.get('COMPLETED', 0)}",
            f"Failed tasks: {counts.get('FAILED', 0)}",
            f"Blocked tasks: {counts.get('BLOCKED', 0)}",
            "Live trading allowed: NO",
            "",
            "Tasks:",
        ]
        for task in tasks:
            lines.append(
                f"- {task.get('task_type')}: {task.get('status')} "
                f"(attempts {task.get('attempts', 0)}/{task.get('max_attempts', 0)})"
            )
            if task.get("error"):
                lines.append(f"  Error: {task.get('error')}")
        lines.extend(["", result.get("message", "Controlled execution completed.")])
        return "\n".join(lines)

    @staticmethod
    def _format_brain_plan(result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return f"Research Brain planning failed: {result.get('message', 'Unknown error.')}"

        plan = result.get("plan") or {}
        goal = plan.get("goal") or {}
        agents = plan.get("required_agents") or []
        restrictions = plan.get("restrictions") or []

        agent_lines = "\n".join(f"- {name}" for name in agents) or "- None"
        restriction_lines = (
            "\n".join(f"- {item}" for item in restrictions)
            or "- No additional restrictions recorded"
        )

        return (
            "RESEARCH BRAIN PLAN\n\n"
            f"Plan ID: {plan.get('plan_id', 'n/a')}\n"
            f"Priority: {str(plan.get('priority', 'unknown')).upper()}\n"
            f"Goal: {goal.get('description', goal.get('goal_id', 'unknown'))}\n"
            f"Recommended action: {plan.get('recommended_action', 'unknown')}\n\n"
            f"Observation:\n{plan.get('observation', 'No observation.')}\n\n"
            f"Reason:\n{plan.get('reason', 'No reason recorded.')}\n\n"
            f"Required agents:\n{agent_lines}\n\n"
            f"Restrictions:\n{restriction_lines}\n\n"
            "Execution mode: PREVIEW ONLY\n"
            "Live trading allowed: NO"
        )

    # ------------------------------------------------------------------


    def _format_adaptive_strategy(self, result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return f"Adaptive strategy workflow failed: {result.get('message', 'unknown error')}"
        selection = result.get("selection", {})
        selected = selection.get("selected_strategy") or {}
        lines = [
            "## Adaptive Strategy Intelligence",
            f"**Action:** {result.get('action', 'UNKNOWN')}",
            f"**Market regime:** {result.get('regime', 'unknown')}",
            f"**Risk environment:** {result.get('risk_environment', 'unknown')}",
        ]
        if selected:
            lines.extend([
                f"**Selected strategy:** {selected.get('strategy_name', 'unknown')}",
                f"**Compatibility:** {float(selected.get('compatibility_score', 0)) * 100:.1f}%",
            ])
        hypothesis = result.get("hypothesis")
        if hypothesis:
            lines.extend([
                "",
                "### Research hypothesis",
                hypothesis.get("hypothesis", ""),
            ])
        lines.extend([
            "",
            result.get("recommendation", ""),
            "",
            "Live deployment remains blocked until all validation stages pass.",
        ])
        return "\n".join(lines)

    def _format_current_intelligence(
        self,
        intelligence: dict[str, Any] | None,
    ) -> str:
        if not intelligence:
            return (
                "## No Market Intelligence Available\n\n"
                "Run `analyze current market` first."
            )
        warnings = intelligence.get("warnings", [])
        warning_lines = [
            f"- `{item.get('severity', 'warning')}`: {item.get('message', '')}"
            for item in warnings
        ] or ["- No active warnings."]
        return "\n".join([
            "## ATLAS Market Intelligence",
            "",
            f"**ID:** `{intelligence.get('intelligence_id', 'n/a')}`",
            f"**Market:** `{intelligence.get('symbol', 'n/a')} {intelligence.get('timeframe', 'n/a')}`",
            f"**Regime:** `{intelligence.get('combined_regime', 'n/a')}`",
            f"**Confidence:** `{float(intelligence.get('confidence', 0)) * 100:.1f}%`",
            "",
            "### Shared Context",
            f"- Direction: `{intelligence.get('direction', 'n/a')}`",
            f"- Trend strength: `{intelligence.get('trend_strength', 'n/a')}`",
            f"- Strategy environment: `{intelligence.get('strategy_environment', 'n/a')}`",
            f"- Risk environment: `{intelligence.get('risk_environment', 'n/a')}`",
            f"- Data quality: `{intelligence.get('data_quality', 'n/a')}`",
            "",
            "### Warnings",
            *warning_lines,
        ])

    def _format_market_analysis(self, result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "## Market Analyst Failed\n\n"
                f"{result.get('message', 'Unknown market-analysis error.')}"
            )

        return "\n".join(
            [
                "## ATLAS Market Analysis Complete",
                "",
                f"**Symbol:** `{result.get('symbol', 'n/a')}`",
                f"**Timeframe:** `{result.get('timeframe', 'n/a')}`",
                f"**Last candle:** `{result.get('last_candle', 'n/a')}`",
                f"**Last close:** `{result.get('last_close', 'n/a')}`",
                "",
                "### Data Status",
                f"- Freshness: `{result.get('freshness_status', 'n/a')}`",
                f"- Data age: `{result.get('data_age_minutes', 'n/a')} minutes`",
                f"- MT5 refresh: `{result.get('mt5_refresh_status', 'n/a')}`",
                "",
                "### Current Regime",
                f"- Trend: `{result.get('trend_regime', 'n/a')}`",
                f"- Volatility: `{result.get('volatility_regime', 'n/a')}`",
                f"- Session: `{result.get('session', 'n/a')}`",
                f"- Confidence: `{result.get('confidence', 'n/a')}%`",
                "",
                "### Intelligence Context",
                f"- Intelligence ID: `{result.get('intelligence_id', 'n/a')}`",
                f"- Strategy environment: `{(result.get('market_intelligence') or {}).get('strategy_environment', 'n/a')}`",
                f"- Risk environment: `{(result.get('market_intelligence') or {}).get('risk_environment', 'n/a')}`",
                "",
                "### Market Analyst",
                result.get("summary", "No market summary was produced."),
            ]
        )

    def _format_regime_analysis(self, result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "## ATLAS Regime Analysis Failed\n\n"
                f"{result.get('message', 'Unknown regime-analysis error.')}"
            )

        latest = result.get("latest_regime", {})
        lines = [
            "## ATLAS Trading Regime Analysis Complete",
            "",
            f"**Trades analyzed:** `{result.get('trades_analyzed', 'n/a')}`",
            "",
            "### Latest Classified Regime",
            f"- Trend: `{latest.get('trend_regime', 'n/a')}`",
            f"- Volatility: `{latest.get('volatility_regime', 'n/a')}`",
            f"- Momentum: `{latest.get('momentum_regime', 'n/a')}`",
            f"- Combined: `{latest.get('combined_regime', 'n/a')}`",
            f"- Confidence: `{latest.get('confidence', 'n/a')}%`",
            "",
            "### Best Historical Regimes",
        ]

        best = result.get("best_regimes", [])
        if best:
            for item in best[:5]:
                lines.append(
                    f"- `{item.get('combined_regime', 'unknown')}` — "
                    f"Trades `{item.get('trades', 'n/a')}`, "
                    f"PF `{self._format_number(item.get('profit_factor'))}`, "
                    f"PnL `{self._format_number(item.get('total_pnl'))}`"
                )
        else:
            lines.append("- No sufficiently supported profitable regimes found.")

        lines.extend(["", "### Worst Historical Regimes"])

        worst = result.get("worst_regimes", [])
        if worst:
            for item in worst[:5]:
                lines.append(
                    f"- `{item.get('combined_regime', 'unknown')}` — "
                    f"Trades `{item.get('trades', 'n/a')}`, "
                    f"PF `{self._format_number(item.get('profit_factor'))}`, "
                    f"PnL `{self._format_number(item.get('total_pnl'))}`"
                )
        else:
            lines.append("- No sufficiently supported weak regimes found.")

        lines.extend(["", "### Interpretation"])

        interpretation = result.get("interpretation", [])
        if interpretation:
            lines.extend(f"- {note}" for note in interpretation)
        else:
            lines.append("- No interpretation was produced.")

        lines.extend(
            [
                "",
                "### Safety",
                (
                    "These are historical associations. Regime-based strategy "
                    "changes must still pass out-of-sample and walk-forward validation."
                ),
            ]
        )

        return "\n".join(lines)

    def _format_strategy_improvement(self, result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "## Strategy Engineer Failed\n\n"
                f"{result.get('message', 'Unknown strategy-engineering error.')}"
            )

        analysis = result.get("analysis", {})
        generated = result.get("generated_strategy", {})
        knowledge = result.get("relevant_knowledge", {})

        return "\n".join(
            [
                "## ATLAS Strategy Engineer Complete",
                "",
                (
                    f"**Analyzed strategy:** "
                    f"`{(analysis.get('strategy') or {}).get('strategy', 'n/a')}`"
                ),
                f"**Trades analyzed:** `{analysis.get('total_trades', 'n/a')}`",
                "",
                "### Weaknesses",
                f"- Weak hours: `{analysis.get('weak_hours', [])}`",
                f"- Weak weekdays: `{analysis.get('weak_weekdays', [])}`",
                "",
                "### Prior ATLAS Knowledge",
                knowledge.get(
                    "summary",
                    "No relevant prior research knowledge was found.",
                ),
                "",
                "### New Candidate",
                f"**Name:** `{generated.get('strategy_name', 'n/a')}`",
                f"**File:** `{generated.get('file_path', 'n/a')}`",
                "",
                "### Next Command",
                "`validate latest generated strategy`",
            ]
        )

    def _format_candidate_validation(
        self,
        validation: dict[str, Any],
        knowledge_result: dict[str, Any],
    ) -> str:
        if validation.get("status") != "complete":
            errors = validation.get("errors") or ["Unknown validation error."]
            return "## Quant Validator Failed\n\n" + "\n".join(
                f"- {error}" for error in errors
            )

        original = validation.get("original_strategy", {})
        candidate = validation.get("candidate_strategy", {})
        original_metrics = original.get("metrics", {})
        candidate_metrics = candidate.get("metrics", {})
        comparison = validation.get("comparison", {})
        verdict = validation.get("verdict", "REVIEW")

        return "\n".join(
            [
                "## ATLAS Quant Validation Complete",
                "",
                f"**Verdict:** `{verdict}`",
                "",
                "### Original",
                f"**Name:** `{original.get('name', 'n/a')}`",
                f"- Trades: `{original_metrics.get('trades', 'n/a')}`",
                f"- Profit Factor: `{original_metrics.get('profit_factor', 'n/a')}`",
                f"- Total PnL: `{original_metrics.get('total_pnl', 'n/a')}`",
                f"- Max Drawdown: `{original_metrics.get('max_drawdown_pct', 'n/a')}`",
                "",
                "### Candidate",
                f"**Name:** `{candidate.get('name', 'n/a')}`",
                f"- Trades: `{candidate_metrics.get('trades', 'n/a')}`",
                f"- Profit Factor: `{candidate_metrics.get('profit_factor', 'n/a')}`",
                f"- Total PnL: `{candidate_metrics.get('total_pnl', 'n/a')}`",
                f"- Max Drawdown: `{candidate_metrics.get('max_drawdown_pct', 'n/a')}`",
                "",
                "### Difference",
                (
                    f"- Profit Factor: "
                    f"`{comparison.get('profit_factor', {}).get('absolute_change', 'n/a')}`"
                ),
                (
                    f"- Total PnL: "
                    f"`{comparison.get('total_pnl', {}).get('absolute_change', 'n/a')}`"
                ),
                (
                    f"- Drawdown: "
                    f"`{comparison.get('max_drawdown_pct', {}).get('absolute_change', 'n/a')}`"
                ),
                "",
                "### Meaning",
                self._candidate_verdict_explanation(verdict),
                "",
                "### Knowledge Agent",
                (
                    f"Stored `{knowledge_result.get('observations_recorded', 0)}` "
                    "new research observation(s)."
                ),
                "",
                "### Safety",
                (
                    "The strategy is not approved for live deployment. Walk-forward, "
                    "Monte Carlo and paper-trading validation remain mandatory."
                ),
            ]
        )

    def _format_tournament(self, result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "## ATLAS Tournament Failed\n\n"
                f"{result.get('message', 'No successful tournament result was produced.')}"
            )

        winner = result.get("winner") or {}
        leaderboard = result.get("leaderboard", [])

        lines = [
            "## ATLAS Variant Tournament Complete",
            "",
            f"**Experiment:** `{result.get('experiment_id', 'n/a')}`",
            f"**Successful variants:** `{result.get('successful_variants', 0)}`",
            "",
            "### Leaderboard",
        ]

        for item in leaderboard[:5]:
            metrics = item.get("metrics", {})
            lines.append(
                f"{item.get('rank', 'n/a')}. `{item.get('slug', 'unknown')}` — "
                f"Score `{item.get('score', 'n/a')}`, "
                f"PF `{self._format_number(metrics.get('profit_factor'))}`, "
                f"PnL `{self._format_number(metrics.get('total_pnl'))}`, "
                f"DD `{self._format_number(metrics.get('max_drawdown_pct'))}%`"
            )

        lines.extend(
            [
                "",
                "### Winner",
                f"**Strategy:** `{winner.get('strategy_name', 'n/a')}`",
                f"**Score:** `{winner.get('score', 'n/a')}`",
                "",
                "### Recommendation",
                result.get("recommendation", "Manual review required."),
                "",
                "### Safety",
                result.get(
                    "safety",
                    "Tournament results are in-sample and are not deployment approval.",
                ),
            ]
        )

        return "\n".join(lines)

    def _format_knowledge_inspection(
        self,
        stats: dict[str, Any],
        knowledge: dict[str, Any],
    ) -> str:
        tag_counts = stats.get("tag_counts", {})
        tag_lines = [
            f"- `{tag}`: {count}"
            for tag, count in list(tag_counts.items())[:10]
        ] or ["- No knowledge tags stored yet."]

        return "\n".join(
            [
                "## ATLAS Knowledge Agent",
                "",
                f"**Stored observations:** `{stats.get('observation_count', 0)}`",
                "",
                "### Most Common Knowledge Tags",
                *tag_lines,
                "",
                "### Relevant Research Knowledge",
                knowledge.get("summary", "No knowledge has been stored yet."),
            ]
        )

    def _format_system_state(self, result: dict[str, Any]) -> str:
        agents = result.get("agents", {})
        lines = [
            "## ATLAS System State",
            "",
            f"**Registered agents:** `{len(agents)}`",
            "",
            "### Agents",
        ]

        for name, state in agents.items():
            lines.append(
                f"- `{name}` — `{state.get('status', 'unknown')}`; "
                f"workflow: `{state.get('last_workflow') or 'none'}`"
            )

        return "\n".join(lines)

    def _format_combined_research(self, result: dict[str, Any]) -> str:
        if result.get("status") != "complete":
            return (
                "## ATLAS Agent Workflow Failed\n\n"
                f"{result.get('message', 'The workflow did not complete.')}"
            )

        market = result.get("market_analysis", {})
        regime = result.get("regime_analysis", {})
        engineering = result.get("strategy_engineering", {})
        validation_wrapper = result.get("candidate_validation", {})
        validation = validation_wrapper.get("validation", validation_wrapper)
        tournament = result.get("tournament") or {}
        generated = engineering.get("generated_strategy", {})
        candidate = validation.get("candidate_strategy", {})
        metrics = candidate.get("metrics", {})
        latest_regime = regime.get("latest_regime", {})

        return "\n".join(
            [
                "## ATLAS Multi-Agent Research Complete",
                "",
                "### Market Analyst",
                f"- Trend: `{market.get('trend_regime', 'n/a')}`",
                f"- Volatility: `{market.get('volatility_regime', 'n/a')}`",
                f"- Freshness: `{market.get('freshness_status', 'n/a')}`",
                "",
                "### Regime Intelligence",
                f"- Combined regime: `{latest_regime.get('combined_regime', 'n/a')}`",
                f"- Confidence: `{latest_regime.get('confidence', 'n/a')}%`",
                "",
                "### Strategy Engineer",
                f"- Candidate: `{generated.get('strategy_name', 'n/a')}`",
                "",
                "### Quant Validator",
                f"- Verdict: `{validation.get('verdict', 'n/a')}`",
                f"- Profit Factor: `{metrics.get('profit_factor', 'n/a')}`",
                f"- Total PnL: `{metrics.get('total_pnl', 'n/a')}`",
                f"- Max Drawdown: `{metrics.get('max_drawdown_pct', 'n/a')}`",
                "",
                "### Tournament",
                f"- Status: `{tournament.get('status', 'not run')}`",
                (
                    f"- Winner: "
                    f"`{(tournament.get('winner') or {}).get('strategy_name', 'n/a')}`"
                ),
                "",
                "### Supervisor Recommendation",
                result.get("recommendation", "Manual review required."),
                "",
                "### Deployment",
                "`BLOCKED` — the complete validation gate has not been passed.",
            ]
        )

    def _format_full_research(
        self,
        report: dict[str, Any],
        safety_message: str,
    ) -> str:
        strategy = report.get("strategy") or {}
        backtest = report.get("backtest") or {}
        monte_carlo = report.get("monte_carlo") or {}
        files = report.get("files") or {}

        return "\n".join(
            [
                "## ATLAS Research Cycle Complete",
                "",
                f"**Strategy:** `{strategy.get('strategy', 'n/a')}`",
                f"**Decision:** `{report.get('decision', 'REVIEW')}`",
                "",
                "### Backtest",
                f"- Trades: `{backtest.get('trades', 'n/a')}`",
                f"- Profit Factor: `{backtest.get('profit_factor', 'n/a')}`",
                f"- Total PnL: `{backtest.get('total_pnl', 'n/a')}`",
                f"- Max Drawdown: `{backtest.get('max_drawdown_pct', 'n/a')}`",
                "",
                "### Monte Carlo",
                (
                    f"- Probability Positive: "
                    f"`{monte_carlo.get('probability_positive', 'n/a')}`"
                ),
                "",
                "### Safety",
                safety_message,
                "",
                "### Files",
                f"- Report: `{files.get('markdown_report', 'n/a')}`",
            ]
        )

    @staticmethod
    def _candidate_verdict_explanation(verdict: str) -> str:
        explanations = {
            "ACCEPT_FOR_WALK_FORWARD": (
                "The candidate may advance to proper out-of-sample and "
                "walk-forward validation."
            ),
            "REVIEW_RISK_IMPROVEMENT": (
                "Risk quality improved, but performance retention is insufficient "
                "for immediate advancement. Less aggressive variants should be tested."
            ),
            "REVIEW": (
                "The evidence is mixed. Additional controlled variants are required."
            ),
            "REJECT": (
                "The candidate should be rejected and the original strategy preserved."
            ),
            "ERROR": "The validation process failed.",
        }
        return explanations.get(verdict, "Manual quantitative review is required.")

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            return f"{float(value):,.3f}"
        except (TypeError, ValueError):
            return "n/a"