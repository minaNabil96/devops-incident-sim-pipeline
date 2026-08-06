# SRE Incident Simulation Report

## Unknown — Incident Report

---

## Stage 0: Scenario

```markdown
# **SecureBank Pro Incident Scenario: Payment Gateway Service Degradation**

## **1. System Overview**
**Application Purpose:**
SecureBank Pro is a high-availability digital banking platform serving retail and corporate customers across North America and Europe. The platform processes **~10,000 transactions/minute** at peak, with **99.95% uptime SLA** for payment operations. Key features include:
- Real-time payment processing (ACH, wire, card)
- Fraud detection and rate limiting
- Multi-currency support
- PCI-DSS compliant transaction handling

**User Base:**
- **5M+ active retail users**
- **20K+ corporate clients**
- **Peak traffic:** Weekdays 9 AM–5 PM (EST), with spikes during payroll cycles (1st/15th of the month).

---

## **2. Architecture Summary**
### **Microservices**
| Service | Purpose | Tech Stack |
|---------|---------|------------|
| `payment-gateway-service` | Handles payment routing, validation, and fraud checks | Python/FastAPI, Redis (caching), PostgreSQL (persistent storage) |
| `auth-service` | JWT/OAuth2 token validation | Python/FastAPI, Redis (session cache) |
| `fraud-detection-service` | ML-based anomaly scoring | Python, TensorFlow, Kafka |
| `transaction-ledger-service` | Immutable transaction logging | Java/Spring Boot, PostgreSQL |
| `notification-service` | Email/SMS alerts | Node.js, SQS |

### **Databases & Caches**
- **PostgreSQL 14** (Multi-AZ, RDS):
  - Primary: `payment-db` (transactions, user accounts)
  - Replica: Read scaling for analytics
- **Redis 7** (ElastiCache Cluster):
  - Cache layer for `payment-gateway-service` (rate limiting, session tokens)
  - **Memory limit:** 16GB per node (3-node cluster)

### **Message Queues**
- **Kafka** (MSK): Fraud detection events, transaction logs
- **SQS**: Async notifications (e.g., payment receipts)

### **Orchestration**
- **Kubernetes 1.27 (EKS):**
  - `payment-gateway-service` runs as a **Deployment** (5 replicas) with **HPA** (CPU target: 70%)
  - **Resource limits:** 2 vCPU, 4GB RAM per pod
  - **Ingress:** ALB with WAF (rate limiting: 10 req/sec/IP)

---

## **3. Current Conditions**
### **Load & Traffic**
- **Baseline:** ~8,000 TPS (transactions per second)
- **Current:** **12,500 TPS** (↑56% from baseline)
- **Error Rate:** **42%** (↑ from 0.1% baseline) for `payment-gateway-service`
- **Latency:** P99 latency **8.2s** (↑ from 200ms baseline)

### **Recent Deployments**
| Timestamp (UTC) | Service | Change | Deployed By |
|-----------------|---------|--------|-------------|
| 2023-11-15 08:45 | `payment-gateway-service` | v2.4.1: Added new fraud rule engine | CI/CD Pipeline |
| 2023-11-15 07:30 | `auth-service` | v1.9.2: Token refresh logic fix | DevOps Team |

### **Anomalies Detected**
- **Prometheus Alerts (Last 30 min):**
  - `redis_memory_usage_bytes` **> 15GB** (↑ from 6GB baseline)
  - `payment_gateway_5xx_errors` **spiked to 3,200/min**
  - `kube_pod_restarts` for `payment-gateway-service` **= 12** (0 baseline)
- **Grafana Dashboards:**
  - Redis **eviction rate**: **5,000 keys/sec** (↑ from 0)
  - `payment-gateway-service` **CPU**: **95%** (↑ from 60%)
- **PagerDuty Incidents:**
  - **#INC-2023-1115-001**: "High payment failure rate" (triggered at 09:12 UTC)
  - **#INC-2023-1115-002**: "Redis cluster memory critical" (triggered at 09:15 UTC)

### **User Impact**
- **Symptoms:**
  - **50% of payment requests fail** with `503 Service Unavailable` or `429 Too Many Requests`
  - **Corporate batch payments** (high-value) timing out
  - **Mobile app** shows "Payment processing delayed" for 30% of users
- **Geographic Scope:** Global (no region-specific outage)

---

## **4. Service Dependencies**
### **Upstream Services (Calls `payment-gateway-service`)**
| Service | Dependency Type | Criticality |
|---------|-----------------|-------------|
| `mobile-app` | REST API (POST /payments) | High |
| `web-portal` | REST API (POST /payments) | High |
| `corporate-batch-service` | gRPC (bulk payments) | High |
| `third-party-integrations` | Webhooks (Stripe, PayPal) | Medium |

### **Downstream Services (Called by `payment-gateway-service`)**
| Service | Purpose | Protocol | Criticality |
|---------|---------|----------|-------------|
| `auth-service` | Validate JWT tokens | HTTP (internal) | **Critical** (blocks all payments if down) |
| `fraud-detection-service` | Risk scoring | Kafka (async) | High |
| `transaction-ledger-service` | Persist transactions | HTTP (sync) | **Critical** |
| **PostgreSQL (`payment-db`)** | Store transaction metadata | PostgreSQL | **Critical** |
| **Redis (`payment-cache`)** | Rate limiting, session cache | Redis | **Critical** |
| **SQS** | Queue payment confirmations | AWS SDK | Medium |

### **Dependency Flow for a Payment Request**
```
mobile-app → [ALB] → payment-gateway-service → auth-service (sync)
                                      ↘ fraud-detection-service (async)
                                      → transaction-ledger-service (sync)
                                      → PostgreSQL (sync)
                                      → Redis (rate limiting/cache)
