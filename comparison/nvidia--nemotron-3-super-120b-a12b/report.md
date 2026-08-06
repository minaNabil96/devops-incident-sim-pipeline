# SRE Incident Simulation Report

## Unknown — Incident Report

---

## Stage 0: Scenario

**SecureBank Pro – Incident Scenario**  
*Affected Service: `payment-gateway-service`*  

---  

### 1. System Overview  
SecureBank Pro is a cloud‑native digital banking platform that enables retail and corporate customers to perform real‑time payments, fund transfers, and bill‑pay services via web, mobile, and API channels. The platform serves **≈2.3 million active users** and processes an average of **≈12 million payment transactions per day** with a target SLA of **≤200 ms latency** for 99.9 % of requests.  

### 2. Architecture Summary  
| Layer | Component | Technology |
|-------|-----------|------------|
| **API Edge** | API Gateway (AWS ALB) + AuthN/Z service | Envoy, OIDC |
| **Core Services** | `payment-gateway-service` (receives & validates payment requests) | Python 3.11, FastAPI |
| | `account‑service` (customer & account data) | Python/FastAPI |
| | `fraud‑detection-service` (real‑time risk scoring) | Python/FastAPI, ML model server |
| | `notification‑service` (SMS/email/push) | Python/FastAPI |
| **Data Stores** | Primary transaction store | PostgreSQL 14 (primary‑replica, 3‑node) |
| | Session & rate‑limit cache | Redis 7 (cluster mode, 3 shards) |
| | Event streaming | Apache Kafka (managed MSK) |
| **Observability** | Metrics collection & alerting | Prometheus + Grafana |
| | Log aggregation | Elasticsearch + Kibana |
| | Incident routing | PagerDuty |
| **Orchestration** | Container platform | Amazon EKS (Kubernetes 1.27) |
| | Service mesh (optional) | Istio (sidecar injection) |
| | CI/CD | GitHub Actions → Argo CD (GitOps) |

### 3. Current Conditions  
- **Traffic Load:** Over the past 30 minutes, inbound request rate to `payment-gateway-service` has risen from the baseline **≈4 k req/s** to **≈9 k req/s**, a ~125 % increase.  
- **Recent Deployments:**  
  - **v2.4.1** of `payment-gateway-service` was rolled out 2 hours ago (feature flag for a new “instant‑settlement” endpoint).  
  - No changes to Redis configuration or PostgreSQL schema in the last 24 h.  
- **Observed Anomalies:**  
  - **Prometheus alerts:** `redis_memory_used_bytes` > 85 % of cluster capacity, triggering a **Critical** alert.  
  - **Grafana dashboards:** Payment success rate dropped from **99.8 %** to **92.5 %**; average latency spiked from **120 ms** to **≈620 ms** for the affected endpoint.  
  - **PagerDuty:** Incident opened for `payment-gateway-service` latency and error‑rate thresholds.  
  - **Application logs:** Increased frequency of `429 Too Many Requests` responses from the rate‑limiting middleware, followed by `500 Internal Server Error` when downstream Redis calls fail with `OOM command not allowed when used memory > 'maxmemory'`.  

### 4. Service Dependencies (payment‑gateway‑service)  
| Direction | Service / Component | Purpose | Communication Protocol |
|-----------|---------------------|---------|------------------------|
| **Upstream** | API Gateway (ALB) | Terminates TLS, performs basic auth, forwards requests | HTTP/1.1 + HTTP/2 |
| | AuthN/Z service | Validates JWT/OAuth2 tokens, extracts user‑ID & roles | gRPC (internal) |
| | Fraud‑detection-service | Calls risk‑scoring model before accepting payment | gRPC |
| | Account‑service | Retrieves account balances, verifies destination account | REST/JSON over HTTP |
| **Downstream** | PostgreSQL (primary) | Persists payment transaction records, updates balances | libpq (asyncpg) |
| | Redis (cluster) | Stores short‑lived rate‑limit counters, idempotency keys, session tokens | redis‑py (async) |
| | Kafka (MSK) | Publishes `payment.created` events for downstream settlement & reporting | Protobuf over TCP |
| | Notification‑service | Sends payment confirmation via SMS/email/push (async) | HTTP webhook (via Kafka consumer) |
| | Monitoring Sidecar (Prometheus exporter) | Exposes `process_*`, `http_request_*`, `redis_*` metrics | HTTP scrape |

