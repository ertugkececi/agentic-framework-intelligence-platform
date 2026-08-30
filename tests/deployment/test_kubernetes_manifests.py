import json
from pathlib import Path


DEPLOYMENT_ROOT = Path("deploy/kubernetes")


def _manifests() -> dict[tuple[str, str], dict]:
    manifests = {}
    for path in sorted(DEPLOYMENT_ROOT.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        documents = document["items"] if document["kind"] == "List" else [document]
        for item in documents:
            manifests[(item["kind"], item["metadata"]["name"])] = item
    return manifests


def test_kustomization_declares_complete_on_prem_stack() -> None:
    resources = {
        line.removeprefix("  - ")
        for line in (DEPLOYMENT_ROOT / "kustomization.yaml")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("  - ")
    }

    assert resources == {
        "namespace.json",
        "platform-config.json",
        "platform-workspace.json",
        "platform.json",
        "postgres.json",
        "qdrant.json",
        "network-policy.json",
    }


def test_platform_is_health_checked_non_root_and_uses_secret_references() -> None:
    manifests = _manifests()
    assert all(kind != "Secret" for kind, _ in manifests)
    deployment = manifests[("Deployment", "agentic-platform")]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    env = {item["name"]: item for item in container["env"]}

    assert container["image"] != "agentic-framework-intelligence-platform:latest"
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/health",
        "port": "http",
    }
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert env["API_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "agentic-platform-secrets",
        "key": "api-key",
    }
    assert env["POSTGRES_DSN"]["valueFrom"]["secretKeyRef"]["key"] == "postgres-dsn"
    assert "value" not in env["API_KEY"]


def test_postgres_and_qdrant_are_private_persistent_services() -> None:
    manifests = _manifests()

    for name, port in (("postgres", 5432), ("qdrant", 6333)):
        stateful_set = manifests[("StatefulSet", name)]
        service = manifests[("Service", name)]
        assert service["spec"]["type"] == "ClusterIP"
        assert service["spec"]["ports"][0]["port"] == port
        assert stateful_set["spec"]["volumeClaimTemplates"][0]["spec"][
            "resources"
        ]["requests"]["storage"]
        pod = stateful_set["spec"]["template"]["spec"]
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["containers"][0]["securityContext"][
            "allowPrivilegeEscalation"
        ] is False

    postgres_env = {
        item["name"]: item
        for item in manifests[("StatefulSet", "postgres")]["spec"]["template"][
            "spec"
        ]["containers"][0]["env"]
    }
    assert postgres_env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"] == {
        "name": "agentic-platform-secrets",
        "key": "postgres-password",
    }


def test_default_deny_and_explicit_internal_egress_policies_exist() -> None:
    manifests = _manifests()
    policies = [
        manifest
        for (kind, _), manifest in manifests.items()
        if kind == "NetworkPolicy"
    ]

    assert {
        "default-deny",
        "platform-egress",
        "platform-access",
        "postgres-access",
        "qdrant-access",
    } <= {policy["metadata"]["name"] for policy in policies}
    default_deny = next(
        policy for policy in policies if policy["metadata"]["name"] == "default-deny"
    )
    assert default_deny["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert default_deny["spec"]["ingress"] == []
    assert default_deny["spec"]["egress"] == []

    egress = next(
        policy for policy in policies if policy["metadata"]["name"] == "platform-egress"
    )["spec"]["egress"]
    allowed_ports = {
        port["port"] for rule in egress for port in rule.get("ports", [])
    }
    assert {53, 5432, 6333} <= allowed_ports