```

---
**Note:** All timestamps in UTC. Incident declared at **09:15 UTC**.
```

---

## Stage 1: Alert

```json
{
  "receiver": "SecureBank-Pro-PagerDuty",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighPaymentGatewayErrorRate",
        "severity": "critical",
        "namespace": "production",
        "service": "payment-gateway-service",
        "pod": "payment-gateway-service-7c8d9f4b5-abcde",
        "job": "payment-gateway-service",
        "instance": "10.0.1.123:8080",
        "cluster": "securebank-prod-eks",
        "region": "us-east-1",
        "environment": "production",
        "team": "payments"
      },
      "annotations": {
        "summary": "High error rate in payment-gateway-service (42% failures, P99 latency 8.2s)",
        "description": "The payment-gateway-service is experiencing a critical degradation with 42% error rate (baseline: 0.1%) and P99 latency of 8.2s (baseline: 200ms). Current TPS: 12,500 (↑56% from baseline). Redis memory usage is at 15.2GB (↑ from 6GB), causing high eviction rates (5,000 keys/sec). Pod restarts detected (12 in last 30 min).",
        "dashboard": "https://grafana.securebank.pro/d/securebank-payments?orgId=1&from=now-1h&to=now&var-service=payment-gateway-service",
        "runbook": "https://wiki.securebank.pro/runbooks/payment-gateway-degradation",
        "impact": "50% of payment requests failing with 503/429 errors. Corporate batch payments and mobile app transactions are affected globally.",
        "severity": "critical",
        "timestamp": "2023-11-15T09:15:00Z",
        "generatorURL": "http://prometheus.securebank.pro:9090/graph?g0.range_input=1h&g0.expr=rate(payment_gateway_http_requests_total%7Bstatus%3D~%225..%22%7D%5B5m%5D)%20%2F%20rate(payment_gateway_http_requests_total%5B5m%5D)&g0.tab=0"
      },
      "startsAt": "2023-11-15T09:12:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "http://prometheus.securebank.pro:9090/graph?g0.range_input=1h&g0.expr=rate(payment_gateway_http_requests_total%7Bstatus%3D~%225..%22%7D%5B5m%5D)%20%2F%20rate(payment_gateway_http_requests_total%5B5m%5D)&g0.tab=0"
    }
  ],
  "groupLabels": {
    "alertname": "HighPaymentGatewayErrorRate",
    "namespace": "production",
    "severity": "critical"
  },
  "commonLabels": {
    "alertname": "HighPaymentGatewayErrorRate",
    "namespace": "production",
    "severity": "critical",
    "service": "payment-gateway-service",
    "team": "payments"
  },
  "commonAnnotations": {
    "summary": "High error rate in payment-gateway-service (42% failures, P99 latency 8.2s)",
    "description": "Critical degradation in payment-gateway-service with high error rates and latency. Redis memory pressure and pod restarts observed.",
    "dashboard": "https://grafana.securebank.pro/d/securebank-payments?orgId=1&from=now-1h&to=now&var-service=payment-gateway-service",
    "runbook": "https://wiki.securebank.pro/runbooks/payment-gateway-degradation"
  },
  "externalUrl": "https://pagerduty.securebank.pro/incidents/INC-2023-1115-001",
  "version": "4",
  "groupKey": "{}:{alertname=\"HighPaymentGatewayErrorRate\", namespace=\"production\", severity=\"critical\"}"
}
```

