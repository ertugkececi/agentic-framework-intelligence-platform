"""Offline framework learning and online LangGraph development workflows."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from agentic_platform.domain.models import (
    CodingContext,
    CommandResult,
    FrameworkRule,
    ValidationReport,
)
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore
from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.models.gateway import CodingModel, DeterministicPythonCodingModel
from agentic_platform.retrieval.context import retrieve_service_context
from agentic_platform.security.policy import poc_grant
from agentic_platform.tasks.parser import TaskParseError, parse_development_task
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange
from agentic_platform.tools.changes import apply_change
from agentic_platform.tools.repository_tools import run_build, run_tests
from agentic_platform.validation.compliance import validate_service


DEFAULT_RETRY_BUDGET = 2
DEFAULT_MAX_FAILURE_OUTPUT = 2_000


@dataclass(frozen=True)
class FailureContext:
    """Compact, bounded evidence passed from a failed check to a repair attempt."""

    stage: str
    attempt: int
    command: tuple[str, ...]
    output: str


class DevelopmentState(TypedDict, total=False):
    workspace: str
    repository: str
    task: str
    specification: DevelopmentTask
    framework_rules: list[FrameworkRule]
    coding_context: CodingContext
    generated_change: GeneratedChange
    generated_files: list[str]
    build_result: CommandResult
    test_result: CommandResult
    validation_report: ValidationReport
    retry_count: int
    retry_budget: int
    failure_context: FailureContext
    failure_history: tuple[FailureContext, ...]
    status: str
    events: list[str]


class FrameworkLearningService:
    """Offline service that learns and persists framework knowledge for a repository."""

    def __init__(self, learner: FrameworkLearner | None = None) -> None:
        self._learner = learner or FrameworkLearner()

    @staticmethod
    def database_path(workspace: Path) -> Path:
        return workspace / "framework_knowledge.sqlite"

    def learn(self, workspace: Path, repository: Path) -> list[FrameworkRule]:
        """Discover rules once and persist them for later online development runs."""
        workspace.mkdir(parents=True, exist_ok=True)
        rules = self._learner.learn(repository)
        store = SQLiteKnowledgeStore(self.database_path(workspace))
        try:
            store.replace_rules(rules)
        finally:
            store.close()
        return rules


class DevelopmentService:
    """Online workflow that retrieves already learned knowledge and develops a task."""

    def __init__(
        self,
        *,
        model_factory: Callable[[], CodingModel] = DeterministicPythonCodingModel,
        build_runner: Callable[[Path, object], CommandResult] = run_build,
        test_runner: Callable[[Path, object], CommandResult] = run_tests,
        validator: Callable[[Path, list[FrameworkRule]], ValidationReport] = validate_service,
        max_failure_output: int = DEFAULT_MAX_FAILURE_OUTPUT,
    ) -> None:
        if max_failure_output < 1:
            raise ValueError("max_failure_output must be positive")
        self._model_factory = model_factory
        self._build_runner = build_runner
        self._test_runner = test_runner
        self._validator = validator
        self._max_failure_output = max_failure_output

    def run(
        self,
        workspace: Path,
        repository: Path,
        task: str = "Create GeneratedService",
        retry_budget: int = DEFAULT_RETRY_BUDGET,
    ) -> DevelopmentState:
        if retry_budget < 0:
            raise ValueError("retry_budget must not be negative")
        return self.build_graph().invoke(
            {
                "workspace": str(workspace),
                "repository": str(repository),
                "task": task,
                "retry_count": 0,
                "retry_budget": retry_budget,
                "failure_history": (),
                "events": [],
                "status": "running",
            }
        )

    def build_graph(self):
        graph = StateGraph(DevelopmentState)
        for name, node in (
            ("parse", self._parse_task),
            ("retrieve", self._retrieve),
            ("generate", self._generate),
            ("repair", self._repair),
            ("apply", self._apply),
            ("build", self._build),
            ("build_failure", self._record_build_failure),
            ("tests", self._tests),
            ("test_failure", self._record_test_failure),
            ("compliance", self._compliance),
            ("compliance_failure", self._record_compliance_failure),
            ("final", self._final),
        ):
            graph.add_node(name, node)

        graph.add_edge(START, "parse")
        graph.add_conditional_edges("parse", self._after_parse, {"retrieve": "retrieve", "final": "final"})
        graph.add_conditional_edges("retrieve", self._after_retrieve, {"generate": "generate", "final": "final"})
        graph.add_edge("generate", "apply")
        graph.add_edge("apply", "build")
        graph.add_conditional_edges("build", self._after_build, {"tests": "tests", "failure": "build_failure"})
        graph.add_conditional_edges("build_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_conditional_edges("tests", self._after_tests, {"compliance": "compliance", "failure": "test_failure"})
        graph.add_conditional_edges("test_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_conditional_edges("compliance", self._after_compliance, {"final": "final", "failure": "compliance_failure"})
        graph.add_conditional_edges("compliance_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_edge("repair", "apply")
        graph.add_edge("final", END)
        return graph.compile()

    @staticmethod
    def _event(state: DevelopmentState, text: str) -> dict[str, list[str]]:
        return {"events": [*state.get("events", []), text]}

    def _parse_task(self, state: DevelopmentState) -> dict[str, object]:
        try:
            return {
                "specification": parse_development_task(state["task"]),
                **self._event(state, "task_parsed"),
            }
        except TaskParseError:
            return {"status": "failed", **self._event(state, "task_unsupported")}

    @staticmethod
    def _after_parse(state: DevelopmentState) -> str:
        return "final" if state.get("status") == "failed" else "retrieve"

    def _retrieve(self, state: DevelopmentState) -> dict[str, object]:
        """Online retrieval only: learning belongs to FrameworkLearningService."""
        database_path = FrameworkLearningService.database_path(Path(state["workspace"]))
        if not database_path.exists():
            return {"status": "failed", **self._event(state, "framework_knowledge_missing")}
        store = SQLiteKnowledgeStore(database_path)
        try:
            rules, context = retrieve_service_context(
                store,
                Path(state["repository"]),
                state["specification"],
            )
        except ValueError:
            return {"status": "failed", **self._event(state, "framework_knowledge_missing")}
        finally:
            store.close()
        return {"framework_rules": rules, "coding_context": context, **self._event(state, "framework_retrieved")}

    @staticmethod
    def _after_retrieve(state: DevelopmentState) -> str:
        return "final" if state.get("status") == "failed" else "generate"

    def _generate(self, state: DevelopmentState) -> dict[str, object]:
        change = self._model_factory().generate_change(state["specification"], state["coding_context"])
        return {"generated_change": change, **self._event(state, "change_generated")}

    def _repair(self, state: DevelopmentState) -> dict[str, object]:
        change = self._model_factory().repair_change(
            state["specification"],
            state["coding_context"],
            state["generated_change"],
            state["failure_context"],
        )
        return {
            "generated_change": change,
            "retry_count": state["retry_count"] + 1,
            **self._event(state, "change_repaired"),
        }

    def _apply(self, state: DevelopmentState) -> dict[str, object]:
        files = apply_change(state["generated_change"], Path(state["repository"]), poc_grant())
        return {"generated_files": files, **self._event(state, "change_applied")}

    def _build(self, state: DevelopmentState) -> dict[str, CommandResult]:
        return {"build_result": self._run_command(self._build_runner, Path(state["repository"]))}

    def _tests(self, state: DevelopmentState) -> dict[str, CommandResult]:
        return {"test_result": self._run_command(self._test_runner, Path(state["repository"]))}

    def _run_command(self, runner: Callable[[Path, object], CommandResult], repository: Path) -> CommandResult:
        try:
            return runner(repository, poc_grant())
        except Exception as error:
            return CommandResult(False, (), f"{type(error).__name__}: {error}")

    def _compliance(self, state: DevelopmentState) -> dict[str, ValidationReport]:
        path = Path(state["repository"]) / state["generated_files"][0]
        try:
            return {"validation_report": self._validator(path, state["framework_rules"])}
        except Exception as error:
            return {"validation_report": ValidationReport(False)}

    @staticmethod
    def _after_build(state: DevelopmentState) -> str:
        return "tests" if state["build_result"].passed else "failure"

    @staticmethod
    def _after_tests(state: DevelopmentState) -> str:
        return "compliance" if state["test_result"].passed else "failure"

    @staticmethod
    def _after_compliance(state: DevelopmentState) -> str:
        return "final" if state["validation_report"].passed else "failure"

    def _record_build_failure(self, state: DevelopmentState) -> dict[str, object]:
        result = state["build_result"]
        return self._record_failure(state, "build", result.command, result.output)

    def _record_test_failure(self, state: DevelopmentState) -> dict[str, object]:
        result = state["test_result"]
        return self._record_failure(state, "tests", result.command, result.output)

    def _record_compliance_failure(self, state: DevelopmentState) -> dict[str, object]:
        report = state["validation_report"]
        output = "; ".join(finding.message for finding in report.findings) or "compliance validation failed"
        return self._record_failure(state, "compliance", (), output)

    def _record_failure(
        self,
        state: DevelopmentState,
        stage: str,
        command: tuple[str, ...],
        output: str,
    ) -> dict[str, object]:
        history = state.get("failure_history", ())
        failure = FailureContext(
            stage=stage,
            attempt=len(history) + 1,
            command=command,
            output=output[: self._max_failure_output],
        )
        history = (*history, failure)
        return {
            "failure_context": failure,
            "failure_history": history,
            **self._event(state, f"{stage}_failed"),
        }

    @staticmethod
    def _after_failure(state: DevelopmentState) -> str:
        # The initial verification is allowed, followed by at most retry_budget repairs.
        if state["retry_count"] >= state["retry_budget"]:
            return "final"
        return "repair"

    def _final(self, state: DevelopmentState) -> dict[str, object]:
        if state.get("status") == "failed" and "specification" not in state:
            return {"status": "failed"}
        if all(state.get(key) and state[key].passed for key in ("build_result", "test_result", "validation_report")):
            return {"status": "succeeded"}
        failure = state.get("failure_context")
        if failure and state["retry_count"] >= state["retry_budget"]:
            return {"status": "failed", **self._event(state, "retry_budget_exhausted")}
        return {"status": "failed"}


def run_framework_learning(workspace: Path, repository: Path) -> list[FrameworkRule]:
    """Public helper for the offline learning phase."""
    return FrameworkLearningService().learn(workspace, repository)


def run_development_task(
    workspace: Path,
    repository: Path,
    task: str = "Create GeneratedService",
    retry_budget: int = DEFAULT_RETRY_BUDGET,
) -> DevelopmentState:
    """Run online development using knowledge learned in an earlier lifecycle phase."""
    return DevelopmentService().run(workspace, repository, task, retry_budget)


def run_poc(
    workspace: Path,
    sample_name: str,
    task: str,
    retry_budget: int = DEFAULT_RETRY_BUDGET,
) -> DevelopmentState:
    repository = workspace / "customer-repo"
    shutil.copytree(Path(__file__).resolve().parents[3] / "examples" / sample_name, repository)
    run_framework_learning(workspace, repository)
    return run_development_task(workspace, repository, task, retry_budget)
