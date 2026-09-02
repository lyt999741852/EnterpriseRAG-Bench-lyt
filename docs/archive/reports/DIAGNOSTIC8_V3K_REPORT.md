# v3k Eight-Type Diagnostic Report

Date: 2026-07-30  
Run: `pageindex_diagnostic8_v3k_20260730`  
Mode: frozen v3k architecture; no optimization or code changes during diagnosis

## Sampling

One question was selected from each previously untested type using the fixed
random seed `20260730`.

| Type | Question |
|---|---|
| basic | `qst_0154` |
| semantic | `qst_0298` |
| constrained | `qst_0386` |
| conflicting_info | `qst_0416` |
| completeness | `qst_0432` |
| miscellaneous | `qst_0459` |
| high_level | `qst_0480` |
| info_not_found | `qst_0498` |

## Official results

| Type | Correct | Completeness | Recall | Extra docs | Observed behavior |
|---|---:|---:|---:|---:|---|
| basic | 100% | 100% | 100% | 0 | Correct direct ES answer |
| semantic | 0% | 0% | 0% | 0 | Fail-closed refusal; missed 2–4 week lead time |
| constrained | 0% | 57.14% | 0% | 0 | Wrong file admitted; expected cause/hotfix not returned |
| conflicting_info | 0% | 16.67% | 0% | 0 | One draft found, but finality gate rejected the evidence set |
| completeness | 0% | 0% | 0% | 0 | Five relevant files admitted, but one missing facet caused refusal |
| miscellaneous | 100% | 100% | 100% | 0 | Correct direct ES answer |
| high_level | 0% | 0% | N/A | N/A | Corpus synthesis rejected as lacking one final org chart |
| info_not_found | 100% | 100% | N/A | N/A | Correct abstention |

Aggregate:

- official correctness: **37.5%**;
- official completeness: **46.73%**;
- document recall for answerable questions: **33.33%**;
- average invalid extra documents: **0.0**;
- combined score: **37.5**.

## Diagnostic conclusions

The current v3k precision gate successfully avoids false document submission,
but it is too conservative outside the two types used to develop it.

1. `basic`, `miscellaneous` and `info_not_found` passed without PageIndex.
2. `semantic` failed on the ES-only path. The final selector returned no
   evidence, so the current artifacts do not yet distinguish top-20 retrieval
   miss from evidence-selector rejection.
3. `constrained` admitted a thematically similar file instead of the gold
   incident file. This is a candidate/constraint matching failure before final
   generation.
4. `conflicting_info` treats draft/proposal evidence as invalid even when the
   task requires reconciling the latest values across conflicting documents.
5. `completeness` found five of six gold files at the PageIndex stage, but the
   strict all-facets gate converted partial coverage into a total refusal.
6. `high_level` expects corpus-level synthesis, while v3k searches for one
   finalized authoritative organization document and rejects distributed
   evidence.

No optimization was performed after observing these failures.

## Artifacts

- `configs/eval_pageindex_diagnostic8_v3k.yaml`
- `outputs/pageindex_diagnostic8_v3k_20260730/answers.jsonl`
- `outputs/pageindex_diagnostic8_v3k_20260730/route_trace.jsonl`
- `outputs/pageindex_diagnostic8_v3k_20260730/results.json`
- `ENTERPRISE_RAG_ARCHITECTURE_FLOW_V3K.png`

Server copy:

`/opt/enterprise-rag-bench/app/outputs/pageindex_diagnostic8_v3k_20260730`