---

## Stage 2: Triage

### **Alert Acknowledgment & Primary Goal**
**Acknowledged**: Critical degradation in `payment-gateway-service` with **42% error rate** (baseline: 0.1%), **P99 latency 8.2s** (baseline: 200ms), and **Redis memory pressure** (15.2GB, high eviction rates).
**Primary Goal**: *Identify the root cause of the degradation* by systematically isolating the bottleneck (application, database, cache, or infrastructure).

---

---

### **Investigation Steps (Socratic Mode)**

#### **Step 1: Verify Current System Load & Resource Saturation**
**Question**:
*What metrics would you check first to confirm whether the issue is driven by resource exhaustion (CPU, memory, I/O) or external dependencies?*
**Hint**:
- Think about the **4 golden signals** (latency, traffic, errors, saturation).
- Focus on the **pod**, **Redis**, and **PostgreSQL** layers.

**Rationale**:
Resource saturation (e.g., CPU throttling, OOM kills, disk I/O) can directly cause high latency and errors. Redis evictions suggest memory pressure, but we need to confirm if this is the *primary* or *secondary* effect.

---

#### **Step 2: Correlate Errors with Dependency Behavior**
**Question**:
*How would you determine if the 503/429 errors are originating from the application, Redis, or PostgreSQL?*
**Hint**:
- Check **error logs** for patterns (e.g., timeouts, connection refusals).
- Look for **dependency-specific metrics** (e.g., Redis `rejected_connections`, PostgreSQL `wait_event_type`).

**Rationale**:
503s often indicate upstream failures (e.g., Redis/PostgreSQL timeouts), while 429s suggest rate limiting. Distinguishing these helps narrow the scope to a specific layer.

---
---
#### **Step 3: Analyze Request Flow & Latency Breakdown**
**Question**:
*What tool or command would you use to trace a single slow request (P99 latency) end-to-end, from the pod to Redis/PostgreSQL?*
**Hint**:
- Consider **distributed tracing** (e.g., Jaeger, OpenTelemetry) or **per-request logs**.
- Look for **blocking operations** (e.g., Redis `BLPOP`, PostgreSQL long-running queries).

**Rationale**:
P99 latency spikes often hide in **synchronous dependencies**. Tracing a single request reveals where time is spent (e.g., Redis blocking calls, N+1 queries).

---
---
### **Open Question for Log Analysis**
*If you observed a sudden spike in Redis `evicted_keys` and PostgreSQL `lock_waits` at the same time the error rate increased, what would be your next investigation step—and why?*

---

## Stage 3: Rca

---

### **SECTION 1 — ARTIFACTS**

