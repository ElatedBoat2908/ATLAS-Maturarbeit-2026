from pathlib import Path
from textwrap import dedent
import json
import subprocess
import sys

import streamlit as st

from atlas.brain.router import AtlasRouter
from atlas.brain.command_engine import CommandEngine
from atlas.ui.theme.css import inject_css
from atlas.ui.components.sidebar import render_sidebar
from atlas.ui.pages.overview import render_overview
from atlas.ui.pages.trade_intelligence import (
    render_trade_intelligence,
)
from atlas.ui.pages.strategies import render_strategies
from atlas.ui.pages.reports import render_reports
from atlas.ui.pages.data import render_data
from atlas.ui.pages.experiments import render_experiments
from atlas.ui.pages.monte_carlo import render_monte_carlo
from atlas.ui.pages.market import render_market
from atlas.ui.pages.agents import render_agents
from atlas.ui.pages.intelligence_center import render_intelligence_center
from atlas.ui.pages.mission_control import render_mission_control
from atlas.ui.pages.market_terminal import render_market_terminal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = PROJECT_ROOT / "atlas" / "memory"


st.set_page_config(
    page_title="ATLAS",
    page_icon="A",
    layout="wide",
)


inject_css()


def load_json(
    path: Path,
):
    if path.exists():
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    return None


def load_text(
    path: Path,
) -> str:
    if path.exists():
        return path.read_text(
            encoding="utf-8"
        )

    return ""


def run_module(
    module_name: str,
):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            module_name,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


project_scan = load_json(
    MEMORY_DIR / "project_scan.json"
)

data_scan = load_json(
    MEMORY_DIR / "data_scan.json"
)

strategy_dashboard = load_json(
    MEMORY_DIR / "strategy_dashboard.json"
)

trade_intelligence = load_json(
    MEMORY_DIR / "trade_intelligence.json"
)

experiments = load_json(
    MEMORY_DIR / "experiments.json"
)

experiment_results = load_json(
    MEMORY_DIR / "experiment_results.json"
)


summary_path = (
    MEMORY_DIR / "project_summary.md"
)

trade_intelligence_path = (
    MEMORY_DIR / "trade_intelligence.md"
)

experiments_path = (
    MEMORY_DIR / "experiments.md"
)

experiment_results_path = (
    MEMORY_DIR / "experiment_results.md"
)


selected_model, page = render_sidebar(
    project_scan=project_scan,
    data_scan=data_scan,
    strategy_dashboard=strategy_dashboard,
    trade_intelligence=trade_intelligence,
    experiments=experiments,
    experiment_results=experiment_results,
    run_module=run_module,
)


if page != "Home":
    st.markdown(
        dedent("""
        <div class="atlas-hero">
            <div class="atlas-title">
                ATLAS
            </div>

            <div class="atlas-subtitle">
                AI Quant Research Platform for strategies,
                experiments, backtests and analysis.
            </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )

    st.divider()


if page == "Home":
    render_overview(
        strategy_dashboard=strategy_dashboard,
        experiments=experiments,
        experiment_results=experiment_results,
    )

elif page == "Chat":
    st.subheader("ATLAS Chat")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    "Hallo Giulio. ATLAS ist bereit. "
                    "Du kannst mich mit echten Research-Kommandos "
                    "beauftragen, zum Beispiel: "
                    "`analyze current market`, "
                    "`improve strategy`, "
                    "`validate latest generated strategy` oder "
                    "`run agent research loop`."
                ),
            }
        ]

    chat_container = st.container(
        height=520
    )

    with chat_container:
        for message in st.session_state.chat_messages:
            with st.chat_message(
                message["role"]
            ):
                st.markdown(
                    message["content"]
                )

    user_input = st.chat_input(
        "Ask ATLAS something..."
    )

    if user_input:
        st.session_state.chat_messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        try:
            command_engine = CommandEngine(
                project_root=PROJECT_ROOT
            )

            if command_engine.can_handle(
                user_input
            ):
                result = command_engine.execute(
                    user_input
                )

                answer = result.get(
                    "message",
                    "ATLAS completed the command but returned no message.",
                )

            else:
                router = AtlasRouter(
                    model=selected_model
                )

                answer = router.process(
                    user_input
                )

                if not answer:
                    answer = (
                        "ATLAS returned an empty response."
                    )

        except Exception as error:
            answer = f"ATLAS error: {error}"

        st.session_state.chat_messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        st.rerun()

elif page == "Agents":
    render_agents(
        project_root=PROJECT_ROOT
    )

elif page == "Intelligence Center":
    render_intelligence_center(
        project_root=PROJECT_ROOT
    )

elif page == "Mission Control":
    render_mission_control(
        project_root=PROJECT_ROOT
    )

elif page == "Market Terminal":
    render_market_terminal(
        project_root=PROJECT_ROOT
    )

elif page == "Market":
    render_market(
        project_root=PROJECT_ROOT
    )

elif page == "Strategies":
    render_strategies(
        strategy_dashboard
    )

elif page == "Research Lab":
    render_experiments(
        experiments=experiments,
        experiment_results=experiment_results,
    )

elif page == "Monte Carlo":
    render_monte_carlo(
        memory_dir=MEMORY_DIR
    )

elif page == "AI Researcher":
    render_trade_intelligence(
        trade_intelligence=trade_intelligence,
        trade_intelligence_path=(
            trade_intelligence_path
        ),
        load_text=load_text,
    )

elif page == "Analytics":
    render_data(
        data_scan
    )

elif page == "Reports":
    render_reports(
        summary_path=summary_path,
        experiments_path=experiments_path,
        experiment_results_path=(
            experiment_results_path
        ),
        trade_intelligence_path=(
            trade_intelligence_path
        ),
        load_text=load_text,
    )