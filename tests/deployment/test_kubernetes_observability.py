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
    api_ingress = next(
        rule
        for rule in ingress
        if rule["from"][0]["podSelector"]["matchLabels"].get(
            "app.kubernetes.io/name"
        )
        == "agentic-platform"
    )
    assert {port["port"] for port in api_ingress["ports"]} == {4317, 4318}
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


def test_prometheus_durably_scrapes_the_collector() -> None:
    manifests = _manifests()
    config = manifests[("ConfigMap", "prometheus-config")]["data"][
        "prometheus.yml"
    ]
    stateful_set = manifests[("StatefulSet", "prometheus")]
    service = manifests[("Service", "prometheus")]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]

    assert "otel-collector:8889" in config
    assert "scrape_interval: 30s" in config
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"][0]["port"] == 9090
    assert stateful_set["spec"]["volumeClaimTemplates"][0]["spec"][
        "resources"
    ]["requests"]["storage"]
    assert "--storage.tsdb.retention.time=15d" in container["args"]
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/-/ready",
        "port": "http",
    }
    pod = stateful_set["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_prometheus_network_access_is_least_privilege() -> None:
    manifests = _manifests()
    policies = {
        name: manifest
        for (kind, name), manifest in manifests.items()
        if kind == "NetworkPolicy"
    }

    scrape = policies["prometheus-egress"]["spec"]
    assert scrape["podSelector"]["matchLabels"]["app.kubernetes.io/name"] == (
        "prometheus"
    )
    assert scrape["egress"] == [
        {
            "to": [{"namespaceSelector": {}}],
            "ports": [
                {"protocol": "UDP", "port": 53},
                {"protocol": "TCP", "port": 53},
            ],
        },
        {
            "to": [
                {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "otel-collector",
                            "app.kubernetes.io/component": "observability",
                        }
                    }
                }
            ],
            "ports": [{"protocol": "TCP", "port": 8889}],
        },
    ]
    collector_ingress = policies["otel-collector-access"]["spec"]["ingress"]
    assert any(
        rule.get("from")
        == [
            {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "prometheus",
                        "app.kubernetes.io/component": "metrics",
                    }
                }
            }
        ]
        and rule.get("ports") == [{"protocol": "TCP", "port": 8889}]
        for rule in collector_ingress
    )