```json
{"timestamp": "2023-11-15T10:00:00Z", "level": "INFO", "service": "payment-gateway-service", "message": "Request processed", "latency_ms": 180, "status": 200, "redis_hit": true, "ip": "192.168.1.100"}
{"timestamp": "2023-11-15T10:05:00Z", "level": "INFO", "service": "payment-gateway-service", "message": "Request processed", "latency_ms": 220, "status": 200, "redis_hit": false, "ip": "192.168.1.101"}
{"timestamp": "2023-11-15T10:10:00Z", "level": "WARN", "service": "payment-gateway-service", "message": "Redis latency spike", "latency_ms": 1200, "redis_evicted_keys": 5, "ip": "10.0.0.1"}
{"timestamp": "2023-11-15T10:12:00Z", "level": "WARN", "service": "payment-gateway-service", "message": "High request volume from new IPs", "requests_per_sec": 45, "unique_ips": 23, "status": 200}
{"timestamp": "2023-11-15T10:15:00Z", "level": "ERROR", "service": "payment-gateway-service", "message": "Redis connection timeout", "latency_ms": 5000, "status": 503, "ip": "10.0.0.2"}
{"timestamp": "2023-11-15T10:16:00Z", "level": "WARN", "service": "redis", "message": "Memory usage critical", "used_memory": "14.8GB", "evicted_keys": 120, "rejected_connections": 3}
{"timestamp": "2023-11-15T10:18:00Z", "level": "ERROR", "service": "payment-gateway-service", "message": "PostgreSQL lock wait timeout", "latency_ms": 8200, "status": 503, "query": "SELECT * FROM transactions WHERE user_id = ?", "ip": "10.0.0.3"}
{"timestamp": "2023-11-15T10:20:00Z", "level": "ERROR", "service": "payment-gateway-service", "message": "Rate limit exceeded", "status": 429, "requests_per_sec": 58, "ip": "10.0.0.4"}
{"timestamp": "2023-11-15T10:22:00Z", "level": "ERROR", "service": "redis", "message": "OOM error, evicting keys", "evicted_keys": 340, "used_memory": "15.1GB"}
{"timestamp": "2023-11-15T10:25:00Z", "level": "ERROR", "service": "payment-gateway-service", "message": "PostgreSQL connection pool exhausted", "status": 503, "active_connections": 98, "max_connections": 100}
{"timestamp": "2023-11-15T10:28:00Z", "level": "WARN", "service": "payment-gateway-service", "message": "Unusual IP pattern detected", "unique_ips": 42, "requests_per_sec": 62, "status": 200}
{"timestamp": "2023-11-15T10:30:00Z", "level": "ERROR", "service": "payment-gateway-service", "message": "Redis command rejected", "status": 503, "error": "NOMEM", "ip": "10.0.0.5"}
{"timestamp": "2023-11-15T10:32:00Z", "level": "ERROR", "service": "postgresql", "message": "Long-running query detected", "duration_ms": 7500, "query": "UPDATE transactions SET status = 'completed' WHERE id IN (...)", "lock_waits": 15}
{"timestamp": "2023-11-15T10:35:00Z", "level": "ERROR", "service": "payment-gateway-service", "message": "Payment failure for user", "status": 500, "user_id": "legit_user_123", "error": "Cache miss, DB timeout"}
{"timestamp": "2023-11-15T10:40:00Z", "level": "CRITICAL", "service": "redis", "message": "Memory limit reached, evictions accelerating", "used_memory": "15.2GB", "evicted_keys": 1200}
```

---

### **SECTION 2 — ANALYSIS**

- **Timeline of Degradation**:
  - **10:00–10:10**: Normal operation with occasional Redis cache misses and slight latency increases.
  - **10:12–10:20**: Sudden spike in request volume from multiple new IPs, coinciding with Redis latency spikes and evictions. Error rates begin climbing (503s, 429s).
  - **10:22–10:30**: Redis memory pressure peaks (15.2GB), leading to OOM errors and rejected connections. PostgreSQL shows lock waits and connection pool exhaustion.
  - **10:35+**: Legitimate user requests start failing due to cache misses and database timeouts.

