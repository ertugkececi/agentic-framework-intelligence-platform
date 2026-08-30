# On-prem Kubernetes deployment

This base deploys the API, PostgreSQL 16, and Qdrant into the dedicated
`framework-intelligence` namespace. Services are cluster-private, persistent,
and protected by default-deny network policies.

Provision the referenced secret outside Git before applying the base:

```sh
kubectl -n framework-intelligence create secret generic agentic-platform-secrets \
  --from-literal=api-key="$API_KEY" \
  --from-literal=postgres-password="$POSTGRES_PASSWORD" \
  --from-literal=postgres-dsn="postgresql://framework_intelligence:$POSTGRES_PASSWORD@postgres:5432/framework_intelligence"
kubectl apply -k deploy/kubernetes
```

The image name is intentionally overrideable for the customer registry:

```sh
kustomize edit set image agentic-framework-intelligence-platform=registry.local/agentic-platform@sha256:<digest>
```

Do not commit rendered Secrets or registry credentials. Production overlays
must use an immutable image digest and a CSI/Vault-backed secret provider.