---  

*This scenario captures the observable symptoms, recent changes, and inter‑service relationships without revealing the underlying root cause.*

---

## Stage 1: Alert

```json
{
  "receiver": "pagerduty",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "namespace": "production",
        "service": "payment-gateway-service",
        "job": "payment-gateway",
        "instance": "10.0.1.23:8080",
        "pod": "payment-gateway-service-5d7c9f6b7c-abcde",
        "container": "payment-gateway"
      },
      "annotations": {
        "summary": "High error rate detected on payment-gateway-service",
        "description": "Error rate > 5% for the last 5m, current value 7.8%. Latency increased to 620ms. Redis OOM causing failures.",
        "runbook_url": "https://runbooks.securebank.pro/payment-gateway-high-error-rate",
        "dashboard_url": "https://grafana.securebank.pro/d/payment-gateway-overview"
      },
      "startsAt": "2025-09-24T14:35:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "http://prometheus.securebank.pro:9090/graph?g0.expr=rate(http_requests_total%7Bjob%3D%22payment-gateway%22%2Cstatus%3D%5E5

---

## Stage 2: Triage

**Acknowledgment & Goal**  
I see the firing alert for **payment-gateway-service** with a critical error rate (>5%) and elevated latency. The immediate goal is to confirm the symptoms, identify any abnormal resource or container state, and gather enough evidence to decide where to look next (e.g., logs).

---

### Investigation Steps (Socratic style)

| # | Question (instead of a command) | Expected Output Description | Rationale |
|---|----------------------------------|-----------------------------|-----------|
| 1 | **What does the error rate and request latency look like for the payment‑gateway service over the last 5 minutes?** | A time‑series showing `rate(http_requests_total{...}[5m])` for 5xx responses > 5 % and a latency histogram or average latency around 620 ms. | Confirms the alert’s symptom, establishes a baseline, and rules out transient spikes. |
| 2 | **Are any payment‑gateway pods reporting increased restart counts or OOMKilled events?** | `kubectl get pods -n production -l app=payment-gateway` showing `RESTARTS` > 0, or `kubectl describe pod …` revealing `State: Terminated` with reason `OOMKilled`. | Helps determine if container crashes or resource limits are contributing to the error surge. |
| 3 | **How have CPU and memory usage trended for the payment‑gateway pods and their underlying nodes in the past 10 minutes?** | Metrics (e.g., from Prometheus or Grafana) displaying memory utilization approaching request/limit thresholds, and CPU usage patterns that correlate with the error spike. | Links resource pressure to the observed failures, guiding whether the issue is likely due to exhaustion, throttling, or contention. |

---

**Open question to lead into log analysis:**  
When you examine the application logs for the payment‑gateway service around the time the error rate began to rise, what patterns or recurring messages do you notice?

---

## Stage 3: Rca

**ARTIFACTS**

```
2025-09-24T11:55:00Z {"level":"INFO","msg":"Payment gateway started","service":"payment-gateway","instance":"pod-7f9c2"}
2025-09-24T11:56:10Z {"level":"INFO","msg":"Health check passed","service":"payment-gateway","instance":"pod-7f9c2"}
2025-09-24T11:57:05Z {"level":"INFO","msg":"Processed 120 payment requests","service":"payment-gateway","instance":"pod-7f9c2","duration_ms":85}
2025-09-24T11:58:20Z {"level":"WARN","msg":"Request rate approaching threshold","service":"payment-gateway","instance":"pod-7f9c2","rate_per_sec":48}
2025-09-24T11:59:00Z {"level":"WARN","msg":"High number of distinct client IPs observed","service":"payment-gateway","instance":"pod-7f9c2","unique_ips_last_min":42}
2025-09-24T11:59:30Z {"level":"WARN","msg":"Redis connection latency increased","service":"payment-gateway","instance":"pod-7f9c2","redis_latency_ms":210}
2025-09-24T12:00:00Z {"level":"ERROR","msg":"Failed to acquire Redis connection","service":"payment-gateway","instance":"pod-7f9c2","error":"redis: connection refused"}
2025-09-24T12:00:10Z {"level":"ERROR","msg":"Payment processing failed due to cache miss","service":"payment-gateway","instance":"pod-7f9c2","payment_id":"pay_9a3b","reason":"cache_lookup_failed"}
2025-09-24T12:00:20Z {"level":"ERROR","msg":"HTTP 5xx response surge","service":"payment-gateway","instance":"pod-7f9c2","status":"500","count_per_min":57}
2025-09-24T12:00:30Z {"level":"ERROR","msg":"Pod memory usage near limit","service":"payment-gateway","instance":"pod-7f9c2","memory_usage_bytes":1073741824,"memory_limit_bytes":1073741824}
2025-09-24T12:00:40Z metric container_memory_usage_bytes{pod="payment-gateway-7f9c2",namespace="production"} 1.07e+09 1737772840
2025-09-24T12:00:45Z metric redis_used_bytes{instance="redis-cache-01",namespace="production"} 5.12e+09 1737772845
2025-09-24T12:00:50Z metric http_requests_total{service="payment-gateway",code=~"5.."} 57 1737772850
2025-09-24T12:00:55Z metric redis_connected_clients{instance="redis-cache-01",namespace="production"} 210 1737772855
```

**ANALYSIS**

- The service begins with normal operation (INFO logs) and processes a modest volume of payment requests with low latency.  
- Around 11:58 – 11:59 WARN entries indicate a rising request rate (approaching 50 req/s) and a noticeable increase in distinct client IPs, suggesting a surge in traffic from many sources.  
- Shortly after, Redis‑related warnings appear: connection latency climbs and then errors show “connection refused” and cache‑lookup failures, coinciding with a spike in HTTP 5xx responses.  
- Memory metrics reveal the payment‑gateway pod’s memory usage hitting its limit, while the Redis instance reports high used memory and a large number of connected clients.  
- The progression from INFO → WARN → ERROR aligns with a traffic surge that overwhelms the cache layer, leading to resource exhaustion and failed payment processing.

**NEXT STEP**

- What is the current eviction rate and memory fragmentation ratio for the Redis instance used by the payment‑gateway service, and are there any signs of OOMKilled events or restart loops in the Redis pods?

---

## Stage 4: Remediation

**HORIZON: Immediate (0‑5 min)**  
**Strategy:** Retrieve the current Redis eviction rate and memory fragmentation ratio, and verify whether the Redis pods have experienced OOMKilled events or restart loops.

```bash
# Step 1: Identify the Redis pod(s) in the production namespace
kubectl get pods -n production -l app=redis-cache --no-headers -o custom-columns="NAME:.metadata.name"