- **Key Anomalies**:
  - Unusually high **requests per second** (50+) from **distributed IPs** (42 unique) with no prior history.
  - **Redis evictions** and **OOM errors** correlate with the surge in traffic, suggesting memory pressure is a secondary effect of increased load.
  - **PostgreSQL lock waits** and **long-running queries** appear after Redis degradation, indicating cascading failures.
  - **429 errors** (rate limiting) are logged, but the traffic volume exceeds expected thresholds without clear rate-limiting enforcement.

- **Component Behavior**:
  - **Redis**: Memory usage grows rapidly, evictions accelerate, and commands are rejected (`NOMEM`).
  - **PostgreSQL**: Lock contention and connection pool exhaustion suggest increased query load, possibly due to cache misses.
  - **Application**: Errors shift from Redis timeouts to database failures, implying dependency failures are propagating upstream.

---

### **SECTION 3 — NEXT STEP**

*How would you verify whether the surge in requests from distributed IPs is bypassing the rate-limiting mechanism, and what logs or metrics would you examine to confirm this?*

---

## Stage 4: Remediation

Here’s a structured **immediate mitigation plan** to verify and address the rate-limiting bypass issue, with rollback steps for each action. The focus is on **low-risk, imperative steps** to contain the surge while preserving system stability.

---

### **HORIZON: Immediate (0–5 minutes)**
**Strategy**: Verify rate-limiting bypass by inspecting ingress logs and metrics, then temporarily block suspicious IPs at the ingress level.

#### **Commands**:
```bash
# Step 1: Check ingress controller logs for rate-limiting headers (e.g., X-RateLimit-Limit)
kubectl -n production logs -l app.kubernetes.io/name=ingress-nginx --tail=100 | grep -E "rate.limit|429|IP:10\.0\."

# Step 2: Check Prometheus/Grafana for request rates per IP (if metrics are exposed)
kubectl -n production exec -it prometheus-0 -- curl -s "http://localhost:9090/api/v1/query?query=sum(rate(nginx_ingress_controller_requests_total{status=~\"429|503\"}[5m])) by (client_ip)"

# Step 3: Temporarily block top offending IPs at the ingress (dry-run first)
kubectl -n production get cm ingress-nginx-whitelist -o yaml > ingress-whitelist-backup.yaml  # Backup
kubectl -n production create cm ingress-nginx-blocklist --from-literal=blocked-ips="10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4,10.0.0.5" --dry-run=client -o yaml
kubectl -n production apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ingress-nginx-blocklist
  namespace: production
data:
  blocked-ips: "10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4,10.0.0.5"
EOF

# Step 4: Patch the ingress-nginx deployment to use the blocklist (dry-run first)
kubectl -n production patch deployment ingress-nginx-controller -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx-ingress-controller","env":[{"name":"BLOCKED_IPS","valueFrom":{"configMapKeyRef":{"name":"ingress-nginx-blocklist","key":"blocked-ips"}}}]}]}}}' --dry-run=client -o yaml
kubectl -n production patch deployment ingress-nginx-controller -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx-ingress-controller","env":[{"name":"BLOCKED_IPS","valueFrom":{"configMapKeyRef":{"name":"ingress-nginx-blocklist","key":"blocked-ips"}}}]}]}}}'
```

#### **Rollback**:
```bash
# Revert ingress-nginx to original config
kubectl -n production delete cm ingress-nginx-blocklist
kubectl -n production apply -f ingress-whitelist-backup.yaml
kubectl -n production rollout restart deployment ingress-nginx-controller
```

---

### **HORIZON: Short-term (5–30 minutes)**
**Strategy**: Scale Redis horizontally to alleviate memory pressure and adjust PostgreSQL connection pools to prevent exhaustion.

