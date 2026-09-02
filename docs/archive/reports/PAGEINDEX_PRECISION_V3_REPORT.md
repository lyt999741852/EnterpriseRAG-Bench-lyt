# ES + PageIndex Precision v3 Experiment Report

Date: 2026-07-30  
Final run: `pageindex_smoke_precision_v3k_20260730`

## Outcome

The precision-first ES + PageIndex path now returns all gold documents and no
extra documents on the two representative questions. The official evaluator
scores both answers correct.

| Metric | Initial hybrid smoke | v3k final |
|---|---:|---:|
| Official correctness | 0% | 100% |
| Official completeness | 51.7% | 95% |
| Combined correctness x completeness | 0 | 95 |
| Document recall | 75% | 100% |
| Average invalid extra documents | 3.0 | 0.0 |

Per question:

| Question | Type | Correct | Complete | Recall | Extra docs |
|---|---|---:|---:|---:|---:|
| `qst_0301` | intra-document reasoning | 100% | 100% | 100% | 0 |
| `qst_0341` | project-related multi-hop | 100% | 90% | 100% | 0 |

This is a two-question architecture smoke test, not an estimate of performance
on all 500 questions.

## Implemented architecture

1. ES remains the corpus-wide recall layer over 511,957 documents and 928,534
   chunks. Existing vectors are reused; the final run indexed zero new chunks.
2. Question planning separates required answer facets, hard constraints, risk
   dimensions, expected document count, candidate width and retrieval depth.
3. Facet-specific queries are interleaved so later facets are not displaced by
   the first query's high-scoring documents.
4. PageIndex performs file-tree selection, node admission and up to two hops.
   Missing facets, rather than one global `coverage_complete` flag, drive the
   second hop.
5. File authority is evaluated against the full original file. Applied Jira or
   Linear records outrank proposal/request emails; general Confluence SLO and
   runbook documents remain eligible as governing evidence.
6. When an admitted short file has incomplete node coverage, retrieval depth is
   increased only inside that admitted file. Rejected files and unrelated ES
   candidates are not reintroduced.
7. Generation uses fail-closed facet coverage, fact verification, final source
   attribution, temporal-state cleanup and evidence-supported slot repair.

## Key failure and fix

For `qst_0341`, ES correctly found the two gold documents but also found a Gmail
thread containing an earlier scheduled 400 RPS proposal. The official answer
requires the later applied Jira override. Including the Gmail detail caused a
material mismatch and made the entire answer incorrect.

The final route rejects that Gmail file as lower-authority proposal evidence,
then reads the admitted Jira and Confluence files deeply enough to cover:

- overload admission control versus quota;
- the applied region-scoped 14-day exception and rollback guardrails;
- route-by-region enterprise SLO verification using availability/error-budget,
  p95/p99, 5xx, overload 429 and `shed_rate` signals.

## Validation artifacts

- `outputs/pageindex_smoke_precision_v3k_20260730/answers.jsonl`
- `outputs/pageindex_smoke_precision_v3k_20260730/route_trace.jsonl`
- `outputs/pageindex_smoke_precision_v3k_20260730/results.json`
- `outputs/pageindex_smoke_precision_v3k_20260730/simple_metrics.json`

The same artifacts are retained on the server under:

`/opt/enterprise-rag-bench/app/outputs/pageindex_smoke_precision_v3k_20260730`

## Recommended next validation

Freeze v3k as the current baseline. Before a 50-question run, evaluate a small
stratified set across conflicting information, constrained retrieval,
completeness, high-level synthesis and information-not-found/refusal. The goal
is to verify that the authority and slot-repair rules generalize without
over-answering or suppressing valid email-only evidence.
