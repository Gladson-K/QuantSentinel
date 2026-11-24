# DecisionGraph

**Organizations forget what they decided, and why. DecisionGraph captures decisions from the places work already happens, links them into a graph with rationale and assumptions, and warns when new work contradicts, repeats, or silently invalidates an earlier decision.**

## The unique problem: decision amnesia
- Decisions are made in meetings, chats, PRs and docs, then scattered and never indexed.
- Teams re-debate settled questions, or worse, quietly contradict them (database choice, rate limits, deploy rules).
- The *reasons* and *assumptions* behind a decision vanish, so nobody knows when it is safe to revisit it.
- Search tools find documents, not decisions; wikis go stale; ADR files cover only a tiny, engineering-only slice.

## Why it is different
Not a note-taker and not a wiki. The unit of value is the **decision** (what, who, when, why, assumptions, status), and the product acts on relationships between decisions: **conflict, supersession, dependency, staleness**.

## Version map
| File | Theme | Headline capability |
|---|---|---|
| V1.md | Capture | Local CLI: extract, search, detect conflicts (working code in `v1_impl/`) |
| V2.md | Understand | LLM-assisted extraction, embeddings, review queue |
| V3.md | Connect | Slack, GitHub, Docs, Jira connectors, incremental sync |
| V4.md | Guard | Real-time conflict warnings in PRs, chat and docs |
| V5.md | Collaborate | Web app, teams, decision lifecycle, review dates |
| V6.md | Reason | Rationale and assumption graph, invalidation alerts |
| V7.md | Measure | Decision analytics and org health scores |
| V8.md | Ask | Cited Q&A agent and what-if impact simulation |
| V9.md | Enterprise | Multi-tenant, SSO, audit, redaction, on-prem |
| V10.md | Ecosystem | Open Decision Record standard, plugins, decision steward agent |

## Run V1
Implementation lives in `v1_impl/`. Docker is the supported test environment.

```bash
docker compose run --rm test
```

Local equivalent commands (stdlib only, Python 3.11+):

```bash
PYTHONPATH=v1_impl python v1_impl/decisiongraph.py ingest v1_impl/sample_notes
PYTHONPATH=v1_impl python v1_impl/decisiongraph.py conflicts
PYTHONPATH=v1_impl python v1_impl/decisiongraph.py search "database"
PYTHONPATH=v1_impl python v1_impl/decisiongraph.py report --out report.md
PYTHONPATH=v1_impl python -m unittest discover -s v1_impl -t v1_impl -p "test_*.py" -v
```

## Run V1 + V2
`docker compose run --rm test` discovers tests from every implementation package.

```bash
docker compose run --rm test
```

V2 is offline by default: the LLM parser falls back to V1 regex when no loopback endpoint is
configured. A remote endpoint is rejected. Model artefacts must be `.onnx`/`.safetensors` with a
matching SHA-256; the ONNX adapter stays disabled until an approved runtime is supplied.