#### **Commands**:
```bash
# Step 1: Scale Redis Cluster (if using Redis Cluster) or add replicas (dry-run first)
kubectl -n production scale statefulset redis --replicas=3 --dry-run=client
kubectl -n production scale statefulset redis --replicas=3

# Step 2: Increase Redis memory limit (if using a ConfigMap for redis.conf)
kubectl -n production get cm redis-config -o yaml > redis-config-backup.yaml
kubectl -n production create cm redis-config --from-literal=maxmemory=16gb --from-literal=maxmemory-policy=allkeys-lru --dry-run=client -o yaml
kubectl -n production apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
  namespace: production
data:
  maxmemory: "16gb"
  maxmemory-policy: "allkeys-lru"
EOF
kubectl -n production rollout restart statefulset redis

# Step 3: Increase PostgreSQL connection pool (dry-run first)
kubectl -n production patch deployment postgresql -p '{"spec":{"template":{"spec":{"containers":[{"name":"postgresql","env":[{"name":"MAX_CONNECTIONS","value":"200"}]}]}}}' --dry-run=client -o yaml
kubectl -n production patch deployment postgresql -p '{"spec":{"template":{"spec":{"containers":[{"name":"postgresql","env":[{"name":"MAX_CONNECTIONS","value":"200"}]}]}}}'
```

#### **Rollback**:
```bash
# Revert Redis scaling
kubectl -n production scale statefulset redis --replicas=1
kubectl -n production apply -f redis-config-backup.yaml
kubectl -n production rollout restart statefulset redis

# Revert PostgreSQL connection pool
kubectl -n production patch deployment postgresql -p '{"spec":{"template":{"spec":{"containers":[{"name":"postgresql","env":[{"name":"MAX_CONNECTIONS","value":"100"}]}]}}}'
kubectl -n production rollout restart deployment postgresql
```

---
---
### **HORIZON: Immediate (0–5 minutes) – Alternative (WAF-Based)**
**Strategy**: Use AWS WAF to block suspicious IPs at the ALB level (if ingress is fronted by ALB).

#### **Commands**:
```bash
# Step 1: List current WAF rules (AWS CLI)
aws wafv2 list-rule-groups --scope REGIONAL --region us-east-1

# Step 2: Create an IP set with offending IPs (dry-run equivalent: validate first)
aws wafv2 create-ip-set --name BlockSuspiciousIPs --scope REGIONAL --ip-address-version IPV4 --addresses 10.0.0.1/32 10.0.0.2/32 10.0.0.3/32 10.0.0.4/32 10.0.0.5/32 --region us-east-1 --dry-run

# Step 3: Apply the IP set to the ALB's Web ACL
aws wafv2 associate-web-acl --web-acl-arn <ALB_WEB_ACL_ARN> --resource-arn <ALB_ARN> --region us-east

---

## Stage 5: Communication

**Message for Slack #incidents (Technical Audience):**

```markdown
**Status:** Investigating
**Impact:** 28m
**Action:** Verifying rate-limiting bypass via ingress logs/metrics. Temporarily blocking top offending IPs (`10.0.0.1-5`) at ingress level. Backup of whitelist taken. Rollback ready if needed.
**Next:** Scaling Redis/PostgreSQL if surge persists.
```

---

## Stage 6: Postmortem

```markdown
# **Blameless Post-Mortem: SecureBank Pro Payment Gateway Degradation**
**Post-Mortem ID:** PM-2023-1115-001
**Status:** Resolved
**Severity:** Critical (SEV-1)
**Duration:** 28 minutes (09:12–09:40 UTC)
**Service:** `payment-gateway-service`
**On-Call Team:** Payments Team

---

---

