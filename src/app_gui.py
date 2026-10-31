"""Streamlit GUI for Personal Task Automation Agent.

Provides a user-friendly interface for:
- Task execution with natural language commands
- Resume upload and analysis
- Job matching based on resume
- Execution history tracking
"""
try:
    import streamlit as st
except ImportError:
    print("Streamlit not installed. Please run: pip install streamlit")
    exit(1)

import os
import sys
import base64
from datetime import datetime
from typing import Optional

import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config import load_config
from src.agent.tool_registry import default_tool_registry
from src.ui.components import render_empty_state, render_event_stream, render_metric, render_page_header
from src.ui.theme import apply_theme


# Page configuration
st.set_page_config(
    page_title="AURA | Autonomous task execution",
    layout="wide"
)
apply_theme()

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []
if "resume_analysis" not in st.session_state:
    st.session_state.resume_analysis = None
if "job_results" not in st.session_state:
    st.session_state.job_results = None


def get_planner_mode():
    """Get the current planner mode from config."""
    cfg = load_config()
    return cfg.get("PLANNER_MODE", "rule")


def get_api_url() -> str:
    return os.getenv("AURA_API_URL", "http://127.0.0.1:8000").rstrip("/")


def execute_command_async(command: str, email: Optional[str] = None):
    """Execute a goal through the FastAPI backend."""
    try:
        cfg = load_config()
        planner_mode = get_planner_mode()

        api_url = get_api_url()
        response = requests.post(
            f"{api_url}/run",
            json={"goal": command, "email": email, "planner": planner_mode},
            timeout=120,
        )
        response.raise_for_status()
        record = response.json()
        record["success"] = record.get("status") == "completed"
        return record
    except requests.RequestException as error:
        return {
            "success": False,
            "error": f"AURA backend unavailable: {error}",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


def main():
    render_page_header(
        "AURA / CONTROL CENTER",
        "What can AURA take care of?",
        "Describe the outcome you want. AURA will plan the steps, do the work, and show you what happened.",
    )
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Start", "Resume", "History", "Capabilities", "Insights"]
    )
    
    # ========== Tab 1: Task Execution ==========
    with tab1:
        st.subheader("Tell AURA what you need")
        st.caption("Use plain language. Include the result you want, not the steps to get there.")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            command = st.text_area(
                "Your goal",
                placeholder="e.g., Compare the latest AI agent frameworks and summarize the differences",
                height=100,
                key="task_command"
            )
        with col2:
            email = st.text_input(
                "Send result to (optional)",
                placeholder="your@email.com",
                key="task_email"
            )
        
        if st.button("Run with AURA", type="primary", use_container_width=True):
            if not command.strip():
                st.error("Please enter a command")
            else:
                with st.spinner("Executing task..."):
                    result = execute_command_async(command, email if email.strip() else None)
                    
                    if result["success"]:
                        st.success("AURA finished this goal")

                        metrics = st.columns(3)
                        with metrics[0]:
                            render_metric("Tasks", str(len(result["plan"].get("steps", []))))
                        with metrics[1]:
                            render_metric("Events", str(len(result.get("events", []))))
                        with metrics[2]:
                            render_metric("Run ID", result.get("run_id", "-")[:8])
                        
                        with st.expander("Plan details"):
                            st.json(result["plan"])
                        
                        with st.expander("Execution log"):
                            for log in result["logs"]:
                                st.text(log)
                        with st.expander("Live event stream", expanded=True):
                            render_event_stream(result.get("events", []))
                    else:
                        st.error(f"Task failed: {result['error']}")
    
    # ========== Tab 2: Resume Analysis ==========
    with tab2:
        st.header("Resume Analysis & Job Matching")
        st.markdown("Upload your resume to get AI-powered analysis and find matching jobs.")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Upload resume")
            uploaded_file = st.file_uploader(
                "Choose a file",
                type=["pdf", "docx", "txt"],
                help="Supported formats: PDF, DOCX, TXT"
            )
            
            if uploaded_file:
                st.success(f"Uploaded: {uploaded_file.name}")
                
                if st.button("Analyze resume", type="primary", use_container_width=True):
                    with st.spinner("Analyzing resume..."):
                        try:
                            response = requests.post(
                                f"{get_api_url()}/resume/analyze",
                                json={
                                    "file_name": uploaded_file.name,
                                    "content_base64": base64.b64encode(
                                        uploaded_file.getvalue()
                                    ).decode("ascii"),
                                },
                                timeout=120,
                            )
                            response.raise_for_status()
                            analyzed = response.json()
                            st.session_state.resume_analysis = {
                                "parse": analyzed["parsed"],
                                "analysis": analyzed["analysis"],
                                "file_name": analyzed["file_name"],
                            }
                            st.success("Resume analyzed by AURA backend")
                        except requests.RequestException as error:
                            st.error(f"AURA backend unavailable: {error}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
        
        with col2:
            st.subheader("Analysis results")
            
            if st.session_state.resume_analysis:
                analysis = st.session_state.resume_analysis["analysis"]
                
                st.markdown("**Candidate Information:**")
                if analysis.get("name"):
                    st.info(f"**Name:** {analysis['name']}")
                
                if analysis.get("field_of_study"):
                    st.info(f"**Field:** {analysis['field_of_study']}")
                
                exp_years = analysis.get("years_experience") or analysis.get("experience_years")
                if exp_years:
                    st.info(f"**Experience:** {exp_years}" if "year" in str(exp_years).lower() else f"**Experience:** {exp_years} years")
                
                if analysis.get("skills"):
                    st.markdown("**Skills:**")
                    st.write(", ".join(analysis["skills"]))
                
                if analysis.get("career_interests"):
                    st.markdown("**Career Interests:**")
                    st.write(", ".join(analysis["career_interests"]))
                
                # Job search section
                st.markdown("---")
                st.subheader("Find matching jobs")
                
                location = st.text_input("Location", value="remote", key="job_location")
                num_results = st.slider("Number of results", 5, 20, 10, key="job_limit")
                
                if st.button("Search jobs", type="primary", use_container_width=True):
                    with st.spinner("Searching for jobs..."):
                        try:
                            response = requests.post(
                                f"{get_api_url()}/resume/match",
                                json={
                                    "analysis": analysis,
                                    "location": location,
                                    "limit": num_results,
                                },
                                timeout=120,
                            )
                            response.raise_for_status()
                            st.session_state.job_results = response.json()
                            st.success(
                                f"Found {len(st.session_state.job_results['job_matches'])} results"
                            )
                        except requests.RequestException as error:
                            st.error(f"AURA backend unavailable: {error}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            else:
                render_empty_state(
                    "Your analysis will appear here",
                    "Upload a resume to see results.",
                )
        
        # Display job results
        if st.session_state.job_results:
            st.markdown("---")
            st.subheader("Job matches")
            
            jobs = st.session_state.job_results["job_matches"]
            query = st.session_state.job_results.get("search_query", "")
            
            st.info(f"**Search Query:** {query}")
            
            for i, job in enumerate(jobs, 1):
                with st.expander(f"{i}. {job['title']} ({job['relevance']} relevance)"):
                    st.markdown(f"**URL:** [{job['url']}]({job['url']})")
                    st.markdown(f"**Description:** {job['snippet']}")
                    if job.get("matched_skills"):
                        st.markdown(f"**Matched Skills:** {', '.join(job['matched_skills'])}")
    
    # ========== Tab 3: History ==========
    with tab3:
        st.header("Execution History")
        api_url = get_api_url()
        try:
            history_response = requests.get(f"{api_url}/runs", timeout=10)
            history_response.raise_for_status()
            runs = history_response.json().get("runs", [])
        except requests.RequestException as error:
            st.error(f"AURA backend unavailable: {error}")
            runs = []

        if not runs:
            st.info("No persisted execution history yet. Start by executing a task.")
        else:
            st.markdown(f"**Persisted Executions:** {len(runs)}")
            for index, run in enumerate(runs, 1):
                with st.expander(
                    f"{index}. {run.get('goal', 'Unnamed run')} - {run.get('status', 'unknown').upper()}"
                ):
                    st.write(f"Run ID: {run.get('run_id', '-')}")
                    st.write(f"Created: {run.get('created_at', '-')}")
                    if run.get("error"):
                        st.error(run["error"])
                    if run.get("plan"):
                        st.json(run["plan"])
                    render_event_stream(run.get("events", []))

    # ========== Tab 4: Tools ===============
    with tab4:
        render_page_header(
            "AURA / CAPABILITIES",
            "Registered tools",
            "These are the capabilities currently available to the controller.",
        )
        tool_registry = default_tool_registry(use_enhanced=True)
        for tool in tool_registry.describe():
            with st.container(border=True):
                details = st.columns([2, 4, 1])
                with details[0]:
                    st.markdown(f"**{tool.name}**")
                    st.caption(tool.risk_level.upper())
                with details[1]:
                    st.write(tool.description)
                    st.caption(f"Timeout: {tool.timeout_seconds}s | Retries: {tool.max_retries}")
                with details[2]:
                    st.success("AVAILABLE")

    # ========== Tab 5: Evaluation ===============
    with tab5:
        render_page_header(
            "AURA / EVALUATION",
            "Execution metrics",
            "Metrics calculated from persisted runs only.",
        )
        try:
            evaluation_response = requests.get(f"{get_api_url()}/evaluation", timeout=10)
            evaluation_response.raise_for_status()
            evaluation = evaluation_response.json()
        except requests.RequestException as error:
            st.error(f"AURA backend unavailable: {error}")
            evaluation = None

        if evaluation is not None:
            metric_columns = st.columns(4)
            with metric_columns[0]:
                render_metric("Runs", str(evaluation["total_runs"]))
            with metric_columns[1]:
                render_metric("Success rate", f"{evaluation['success_rate']:.0%}")
            with metric_columns[2]:
                render_metric("Recovery rate", f"{evaluation['recovery_rate']:.0%}")
            with metric_columns[3]:
                render_metric("Verification", f"{evaluation['verification_coverage']:.0%}")

            if not evaluation["total_runs"]:
                st.info("Run tasks to generate evaluation metrics.")
            else:
                st.subheader("Planner comparison")
                for planner_name, planner_metrics in evaluation["planner_comparison"].items():
                    planner_columns = st.columns(2)
                    with planner_columns[0]:
                        st.markdown(f"**{planner_name.upper()} planner**")
                    with planner_columns[1]:
                        st.write(
                            f"{planner_metrics['runs']} runs · "
                            f"{planner_metrics['success_rate']:.0%} successful"
                        )
                st.subheader("Failure categories")
                if evaluation["failure_categories"]:
                    for category, count in evaluation["failure_categories"].items():
                        st.write(f"{category.replace('_', ' ').capitalize()}: {count}")
                else:
                    st.success("No failures recorded")


if __name__ == "__main__":
    main()
