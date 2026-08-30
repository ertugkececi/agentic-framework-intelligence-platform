import json
from pathlib import Path


ROOT = Path("deploy/kubernetes")


def _manifests() -> dict[tuple[str, str], dict]:
    manifests = {}
    for path in sorted(ROOT.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        documents = document["items"] if document["kind"] == "List" else [document]
        for item in documents:
            manifests[(item["kind"], item["metadata"]["name"])] = item
    return manifests


def test_otlp_collector_is_wired_into_the_kubernetes_base() -> None:
    manifests = _manifests()
    kustomization = (ROOT / "kustomization.yaml").read_text(encoding="utf-8")

    assert "  - observability.json" in kustomization.splitlines()
    config = manifests[("ConfigMap", "otel-collector-config")]["data"]["config.yaml"]
    assert "otlp:" in config
    assert "prometheus:" in config
    assert "memory_limiter" in config
    assert "batch" in config

    deployment = manifests[("Deployment", "otel-collector")]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert "@sha256:" in container["image"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]

    ports = {item["port"] for item in manifests[("Service", "otel-collector")]["spec"]["ports"]}
    assert {4317, 4318, 8889} <= ports


def test_api_telemetry_egress_is_explicitly_allowlisted() -> None:
    manifests = _manifests()
    platform_config = manifests[("ConfigMap", "agentic-platform-config")]["data"]
    assert platform_config["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"

    collector_access = manifests[("NetworkPolicy", "otel-collector-access")]
    ingress = collector_access["spec"]["ingress"]
    assert {port["port"] for rule in ingress for port in rule["ports"]} == {4317, 4318}
    assert ingress[0]["from"][0]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "agentic-platform",
        "app.kubernetes.io/component": "api",
    }

    platform_egress = manifests[("NetworkPolicy", "platform-egress")]["spec"]["egress"]
    otlp_rules = [
        rule for rule in platform_egress
        if {port["port"] for port in rule.get("ports", [])} & {4317, 4318}
    ]
    assert len(otlp_rules) == 1
    assert otlp_rules[0]["to"][0]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "otel-collector",
        "app.kubernetes.io/component": "observability",
    }