## **1. Executive Summary**
On **2023-11-15**, SecureBank Pro experienced a **28-minute degradation** of the `payment-gateway-service`, causing **42% payment failures** (baseline: 0.1%) and **P99 latency spikes to 8.2s** (baseline: 200ms). The incident was triggered by a **distributed traffic surge** (50+ requests/sec from 42 unique IPs) that **bypassed rate-limiting**, leading to **Redis memory exhaustion (15.2GB)** and **PostgreSQL connection pool depletion**. Mitigation involved **blocking malicious IPs at the ingress level** and **scaling Redis/PostgreSQL resources**. No data loss occurred, but **~50% of payment requests failed** globally.

**Root Cause:** A **misconfigured WAF rule** allowed high-volume requests from new IPs to bypass the **ALB’s rate-limiting (10 req/sec/IP)**, overwhelming Redis and PostgreSQL.

---

---

## **2. Impact**
| **Category**       | **Details**                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| **User-Facing**    | 50% of payment requests failed with `503 Service Unavailable` or `429 Too Many Requests`. Mobile app and corporate batch payments were delayed. |
| **Business**       | **~6,250 transactions/minute failed** (50% of 12,500 TPS). Potential revenue impact from delayed corporate payments. |
| **Duration**       | **28 minutes** (09:12–09:40 UTC).                                          |
| **Geographic Scope** | Global (no region-specific outage).                                       |

---

---

## **3. Timeline**
| **Time (UTC)**       | **Event**                                                                                     | **Detected By**               |
|----------------------|---------------------------------------------------------------------------------------------|-------------------------------|
| 09:12                | Prometheus alert `HighPaymentGatewayErrorRate` fired (42% errors, P99 latency 8.2s).       | PagerDuty (Payments Team)     |
| 09:15                | Incident declared. Redis memory at **15.2GB** (evictions: 5,000 keys/sec).                 | Grafana + Prometheus          |
| 09:18                | Logs show **unusual IP pattern** (42 unique IPs, 62 req/sec).                                | ELK Stack                     |
| 09:20                | PostgreSQL connection pool exhausted (98/100 connections).                                   | PostgreSQL Metrics            |
| 09:22                | Redis OOM errors (`NOMEM`) and rejected connections.                                         | Redis Logs                    |
| 09:25                | Ingress logs confirm **rate-limiting bypass** (no `429` headers for offending IPs).         | Ingress-Nginx Logs            |
| 09:28                | **Mitigation Step 1:** Blocked top 5 offending IPs (`10.0.0.1-5`) at ingress level.         | Payments Team                 |
| 09:30                | **Mitigation Step 2:** Scaled Redis to 3 replicas; increased `maxmemory` to 16GB.          | Payments Team                 |
| 09:35                | PostgreSQL connection pool increased to 200.                                                 | Payments Team                 |
| 09:40                | Error rate dropped to **<1%**, latency returned to baseline (200ms). Incident resolved.     | Prometheus + Grafana          |

**Total Duration:** **28 minutes**

---

---

## **4. Root Cause Analysis**
### **Direct Cause**
A **misconfigured WAF rule** in the ALB allowed **high-volume requests from 42 unique IPs** to bypass the **10 req/sec/IP rate limit**. This surge:
1. **Overwhelmed Redis**, causing:
   - Memory usage to spike to **15.2GB** (limit: 16GB).
   - **Eviction storms** (1,200 keys/sec), leading to cache misses.
   - `NOMEM` errors and rejected connections.
2. **Cascaded to PostgreSQL**:
   - Cache misses forced **synchronous DB queries**, increasing load.
   - **Lock contention** and **connection pool exhaustion** (98/100 connections).
3. **Propagated to the application**:
   - `payment-gateway-service` returned **503s (Redis/PostgreSQL timeouts)** and **429s (rate-limiting)**.
   - **Pod restarts** (12 in 30 min) due to OOM kills.

### **Why It Happened**
- The **WAF rule** for rate-limiting was **not applied to the new IP range** (likely a misconfiguration during a recent ALB update).
- **Redis memory limits** were set to **16GB per node**, but the **eviction policy (`allkeys-lru`)** was not aggressive enough to handle the sudden load.
- **PostgreSQL connection pool** was **static (100 connections)**, unable to scale with the surge.

