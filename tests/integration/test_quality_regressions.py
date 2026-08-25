from pathlib import Path

import pytest

from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.orchestration.graph import run_poc
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
    rules = grouped(FrameworkLearner().learn(root / "examples/sample_customer_repo_b"))["dependency.constructor"]
    common = next(rule for rule in rules if rule.expected_value == "log")
    task_specific = next(rule for rule in rules if rule.expected_value == "payment_client")
    assert common.status.value == "active"
    assert task_specific.status.value == "candidate"
    assert task_specific.confidence == pytest.approx(1 / 3)


def test_minimum_evidence_four_keeps_three_of_three_pattern_candidate():
    root = Path(__file__).resolve().parents[2]
    rules = FrameworkLearner(minimum_evidence=4).learn(root / "examples/sample_customer_repo_b")
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
        store.replace_rules(FrameworkLearner().learn(repository))
        _, context = retrieve_service_context(store, repository, task)
    finally:
        store.close()

    examples = {item.symbol: item for item in context.examples}
    assert examples["PaymentService"].score > examples["OrderService"].score
    assert examples["PaymentService"].score > examples["ProfileService"].score
    assert examples["PaymentService"].reasons
    assert all(item.score >= 0 for item in context.examples)


def test_source_index_tokenizes_camel_and_snake_names_and_returns_task_specific_candidates(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    repository = root / "examples/sample_customer_repo_b"
    assert tokenize_identifier("PaymentHTTPClient_payment_id") == ("payment", "http", "client", "payment", "id")
    index = build_source_index(repository)
    assert {entry.symbol for entry in index.entries} == {"OrderService", "PaymentService", "ProfileService"}

    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        store.replace_rules(FrameworkLearner().learn(repository))
        task = DevelopmentTask("service", "OrderHistoryService", ())
        _, context = retrieve_service_context(store, repository, task)
    finally:
        store.close()

    assert [(candidate.attribute, candidate.class_name) for candidate in context.unresolved_dependencies] == [("payment_client", "PaymentClient")]
    assert context.unresolved_dependencies[0].reasons
