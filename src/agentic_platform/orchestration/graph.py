"""Real LangGraph PoC: learn, persist, retrieve, generate, build, test, validate."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agentic_platform.agents.coding import implement_service
from agentic_platform.domain.models import CodingContext, CommandResult, FrameworkRule, ValidationReport
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore
from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.models.gateway import DeterministicPythonCodingModel
from agentic_platform.retrieval.context import retrieve_service_context
from agentic_platform.security.policy import poc_grant
from agentic_platform.tools.repository_tools import run_build, run_tests
from agentic_platform.validation.compliance import validate_service


class DevelopmentState(TypedDict, total=False):
    workspace: str
    repository: str
    task: str
    task_kind: str
    framework_rules: list[FrameworkRule]
    coding_context: CodingContext
    plan: str
    generated_files: list[str]
    build_result: CommandResult
    test_result: CommandResult
    validation_report: ValidationReport
    status: str
    events: list[str]


def _event(state: DevelopmentState, event: str) -> dict[str, Any]:
    return {"events": [*state.get("events", []), event]}


def analyze_task(state: DevelopmentState) -> dict[str, Any]:
    if "service" not in state["task"].lower():
        return {"task_kind": "unknown", "status": "failed", **_event(state, "task_unsupported")}
    return {"task_kind": "service", **_event(state, "task_analyzed:service")}


def learn_and_retrieve(state: DevelopmentState) -> dict[str, Any]:
    repository = Path(state["repository"])
    store = SQLiteKnowledgeStore(Path(state["workspace"]) / "framework_knowledge.sqlite")
    try:
        store.replace_rules(FrameworkLearner(minimum_evidence=3).learn(repository))
        rules, context = retrieve_service_context(store, repository)
    except ValueError as error:
        return {"status": "failed", **_event(state, f"context_unavailable:{error}")}
    finally:
        store.close()
    return {
        "framework_rules": rules,
        "coding_context": context,
        **_event(state, f"context_retrieved:rules={len(rules)} examples={len(context.examples)}"),
    }


def plan_change(state: DevelopmentState) -> dict[str, Any]:
    context = state.get("coding_context")
    if context is None:
        return {"status": "failed", **_event(state, "no_coding_context")}
    return {
        "plan": f"Create CustomerAccountService using {len(context.imports)} learned imports",
        **_event(state, "plan_created"),
    }


def implement_change(state: DevelopmentState) -> dict[str, Any]:
    generated = implement_service(
        Path(state["repository"]), "CustomerAccountService", state["coding_context"],
        DeterministicPythonCodingModel(), poc_grant(),
    )
    return {"generated_files": generated, **_event(state, "implementation_written")}


def build(state: DevelopmentState) -> dict[str, Any]:
    result = run_build(Path(state["repository"]), poc_grant())
    return {"build_result": result, **_event(state, f"build:{result.passed}")}


def tests(state: DevelopmentState) -> dict[str, Any]:
    result = run_tests(Path(state["repository"]), poc_grant())
    return {"test_result": result, **_event(state, f"tests:{result.passed}")}


def compliance(state: DevelopmentState) -> dict[str, Any]:
    report = validate_service(Path(state["repository"]) / "app" / "customer_account_service.py", state["framework_rules"])
    return {"validation_report": report, **_event(state, f"compliance:{report.passed}")}


def finalize(state: DevelopmentState) -> dict[str, Any]:
    succeeded = (
        state.get("status") != "failed"
        and bool(state.get("build_result") and state["build_result"].passed)
        and bool(state.get("test_result") and state["test_result"].passed)
        and bool(state.get("validation_report") and state["validation_report"].passed)
    )
    return {"status": "succeeded" if succeeded else "failed", **_event(state, "finalized")}


def _after_task(state: DevelopmentState) -> str:
    return "learn" if state.get("status") != "failed" else "finalize"


def _after_plan(state: DevelopmentState) -> str:
    return "implement" if state.get("status") != "failed" else "finalize"


def _after_build(state: DevelopmentState) -> str:
    return "tests" if state["build_result"].passed else "finalize"


def _after_tests(state: DevelopmentState) -> str:
    return "compliance" if state["test_result"].passed else "finalize"


def build_graph():
    graph = StateGraph(DevelopmentState)
    graph.add_node("analyze_task", analyze_task)
    graph.add_node("learn", learn_and_retrieve)
    graph.add_node("plan", plan_change)
    graph.add_node("implement", implement_change)
    graph.add_node("build", build)
    graph.add_node("tests", tests)
    graph.add_node("compliance", compliance)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "analyze_task")
    graph.add_conditional_edges("analyze_task", _after_task, {"learn": "learn", "finalize": "finalize"})
    graph.add_edge("learn", "plan")
    graph.add_conditional_edges("plan", _after_plan, {"implement": "implement", "finalize": "finalize"})
    graph.add_edge("implement", "build")
    graph.add_conditional_edges("build", _after_build, {"tests": "tests", "finalize": "finalize"})
    graph.add_conditional_edges("tests", _after_tests, {"compliance": "compliance", "finalize": "finalize"})
    graph.add_edge("compliance", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_development_task(workspace: Path, repository: Path, task: str = "Create CustomerAccountService") -> DevelopmentState:
    initial: DevelopmentState = {
        "workspace": str(workspace), "repository": str(repository), "task": task,
        "events": [], "status": "running",
    }
    return build_graph().invoke(initial)


def run_poc(workspace: Path, sample_name: str = "sample_customer_repo") -> DevelopmentState:
    """Copy a selected real customer repository and execute the complete graph."""
    root = Path(__file__).resolve().parents[3]
    repository = workspace / "customer-repo"
    shutil.copytree(root / "examples" / sample_name, repository)
    return run_development_task(workspace, repository)