---

---

## **5. Contributing Factors**
| **Factor**                          | **Description**                                                                 |
|-------------------------------------|---------------------------------------------------------------------------------|
| **Lack of IP Whitelisting**         | No pre-approved IP list for high-volume clients (e.g., corporate batch services). |
| **Insufficient Redis Monitoring**   | Alerts for Redis memory usage were **not tied to eviction rates**.               |
| **Static PostgreSQL Pool**          | Connection pool did not auto-scale with traffic spikes.                         |
| **Missing WAF Validation**          | No automated checks to verify WAF rules post-deployment.                        |
| **No Circuit Breakers**             | `payment-gateway-service` did not **fail fast** when Redis/PostgreSQL degraded. |

---

---

## **6. Action Items**
| **ID** | **Description**                                                                 | **Owner**          | **Priority** | **Due Date**       |
|--------|---------------------------------------------------------------------------------|--------------------|--------------|--------------------|
| AI-1   | **Fix WAF rule** to enforce **10 req/sec/IP rate-limiting** for all traffic.     | Security Team      | P0           | 2023-11-18         |
| AI-2   | **Implement Redis auto-scaling** (horizontal) with **eviction rate alerts**.     | DevOps Team        | P0           | 2023-11-22         |
| AI-3   | **Add PostgreSQL connection pool auto-scaling** (max 300 connections).          | Database Team      | P1           | 2023-11-25         |
| AI-4   | **Deploy circuit breakers** in `payment-gateway-service` for Redis/PostgreSQL.   | Payments Team      | P1           | 2023-11-28         |

---

---

## **7. Lessons Learned**
### **What Went Well**
✅ **Rapid Detection:** Prometheus + Grafana alerts triggered within **3 minutes** of degradation.
✅ **Effective Triage:** Team quickly identified **Redis memory pressure** and **PostgreSQL locks** as secondary effects.
✅ **Fast Mitigation:** Blocking IPs at the ingress level **reduced load within 5 minutes**.
✅ **Blameless Culture:** Focus remained on **systemic issues** (WAF misconfiguration, static pools) rather than individuals.

### **What to Improve**
🔧 **WAF Rule Validation:** Add **automated tests** to verify rate-limiting rules post-deployment.
🔧 **Dynamic Resource Scaling:** Implement **auto-scaling for Redis/PostgreSQL** to handle traffic spikes.
🔧 **Dependency Resilience:** Add **circuit breakers** and **retry policies** for Redis/PostgreSQL calls.
🔧 **IP Whitelisting:** Maintain a **pre-approved list** for high-volume clients (e.g., corporate batch services).

### **What We Got Lucky With**
🍀 **No Data Loss:** Despite PostgreSQL locks, **no transactions were corrupted**.
🍀 **Ingress Logs Available:** Logs confirmed the **rate-limiting bypass**, enabling quick mitigation.
🍀 **Redis Replicas Available:** Existing Redis cluster allowed **horizontal scaling** without downtime.

---

---

## **8. Appendix: Key Metrics**
| **Metric**               | **Peak Value** | **Baseline** | **Notes**                          |
|--------------------------|----------------|--------------|------------------------------------|
| **Error Rate**           | 42%            | 0.1%         | 503s (Redis/PostgreSQL) + 429s     |
| **P99 Latency**          | 8.2s           | 200ms        | Caused by Redis/PostgreSQL timeouts|
| **Redis Memory Usage**   | 15.2GB         | 6GB          | Evictions: 1,200 keys/sec          |
| **PostgreSQL Connections** | 98/100       | 50/100       | Connection pool exhausted          |
| **Affected Users**       | ~50%           | N/A          | Global impact                      |
| **MTTR**                 | **28 minutes** | N/A          | From alert to resolution           |
| **Transactions Failed** | ~6,250/min     | ~10/min      | 50% of 12,500 TPS                  |
```

---
