from pathlib import Path

import pytest

from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.orchestration.graph import run_poc
from agentic_platform.retrieval.context import AmbiguousFrameworkRuleError


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
    result = run_poc(tmp_path, "sample_customer_repo_c")
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
