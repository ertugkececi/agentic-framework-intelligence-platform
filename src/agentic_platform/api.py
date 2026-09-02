import os
import secrets
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agentic_platform.domain.models import CodingContext, FrameworkRule, KnowledgeScope
from agentic_platform.framework_knowledge.postgres_store import PostgresKnowledgeStore
from agentic_platform.framework_knowledge.sqlite_store import repository_fingerprint
from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.orchestration.checkpoints import PostgresCheckpointProvider
from agentic_platform.orchestration.graph import DevelopmentService
from agentic_platform.retrieval.assembly import assemble_coding_context
from agentic_platform.retrieval.embeddings import DeterministicEmbedding
from agentic_platform.retrieval.qdrant_store import QdrantSemanticStore
from agentic_platform.retrieval.source_indexing import (
    RepositorySemanticIndexer,
    RepositorySourceChunkExtractor,
)
from agentic_platform.security.policy import Capability, CapabilityGrant, Principal, Role
from agentic_platform.tasks.types import DevelopmentTask


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise RuntimeError(f"{name} environment variable is required")
    return value


app = FastAPI(title="Agentic Framework Intelligence Platform", version="0.1.0")
ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()
API_KEY = _required_env("API_KEY")
POSTGRES_DSN = _required_env("POSTGRES_DSN")
QDRANT_URL = _required_env("QDRANT_URL")
TENANT_ID = _required_env("TENANT_ID")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "framework-knowledge")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
try:
    EMBEDDING_VECTOR_SIZE = int(os.environ.get("EMBEDDING_VECTOR_SIZE", "384"))
except ValueError as exception:
    raise RuntimeError("EMBEDDING_VECTOR_SIZE must be a positive integer") from exception
if EMBEDDING_VECTOR_SIZE < 1:
    raise RuntimeError("EMBEDDING_VECTOR_SIZE must be a positive integer")
CHECKPOINT_PROVIDER = PostgresCheckpointProvider(POSTGRES_DSN)
security = HTTPBearer()


def require_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    if credentials.scheme.lower() != "bearer" or not secrets.compare_digest(credentials.credentials, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


class ScopedRequest(BaseModel):
    framework_id: str
    framework_version_id: str
    project_id: str
    module_id: str | None = None

    @property
    def knowledge_scope(self) -> KnowledgeScope:
        return KnowledgeScope(TENANT_ID, self.framework_id, self.framework_version_id, self.project_id, self.module_id)


class LearnRequest(ScopedRequest):
    repository: str
    workspace: str = "."


class DevelopRequest(ScopedRequest):
    repository: str
    workspace: str = "."
    task: str
    query_vector: list[float]


def resolve_workspace_path(value: str) -> Path:
    path = (ROOT  / value).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise HTTPException(status_code=400, detail="Path must be inside workspace root")
    return path


def paths(repository: str, workspace: str) -> tuple[Path, Path]:
    repo = resolve_workspace_path(repository)
    work = resolve_workspace_path(workspace)
    if not repo.is_dir():
        raise HTTPException(status_code=400, detail="Repository does not exist")
    work.mkdir(parents=True, exist_ok=True)
    return repo, work


def production_grant(repository: Path, *, database_write: bool = False) -> CapabilityGrant:
    principal = Principal(
        "platform-api", TENANT_ID, frozenset({Role.DEVELOPER, Role.KNOWLEDGE_ADMIN})
    )
    allowed = {
        Capability.READ_REPOSITORY,
        Capability.WRITE_REPOSITORY,
        Capability.RUN_BUILD,
        Capability.RUN_TEST,
        Capability.STATIC_ANALYSIS,
        Capability.DATABASE_READ,
    }
    if database_write:
        allowed.add(Capability.DATABASE_WRITE)
    return CapabilityGrant(frozenset(allowed), repository, principal)


def production_context_retriever(request: DevelopRequest, repository: Path) -> Callable[[Path, DevelopmentTask], tuple[list[FrameworkRule], CodingContext]]:
    if len(request.query_vector) != EMBEDDING_VECTOR_SIZE:
        raise HTTPException(status_code=422, detail=f"query_vector must have dimension {EMBEDDING_VECTOR_SIZE}")
    scope = request.knowledge_scope
    grant = production_grant(repository)

    def retrieve(repo: Path, task: DevelopmentTask) -> tuple[list[FrameworkRule], CodingContext]:
        if repo.resolve() != repository.resolve():
            raise PermissionError("context retriever repository mismatch")
        rule_store = PostgresKnowledgeStore.from_dsn(POSTGRES_DSN, grant=grant, initialize_schema=False)
        try:
            semantic_store = QdrantSemanticStore.from_url(QDRANT_URL, grant=grant, collection_name=QDRANT_COLLECTION, vector_size=EMBEDDING_VECTOR_SIZE, api_key=QDRANT_API_KEY, initialize_collection=False)
            return assemble_coding_context(rule_store, semantic_store, scope, repository, task, request.query_vector)
        finally:
            rule_store.close()

    return retrieve


def production_learn(request: LearnRequest, repository: Path) -> list[FrameworkRule]:
    result = FrameworkLearner().learn(repository)
    grant = production_grant(repository, database_write=True)
    store = PostgresKnowledgeStore.from_dsn(POSTGRES_DSN, grant=grant)
    try:
        store.replace_rules(result.rules, repository_fingerprint(repository), scope=request.knowledge_scope)
        semantic_store = QdrantSemanticStore.from_url(
            QDRANT_URL,
            grant=grant,
            collection_name=QDRANT_COLLECTION,
            vector_size=EMBEDDING_VECTOR_SIZE,
            api_key=QDRANT_API_KEY,
            initialize_collection=True,
        )
        RepositorySemanticIndexer(
            grant=grant,
            extractor=RepositorySourceChunkExtractor(grant=grant),
            embedding=DeterministicEmbedding(EMBEDDING_VECTOR_SIZE),
            store=semantic_store,
        ).index(repository, request.knowledge_scope)
    finally:
        store.close()
    return result.rules


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/learn", dependencies=[Depends(require_api_key)])
def learn(request: LearnRequest):
    repo, work = paths(request.repository, request.workspace)
    rules = production_learn(request, repo)
    return {"status": "succeeded", "repository": str(repo), "workspace": str(work), "knowledge_backend": "postgresql", "rules_persisted": len(rules)}


@app.post("/develop", dependencies=[Depends(require_api_key)])
def develop(request: DevelopRequest):
    repo, work = paths(request.repository, request.workspace)
    retriever = production_context_retriever(request, repo)
    state = DevelopmentService(checkpoint_provider=CHECKPOINT_PROVIDER, context_retriever=retriever).run(work, repo, request.task, grant=production_grant(repo))
    return {"status": state.get("status"), "events": state.get("events", []), "generated_files": state.get("generated_files", [])}


@app.post("/run", dependencies=[Depends(require_api_key)])
def run(request: DevelopRequest):
    repo, _ = paths(request.repository, request.workspace)
    production_learn(LearnRequest(**request.model_dump(exclude={"task", "query_vector"})), repo)
    return develop(request)
