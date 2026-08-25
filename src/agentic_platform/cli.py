"""Public, local-only lifecycle CLI for framework learning and development."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from agentic_platform.orchestration.graph import (
    FrameworkLearningService,
    run_development_task,
    run_framework_learning,
)


class CLIInputError(ValueError):
    """A concise, safe error caused by invalid public CLI input."""


class JSONArgumentParser(argparse.ArgumentParser):
    """Argparse adapter that lets the CLI emit one JSON outcome on input errors."""

    def error(self, message: str) -> None:
        raise CLIInputError(message)


def _outcome(
    *,
    status: str,
    command: str | None,
    workspace: Path | None = None,
    repository: Path | None = None,
    **details: object,
) -> dict[str, object]:
    outcome: dict[str, object] = {"status": status}
    if command:
        outcome["command"] = command
    if workspace:
        outcome["workspace"] = str(workspace)
    if repository:
        outcome["repository"] = str(repository)
    outcome.update(details)
    return outcome


def _error(command: str | None, code: str, message: str) -> dict[str, object]:
    return _outcome(status="failed", command=command, error={"code": code, "message": message})


def _build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(description="Run local framework intelligence lifecycle commands.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("learn", "develop", "run"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--repository", required=True, type=Path, help="Local repository to learn from or develop in.")
        subparser.add_argument("--workspace", required=True, type=Path, help="Workspace containing framework_knowledge.sqlite.")
        subparser.add_argument("--deterministic", action="store_true", required=True, help="Use the bounded, offline deterministic coding model.")
        if command in {"develop", "run"}:
            subparser.add_argument("--task", required=True, help="Development task to execute.")
    return parser


def _validate_repository(repository: Path) -> None:
    if not repository.is_dir():
        raise CLIInputError("repository must be an existing local directory")


def _run(arguments: argparse.Namespace) -> dict[str, object]:
    command = arguments.command
    repository = arguments.repository.resolve()
    workspace = arguments.workspace.resolve()
    _validate_repository(repository)
    workspace.mkdir(parents=True, exist_ok=True)
    database = FrameworkLearningService.database_path(workspace)

    if command == "learn":
        rules = run_framework_learning(workspace, repository)
        return _outcome(
            status="succeeded",
            command=command,
            workspace=workspace,
            repository=repository,
            knowledge_database=str(database),
            rules_persisted=len(rules),
        )

    if command == "develop" and not database.is_file():
        return _outcome(
            status="failed",
            command=command,
            workspace=workspace,
            repository=repository,
            error={"code": "framework_knowledge_missing", "message": "run learn before develop"},
        )

    if command == "run":
        run_framework_learning(workspace, repository)

    state = run_development_task(workspace, repository, arguments.task)
    if state["status"] != "succeeded":
        error_code = (
            "framework_knowledge_repository_mismatch"
            if "framework_knowledge_repository_mismatch" in state.get("events", [])
            else "workflow_failed"
        )
        return _outcome(
            status="failed",
            command=command,
            workspace=workspace,
            repository=repository,
            knowledge_database=str(database),
            error={
                "code": error_code,
                "message": "knowledge was learned from a different repository"
                if error_code == "framework_knowledge_repository_mismatch"
                else "development workflow did not succeed",
            },
            events=state.get("events", []),
        )
    return _outcome(
        status="succeeded",
        command=command,
        workspace=workspace,
        repository=repository,
        knowledge_database=str(database),
        generated_files=state.get("generated_files", []),
        events=state.get("events", []),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    command: str | None = None
    try:
        arguments = parser.parse_args(argv)
        command = arguments.command
        outcome = _run(arguments)
    except CLIInputError as error:
        outcome = _error(command, "invalid_repository" if command else "invalid_arguments", str(error))
    except Exception:
        outcome = _error(command, "workflow_failed", "workflow could not be completed")
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
