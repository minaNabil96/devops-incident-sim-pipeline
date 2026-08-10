# Model Comparison: Incident Simulation Report Quality

Three-way comparison of generated incident reports against the SPbETU-2026 paper
validation criteria (7-stage lifecycle, 100% structural compliance) and the
`DEFAULT_HIDDEN_CAUSE` in `src/pipeline.py`.

| Model (backend) | Report | Size | Truncation | Paper compliance |
|---|---|---|---|---|
| Gemini 3.6 Flash (Google, OpenAI-compatible) | `incident_simulation_report.md` (Desktop) | 31,888 chars / 3,744 words | None — 7/7 stages complete | ✅ All 20 structural criteria |
| Nemotron 3 120B (NVIDIA build API) | `nvidia--nemotron-3-super-120b-a12b/report.md` | 19,238 chars / 2,436 words | ❌ Stage 1 cut mid-JSON, Stage 6 cut mid action-item table | ⚠️ Partial |
| Mistral Medium 3.5 128B (NVIDIA build API) | `mistralai--mistral-medium-3-5-128b/report.md` | 30,740 chars / 3,355 words | None (but stages wrapped in ```markdown fences) | ⚠️ Mostly, formatting-tainted |

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