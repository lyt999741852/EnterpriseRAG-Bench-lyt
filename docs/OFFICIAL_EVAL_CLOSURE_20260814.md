# Official evaluation closure

## Two supported scoring modes

- Fast experiment mode: run the upstream `metrics_based_eval` with
  `--no-correction`. This keeps the released gold answer, facts, and document
  IDs fixed and is the default for frequent local A/B tests.
- Official-default compatibility mode: omit `--no-correction`. The evaluator
  applies its three-judge document correction flow and may update required or
  valid documents, the gold answer, and answer facts before scoring.

Both modes consume the same submission artifact:

```json
{"question_id": "qst_0001", "answer": "...", "document_ids": ["dsid_..."]}
```

Do not compare scores produced by different correction modes as if they used
the same protocol.

## Minimal raw-document bundle

The upstream correction implementation loads raw JSON documents through
`generated_data/uuid_index.json`. The retrieval corpus remains the exported TXT
corpus; raw JSON is downloaded only for evaluator use.

Prepare an isolated bundle with:

```bash
python scripts/remote/_prepare_official_correction_bundle.py \
  --questions-file /opt/enterprise-rag-bench/app/questions.jsonl \
  --answers-file /path/to/answers.jsonl \
  --official-root /opt/enterprise-rag-bench/app/EnterpriseRAG-Bench \
  --bundle-dir /path/to/official_correction \
  --workers 8
```

The helper:

1. creates a question file containing exactly the answer IDs;
2. collects gold and submitted document IDs;
3. downloads the official `uuid_index.json` once;
4. downloads only the required upstream raw JSON documents;
5. validates every downloaded document UUID;
6. writes an isolated filtered UUID index and manifest.

For the current 50-question run, the validated bundle contains 50 questions
and 85 documents. A final 500-question answer file will automatically expand
the bundle to all referenced gold and submitted documents; it does not require
materializing all 500k raw JSON documents.

## Promotion policy

- Frequent A/B: sampled questions, current experiment judge,
  `--no-correction`.
- Milestone candidate: score the same answers once with correction disabled and
  once with correction enabled.
- Final candidate: all 500 questions, official/default correction flow and the
  designated final judge.
- Preserve the original `answers.jsonl`; correction outputs and updated
  questions always go into an isolated `official_correction/` directory.
