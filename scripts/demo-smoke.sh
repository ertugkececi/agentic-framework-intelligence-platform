#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
: "${API_KEY:?API_KEY is required}"
: "${GRAFANA_ADMIN_USER:?GRAFANA_ADMIN_USER is required}"
: "${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}"

rm -rf .poc-docker/demo-repository .poc-docker/demo-workspace
mkdir -p .poc-docker/demo-workspace
cp -R examples/sample_customer_repo .poc-docker/demo-repository

request() { curl --fail --silent --show-error "$@"; }
json_assert() { python3 -c "import json,sys; d=json.load(sys.stdin); assert $1"; }

request http://127.0.0.1:8000/health | json_assert "d['status'] == 'ok'"
SCOPE='"framework_id":"sample-framework","framework_version_id":"1.0","project_id":"demo"'
LEARN=$(request -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" \
  -d "{${SCOPE},\"repository\":\"demo-repository\",\"workspace\":\"demo-workspace\"}" \
  http://127.0.0.1:8000/learn)
printf '%s' "$LEARN" | json_assert "d['status'] == 'succeeded' and d['rules_persisted'] > 0"
VECTOR=$(python3 -c 'import json; print(json.dumps([0.0]*384))')
RUN=$(request -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json" \
  -d "{${SCOPE},\"repository\":\"demo-repository\",\"workspace\":\"demo-workspace\",\"task\":\"Create InvoiceService with method run()\",\"query_vector\":${VECTOR}}" \
  http://127.0.0.1:8000/run)
printf '%s' "$RUN" | json_assert "d['status'] == 'succeeded' and d['generated_files']"
printf '%s' "$RUN" | python3 -c 'import json,sys; from pathlib import Path; d=json.load(sys.stdin); root=Path(".poc-docker/demo-repository"); missing=[x for x in d["generated_files"] if not (root/x).is_file()]; assert not missing, missing; print("generated file read-back:", *d["generated_files"])'

NOW=$(python3 -c 'import time; print(time.time_ns())')
request -H "Content-Type: application/json" -d "{\"resourceSpans\":[{\"resource\":{\"attributes\":[{\"key\":\"service.name\",\"value\":{\"stringValue\":\"demo-smoke\"}}]},\"scopeSpans\":[{\"spans\":[{\"traceId\":\"0123456789abcdef0123456789abcdef\",\"spanId\":\"0123456789abcdef\",\"name\":\"authenticated-run\",\"kind\":1,\"startTimeUnixNano\":\"${NOW}\",\"endTimeUnixNano\":\"${NOW}\"}]}]}]}" http://127.0.0.1:4318/v1/traces >/dev/null
request -H "Content-Type: application/json" -d "{\"resourceLogs\":[{\"resource\":{\"attributes\":[{\"key\":\"service.name\",\"value\":{\"stringValue\":\"demo-smoke\"}}]},\"scopeLogs\":[{\"logRecords\":[{\"timeUnixNano\":\"${NOW}\",\"body\":{\"stringValue\":\"demo-smoke-complete\"}}]}]}]}" http://127.0.0.1:4318/v1/logs >/dev/null
request -H "Content-Type: application/json" -d "{\"resourceMetrics\":[{\"resource\":{\"attributes\":[{\"key\":\"service.name\",\"value\":{\"stringValue\":\"demo-smoke\"}}]},\"scopeMetrics\":[{\"metrics\":[{\"name\":\"demo_runs_total\",\"sum\":{\"aggregationTemporality\":2,\"isMonotonic\":true,\"dataPoints\":[{\"asInt\":\"1\",\"timeUnixNano\":\"${NOW}\"}]}}]}]}]}" http://127.0.0.1:4318/v1/metrics >/dev/null
sleep 8
request http://127.0.0.1:9090/api/v1/targets | json_assert "d['status'] == 'success' and any(x['health'] == 'up' for x in d['data']['activeTargets'])"
request 'http://127.0.0.1:9090/api/v1/query?query=demo_runs_total' | json_assert "d['status'] == 'success' and d['data']['result']"
request 'http://127.0.0.1:3200/api/search?tags=service.name%3Ddemo-smoke' | json_assert "d.get('traces')"
request -G --data-urlencode 'query={service_name="demo-smoke"}' --data-urlencode 'limit=10' http://127.0.0.1:3100/loki/api/v1/query_range | json_assert "d['status'] == 'success' and d['data']['result']"
for uid in prometheus loki; do
  request -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" "http://127.0.0.1:3000/api/datasources/uid/${uid}/health" | json_assert "d.get('status') == 'OK'"
done
request -u "${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}" "http://127.0.0.1:3000/api/datasources/proxy/uid/tempo/api/search?tags=service.name%3Ddemo-smoke" | json_assert "d.get('traces')"
printf 'CANLI DEMO SMOKE: PASS\n'
