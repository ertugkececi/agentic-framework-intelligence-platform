"""Real LangGraph PoC: learn, persist, retrieve, generate, build, test, validate."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agentic_platform.agents.coding import implement_service
from agentic_platform.domain.models import CommandResult, FrameworkRule, ValidationReport
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
    examples: list[str]
    dependency_paths: list[str]
    plan: str
    generated_files: list[str]
    build_result: CommandResult
    test_result: CommandResult
    validation_report: ValidationReport
    retry_count: int
    retry_budget: int
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
        rules, examples, dependencies = retrieve_service_context(store, repository)
    finally:
        store.close()
    return {
        "framework_rules": rules,
        "examples": examples,
        "dependency_paths": dependencies,
        **_event(state, f"context_retrieved:rules={len(rules)} examples={len(examples)}"),
    }


def plan_change(state: DevelopmentState) -> dict[str, Any]:
    if not state.get("framework_rules"):
        return {"status": "failed", **_event(state, "no_active_framework_rules")}
    rules = ", ".join(f"{r.kind}={r.expected_value}" for r in state["framework_rules"])
    return {"plan": f"Create CustomerAccountService constrained by: {rules}", **_event(state, "plan_created")}


def implement_change(state: DevelopmentState) -> dict[str, Any]:
    generated = implement_service(
        Path(state["repository"]), "CustomerAccountService", state["plan"],
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
    succeeded = state["build_result"].passed and state["test_result"].passed and state["validation_report"].passed
    return {"status": "succeeded" if succeeded else "failed", **_event(state, "finalized")}


def _after_task(state: DevelopmentState) -> str:
    return "learn" if state.get("status") != "failed" else "finalize"


def _after_build(state: DevelopmentState) -> str:
    return "tests" if state["build_result"].passed else "finalize"


def _after_tests(state: DevelopmentState) -> str:
    return "compliance" if state["test_result"].passed else "finalize"


def _after_compliance(state: DevelopmentState) -> str:
    return "finalize"


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
    graph.add_edge("plan", "implement")
    graph.add_edge("implement", "build")
    graph.add_conditional_edges("build", _after_build, {"tests": "tests", "finalize": "finalize"})
    graph.add_conditional_edges("tests", _after_tests, {"compliance": "compliance", "finalize": "finalize"})
    graph.add_conditional_edges("compliance", _after_compliance, {"finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


def run_poc(workspace: Path) -> DevelopmentState:
    """Copy a real sample customer repository and execute the complete graph."""
    root = Path(__file__).resolve().parents[3]
    repository = workspace / "customer-repo"
    shutil.copytree(root / "examples" / "sample_customer_repo", repository)
    initial: DevelopmentState = {
        "workspace": str(workspace), "repository": str(repository),
        "task": "Create CustomerAccountService", "retry_count": 0, "retry_budget": 2,
        "events": [], "status": "running",
    }
    return build_graph().invoke(initial)
