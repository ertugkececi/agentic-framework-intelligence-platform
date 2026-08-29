from pathlib import Path
import shutil

from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.orchestration.graph import FrameworkLearningService, run_development_task, run_framework_learning, run_poc


def rules_by_kind(result):
    grouped = {}
    source = result if isinstance(result, list) else result["framework_rules"]
    for rule in source:
        grouped.setdefault(rule.kind, []).append(rule)
    return grouped


def test_framework_a_regression_generates_from_learned_dependency_context(tmp_path: Path):
    result = run_poc(tmp_path, "sample_customer_repo", "Create CustomerAccountService with method get_account(account_id)")
    assert result["status"] == "succeeded"
    context = result["coding_context"]
    assert [(item.attribute, item.class_name, item.methods) for item in context.dependencies] == [("logger", "CompanyLogger", ("info",))]


def test_multiple_constructor_dependencies_are_generic_structured_rules(tmp_path: Path):
    result = run_poc(tmp_path, "sample_customer_repo_b", "Create CustomerAccountService with method get_account(account_id)")
    root = Path(__file__).resolve().parents[2]
    result = FrameworkLearner().learn(root / "examples/sample_customer_repo_b")
    rules = rules_by_kind(result.rules)["dependency.constructor"]
    assert {rule.expected_value for rule in rules} == {"log", "repository", "mapper", "payment_client", "notification_client"}
    assert all(not rule.kind.startswith("logging.") for rule in rules)
    log = next(rule for rule in rules if rule.expected_value == "log")
    assert log.metadata["concrete_types"] == ["EnterpriseLog"]
    assert log.metadata["usage_methods"] == ["audit"]


def test_many_dependency_rules_preserve_cardinality_and_common_threshold(tmp_path: Path):
    result = run_poc(tmp_path, "sample_customer_repo_b", "Create CustomerAccountService with method get_account(account_id)")
    dependencies = {item.attribute: item for item in result["coding_context"].dependencies}
    assert set(dependencies) == {"log", "repository", "mapper"}
    assert dependencies["repository"].class_name is None
    assert dependencies["repository"].type_pattern == "*Repository"
    assert dependencies["repository"].methods == ("save",)
    assert "payment_client" not in dependencies


def test_framework_b_and_mutation_remain_runtime_driven(tmp_path: Path):
    result = run_poc(tmp_path, "sample_customer_repo_b", "Create CustomerAccountService with method get_account(account_id)")
    generated = (tmp_path / "customer-repo/app/customer_account_service.py").read_text()
    assert "class CustomerAccountService(FrameworkComponent):" in generated
    assert "self.log = EnterpriseLog(__name__)" in generated
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "mutated"
    shutil.copytree(root / "examples/sample_customer_repo_b", repository)
    for path in (repository / "app").glob("*.py"):
        path.write_text(path.read_text().replace("FrameworkComponent", "DomainUnit"))
    run_framework_learning(tmp_path, repository)
    mutated = run_development_task(tmp_path, repository, "Create DomainLookupService with method run()")
    assert "class DomainLookupService(DomainUnit):" in (repository / "app/domain_lookup_service.py").read_text()
    assert mutated["status"] == "succeeded"


def test_development_task_reuses_explicitly_learned_knowledge(tmp_path: Path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    shutil.copytree(root / "examples/sample_customer_repo", repository)

    run_framework_learning(tmp_path, repository)
    monkeypatch.setattr(
        FrameworkLearningService,
        "learn",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("development must not learn")),
    )
    result = run_development_task(tmp_path, repository, "Create ReusedKnowledgeService with method run()")

    assert result["framework_rules"]
    assert result["status"] == "succeeded"


def test_development_task_fails_cleanly_when_knowledge_has_not_been_learned(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    shutil.copytree(root / "examples/sample_customer_repo", repository)

    result = run_development_task(tmp_path, repository, "Create MissingKnowledgeService")

    assert result["status"] == "failed"
    assert "framework_knowledge_missing" in result["events"]
    assert not (repository / "app/missing_knowledge_service.py").exists()
    assert not (tmp_path / "framework_knowledge.sqlite").exists()


def test_product_source_has_no_customer_symbol_leaks():
    root = Path(__file__).resolve().parents[2]
    forbidden = {"BaseService", "business_service", "CompanyLogger", "FrameworkComponent", "managed_component", "EnterpriseLog", "OrderRepository", "PaymentRepository", "OrderMapper", "PaymentClient"}
    hits = [f"{path}:{symbol}" for path in (root / "src/agentic_platform").rglob("*.py") for symbol in forbidden if symbol in path.read_text()]
    assert not hits, hits
