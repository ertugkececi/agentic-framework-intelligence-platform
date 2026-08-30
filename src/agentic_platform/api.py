import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agentic_platform.orchestration.graph import (
    DevelopmentService,
    FrameworkLearningService,
    run_framework_learning,
)
from agentic_platform.orchestration.checkpoints import PostgresCheckpointProvider
from agentic_platform.security.policy import poc_grant

app = FastAPI(
    title="Agentic Framework Intelligence Platform",
    version="0.1.0",
)

ROOT = Path("/workspace").resolve()

API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY environment variable is required")

POSTGRES_DSN = os.environ.get("POSTGRES_DSN")
if not POSTGRES_DSN:
    raise RuntimeError("POSTGRES_DSN environment variable is required")
CHECKPOINT_PROVIDER = PostgresCheckpointProvider(POSTGRES_DSN)

security = HTTPBearer()


def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> None:
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    if not secrets.compare_digest(credentials.credentials, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


class LearnRequest(BaseModel):
    repository: str
    workspace: str = "."


class DevelopRequest(BaseModel):
    repository: str
    workspace: str = "."
    task: str


def resolve_workspace_path(value: str) -> Path:
    path = (ROOT / value).resolve()

    if path != ROOT and ROOT not in path.parents:
        raise HTTPException(
            status_code=400,
            detail="Path must be inside /workspace",
        )

    return path


def paths(repository: str, workspace: str):
    repo = resolve_workspace_path(repository)
    work = resolve_workspace_path(workspace)

    if not repo.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Repository does not exist",
        )

    work.mkdir(parents=True, exist_ok=True)

    return repo, work


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/learn", dependencies=[Depends(require_api_key)])
def learn(request: LearnRequest):
    repo, work = paths(request.repository, request.workspace)

    rules = run_framework_learning(work, repo)

    return {
        "status": "succeeded",
        "repository": str(repo),
        "workspace": str(work),
        "knowledge_database": str(
            FrameworkLearningService.database_path(work)
        ),
        "rules_persisted": len(rules),
    }


@app.post("/develop", dependencies=[Depends(require_api_key)])
def develop(request: DevelopRequest):
    repo, work = paths(request.repository, request.workspace)

    database = FrameworkLearningService.database_path(work)

    if not database.is_file():
        raise HTTPException(
            status_code=409,
            detail="Framework knowledge missing. Run /learn first.",
        )

    state = DevelopmentService(checkpoint_provider=CHECKPOINT_PROVIDER).run(
        work, repo, request.task, grant=poc_grant(repo)
    )

    return {
        "status": state.get("status"),
        "events": state.get("events", []),
        "generated_files": state.get("generated_files", []),
    }


@app.post("/run", dependencies=[Depends(require_api_key)])
def run(request: DevelopRequest):
    repo, work = paths(request.repository, request.workspace)

    run_framework_learning(work, repo)
    state = DevelopmentService(checkpoint_provider=CHECKPOINT_PROVIDER).run(
        work, repo, request.task, grant=poc_grant(repo)
    )

    return {
        "status": state.get("status"),
        "events": state.get("events", []),
        "generated_files": state.get("generated_files", []),
        "knowledge_database": str(
            FrameworkLearningService.database_path(work)
        ),
    }
