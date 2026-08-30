import json
import re
from pathlib import Path


ROOT = Path("deploy/overlays/production")


def test_production_overlay_pins_the_api_image_and_inherits_the_base() -> None:
    kustomization = (ROOT / "kustomization.yaml").read_text(encoding="utf-8")

    assert "  - ../../kubernetes" in kustomization.splitlines()
    assert "newName: registry.example.invalid/agentic-platform" in kustomization
    digest = re.search(r"digest: (sha256:[0-9a-f]{64})", kustomization)
    assert digest is not None
    assert digest.group(1) != "sha256:" + "0" * 64
    assert "newTag:" not in kustomization


def test_production_overlay_sources_runtime_secrets_from_vault_csi() -> None:
    provider = json.loads((ROOT / "secret-provider.json").read_text(encoding="utf-8"))
    assert provider["apiVersion"] == "secrets-store.csi.x-k8s.io/v1"
    assert provider["kind"] == "SecretProviderClass"
    assert provider["spec"]["provider"] == "vault"

    secret_objects = provider["spec"]["secretObjects"]
    assert len(secret_objects) == 1
    synced = secret_objects[0]
    assert synced["secretName"] == "agentic-platform-secrets"
    assert synced["type"] == "Opaque"
    assert {item["key"] for item in synced["data"]} == {
        "api-key",
        "postgres-password",
        "postgres-dsn",
        "grafana-admin-user",
        "grafana-admin-password",
    }
    assert "secretKey" not in provider["spec"]["parameters"]
    assert "token" not in provider["spec"]["parameters"]


def test_production_api_mounts_the_csi_provider_read_only() -> None:
    patch = json.loads((ROOT / "platform-csi-patch.json").read_text(encoding="utf-8"))
    pod = patch["spec"]["template"]["spec"]
    volume = next(item for item in pod["volumes"] if item["name"] == "runtime-secrets")
    csi = volume["csi"]
    assert csi == {
        "driver": "secrets-store.csi.k8s.io",
        "readOnly": True,
        "volumeAttributes": {"secretProviderClass": "agentic-platform-vault"},
    }
    container = pod["containers"][0]
    mount = next(
        item for item in container["volumeMounts"] if item["name"] == "runtime-secrets"
    )
    assert mount["readOnly"] is True
    assert mount["mountPath"] == "/mnt/runtime-secrets"
