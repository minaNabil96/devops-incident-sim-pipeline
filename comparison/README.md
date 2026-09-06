# Model Comparison: Incident Simulation Report Quality

Four-way comparison of generated incident reports against the SPbETU-2026 paper
validation criteria (7-stage lifecycle, 100% structural compliance) and the
`DEFAULT_HIDDEN_CAUSE` in `src/pipeline.py`.

| Model (backend) | Report | Size | Truncation | Paper compliance |
|---|---|---|---|---|
| Gemini 3.6 Flash (Google, OpenAI-compatible) | `incident_simulation_report.md` (Desktop) | 31,888 chars / 3,744 words | None — 7/7 stages complete | ✅ All 20 structural criteria |
| Nemotron 3 120B (NVIDIA build API) | `nvidia--nemotron-3-super-120b-a12b/report.md` | 19,238 chars / 2,436 words | ❌ Stage 1 cut mid-JSON, Stage 6 cut mid action-item table | ⚠️ Partial |
| Mistral Medium 3.5 128B (NVIDIA build API) | `mistralai--mistral-medium-3-5-128b/report.md` | 30,740 chars / 3,355 words | None (but stages wrapped in ```markdown fences) | ⚠️ Mostly, formatting-tainted |
| DeepSeek v4 Flash (OrcaRouter fallback, pre-fix run) | `incident_simulation_report (5).md` (Desktop) | ~12,000 chars visible | ❌ Stages 1, 3, 6 fully EMPTY (reasoning starved content) | ❌ 4/7 stages with content |
| DeepSeek v4 Flash (OrcaRouter, post-fix `aad6c21`) | `incident_simulation_deepreport.md` (Desktop) | ~35,000 chars / 7 stages | None — 7/7 complete | ✅ ~95% (all sections present; root-cause reveal discipline violated in S0) |

## DeepSeek v4 Flash (OrcaRouter) — detailed analysis

Pre-fix run (`incident_simulation_report (5).md`): DeepSeek v4 is a reasoning
model that streams hidden `reasoning_content` before any visible `content`,
and the thinking consumed the whole `max_tokens` budget on the three heaviest
structured stages (1 Alert JSON, 3 RCA, 6 Post-mortem) — they were saved empty.
Stage 4's honest refusal to plan remediation was a cascade of Stage 3 being
empty (no ROOT CAUSE CONTEXT). Fixed in commit `aad6c21` (3x token budget +
8000 floor for reasoning providers, starvation detection + 4x retry).

Post-fix run (`incident_simulation_deepreport.md`) vs the paper (SPbETU 2026):

- Stage 0: all 4 required sections present, metrics realistic; BUT violates
  the paper's DO-NOT-REVEAL constraint — explicitly concludes "coordinated,
  automated attack" and narrates remediation (HPA scaling, maxmemory-policy
  switch) that belongs to Stages 2–4. Also has continuation-stitch artifacts:
  duplicated "Service Dependencies"/"Current Conditions" sections, and the
  stage is wrapped in a ```markdown fence (same issue as the Mistral report).
- Stage 1: complete, valid Alertmanager v4 webhook payload (version "4",
  groupKey, truncatedAlerts, fingerprint); values consistent with Stage 0
  (34% error, 7.1s P95, Redis 950MB/1GB). PagerDuty summary embedded as an
  annotation rather than a standalone block (minor).
- Stage 2: exactly 3 steps with command/expected/rationale + guiding question;
  guided-style commands rather than pure Socratic questions (partial).
- Stage 3: exactly 15 evidence lines, graduated 4 INFO → 5 WARN → 6 ERROR,
  subtle clue embedding (TEST-NET IPs, `rl:acc:anonymous` fallback bucket,
  high-entropy account IDs). Log timestamps say 2023-10-24 while the incident
  is 2025-04-08 — a context-chaining slip.
- Stage 4: fully compliant — dry-run preview before the NetworkPolicy apply,
  WARNING label on the destructive step, rollback per change, `production`
  namespace throughout.
- Stage 5: 3 audiences, "investigating — not resolved" honored, word limits
  respected, 28-min duration cited (mentions 429s absent from the alert mix).
- Stage 6: all 9 required sections; 4 SMART action items with owners and due
  dates; strictly blameless (team names only); timeline 14:28→14:56 = exactly
  28 minutes; MTTD/MTTA/MTTR appendix.

Comparison with the paper's Qwen2.5-72B reference (§5):
- Cross-stage numeric consistency is STRONGER than Qwen (no context drift —
  the paper's §6.2 ShopFlow drift problem does not occur).
- Output is ~2x deeper (~35k vs ~18.6k chars); artifacts include stacktraces
  with file paths; remediation commands are more operationally realistic.
- Constraint adherence is WEAKER: Qwen held the root cause through Stages 0–5
  (paper §7.1-3); DeepSeek discloses it in Stage 0. Citable for §7.2:
  DO-NOT-REVEAL enforcement is model-sensitive — stronger reasoning models
  over-infer from embedded clues and need harder constraints.
- Verdict: ~95% structural compliance; failures are behavioral (premature
  disclosure), not structural.

## Per-criterion table

| Criterion (SPbETU-2026) | Gemini (current) | Nemotron (prev) | Mistral (prev) |
|---|---|---|---|
| 7-stage lifecycle | ✅ 7/7 complete | ✅ 7 stages | ✅ 7 stages |
| Alertmanager v4 JSON (valid) | ✅ `version: "4"` + PagerDuty summary | ❌ truncated mid-JSON | ✅ valid |
| Namespace = `production` | ✅ all artifacts | ✅ | ✅ |
| Socratic triage, 3 steps + open question | ✅ exact structure | ✅ | ⚠️ hints instead of questions |
| RCA: 3 sections, INFO→WARN→ERROR graduated, root cause withheld | ✅ exact | ⚠️ plain text | ✅ but fenced |
| Remediation: `--dry-run=client`, rollback, `WARNING` labels | ✅ 3 horizons | ⚠️ 1 horizon | ✅ 3 horizons |
| Triple-audience comms (Tech/Business/Exec) | ✅ full | ⚠️ one line | ⚠️ minimal |
| Blameless post-mortem, 9 sections, SMART items, 28-min duration | ✅ 4 SMART items, consistent | ❌ truncated | ✅ complete |
| Root cause narrative matches `DEFAULT_HIDDEN_CAUSE` (rate-limit bypass → Redis OOM) | ✅ | ❌ different (feature-flag traffic) | ⚠️ WAF-misconfig variant |

## Known issues

- All three generations pre-fix rendered the header as `## Unknown — Incident
  Report` because `application_name` was never seeded into context. Fixed in
  `src/pipeline.py` (commit `f76307c`).
- Truncation recovery (`_looks_incomplete`, continuation turns, quota-error
  handling) landed in commit `ae07480` and is verified working on the Gemini run.