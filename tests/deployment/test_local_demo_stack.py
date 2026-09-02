from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_compose_declares_complete_local_demo_stack() -> None:
    compose = yaml.safe_load((ROOT / "compose.yml").read_text())
    services = compose["services"]
    assert set(services) == {
        "agentic-platform", "postgres", "qdrant", "otel-collector",
        "prometheus", "tempo", "loki", "grafana",
    }
    assert services["agentic-platform"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["agentic-platform"]["depends_on"]["qdrant"]["condition"] == "service_healthy"
    for name in services:
        assert "healthcheck" in services[name], name


def test_local_demo_configuration_has_no_committed_credentials() -> None:
    example = (ROOT / ".env.example").read_text()
    assert "change-me" in example
    assert "API_KEY=" in example
    assert "POSTGRES_PASSWORD=" in example
    tracked = {line.strip() for line in __import__("subprocess").check_output(["git", "ls-files"], text=True).splitlines()}
    assert ".env" not in tracked
    compose = (ROOT / "compose.yml").read_text()
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "API_KEY: ${API_KEY:?" in compose


def test_smoke_script_covers_real_http_flow_and_observability_readback() -> None:
    smoke = (ROOT / "scripts/demo-smoke.sh").read_text()
    for evidence in (
        "/health", "/learn", "/run", "generated_files",
        "/api/v1/targets", "/api/search", "/loki/api/v1/query_range",
        "/api/datasources/uid/${uid}/health", "/api/datasources/proxy/uid/tempo/api/search",
        "prometheus loki", 'Authorization: Bearer ${API_KEY}',
    ):
        assert evidence in smoke
    assert smoke.count('-H "Authorization: Bearer ${API_KEY}"') == 2
    assert '-H "Authorization: Bearer ***"' not in smoke


def test_local_api_image_runs_as_non_root() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text().splitlines()
    assert "USER 1000:1000" in dockerfile
