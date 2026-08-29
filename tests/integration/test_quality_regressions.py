import shutil
from pathlib import Path

import pytest

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService, run_poc
from agentic_platform.security.policy import poc_grant
from agentic_platform.retrieval.context import AmbiguousFrameworkRuleError
from agentic_platform.retrieval.context import build_source_index, retrieve_service_context, tokenize_identifier
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore
from agentic_platform.tasks.types import DevelopmentTask, OperationSpec, ParameterSpec


def grouped(rules):
    values = {}
    for rule in rules:
        values.setdefault(rule.kind, []).append(rule)
    return values


def test_inference_status_uses_support_confidence_and_minimum_evidence(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    result = FrameworkLearner().learn(root / "examples/sample_customer_repo_b")
    rules = grouped(result.rules)["dependency.constructor"]
    common = next(rule for rule in rules if rule.expected_value == "log")
    task_specific = next(rule for rule in rules if rule.expected_value == "payment_client")
    assert common.status.value == "active"
    assert task_specific.status.value == "candidate"
    assert task_specific.confidence == pytest.approx(1 / 3)


def test_minimum_evidence_four_keeps_three_of_three_pattern_candidate():
    root = Path(__file__).resolve().parents[2]
    result = FrameworkLearner(minimum_evidence=4).learn(root / "examples/sample_customer_repo_b")
    rules = result.rules
    assert all(rule.status.value == "candidate" for rule in rules)


def test_framework_c_generic_suffix_and_constructor_invocation(tmp_path: Path):
    result = run_poc(tmp_path, "sample_customer_repo_c", "Create CustomerAccountService with method get_account(account_id)")
    dependencies = {item.attribute: item for item in result["coding_context"].dependencies}
    assert dependencies["storage"].type_pattern == "*Storage"
    assert dependencies["converter"].type_pattern == "*Converter"
    assert dependencies["audit"].constructor_arguments == ("__name__",)
    assert dependencies["cache"].constructor_arguments == ()
    generated = (tmp_path / "customer-repo/app/customer_account_service.py").read_text()
    assert "self.audit = AuditSink(__name__)" in generated
    assert "self.cache = SharedCache()" in generated
    assert result["coding_context"].examples


def test_ambiguous_service_rule_is_not_silently_selected():
    with pytest.raises(AmbiguousFrameworkRuleError):
        from agentic_platform.retrieval.context import select_rule
        from agentic_platform.domain.models import Evidence, FrameworkRule, RuleStatus
        select_rule([
            FrameworkRule("service.base_class", "Alpha", .9, 3, 0, (), status=RuleStatus.ACTIVE),
            FrameworkRule("service.base_class", "Beta", .9, 3, 0, (), status=RuleStatus.ACTIVE),
        ], "service.base_class")


def test_task_aware_source_ranking_prefers_payment_examples_and_exposes_scores(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = root / "examples/sample_customer_repo_b"
    task = DevelopmentTask("service", "PaymentHistoryService", (OperationSpec("list_history", (ParameterSpec("customer_id"),)),))
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        store.replace_rules(FrameworkLearner().learn(repository).rules)
        _, context = retrieve_service_context(store, repository, task)
    finally:
        store.close()

    examples = {item.symbol: item for item in context.examples}
    service_examples = {sym: ex for sym, ex in examples.items() if sym.endswith("Service")}
    assert service_examples["PaymentService"].score > service_examples["OrderService"].score
    assert service_examples["PaymentService"].score > service_examples["ProfileService"].score
    assert examples["PaymentService"].reasons
    assert all(item.score >= 0 for item in context.examples)


def test_source_index_tokenizes_camel_and_snake_names_and_returns_task_specific_candidates(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = root / "examples/sample_customer_repo_b"
    assert tokenize_identifier("PaymentHTTPClient_payment_id") == ("payment", "http", "client", "payment", "id")
    index = build_source_index(repository)
    assert {entry.symbol for entry in index.entries} == {
        "OrderService", "PaymentService", "ProfileService",
        "OrderController", "PaymentController", "ProfileController",
    }

    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        store.replace_rules(FrameworkLearner().learn(repository).rules)
        task = DevelopmentTask("service", "OrderHistoryService", ())
        _, context = retrieve_service_context(store, repository, task)
    finally:
        store.close()

    assert [(candidate.attribute, candidate.class_name) for candidate in context.unresolved_dependencies] == [
        ("mapper", "OrderMapper"),
        ("payment_client", "PaymentClient"),
        ("repository", "OrderRepository"),
    ]
    assert context.unresolved_dependencies[0].reasons


def test_graph_retrieval_ranks_payment_example_for_payment_task(tmp_path: Path):
    result = run_poc(
        tmp_path,
        "sample_customer_repo_b",
        "Create PaymentHistoryService with method list_history(customer_id)",
    )

    assert result["coding_context"].examples[0].symbol == "PaymentService"
    assert result["coding_context"].examples[0].score > 0


def test_development_run_keeps_matching_pattern_candidates_and_rules_store_read_only(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    shutil.copytree(root / "examples/sample_customer_repo_c", repository)
    FrameworkLearningService().learn(tmp_path, repository)
    database_path = FrameworkLearningService.database_path(tmp_path)
    rules_before = database_path.read_bytes()

    passed = CommandResult(True, ("check",), "passed")
    result = DevelopmentService(
        build_runner=lambda repository, grant: passed,
        test_runner=lambda repository, grant: passed,
        validator=lambda path, rules: ValidationReport(True),
    ).run(tmp_path, repository, "Create PaymentHistoryService with method list_history(customer_id)", grant=poc_grant(repository))

    assert [(item.attribute, item.class_name) for item in result["coding_context"].unresolved_dependencies] == [
        ("converter", "PaymentConverter"),
        ("storage", "PaymentStorage"),
    ]
    candidates = {item.attribute: item for item in result["coding_context"].unresolved_dependencies}
    assert "matched type pattern: *Storage" in candidates["storage"].reasons
    assert "matched type pattern: *Converter" in candidates["converter"].reasons
    assert database_path.read_bytes() == rules_before


def test_development_run_excludes_candidate_that_misses_attribute_type_pattern(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    shutil.copytree(root / "examples/sample_customer_repo_c", repository)
    FrameworkLearningService().learn(tmp_path, repository)
    payment_service = repository / "app/payment_service.py"
    payment_service.write_text(payment_service.read_text().replace("self.storage=PaymentStorage()", "self.storage=PaymentConverter()"))

    passed = CommandResult(True, ("check",), "passed")
    result = DevelopmentService(
        build_runner=lambda repository, grant: passed,
        test_runner=lambda repository, grant: passed,
        validator=lambda path, rules: ValidationReport(True),
    ).run(tmp_path, repository, "Create PaymentHistoryService with method list_history(customer_id)", grant=poc_grant(repository))

    assert [(item.attribute, item.class_name) for item in result["coding_context"].unresolved_dependencies] == [
        ("converter", "PaymentConverter"),
    ]


def test_development_run_preserves_ambiguous_pattern_dependencies(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    shutil.copytree(root / "examples/sample_customer_repo_c", repository)
    FrameworkLearningService().learn(tmp_path, repository)

    passed = CommandResult(True, ("check",), "passed")
    result = DevelopmentService(
        build_runner=lambda repository, grant: passed,
        test_runner=lambda repository, grant: passed,
        validator=lambda path, rules: ValidationReport(True),
    ).run(tmp_path, repository, "Create StorageService with method run()", grant=poc_grant(repository))

    storage = next(item for item in result["coding_context"].dependencies if item.attribute == "storage")
    assert storage.class_name is None
    assert storage.type_pattern == "*Storage"
