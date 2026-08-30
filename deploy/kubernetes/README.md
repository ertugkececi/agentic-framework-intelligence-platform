# On-prem Kubernetes deployment

This base deploys the API, PostgreSQL 16, Qdrant, an OpenTelemetry
Collector, durable Prometheus metrics, Tempo traces, Loki logs, and a durable
Grafana frontend into the dedicated `framework-intelligence` namespace. Services
are cluster-private, persistent,
and protected by default-deny network policies. The API exports OTLP only to the
collector through explicit pod-to-pod network policy rules. Prometheus scrapes the
collector's metrics endpoint through a dedicated least-privilege policy, retains
15 days of metrics on its own persistent volume, and has no API or database access.
The collector sends traces over namespace-local OTLP to Tempo, which retains 14 days
of trace blocks on its own persistent volume and accepts ingestion only from the
collector. The collector also exports OTLP logs to Loki, which retains 14 days
of logs on a dedicated persistent volume and accepts ingestion only from the collector.
Grafana provisions all three backends as immutable data sources, persists its local
state, disables anonymous access and self-registration, and can egress only to those
backends. Its cluster-private service must be exposed through a customer-approved
Ingress, service mesh, or `kubectl port-forward` path.

For local evaluation, provision the referenced secret outside Git before applying the base:

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

Do not commit rendered Secrets or registry credentials. The collector and Grafana
images are pinned to verified multi-architecture manifest digests.
## Production overlay

`../overlays/production` inherits the complete base, pins the API image by digest,
and replaces literal Secret provisioning with the Secrets Store CSI Driver and
the HashiCorp Vault provider. The checked-in `registry.example.invalid` image is
intentionally non-routable: promotion must fail closed until an operator replaces
both the registry and digest with the verified customer image.

Prerequisites:

- Secrets Store CSI Driver with Kubernetes Secret synchronization enabled
- HashiCorp Vault CSI provider
- TLS-reachable Vault service at the configured `vaultAddress`
- Vault Kubernetes auth role `framework-intelligence` authorized only for
  `secret/data/framework-intelligence/runtime`
- The five keys declared in `secret-provider.json`

Promote and render from a clean checkout without committing credentials:

```sh
cd deploy/overlays/production
kustomize edit set image \
  agentic-framework-intelligence-platform=registry.customer.local/agentic-platform@sha256:<verified-digest>
kustomize build . > /tmp/agentic-platform-production.yaml
kubectl apply --server-side --dry-run=server -f /tmp/agentic-platform-production.yaml
kubectl apply --server-side -f /tmp/agentic-platform-production.yaml
```

The CSI volume is read-only. Vault values are synchronized into the existing
`agentic-platform-secrets` contract so no credential value appears in Kustomize,
source control, pod arguments, or ConfigMaps. Adjust Vault address, role and path
as deployment metadata; never replace identifier fields with resolved values.
