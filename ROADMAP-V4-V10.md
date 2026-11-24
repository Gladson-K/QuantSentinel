# DecisionGraph roadmap: V4 to V10 (design only)

Scope: engineering design derived from `V4.md` to `V10.md`. No implementation or release
claim is made here. QuantSentinel is Tier B until reclassified in the workspace risk register.
All versions after V3 remain local-first by default: no external provider call, no telemetry,
no secret in source, and no unverified model artefact.

## V4 — Guard (real-time conflict prevention)
- Components: GitHub App webhook receiver with signature verification, PR intent extractor,
  Slack ephemeral responder, browser/editor hint endpoint, decision-guard DSL parser and CI action.
- Data model: `guards(id, decision_ref, match_spec, assert_spec, severity)`, `alert_events(id, target, kind, state, feedback)`.
- Flow: event -> trigger router -> scoped retrieval (ANN + ACL) -> V2 NLI/rules -> policy engine -> notifier.
- Latency: chat hint p95 < 3 s; PR check p95 < 60 s. Block severity is off by default.
- Tests: webhook signature replay, guard DSL unit tests with dry-run, replay of historical PRs,
  ACL check before quoting decision text, alert precision >= 0.75 on labelled set.
- Gate: no live GitHub/Slack app creation without owner approval; fixture-based tests only.

## V5 — Collaborate (web app, teams, lifecycle)
- Components: FastAPI REST/OpenAPI backend, React/TypeScript SPA, PostgreSQL, Redis worker,
  OIDC auth, RBAC policy module, audit event writer, notification service.
- Data model: `workspaces, users, memberships, audit_events`; decisions gain owner, status and review-by date.
- Lifecycle: proposed -> accepted -> superseded | reversed | expired | archived; guarded transitions.
- Tests: policy-module unit tests for every role/transition, E2E flows with Playwright,
  row-level security checks scoped on workspace id.
- Gate: Article 50 disclosure required before any generative feature is user-facing.

## V6 — Reason (assumption and rationale graph)
- Components: assumption extractor with evidence-span validation, monitor runner with pluggable
  signal adapters (Prometheus/SQL/HTTP/RSS), graph adjacency tables, impact resolver (BFS),
  staleness scorer.
- Data model: `assumptions, edges, monitors, signals, signal_values`; typed edges
  `depends_on, supersedes, conflicts_with, enables, blocked_by, derived_from`.
- Tests: backtest on historical decisions with known reversals, monitor unhealthy state,
  BFS depth/confidence weighting, no plaintext credential in monitor config.
- Gate: monitor credentials in a vault; secret scan in CI.

## V7 — Measure (analytics and org health)
- Components: event snapshot job, versioned metric definitions (SQL/dbt-style), warehouse tables,
  dashboard API, cohort comparison, outcome tagging flow.
- Metrics: velocity, reversal rate, re-litigation count, conflict rate, stale backlog,
  ownership coverage, decision debt, quality score.
- Privacy: aggregate-only defaults, minimum group size, no individual performance ranking.
- Tests: metric unit tests on synthetic org data, report generation < 5 s.
- Gate: transparency of definitions; Goodhart/surveillance review before enabling team rankings.

## V8 — Ask (cited Q&A and what-if)
- Components: intent router (lookup/timeline/impact/draft), hybrid retrieval (BM25 + vectors +
  graph expansion), reranker, answer verifier with claim-to-evidence mapping, impact API.
- Contract: `{claims:[{text, evidence_ids[]}]}`; claims without evidence are dropped; refusal when
  evidence is missing. Access control filters before retrieval, never after generation.
- Tests: 300-question evaluation set with gold evidence, citation validity 100%, groundedness >= 95%,
  pre-retrieval ACL tests.
- Gate: label generated output and disclose AI interaction (Article 50) from first user-facing release.

## V9 — Enterprise (multi-tenant, compliance, on-prem)
- Components: tenant context and row-level security, SAML/OIDC + SCIM, OPA-style policy engine,
  redaction pipeline (regex + NER, reversible vault), append-only hash-chained audit log,
  BYOK/KMS, Helm/Terraform on-prem packaging.
- Data model: `tenants, tenant_keys, redaction_tokens, approvals`; tenant id in request context.
- Tests: cross-tenant access must fail, redaction recall >= 99% on labelled test set,
  audit chain tamper detection, restore drills.
- Gate: triggers privacy and security review and possible tier reclassification; no autonomous release.

## V10 — Ecosystem (standard, plugins, steward agent)
- Components: Open Decision Record v1 schema and conformance suite, ADR/RFC/wiki converters,
  plugin SDK with WASM/container sandbox and capability manifest, signed marketplace packages,
  decision steward agent with planner-executor loop, optional differential-privacy benchmarks,
  signed federation with transparency log.
- Controls: approval gates and daily action budget for the steward, dry-run mode, kill switch,
  full action log, minimum cohort size and formal DP accounting for benchmarks.
- Tests: converter round-trips, sandbox escape and resource-quota tests, signature verification,
  steward proposal acceptance target >= 60% in pilot.
- Gate: supply-chain review for plugin signing and marketplace; privacy review for benchmarks.

## Dependency order
V4 needs V2 retrieval and V3 ACL. V5 needs V3 connectors and V4 feedback. V6 needs V5 lifecycle
and audit. V7 needs V6 graph and V5 audit events. V8 needs V6 impact resolver and V7 metrics.
V9 needs V5 RBAC and V8 retrieval controls. V10 needs V9 tenancy and V6 graph.
