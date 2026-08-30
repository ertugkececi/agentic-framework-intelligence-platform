# On-prem Kubernetes deployment

This base deploys the API, PostgreSQL 16, Qdrant, an OpenTelemetry
Collector, durable Prometheus metrics, Tempo traces, and Loki logs backends into
the dedicated `framework-intelligence` namespace. Services are cluster-private, persistent,
and protected by default-deny network policies. The API exports OTLP only to the
collector through explicit pod-to-pod network policy rules. Prometheus scrapes the
collector's metrics endpoint through a dedicated least-privilege policy, retains
15 days of metrics on its own persistent volume, and has no API or database access.
The collector sends traces over namespace-local OTLP to Tempo, which retains 14 days
of trace blocks on its own persistent volume and accepts ingestion only from the
collector. The collector also exports OTLP logs to Loki, which retains 14 days
of logs on a dedicated persistent volume and accepts ingestion only from the collector.

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

Do not commit rendered Secrets or registry credentials. The collector image is
pinned to its verified multi-architecture manifest digest.
Production overlays must use an immutable image digest and a CSI/Vault-backed secret provider.
