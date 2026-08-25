"""Local, transport-neutral entry point for the executable PoC."""
from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path

from agentic_platform.orchestration.graph import run_poc


def _json_default(value: object) -> object:
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Framework Intelligence LangGraph PoC")
    parser.add_argument("--workspace", type=Path, help="Output directory; uses a temporary directory if omitted")
    arguments = parser.parse_args()
    if arguments.workspace:
        arguments.workspace.mkdir(parents=True, exist_ok=True)
        state = run_poc(arguments.workspace)
        print(json.dumps(state, default=_json_default, indent=2))
        return
    with tempfile.TemporaryDirectory(prefix="framework-intelligence-") as temporary:
        print(json.dumps(run_poc(Path(temporary)), default=_json_default, indent=2))


if __name__ == "__main__":
    main()
