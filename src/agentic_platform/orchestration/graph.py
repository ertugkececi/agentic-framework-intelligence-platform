"""Offline framework learning and safe online LangGraph development workflows."""
from __future__ import annotations

import re
import shutil
import uuid
from functools import partial
from pathlib import Path
from typing import Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agentic_platform.agents.development import (
    ChangePlan, ChangePlanner, ChangeReview, ChangeReviewer,
    DeterministicChangePlanner, DeterministicChangeReviewer,
    HumanApprovalDecision, HumanApprovalPolicy, HumanApprovalRequest,
    NoHumanApprovalRequired,
)
from agentic_platform.domain.models import CodingContext, CommandResult, FrameworkRule, ValidationFinding, ValidationReport
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore, repository_fingerprint
from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.framework_learning.inventory import RepositoryRevision, RepositoryScanner
from agentic_platform.models.gateway import CodingModel, CodingModelError, DeterministicPythonCodingModel, FailureContext
from agentic_platform.retrieval.context import (
    UnsupportedInvocationRequirementError,
    retrieve_artifact_structure,
    retrieve_controller_context,
    retrieve_service_context,
)
from agentic_platform.orchestration.run_records import DevelopmentRunRecord, DevelopmentRunRecordStore
from agentic_platform.security.sandbox import StagingSandbox
from agentic_platform.security.policy import (
    Capability,
    CapabilityGrant,
    _StagingAuthorization,
    _create_staging_authorization,
    _register_staging_copy,
    _revoke_staging_authorization,
    poc_grant,
)
from agentic_platform.tasks.parser import TaskParseError, parse_development_task
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange
from agentic_platform.tools.changes import ChangeValidationError, apply_change
from agentic_platform.tools.repository_tools import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_MAX_COMMAND_OUTPUT,
    run_build,
    run_tests,
)
from agentic_platform.validation.compliance import validate_service

DEFAULT_RETRY_BUDGET = 2
DEFAULT_MAX_FAILURE_OUTPUT = 2_000
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*[=:]\s*)([^\s,;]+)",
)
_SECRET_JSON_ASSIGNMENT = re.compile(
    r'(?i)(")([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)("\s*:\s*)(")(?:\\.|[^"\\])*(")',
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(r"(?i)\bhttps?://[^\s/@:]+:[^\s/@]+@"),
)


class DevelopmentState(TypedDict, total=False):
    run_id: str
    repository_revision: str
    model_identity: str
    run_record_identity: str
    workspace: str
    repository: str
    staging_repository: str
    staging_authorization: _StagingAuthorization
    grant: CapabilityGrant
    task: str
    specification: DevelopmentTask
    framework_rules: list[FrameworkRule]
    coding_context: CodingContext
    plan: ChangePlan
    approval_required: bool
    approval_request: HumanApprovalRequest
    approval_decision: HumanApprovalDecision
    generated_change: GeneratedChange
    review: ChangeReview
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
        workspace.mkdir(parents=True, exist_ok=True)
        result = self._learner.learn(repository)
        store = SQLiteKnowledgeStore(self.database_path(workspace))
        try:
            store.replace_rules(result.rules, repository_fingerprint(repository))
        finally:
            store.close()
        return result.rules


