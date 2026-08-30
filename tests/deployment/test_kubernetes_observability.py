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


def test_tempo_durably_receives_collector_traces() -> None:
    manifests = _manifests()
    collector_config = manifests[("ConfigMap", "otel-collector-config")]["data"][
        "config.yaml"
    ]
    tempo_config = manifests[("ConfigMap", "tempo-config")]["data"]["tempo.yaml"]
    stateful_set = manifests[("StatefulSet", "tempo")]
    service = manifests[("Service", "tempo")]
    pod = stateful_set["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert "endpoint: tempo:4317" in collector_config
    assert "exporters: [otlp/tempo]" in collector_config
    assert "backend: local" in tempo_config
    assert service["spec"]["type"] == "ClusterIP"
    assert {port["port"] for port in service["spec"]["ports"]} == {3200, 4317}
    assert stateful_set["spec"]["volumeClaimTemplates"][0]["spec"][
        "resources"
    ]["requests"]["storage"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert "@sha256:" in container["image"]
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "http",
    }
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_tempo_ingestion_access_is_collector_only() -> None:
    manifests = _manifests()
    policies = {
        name: manifest
        for (kind, name), manifest in manifests.items()
        if kind == "NetworkPolicy"
    }
    collector_egress = policies["otel-collector-egress"]["spec"]
    assert collector_egress["egress"] == [
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
                            "app.kubernetes.io/name": "tempo",
                            "app.kubernetes.io/component": "traces",
                        }
                    }
                }
            ],
            "ports": [{"protocol": "TCP", "port": 4317}],
        },
        {
            "to": [
                {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "loki",
                            "app.kubernetes.io/component": "logs",
                        }
                    }
                }
            ],
            "ports": [{"protocol": "TCP", "port": 3100}],
        },
    ]
    tempo_ingress = policies["tempo-access"]["spec"]
    assert tempo_ingress["ingress"][0] == {
        "from": [
            {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "otel-collector",
                        "app.kubernetes.io/component": "observability",
                    }
                }
            }
        ],
        "ports": [{"protocol": "TCP", "port": 4317}],
    }


def test_loki_durably_receives_collector_logs() -> None:
    manifests = _manifests()
    collector_config = manifests[("ConfigMap", "otel-collector-config")]["data"][
        "config.yaml"
    ]
    loki_config = manifests[("ConfigMap", "loki-config")]["data"]["loki.yaml"]
    stateful_set = manifests[("StatefulSet", "loki")]
    service = manifests[("Service", "loki")]
    pod = stateful_set["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert "endpoint: http://loki:3100/otlp" in collector_config
    assert "exporters: [otlphttp/loki]" in collector_config
    assert "retention_period: 336h" in loki_config
    assert "retention_enabled: true" in loki_config
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"][0]["port"] == 3100
    assert stateful_set["spec"]["volumeClaimTemplates"][0]["spec"][
        "resources"
    ]["requests"]["storage"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert "@sha256:" in container["image"]
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/ready",
        "port": "http",
    }
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_loki_ingestion_access_is_collector_only() -> None:
    manifests = _manifests()
    policies = {
        name: manifest
        for (kind, name), manifest in manifests.items()
        if kind == "NetworkPolicy"
    }
    collector_egress = policies["otel-collector-egress"]["spec"]["egress"]
    assert {
        "to": [
            {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "loki",
                        "app.kubernetes.io/component": "logs",
                    }
                }
            }
        ],
        "ports": [{"protocol": "TCP", "port": 3100}],
    } in collector_egress
    loki_ingress = policies["loki-access"]["spec"]
    assert loki_ingress["ingress"][0] == {
        "from": [
            {
                "podSelector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "otel-collector",
                        "app.kubernetes.io/component": "observability",
                    }
                }
            }
        ],
        "ports": [{"protocol": "TCP", "port": 3100}],
    }


def test_grafana_provisions_durable_private_observability_frontend() -> None:
    manifests = _manifests()
    datasources = manifests[("ConfigMap", "grafana-provisioning")]["data"][
        "datasources.yaml"
    ]
    stateful_set = manifests[("StatefulSet", "grafana")]
    service = manifests[("Service", "grafana")]
    pod = stateful_set["spec"]["template"]["spec"]
    container = pod["containers"][0]
    env = {item["name"]: item for item in container["env"]}

    assert "url: http://prometheus:9090" in datasources
    assert "url: http://tempo:3200" in datasources
    assert "url: http://loki:3100" in datasources
    assert "uid: prometheus" in datasources
    assert "uid: tempo" in datasources
    assert "uid: loki" in datasources
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 3000, "targetPort": "http"}
    ]
    assert stateful_set["spec"]["volumeClaimTemplates"][0]["spec"][
        "resources"
    ]["requests"]["storage"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert "@sha256:" in container["image"]
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/api/health",
        "port": "http",
    }
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert env["GF_SECURITY_ADMIN_USER"]["valueFrom"]["secretKeyRef"] == {
        "name": "agentic-platform-secrets",
        "key": "grafana-admin-user",
    }
    assert env["GF_SECURITY_ADMIN_PASSWORD"]["valueFrom"]["secretKeyRef"] == {
        "name": "agentic-platform-secrets",
        "key": "grafana-admin-password",
    }
    assert env["GF_USERS_ALLOW_SIGN_UP"]["value"] == "false"
    assert env["GF_AUTH_ANONYMOUS_ENABLED"]["value"] == "false"


def test_grafana_network_access_is_backend_read_only() -> None:
    manifests = _manifests()
    policies = {
        name: manifest
        for (kind, name), manifest in manifests.items()
        if kind == "NetworkPolicy"
    }
    grafana_egress = policies["grafana-egress"]["spec"]["egress"]
    backend_routes = {
        (
            rule["to"][0]["podSelector"]["matchLabels"]["app.kubernetes.io/name"],
            rule["ports"][0]["port"],
        )
        for rule in grafana_egress
        if "podSelector" in rule["to"][0]
    }
    assert backend_routes == {
        ("prometheus", 9090),
        ("tempo", 3200),
        ("loki", 3100),
    }
    assert {port["port"] for port in grafana_egress[0]["ports"]} == {53}
    assert all(
        route not in backend_routes
        for route in (("agentic-platform", 8000), ("postgres", 5432), ("qdrant", 6333))
    )

    for policy_name, port in (
        ("prometheus-access", 9090),
        ("tempo-access", 3200),
        ("loki-access", 3100),
    ):
        assert any(
            rule.get("from", [{}])[0].get("podSelector", {}).get(
                "matchLabels", {}
            ).get("app.kubernetes.io/name") == "grafana"
            and {item["port"] for item in rule.get("ports", [])} == {port}
            for rule in policies[policy_name]["spec"]["ingress"]
        )
