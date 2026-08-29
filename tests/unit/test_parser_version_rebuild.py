from __future__ import annotations

from pathlib import Path

import pytest

from agentic_platform.domain.models import FrameworkRule
from agentic_platform.framework_learning.learner import FrameworkLearner, LearnResult
from agentic_platform.framework_knowledge.snapshots import FrameworkKnowledgeSnapshot


class TestParserVersionTrigger:
    def test_learner_tracks_parser_version(self) -> None:
        learner = FrameworkLearner(parser_version="python-ast-1")
        assert learner.parser_version == "python-ast-1"

    def test_learner_default_parser_version(self) -> None:
        learner = FrameworkLearner()
        assert learner.parser_version  # has a default value

    def test_learn_produces_snapshot_with_parser_version(self, tmp_path: Path) -> None:
        (tmp_path / "svc.py").write_text(
            "from framework import Base, managed\n"
            "@managed\n"
            "class MyService(Base):\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        learner = FrameworkLearner(minimum_evidence=1, parser_version="python-ast-1")
        result = learner.learn(tmp_path)
        assert isinstance(result, LearnResult)
        assert result.snapshot.metadata.parser_version == "python-ast-1"

    def test_parser_version_change_invalidates_prior_knowledge(self, tmp_path: Path) -> None:
        (tmp_path / "svc.py").write_text(
            "from framework import Base, managed\n"
            "@managed\n"
            "class MyService(Base):\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        store = FrameworkLearner.KnowledgeStore(tmp_path / "knowledge.db")
        learner_v1 = FrameworkLearner(minimum_evidence=1, parser_version="python-ast-1")
        result_v1 = learner_v1.learn(tmp_path, store=store)
        assert result_v1.is_full_rebuild
        assert result_v1.rules  # has rules

        # Same parser version → incremental
        learner_v1_again = FrameworkLearner(minimum_evidence=1, parser_version="python-ast-1")
        result_incremental = learner_v1_again.learn(tmp_path, store=store)
        assert not result_incremental.is_full_rebuild

        # Changed parser version → full rebuild
        learner_v2 = FrameworkLearner(minimum_evidence=1, parser_version="python-ast-2")
        result_rebuild = learner_v2.learn(tmp_path, store=store)
        assert result_rebuild.is_full_rebuild

    def test_learn_returns_rules_and_snapshot(self, tmp_path: Path) -> None:
        (tmp_path / "svc.py").write_text(
            "from framework import Base, managed\n"
            "@managed\n"
            "class MyService(Base):\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        learner = FrameworkLearner(minimum_evidence=1)
        result = learner.learn(tmp_path)
        assert isinstance(result.rules, list)
        assert isinstance(result.snapshot, FrameworkKnowledgeSnapshot)
        assert result.is_full_rebuild  # first learn is always full rebuild

    def test_full_rebuild_flag_reflects_no_prior_snapshot(self, tmp_path: Path) -> None:
        (tmp_path / "svc.py").write_text(
            "from framework import Base, managed\n"
            "@managed\n"
            "class MyService(Base):\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        learner = FrameworkLearner(minimum_evidence=1)
        result = learner.learn(tmp_path)
        # No prior snapshot → full rebuild
        assert result.is_full_rebuild
