"""Streamlit operations dashboard for the local Aegis foundation."""

from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from docx import Document
from pypdf import PdfReader

from agents.orchestrator import AegisOrchestrator
from databases.setup_databases import COLLECTIONS
from utils.paths import agency_root


st.set_page_config(page_title="Aegis Command Center", page_icon="🛡️", layout="wide")


@st.cache_resource
def get_aegis() -> AegisOrchestrator:
    return AegisOrchestrator()


def safe_call(callback: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return callback(*args, **kwargs)
    except Exception as exc:
        st.error(f"Operation failed safely: {exc}")
        return None


def query_database(aegis: AegisOrchestrator, query: str, parameters: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    try:
        with aegis.database.connection() as connection:
            return connection.execute(query, parameters).fetchall()
    except Exception as exc:
        st.warning(f"Encrypted metrics unavailable: {exc}")
        return []


def knowledge_size(aegis: AegisOrchestrator) -> int:
    total = 0
    for name in COLLECTIONS:
        try:
            total += int(aegis.pipeline._collection(name).count())
        except Exception:
            continue
    return total


def render_sidebar(aegis: AegisOrchestrator) -> None:
    with st.sidebar:
        st.title("🛡️ Aegis")
        status = aegis.report_status()
        state = status["state"]
        st.success(f"Status: {state}") if state == "idle" else st.warning(f"Status: {state}")
        privacy = safe_call(aegis.verify_model_privacy)
        if privacy and privacy.get("verified"):
            st.success("Local model privacy verified")
        else:
            st.error("Model privacy not verified")
        st.caption(f"Model: {aegis.model}")
        st.caption(f"Root: {agency_root()}")
        st.divider()
        st.subheader("Agents")
        if not aegis.agents:
            st.info("No specialist agents registered")
        for agent in aegis.agents.values():
            report = agent.report_status()
            st.write(f"{'🟢' if report['state'] == 'idle' else '🟠'} {agent.name}")
        st.divider()
        st.subheader("Quick commands")
        if st.button("Run security audit", use_container_width=True):
            st.session_state["latest_audit"] = safe_call(aegis.daily_security_audit)
        if st.button("Business review", use_container_width=True):
            st.session_state["business_review"] = safe_call(aegis.business_review)
        if st.button("Detect anomalies", use_container_width=True):
            st.session_state["anomalies"] = safe_call(aegis.detect_anomalies)


def render_overview(aegis: AegisOrchestrator) -> None:
    metrics = query_database(
        aegis,
        """SELECT COUNT(*), COALESCE(SUM(success), 0), COALESCE(SUM(revenue_generated), 0),
        COALESCE(SUM(security_flag), 0) FROM agent_metrics""",
    )
    task_count, successes, revenue, security_flags = metrics[0] if metrics else (0, 0, 0, 0)
    audit = st.session_state.get("latest_audit")
    columns = st.columns(5)
    columns[0].metric("Active agents", 1 + sum(agent.report_status()["state"] == "thinking" for agent in aegis.agents.values()))
    columns[1].metric("Tasks", task_count)
    columns[2].metric("Revenue", f"${float(revenue):,.2f}")
    columns[3].metric("Knowledge entries", knowledge_size(aegis))
    columns[4].metric("Security score", f"{audit.get('security_score', 0):.0f}%" if audit else "Not audited")
    st.subheader("Agent status")
    statuses = [aegis.report_status(), *[agent.report_status() for agent in aegis.agents.values()]]
    st.dataframe(pd.DataFrame(statuses), use_container_width=True, hide_index=True)
    st.subheader("Today's intelligence briefing")
    latest = safe_call(
        aegis.pipeline.retrieve_knowledge,
        "daily AI briefing",
        "ai_industry_intel",
        top_k=1,
        security_clearance="admin",
    )
    if latest:
        st.json(latest[0]["data"])
    else:
        st.info("No briefing generated yet. Online research must be explicitly enabled for a briefing run.")
    st.subheader("Quick actions")
    action, value = st.columns([1, 3])
    mode = action.selectbox("Action", ["Analyze", "Delegate", "Strategy"])
    topic = value.text_input("Topic or goal", key="overview_action_topic")
    if st.button("Run quick action", disabled=not topic):
        callback = {"Analyze": aegis.analyze_with_me, "Delegate": aegis.delegate_task, "Strategy": aegis.strategy_session}[mode]
        result = safe_call(callback, topic)
        if result:
            st.json(result)


def render_agents(aegis: AegisOrchestrator) -> None:
    rows = query_database(
        aegis,
        """SELECT agent_name, COUNT(*), AVG(response_time_ms), SUM(tokens_used),
        100.0 * SUM(success) / COUNT(*), SUM(security_flag) FROM agent_metrics GROUP BY agent_name""",
    )
    frame = pd.DataFrame(rows, columns=["agent", "tasks", "avg_response_ms", "tokens", "success_percent", "security_flags"])
    if not frame.empty:
        first, second = st.columns(2)
        first.plotly_chart(px.bar(frame, x="agent", y="success_percent", title="Task success rate"), use_container_width=True)
        second.plotly_chart(px.bar(frame, x="agent", y="avg_response_ms", title="Average response time"), use_container_width=True)
        st.dataframe(frame, use_container_width=True, hide_index=True)
    else:
        st.info("No agent metrics yet")
    st.subheader("Recent task history")
    task_rows = query_database(
        aegis,
        """SELECT agent_name, task_type, start_time, end_time, tokens_used, success,
        response_time_ms, revenue_generated, security_flag FROM agent_metrics ORDER BY id DESC LIMIT 100""",
    )
    st.dataframe(
        pd.DataFrame(
            task_rows,
            columns=["agent", "task", "started", "ended", "tokens", "success", "response_ms", "revenue", "security_flag"],
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Knowledge collections")
    collection_rows = []
    for name in COLLECTIONS:
        try:
            collection_rows.append({"collection": name, "entries": aegis.pipeline._collection(name).count()})
        except Exception as exc:
            collection_rows.append({"collection": name, "entries": 0, "error": str(exc)})
    st.dataframe(pd.DataFrame(collection_rows), use_container_width=True, hide_index=True)
    st.subheader("Local model assignments")
    model_options = ["llama3.1:8b", "llama3.2:3b"]
    agent_options = ["Aegis", *[agent.name for agent in aegis.agents.values()]]
    selected_agent = st.selectbox("Agent", agent_options)
    selected_model = st.selectbox("Approved local model", model_options)
    if st.button("Apply model assignment"):
        target = aegis if selected_agent == "Aegis" else aegis.agents[selected_agent.lower()]
        target.model = selected_model
        st.success(f"{selected_agent} now uses {selected_model}")


def render_security(aegis: AegisOrchestrator) -> None:
    audit = st.session_state.get("latest_audit")
    if st.button("Run full security audit", type="primary"):
        audit = safe_call(aegis.daily_security_audit)
        st.session_state["latest_audit"] = audit
    if audit:
        score, status, time_col = st.columns(3)
        score.metric("Security score", f"{audit['security_score']:.1f}%")
        status.metric("Critical controls", "PASS" if audit["passed"] else "FAIL")
        time_col.metric("Last audit", audit["timestamp"][:19])
        checks = pd.DataFrame(audit["checks"])
        st.dataframe(checks, use_container_width=True, hide_index=True)
        failures = checks[checks["passed"] == False]  # noqa: E712
        if not failures.empty:
            st.error("Unresolved security controls require attention before production use.")
    else:
        st.warning("No security audit has run in this dashboard session")
    st.subheader("Data access audit")
    access = safe_call(aegis.monitor_data_access, 200) or []
    st.dataframe(pd.DataFrame(access), use_container_width=True, hide_index=True)
    st.subheader("External connection monitor")
    snapshot = safe_call(aegis.monitor.snapshot)
    if snapshot:
        st.dataframe(pd.DataFrame(snapshot.outbound_connections), use_container_width=True, hide_index=True)
    st.subheader("Incident response log")
    incidents = query_database(
        aegis,
        "SELECT timestamp, check_type, result, severity, action_taken, resolved FROM security_audit_log ORDER BY id DESC LIMIT 100",
    )
    st.dataframe(pd.DataFrame(incidents, columns=["timestamp", "check", "result", "severity", "action", "resolved"]), use_container_width=True, hide_index=True)


def render_research(aegis: AegisOrchestrator) -> None:
    offline = os.getenv("AI_AGENCY_OFFLINE_MODE", "true").lower() == "true"
    st.info(f"External research is {'disabled' if offline else 'enabled'} for this process.")
    topic = st.text_input("Public research topic")
    depth = st.select_slider("Depth", ["quick", "standard", "deep"], value="standard")
    if st.button("Start research", disabled=not topic):
        result = safe_call(aegis.research, topic, depth)
        if result:
            st.json(result)
    st.subheader("Active research queue")
    st.caption("Interactive research runs synchronously; scheduled research is managed by run_agency.py.")
    st.dataframe(pd.DataFrame([], columns=["topic", "depth", "status", "started"]), use_container_width=True, hide_index=True)
    st.subheader("Research history")
    research_rows = query_database(
        aegis,
        """SELECT topic, source, date_collected, confidence_score, source_type, security_level
        FROM knowledge_updates WHERE source_type IN ('web_search', 'api_research', 'github_analysis', 'open_source_verified')
        ORDER BY id DESC LIMIT 100""",
    )
    st.dataframe(
        pd.DataFrame(research_rows, columns=["topic", "source", "collected", "confidence", "source_type", "security"]),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Knowledge staleness alerts")
    stale = safe_call(aegis.pipeline.check_staleness) or []
    st.dataframe(pd.DataFrame(stale), use_container_width=True, hide_index=True)
    st.subheader("Competitor tracking")
    competitors = safe_call(aegis.monitor_competitors)
    if competitors:
        st.json(competitors)


def render_open_source(aegis: AegisOrchestrator) -> None:
    repo_url = st.text_input("Public GitHub repository URL", key="oss_repo")
    if st.button("Analyze repository", disabled=not repo_url):
        result = safe_call(aegis.analyze_github_repository, repo_url)
        if result:
            st.json(result)
    rows = query_database(
        aegis,
        """SELECT repo_name, url, category, analyzed_date, implementation_ideas, code_quality_score
        FROM open_source_intel ORDER BY id DESC LIMIT 100""",
    )
    st.subheader("Analyzed repositories")
    st.dataframe(pd.DataFrame(rows, columns=["repository", "url", "category", "analyzed", "implementation_ideas", "quality_score"]), use_container_width=True, hide_index=True)
    st.subheader("Technology radar")
    patterns = safe_call(aegis.pipeline.extract_implementation_patterns)
    if patterns:
        radar = []
        for item in patterns["common_patterns"]:
            occurrences = item["occurrences"]
            radar.append({**item, "recommendation": "adopt" if occurrences >= 3 else "watch" if occurrences >= 1 else "ignore"})
        st.dataframe(pd.DataFrame(radar), use_container_width=True, hide_index=True)


def render_mobile(aegis: AegisOrchestrator) -> None:
    token_enabled = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    allowed_ids = [value for value in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if value.strip().isdigit()]
    first, second = st.columns(2)
    first.metric("Telegram bot", "Configured" if token_enabled else "Disabled")
    second.metric("Whitelisted users", len(allowed_ids))
    sessions = query_database(
        aegis,
        """SELECT user_id, device_info, session_start, session_end, commands_issued, security_verified
        FROM mobile_sessions ORDER BY id DESC LIMIT 100""",
    )
    st.dataframe(pd.DataFrame(sessions, columns=["user_id", "device", "start", "end", "commands", "verified"]), use_container_width=True, hide_index=True)
    st.subheader("Recent mobile commands")
    commands = query_database(
        aegis,
        """SELECT command, timestamp, status, result_summary, security_check FROM aegis_commands
        ORDER BY id DESC LIMIT 100""",
    )
    st.dataframe(
        pd.DataFrame(commands, columns=["command", "timestamp", "status", "result", "security_verified"]),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Command reference")
    st.code("/status\n/etsy [query]\n/review\n/learn [url]\n/security\n/briefing\n/github [url]\n/revenue\n/agents\n/deploy\n/shutdown")


def extract_upload(uploaded: Any) -> str:
    data = uploaded.getvalue()
    suffix = Path(uploaded.name).suffix.lower()
    if len(data) > 20_000_000:
        raise ValueError("Upload exceeds the 20 MB dashboard limit")
    if suffix in {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}:
        return data.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if suffix == ".docx":
        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(data)).paragraphs)
    raise ValueError("Supported uploads: TXT, MD, CSV, JSON, YAML, PDF, DOCX")


def render_chat(aegis: AegisOrchestrator) -> None:
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    for item in st.session_state["chat_history"]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
    prompt = st.chat_input("Talk with Aegis")
    if prompt:
        st.session_state["chat_history"].append({"role": "user", "content": prompt})
        response = safe_call(aegis.think, prompt)
        if response:
            st.session_state["chat_history"].append({"role": "assistant", "content": response})
            st.rerun()
    uploaded = st.file_uploader("Teach Aegis from a local document", type=["txt", "md", "csv", "json", "yaml", "yml", "pdf", "docx"])
    if uploaded and st.button("Learn from uploaded file"):
        text = safe_call(extract_upload, uploaded)
        if text:
            result = safe_call(aegis.pipeline.learn_from_video, text, Path(uploaded.name).stem)
            if result:
                st.success(f"Stored {len(result)} encrypted knowledge segments")
    page_url = st.text_input("Public webpage URL", key="chat_page_url")
    page_topic = st.text_input("Learning topic", key="chat_page_topic")
    if st.button("Analyze webpage", disabled=not (page_url and page_topic)):
        result = safe_call(aegis.learn_from_browsing, page_url, page_topic)
        if result:
            st.json(result)
    if st.download_button(
        "Export conversation",
        data=json.dumps(st.session_state["chat_history"], ensure_ascii=False, indent=2),
        file_name=f"aegis-conversation-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json",
        mime="application/json",
    ):
        st.warning("Conversation exports are plaintext. Store them only in an approved encrypted location.")


def main() -> None:
    st.title("Aegis Command Center")
    st.caption("Local-first AI agency operations, intelligence, and security")
    aegis = get_aegis()
    render_sidebar(aegis)
    tab_names = ["Overview", "Agents", "Security", "Research", "Open Source Intel", "Mobile", "Chat"]
    tabs = st.tabs(tab_names)
    renderers = [render_overview, render_agents, render_security, render_research, render_open_source, render_mobile, render_chat]
    for tab, renderer in zip(tabs, renderers):
        with tab:
            renderer(aegis)
    st.divider()
    with st.expander("Always-available Aegis quick chat", expanded=True):
        quick = st.text_input("Quick message", key="persistent_aegis_chat")
        if st.button("Send to Aegis", disabled=not quick, key="persistent_send"):
            answer = safe_call(aegis.think, quick)
            if answer:
                st.write(answer)


if __name__ == "__main__":
    main()