# Step 2: Store the pod name(s) for later use (assuming a single pod redis-cache-01)
REDIS_POD=$(kubectl get pods -n production -l app=redis-cache -o jsonpath='{.items[0].metadata.name}')
echo "Redis pod: $REDIS_POD"

# Step 3: Capture initial Redis INFO metrics (evicted_keys, used_memory, mem_fragmentation_ratio)
kubectl exec -n production "$REDIS_POD" -- redis-cli INFO | grep -E 'evicted_keys|used_memory|mem_fragmentation_ratio' > /tmp/redis_info_initial.txt
cat /tmp/redis_info_initial.txt

# Step 4: Wait a short interval (10 s) to compute a rate
sleep 10

# Step 5: Capture Redis INFO metrics again after the interval
kubectl exec -n production "$REDIS_POD" -- redis-cli INFO | grep -E 'evicted_keys|used_memory|mem_fragmentation_ratio' > /tmp/redis_info_later.txt
cat /tmp/redis_info_later.txt

# Step 6: Calculate eviction rate (evicted_keys per second)
EVIC_INIT=$(awk -F: '/evicted_keys/ {print $2}' /tmp/redis_info_initial.txt | tr -d ' ')
EVIC_LATER=$(awk -F: '/evicted_keys/ {print $2}' /tmp/redis_info_later.txt | tr -d ' ')
EVIC_RATE=$(( (EVIC_LATER - EVIC_INIT) / 10 ))
echo "Eviction rate: $EVIC_RATE keys/sec"