class DevelopmentService:
    """Generate and verify in a disposable copy, then atomically publish new files only."""

    def __init__(
        self,
        *,
        model_factory: Callable[[], CodingModel] = DeterministicPythonCodingModel,
        planner_factory: Callable[[], ChangePlanner] = DeterministicChangePlanner,
        reviewer_factory: Callable[[], ChangeReviewer] = DeterministicChangeReviewer,
        approval_policy_factory: Callable[[], HumanApprovalPolicy] = NoHumanApprovalRequired,
        build_runner: Callable[[Path, CapabilityGrant], CommandResult] | None = None,
        test_runner: Callable[[Path, CapabilityGrant], CommandResult] | None = None,
        validator: Callable[[Path, list[FrameworkRule]], ValidationReport] = validate_service,
        max_failure_output: int = DEFAULT_MAX_FAILURE_OUTPUT,
        command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        max_command_output: int = DEFAULT_MAX_COMMAND_OUTPUT,
    ) -> None:
        if max_failure_output < 1 or command_timeout_seconds <= 0 or max_command_output < 1:
            raise ValueError("failure output, command timeout, and command output limits must be positive")
        self._model_factory = model_factory
        self._planner_factory = planner_factory
        self._reviewer_factory = reviewer_factory
        self._approval_policy_factory = approval_policy_factory
        self._model: CodingModel | None = None
        self._planner: ChangePlanner | None = None
        self._reviewer: ChangeReviewer | None = None
        self._approval_policy: HumanApprovalPolicy | None = None
        self._run_grant: CapabilityGrant | None = None
        self._staging_authorization: _StagingAuthorization | None = None
        self._build_runner = build_runner
        self._test_runner = test_runner
        self._validator = validator
        self._max_failure_output = max_failure_output
        self._command_timeout_seconds = command_timeout_seconds
        self._max_command_output = max_command_output

    @staticmethod
    def checkpoint_database_path(workspace: Path) -> Path:
        return workspace.resolve() / "development_checkpoints.sqlite"

    @staticmethod
    def run_record_database_path(workspace: Path) -> Path:
        return workspace.resolve() / "development_run_records.sqlite"

    def run(
        self,
        workspace: Path,
        repository: Path,
        task: str = "Create GeneratedService",
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        *,
        run_id: str | None = None,
        grant: CapabilityGrant | None = None,
    ) -> DevelopmentState:
        """Run against a staging copy only with a caller-supplied capability grant."""
        if retry_budget < 0:
            raise ValueError("retry_budget must not be negative")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        run_id = run_id or uuid.uuid4().hex
        repository = repository.resolve()
        if not isinstance(grant, CapabilityGrant):
            return {"repository": str(repository), "task": task, "status": "failed", "events": ["capability_grant_required"]}
        denied = self._preflight(grant, repository)
        if denied:
            return {"repository": str(repository), "task": task, "status": "failed", "events": [denied]}
        repository_revision = RepositoryRevision.from_inventory(RepositoryScanner().scan(repository)).value
        factory_type = type(self._model_factory)
        model_identity = (
            f"{getattr(self._model_factory, '__module__', factory_type.__module__)}."
            f"{getattr(self._model_factory, '__qualname__', factory_type.__qualname__)}"
        )
        if self._empty_task_requires_invocation(workspace, repository, task):
            return {
                "repository": str(repository),
                "task": task,
                "status": "failed",
                "events": ["required_invocation_operation_missing"],
            }
        sandbox: StagingSandbox | None = None
        stage = workspace.resolve() / ".development-staging" / uuid.uuid4().hex
        staging_authorization: _StagingAuthorization | None = None
        preserve_stage = False
        self._model = None
        self._planner = None
        self._reviewer = None
        self._approval_policy = None
        self._run_grant = grant
        try:
            sandbox = StagingSandbox.create(workspace, repository, stage.name)
            stage = sandbox.path
            lifecycle = _register_staging_copy(workspace, repository, stage)
            staging_authorization = _create_staging_authorization(grant, repository, stage, lifecycle)
            self._staging_authorization = staging_authorization
            checkpoint_path = self.checkpoint_database_path(workspace)
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                result = self.build_graph(checkpointer=checkpointer).invoke(
                    {
                        "run_id": run_id, "repository_revision": repository_revision,
                        "model_identity": model_identity,
                        "workspace": str(workspace.resolve()), "repository": str(repository),
                        "staging_repository": str(stage), "task": task,
                        "retry_count": 0, "retry_budget": retry_budget, "failure_history": (),
                        "events": [], "status": "running",
                    },
                    {
                        "configurable": {"thread_id": run_id},
                        "recursion_limit": 12 + 8 * (retry_budget + 1),
                    },
                )
                result["grant"] = grant
                result["staging_authorization"] = staging_authorization
                self._persist_run_record(workspace, result)
                preserve_stage = result.get("status") == "needs_human_review"
                return result
        finally:
            self._model = None
            self._planner = None
            self._reviewer = None
            self._approval_policy = None
            self._run_grant = None
            self._staging_authorization = None
            _revoke_staging_authorization(staging_authorization)
            if not preserve_stage and sandbox is not None:
                sandbox.remove()

    def resume(
        self,
        workspace: Path,
        repository: Path,
        run_id: str,
        decision: HumanApprovalDecision,
        *,
        grant: CapabilityGrant | None = None,
    ) -> DevelopmentState:
        """Resume one persisted approval interrupt with fresh runtime authority."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(decision, HumanApprovalDecision):
            raise ValueError("a typed human approval decision is required")
        workspace = workspace.resolve()
        repository = repository.resolve()
        if not isinstance(grant, CapabilityGrant):
            return {"repository": str(repository), "status": "failed", "events": ["capability_grant_required"]}
        denied = self._preflight(grant, repository)
        if denied:
            return {"repository": str(repository), "status": "failed", "events": [denied]}

        checkpoint_path = self.checkpoint_database_path(workspace)
        if not checkpoint_path.is_file():
            return {"repository": str(repository), "status": "failed", "events": ["approval_resume_not_found"]}
        config = {"configurable": {"thread_id": run_id}}
        staging_authorization: _StagingAuthorization | None = None
        stage: Path | None = None
        sandbox: StagingSandbox | None = None
        preserve_stage = False
        self._model = None
        self._planner = None
        self._reviewer = None
        self._approval_policy = None
        self._run_grant = grant
        try:
            with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                graph = self.build_graph(checkpointer=checkpointer)
                state = graph.get_state(config).values
                current_revision = RepositoryRevision.from_inventory(RepositoryScanner().scan(repository)).value
                if (
                    state.get("run_id") != run_id
                    or state.get("repository_revision") != current_revision
                    or state.get("workspace") != str(workspace)
                    or state.get("repository") != str(repository)
                    or state.get("status") != "needs_human_review"
                ):
                    return {"repository": str(repository), "status": "failed", "events": ["approval_resume_invalid"]}
                stage = Path(state["staging_repository"]).resolve()
                staging_parent = workspace / ".development-staging"
                if stage.parent != staging_parent or not stage.is_dir():
                    return {"repository": str(repository), "status": "failed", "events": ["approval_staging_missing"]}
                sandbox = StagingSandbox.attach(workspace, repository, stage)
                lifecycle = _register_staging_copy(workspace, repository, stage)
                staging_authorization = _create_staging_authorization(grant, repository, stage, lifecycle)
                self._staging_authorization = staging_authorization
                result = graph.invoke(
                    Command(resume={
                        "approved": decision.approved,
                        "actor": decision.actor,
                        "reason": self._redact(decision.reason),
                    }),
                    {**config, "recursion_limit": 12 + 8 * (state["retry_budget"] + 1)},
                )
                result["grant"] = grant
                result["staging_authorization"] = staging_authorization
                self._persist_run_record(workspace, result)
                preserve_stage = result.get("status") == "needs_human_review"
                return result
        finally:
            self._model = None
            self._planner = None
            self._reviewer = None
            self._approval_policy = None
            self._run_grant = None
            self._staging_authorization = None
            _revoke_staging_authorization(staging_authorization)
            if sandbox is not None and not preserve_stage:
                sandbox.remove()

    def _persist_run_record(self, workspace: Path, result: DevelopmentState) -> None:
        record = DevelopmentRunRecord.capture(
            run_id=result["run_id"], repository_revision=result["repository_revision"],
            task=result["task"], model_identity=result["model_identity"],
            retry_budget=result["retry_budget"], rules=result.get("framework_rules", []),
            change=result.get("generated_change"), status=result["status"],
        )
        store = DevelopmentRunRecordStore(self.run_record_database_path(workspace))
        try:
            store.save(record)
        finally:
            store.close()
        result["run_record_identity"] = record.identity

    @staticmethod
    def _remove_staging_copy(stage: Path) -> None:
        shutil.rmtree(stage, ignore_errors=True)
        parent = stage.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    @staticmethod
    def _preflight(grant: CapabilityGrant, repository: Path) -> str | None:
        try:
            grant.require_repository(repository)
            for capability in (
                Capability.READ_REPOSITORY,
                Capability.WRITE_REPOSITORY,
                Capability.RUN_BUILD,
                Capability.RUN_TEST,
                Capability.STATIC_ANALYSIS,
            ):
                grant.require(capability)
        except PermissionError as error:
            return "capability_repository_mismatch" if "mismatch" in str(error) else "capability_denied"
        return None

    @staticmethod
    def _empty_task_requires_invocation(workspace: Path, repository: Path, task: str) -> bool:
        """Reject invocation-less tasks before creating a disposable staging copy."""
        try:
            specification = parse_development_task(task)
        except TaskParseError:
            return False
        if specification.operations:
            return False
        database_path = FrameworkLearningService.database_path(workspace)
        if not database_path.exists():
            return False
        store = SQLiteKnowledgeStore(database_path)
        try:
            if store.repository_fingerprint() != repository_fingerprint(repository):
                return False
            if specification.artifact_type == "controller":
                _, context = retrieve_controller_context(store, repository, specification)
            else:
                _, context = retrieve_service_context(store, repository, specification)
        except (UnsupportedInvocationRequirementError, ValueError):
            return False
        finally:
            store.close()
        return any(
            requirement.supported
            for dependency in context.dependencies
            for requirement in dependency.required_invocations
        )

    def build_graph(self, *, checkpointer=None):
        graph = StateGraph(DevelopmentState)
        for name, node in (
            ("parse", self._parse_task), ("retrieve", self._retrieve), ("plan", self._plan),
            ("approval_request", self._request_approval), ("approval", self._approval),
            ("generate", self._generate),
            ("repair", self._repair), ("apply", self._apply), ("build", self._build),
            ("build_failure", self._record_build_failure), ("tests", self._tests),
            ("test_failure", self._record_test_failure), ("compliance", self._compliance),
            ("compliance_failure", self._record_compliance_failure), ("review", self._review),
            ("review_failure", self._record_review_failure), ("publish", self._publish), ("final", self._final),
        ):
            graph.add_node(name, node)
        graph.add_edge(START, "parse")
        graph.add_conditional_edges("parse", self._after_parse, {"retrieve": "retrieve", "final": "final"})
        graph.add_conditional_edges("retrieve", self._after_retrieve, {"plan": "plan", "final": "final"})
        graph.add_conditional_edges("plan", self._after_plan, {"approval_request": "approval_request", "generate": "generate", "final": "final"})
        graph.add_edge("approval_request", "approval")
        graph.add_conditional_edges("approval", self._after_approval, {"generate": "generate", "final": "final"})
        graph.add_conditional_edges("generate", self._after_model, {"apply": "apply", "final": "final"})
        graph.add_conditional_edges("apply", self._after_apply, {"build": "build", "final": "final"})
        graph.add_conditional_edges("build", self._after_build, {"tests": "tests", "failure": "build_failure"})
        graph.add_conditional_edges("build_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_conditional_edges("tests", self._after_tests, {"compliance": "compliance", "failure": "test_failure"})
        graph.add_conditional_edges("test_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_conditional_edges("compliance", self._after_compliance, {"review": "review", "failure": "compliance_failure"})
        graph.add_conditional_edges("compliance_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_conditional_edges("repair", self._after_model, {"apply": "apply", "final": "final"})
        graph.add_conditional_edges("review", self._after_review, {"publish": "publish", "failure": "review_failure", "final": "final"})
        graph.add_conditional_edges("review_failure", self._after_failure, {"repair": "repair", "final": "final"})
        graph.add_edge("publish", "final")
        graph.add_edge("final", END)
        return graph.compile(checkpointer=checkpointer)

    @staticmethod
    def _event(state: DevelopmentState, text: str) -> dict[str, list[str]]:
        return {"events": [*state.get("events", []), text]}

    def _parse_task(self, state: DevelopmentState) -> dict[str, object]:
        try:
            return {"specification": parse_development_task(state["task"]), **self._event(state, "task_parsed")}
        except TaskParseError:
            return {"status": "failed", **self._event(state, "task_unsupported")}

    @staticmethod
    def _after_parse(state: DevelopmentState) -> str:
        return "final" if state.get("status") == "failed" else "retrieve"

    def _retrieve(self, state: DevelopmentState) -> dict[str, object]:
        database_path = FrameworkLearningService.database_path(Path(state["workspace"]))
        if not database_path.exists():
            return {"status": "failed", **self._event(state, "framework_knowledge_missing")}
        store = SQLiteKnowledgeStore(database_path)
        try:
            if store.repository_fingerprint() != repository_fingerprint(Path(state["repository"])):
                return {"status": "failed", **self._event(state, "framework_knowledge_repository_mismatch")}
            if state["specification"].artifact_type == "controller":
                rules, context = retrieve_controller_context(
                    store, Path(state["repository"]), state["specification"]
                )
            else:
                rules, context = retrieve_service_context(
                    store, Path(state["repository"]), state["specification"]
                )
        except UnsupportedInvocationRequirementError:
            return {"status": "failed", **self._event(state, "required_invocation_unsupported")}
        except ValueError:
            return {"status": "failed", **self._event(state, "framework_knowledge_missing")}
        finally:
            store.close()
        if not state["specification"].operations and any(
            requirement.supported
            for dependency in context.dependencies
            for requirement in dependency.required_invocations
        ):
            return {"status": "failed", **self._event(state, "required_invocation_operation_missing")}
        return {"framework_rules": rules, "coding_context": context, **self._event(state, "framework_retrieved")}

    @staticmethod
    def _after_retrieve(state: DevelopmentState) -> str:
        return "final" if state.get("status") == "failed" else "plan"

    def _plan(self, state: DevelopmentState) -> dict[str, object]:
        try:
            if self._planner is None:
                self._planner = self._planner_factory()
            plan = self._planner.plan(
                state["specification"], state["coding_context"], tuple(state["framework_rules"])
            )
            if not isinstance(plan, ChangePlan):
                raise TypeError("planner returned an invalid plan")
            if self._approval_policy is None:
                self._approval_policy = self._approval_policy_factory()
            approval_required = self._approval_policy.requires_approval(plan)
            if not isinstance(approval_required, bool):
                raise TypeError("approval policy returned an invalid decision")
        except Exception:
            return {"status": "failed", **self._event(state, "change_planning_failed")}
        return {"plan": plan, "approval_required": approval_required, **self._event(state, "change_planned")}

    @staticmethod
    def _after_plan(state: DevelopmentState) -> str:
        if state.get("status") == "failed":
            return "final"
        return "approval_request" if state["approval_required"] else "generate"

    def _request_approval(self, state: DevelopmentState) -> dict[str, object]:
        plan = state["plan"]
        request = HumanApprovalRequest(
            run_id=state["run_id"],
            artifact_family=plan.artifact_family,
            artifact_name=plan.artifact_name,
            target_paths=plan.target_paths,
            rule_kinds=plan.rule_kinds,
        )
        return {
            "approval_request": request,
            "status": "needs_human_review",
            **self._event(state, "human_approval_requested"),
        }

    def _approval(self, state: DevelopmentState) -> dict[str, object]:
        request = state["approval_request"]
        payload = interrupt({
            "run_id": request.run_id,
            "artifact_family": request.artifact_family,
            "artifact_name": request.artifact_name,
            "target_paths": request.target_paths,
            "rule_kinds": request.rule_kinds,
        })
        try:
            if not isinstance(payload, dict):
                raise ValueError("approval payload must be a mapping")
            decision = HumanApprovalDecision(
                payload.get("approved"), payload.get("actor", ""), payload.get("reason", "")
            )
        except (TypeError, ValueError):
            return {"status": "failed", **self._event(state, "human_approval_invalid")}
        event = "human_approval_granted" if decision.approved else "human_approval_rejected"
        return {
            "approval_decision": decision,
            "status": "running" if decision.approved else "failed",
            **self._event(state, event),
        }

    @staticmethod
    def _after_approval(state: DevelopmentState) -> str:
        return "generate" if state.get("status") == "running" else "final"

    def _generate(self, state: DevelopmentState) -> dict[str, object]:
        try:
            change = self._current_model().generate_change(state["specification"], state["coding_context"])
        except CodingModelError:
            return {"status": "failed", **self._event(state, "model_generation_failed")}
        return {"generated_change": change, **self._event(state, "change_generated")}

    def _repair(self, state: DevelopmentState) -> dict[str, object]:
        try:
            change = self._current_model().repair_change(state["specification"], state["coding_context"], state["generated_change"], state["failure_context"])
        except CodingModelError:
            return {"status": "failed", **self._event(state, "model_repair_failed")}
        return {"generated_change": change, "retry_count": state["retry_count"] + 1, **self._event(state, "change_repaired")}

    def _active_grant(self) -> CapabilityGrant:
        if self._run_grant is None:
            raise RuntimeError("development run capability is unavailable")
        return self._run_grant

    def _active_staging_authorization(self) -> _StagingAuthorization:
        if self._staging_authorization is None:
            raise RuntimeError("development staging authorization is unavailable")
        return self._staging_authorization

    def _current_model(self) -> CodingModel:
        if self._model is None:
            self._model = self._model_factory()
        return self._model

    @staticmethod
    def _after_model(state: DevelopmentState) -> str:
        return "final" if state.get("status") == "failed" else "apply"

    def _apply(self, state: DevelopmentState) -> dict[str, object]:
        try:
            files = apply_change(
                state["generated_change"], Path(state["staging_repository"]), self._active_grant(),
                allow_overwrite=True, staging_authorization=self._active_staging_authorization(),
            )
        except (ChangeValidationError, OSError, PermissionError):
            return {"status": "failed", **self._event(state, "change_apply_failed")}
        return {"generated_files": files, **self._event(state, "change_applied_to_staging")}

    @staticmethod
    def _after_apply(state: DevelopmentState) -> str:
        return "final" if state.get("status") == "failed" else "build"

    def _build(self, state: DevelopmentState) -> dict[str, CommandResult]:
        runner = self._build_runner or partial(
            run_build, timeout_seconds=self._command_timeout_seconds, max_output_chars=self._max_command_output,
            staging_authorization=self._active_staging_authorization(),
        )
        return {"build_result": self._run_command(runner, Path(state["staging_repository"]), self._active_grant())}

    def _tests(self, state: DevelopmentState) -> dict[str, CommandResult]:
        runner = self._test_runner or partial(
            run_tests, timeout_seconds=self._command_timeout_seconds, max_output_chars=self._max_command_output,
            staging_authorization=self._active_staging_authorization(),
        )
        return {"test_result": self._run_command(runner, Path(state["staging_repository"]), self._active_grant())}

    def _run_command(self, runner: Callable[[Path, CapabilityGrant], CommandResult], repository: Path, grant: CapabilityGrant) -> CommandResult:
        try:
            result = runner(repository, grant)
            return CommandResult(result.passed, result.command, self._redact(result.output), result.timed_out)
        except Exception as error:
            return CommandResult(False, (), self._redact(f"{type(error).__name__}: {error}"))

    def _compliance(self, state: DevelopmentState) -> dict[str, ValidationReport]:
        try:
            self._active_grant().require(Capability.STATIC_ANALYSIS)
            path = Path(state["staging_repository"]) / state["generated_files"][0]
            report = self._validator(path, state["framework_rules"])
            return {"validation_report": ValidationReport(
                report.passed,
                tuple(ValidationFinding(item.rule_kind, self._redact(item.message), item.severity) for item in report.findings),
            )}
        except Exception:
            return {"validation_report": ValidationReport(False)}

    @staticmethod
    def _after_build(state: DevelopmentState) -> str:
        return "tests" if state["build_result"].passed else "failure"

    @staticmethod
    def _after_tests(state: DevelopmentState) -> str:
        return "compliance" if state["test_result"].passed else "failure"

    @staticmethod
    def _after_compliance(state: DevelopmentState) -> str:
        return "review" if state["validation_report"].passed else "failure"

    def _review(self, state: DevelopmentState) -> dict[str, object]:
        try:
            if self._reviewer is None:
                self._reviewer = self._reviewer_factory()
            review = self._reviewer.review(
                state["plan"], state["generated_change"], state["validation_report"]
            )
            if not isinstance(review, ChangeReview):
                raise TypeError("reviewer returned an invalid review")
        except Exception:
            return {"status": "failed", **self._event(state, "change_review_failed")}
        event = "change_review_approved" if review.approved else "change_review_rejected"
        return {"review": review, **self._event(state, event)}

    @staticmethod
    def _after_review(state: DevelopmentState) -> str:
        if state.get("status") == "failed":
            return "final"
        return "publish" if state["review"].approved else "failure"

    def _publish(self, state: DevelopmentState) -> dict[str, object]:
        try:
            files = apply_change(state["generated_change"], Path(state["repository"]), self._active_grant())
        except (ChangeValidationError, OSError, PermissionError):
            return {"status": "failed", **self._event(state, "publish_failed")}
        return {"generated_files": files, **self._event(state, "change_published")}

    def _record_build_failure(self, state: DevelopmentState) -> dict[str, object]:
        result = state["build_result"]
        return self._record_failure(state, "build", result.command, result.output)

    def _record_test_failure(self, state: DevelopmentState) -> dict[str, object]:
        result = state["test_result"]
        return self._record_failure(state, "tests", result.command, result.output)

    def _record_compliance_failure(self, state: DevelopmentState) -> dict[str, object]:
        report = state["validation_report"]
        return self._record_failure(state, "compliance", (), "; ".join(item.message for item in report.findings) or "compliance validation failed")

    def _record_review_failure(self, state: DevelopmentState) -> dict[str, object]:
        return self._record_failure(state, "review", (), state["review"].reason)

    def _record_failure(self, state: DevelopmentState, stage: str, command: tuple[str, ...], output: str) -> dict[str, object]:
        history = state.get("failure_history", ())
        failure = FailureContext(stage, len(history) + 1, command, self._redact(output)[:self._max_failure_output])
        return {"failure_context": failure, "failure_history": (*history, failure), **self._event(state, f"{stage}_failed")}

    @staticmethod
    def _redact(output: str) -> str:
        redacted = _SECRET_JSON_ASSIGNMENT.sub(
            lambda match: f'{match.group(1)}{match.group(2)}{match.group(3)}{match.group(4)}[REDACTED]{match.group(5)}',
            output,
        )
        redacted = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    @staticmethod
    def _after_failure(state: DevelopmentState) -> str:
        return "final" if state["retry_count"] >= state["retry_budget"] else "repair"

    def _final(self, state: DevelopmentState) -> dict[str, object]:
        if all(state.get(key) and state[key].passed for key in ("build_result", "test_result", "validation_report")) and "change_published" in state.get("events", []):
            return {"status": "succeeded"}
        if state.get("failure_context") and state["retry_count"] >= state["retry_budget"]:
            return {"status": "failed", **self._event(state, "retry_budget_exhausted")}
        return {"status": "failed"}


def run_framework_learning(workspace: Path, repository: Path) -> list[FrameworkRule]:
    return FrameworkLearningService().learn(workspace, repository)


def run_development_task(workspace: Path, repository: Path, task: str = "Create GeneratedService", retry_budget: int = DEFAULT_RETRY_BUDGET) -> DevelopmentState:
    """Public local composition boundary that explicitly constructs the demo grant."""
    return DevelopmentService().run(workspace, repository, task, retry_budget, grant=poc_grant(repository))


def run_poc(workspace: Path, sample_name: str, task: str, retry_budget: int = DEFAULT_RETRY_BUDGET) -> DevelopmentState:
    repository = workspace / "customer-repo"
    shutil.copytree(Path(__file__).resolve().parents[3] / "examples" / sample_name, repository)
    run_framework_learning(workspace, repository)
    return run_development_task(workspace, repository, task, retry_budget)
