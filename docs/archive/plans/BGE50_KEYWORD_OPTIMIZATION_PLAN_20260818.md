# BGE fixed-50 keyword optimization plan

## Frozen reference

- Full benchmark configuration snapshot: `configs/snapshots/eval_pageindex_full500_bge_rerank_question_only_llm_route_multiview_p0_20260817.yaml`
- Full 500-question result: `configs/snapshots/BGE500_NO_CORRECTION_SNAPSHOT_20260818.json`
- Scoring mode for all optimization runs: official `metrics_based_eval` with `--no-correction`
- Fixed comparison set: the 50 question IDs in `configs/eval_pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814.yaml`

## Existing fixed-50 baseline

`pageindex_balanced50_bge_rerank_question_only_llm_route_multiview_20260814`

| Correctness | Completeness | Combined | Recall | Invalid Extra |
|---:|---:|---:|---:|---:|
| 64.00% | 65.49% | 59.14 | 60.87% | 0.23 |

## Controlled variants

All non-weight parameters remain unchanged: BGE-small index, question-only input,
LLM route inference, RRF, remote reranker, PageIndex, evidence selection, answer
generation, and the fixed 50-question IDs.

| Variant | Keyword | Original dense | Rewritten dense | Answer intent | Purpose |
|---|---:|---:|---:|---:|---|
| Baseline | 1.2 | 1.0 | 0.9 | 0.4 | Existing reference |
| Lexical A | 1.6 | 0.8 | 0.5 | 0.2 | Moderate BM25 emphasis |
| Lexical B | 2.0 | 0.8 | 0.4 | 0.1 | Strong BM25 emphasis |

## Decision rule

1. Compare `combined`, correctness, and recall first; use invalid extra as a
   safety constraint rather than the primary optimization target.
2. Lexical A is promising if combined improves by at least 2 points without
   correctness or recall falling by more than 2 points.
3. Lexical B is only worth keeping if it improves Basic/Constrained/Conflicting
   questions while not materially damaging Semantic/Project/Completeness.
4. If both variants improve recall but not correctness, the next experiment
   should target evidence selection or route fallback, not further BM25 weight.
5. If correctness improves while recall is flat, inspect answer/evidence audit;
   retrieval is no longer the limiting stage for this subset.

The 500-question snapshot remains a reporting baseline and must not be overwritten
by any 50-question experiment. A final submission candidate still requires a
separate official-default correction run.