# Step 7: Extract memory fragmentation ratio (latest value)
FRAG_INIT=$(awk -F: '/mem_fragmentation_ratio/ {print $2}' /tmp/redis_info_initial.txt | tr -d ' ')
FRAG_LATER=$(awk -F: '/mem_fragmentation_ratio/ {print $2}' /tmp/redis_info_later.txt | tr -d ' ')
# Use the later value as the current ratio
echo "Memory fragmentation ratio: $FRAG_LATER"

# Step 8: Check Redis pod restart count
kubectl get pod "$REDIS_POD" -n production -o jsonpath='{.status.containerStatuses[0].restartCount}'
echo "Restart count: $(kubectl get pod "$REDIS_POD" -n production -o jsonpath='{.status.containerStatuses[0].restartCount}')"

# Step 9: Look for OOMKilled events in the pod's recent events
kubectl get events -n production --field-selector involvedObject.name="$REDIS_POD" | grep -i OOMKilled || echo "No OOMKilled events found."
```

**Rollback:**  
No changes are made in this horizon; therefore no rollback is required. If any diagnostic command were to be altered in the future, re‑run the same steps to verify the state returned to baseline.  

```bash
# No rollback needed – diagnostics only
```

---

## Stage 5: Communication

:mag: *Investigating Redis performance* (production namespace)

- Identified pod: `redis-cache-01`
- Captured initial INFO metrics (evicted_keys, used_memory, mem_fragmentation_ratio)
- Waiting 10 s to compute eviction rate
- Next: calculate eviction rate, check fragmentation ratio, restart count, and look for OOMKilled events

Stay tuned for the results.

---

## Stage 6: Postmortem

# Post‑mortem: Payment‑Gateway Service Incident  
**Date:** 2025‑09‑24  
**Duration:** 28 minutes (exact)  

---

## 1. Metadata  

| Field | Value |
|-------|-------|
| **Service** | `payment-gateway-service` |
| **Date** | 2025‑09‑24 |
| **Severity** | Critical |
| **Duration** | 28 minutes |
| **Status** | Resolved |
| **On‑call Team** | Platform Reliability Team (SRE) |

---

## 2. Executive Summary  

At 14:35 UTC a Prometheus alert fired for a critical error rate (>5 %) and elevated latency on the `payment-gateway-service`. Investigation revealed a sudden traffic surge (≈9 k req/s, up from 4 k req/s) caused by the rollout of feature flag **v2.4.1 – instant‑settlement endpoint**. The surge exhausted the Redis cache layer, triggering OOM conditions, connection refusals, and cache‑lookup failures. This caused HTTP 5xx responses, raising the error rate to 7.8% and latency to ~620 ms. The incident was mitigated by scaling Redis, adjusting memory limits, and restarting affected payment‑gateway pods. Service returned to SLA (<200 ms latency, >99.8 % success) by 15:03 UTC, and the alert auto‑resolved.  

---

## 3. Impact  

| Dimension | Detail |
|-----------|--------|
| **User‑facing** | Payment requests experienced latency spikes (120 ms → 620 ms) and a failure rate of ~7.8 %; users saw timeouts or error messages when attempting payments. |
| **Business** | Approx. 0.85 M payment requests failed during the 28‑minute window (≈7.8 % of ~10.9 M requests processed). Potential revenue impact and erosion of customer trust, though no financial data was lost. |
| **Duration** | 28 minutes (14:35 – 15:03 UTC). |
| **Services Affected** | `payment-gateway-service` (primary); downstream effects on `notification-service` (delayed confirmations) and `fraud‑detection-service` (reduced input volume). |

---

## 4. Timeline  

| Time (UTC) | Event | Detected By |
|------------|-------|--------------|
| 14:35:00 | Prometheus alert **HighErrorRate** fires (error > 5 %, latency ≈ 620 ms) | Prometheus → PagerDuty |
| 14:36:00 | On‑call engineer acknowledges incident in PagerDuty | SRE (Platform Reliability Team) |
| 14:38:00 | SRE observes rising latency & error rate on Grafana dashboard | SRE |
| 14:42:00 | Application logs show `Redis connection refused` and cache‑lookup failures | SRE (log analysis) |
| 14:45:00 | `redis-cli INFO` reveals used memory ≈ 85 % of cluster, eviction rate rising | SRE (Redis diagnostics) |
| 14:50:00 | Immediate remediation: scale Redis cluster (add shard), raise `maxmemory`, restart impacted payment‑gateway pods | Platform Engineering Team |
| 14:55:00 | Error rate begins to decline; latency trending downward | SRE |
| 15:00:00 | Success rate restored to >99.8 %; average latency <200 ms (SLA met) | SRE |
| 15:03:00 | Alert auto‑resolved; incident declared closed | PagerDuty (auto‑resolve) |

*The interval between the first and last timestamps is exactly 28 minutes.*

---

## 5. Root Cause Analysis  

The primary cause was **resource exhaustion of the Redis cache layer** triggered by an unanticipated traffic surge:

1. **Traffic surge** – The rollout of v2.4.1 introduced the *instant‑settlement* feature flag, which doubled the request rate for the payment‑gateway endpoint (from ~4 k to ~9 k req/s) within 30 minutes.  
2. **Insufficient Redis capacity** – The Redis cluster was provisioned for baseline load; its `maxmemory` limit was reached (~5.12 GB used, 85 % of total) as the surge filled the cache with rate‑limit counters and idempotency keys.  
3. **Aggressive eviction policy** – The instance used the default `volatile-lru` policy, which only evicts keys with an expiry set. Many rate‑limit keys lacked expiry, causing memory to fill until the OOM condition (`OOM command not allowed when used memory > 'maxmemory'`).  
4. **Cache miss → downstream failures** – When Redis refused new connections, the payment‑gateway service fell back to a cache‑miss path, leading to failed payment processing, HTTP 5xx responses, and the observed error‑rate spike.  

Thus, the incident stemmed from a combination of **unvalidated feature‑flag traffic** and **inadequate cache capacity planning**.

---

## 6. Contributing Factors  

| Factor | Explanation |
|--------|-------------|
| **Feature‑flag rollout without load testing** | The instant‑settlement flag was enabled globally without a staged canary or performance test at 2× peak load. |
| **Static Redis memory allocation** | No vertical/horizontal autoscaling policy for Redis; memory limits were set based on historical averages. |
| **Missing Redis memory‑fragmentation alert** | No alert on `mem_fragmentation_ratio`; rising fragmentation contributed to effective memory pressure. |
| **Rate‑limiting fallback logic** | Upon receiving `429 Too Many Requests`, the service attempted to write a new rate‑limit key to Redis; when Redis was unavailable, the request proceeded without rate‑limit protection, exacerbating load. |
| **Insufficient circuit breaker** | Calls to Redis lacked a circuit‑breaker pattern, causing repeated connection attempts that worsened Redis load and delayed failure detection. |
| **Observability gap** | While Redis used memory was monitored, the eviction rate and fragmentation ratio were not surfaced in dashboards, delaying early detection. |

---

## 7. Action Items  

Exactly **4** SMART items (Specific, Measurable, Achievable, Relevant, Time‑bound).

| ID | Description | Owner | Priority | Due Date |
|----|-------------|-------|----------|----------|
| **AI-001** | Implement **

---
