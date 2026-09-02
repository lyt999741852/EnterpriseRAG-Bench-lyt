# O3.9：Metadata/BM25 增强与 top-500 候选测试计划

日期：2026-09-01
状态：O3.9.1–O3.9.3 已完成；O3.9.4 因 rerank 服务 broken pipe 未通过；未修改生产索引或 alias

## 背景

O3.8 已证明当前 BGE-small 索引的原题 `dense ∪ BM25` 在 top-500 能覆盖 32.61%（15/46）的有效 raw-miss，而生产 pre-rerank 窗口相当于 top-120。与此同时，当前索引缺少可用的 title/path/section 辅助字段。下一阶段先补充可不重算向量的 metadata/BM25 表征，再验证 top-500 候选是否能安全进入 rerank 和生成。

## 冻结基线

- 数据集：现有 EnterpriseRAG 原始 corpus、当前 BGE-small 384 维索引。
- 模型：BGE-small、rerank 服务、DPV4；评分使用 `no-correction`。
- 题集：O0 46 个有效 raw-miss；RAG smoke 沿用固定 20 题（raw-miss 与控制题混合）。
- 生产约束：不切换 alias、不覆盖 `enterprise-rag-bge-small-v1`，所有写入使用版本化 shadow index；主链源码不直接合入。

## 分阶段任务

### O3.9.1：Metadata 来源与覆盖审计（只读）

**结果：通过。** corpus/manifest 共 511,957 个唯一 doc_id，BGE/Conan gold 映射 100%；生产两个索引的 title/path/section/lexical 字段实际覆盖率均为 0%。

1. 从 corpus/manifest 建立 `doc_id → source_path/file_name/title/section` 映射。
2. 对 BGE、Conan 和 61 个 gold 文档检查映射覆盖、重复 doc_id、路径漂移和章节为空比例。
3. 读取现有 ES mapping，确认 `title/file_path/section_context` 是否存在、是否实际有值。

通过条件：gold 映射覆盖 100%，全库映射覆盖率可量化；不向现有索引写入任何字段。

### O3.9.2：BGE metadata/BM25 shadow index

**结果：通过。** `o391_bge_meta_bm25_20260901` 完成 928,534 条复制与 metadata 回填，bulk failure=0，新增字段覆盖率 100%，原向量/正文保持不变。shadow text-only 结果与生产一致。

1. 从现有 BGE 文档复制向量和正文，新增 `title`、`file_path`、`section_context`、`lexical_context` 字段；`lexical_context` 只服务 BM25，不改变 embedding。
2. `lexical_context` 采用标题/路径/章节 + 正文的可审计拼接，保留原 `text` 字段，禁止答案或 gold 文档信息注入。
3. 使用版本化 shadow index 和独立 alias；bulk 过程记录成功/失败、字段非空率、doc/chunk 数和 mapping。
4. 对同一 46 题做 BM25 原题与 metadata-enhanced BM25 对照，记录 Recall@30/120/240/500、目标首 rank 和延迟。

通过条件：bulk failure=0；gold 文档/目标 chunk 不减少；metadata 字段覆盖率 ≥99%；BM25 不得在控制题前段产生明显回退（@30 命中下降不超过 1 pp）。

### O3.9.3：top-500 原题 dense + BM25 候选 union

**结果：部分通过。** text-only 基线复现 O3.8 的 raw-miss union @500=15/46（32.61%）。metadata `bool_should` 仅增至 16/46（34.78%），但有效题控制 @500 从 93.19% 降至 88.51%；text BM25 保持前段再 append metadata 无增益（32.61%）。因此 metadata 暂不进入 BM25 主分数。

1. dense 与 BM25 各取 top-500；原题两路前段候选保持原顺序，附加候选只 append，不重新 RRF 覆盖前 120。
2. 以 120 作为 rerank 输入上限，采用“前段候选 + 尾部 reserve”的实现；每文档设置 chunk cap，避免单文档占满候选。
3. 记录 46 个 raw-miss 的 raw/pre-rerank/post-rerank/final-before-generation/submitted 分层，以及 @120/@240/@500 gold coverage。
4. 并行执行 ES 查询（建议 8 workers），复用已编码的原题向量；不增加 LLM rewrite/intent 调用作为首个变量。

通过条件：top-500 union 至少复现 O3.8 的 15/46 raw-miss 候选覆盖；前 120 原始候选不丢失；rerank 输入保持 120 且无超时。

### O3.9.4：20 题 RAG smoke

**结果：未通过运行门槛。** append-only 临时 patch 已验证语法并应用/回滚；两次并发 1 重试均在首个 rerank 请求出现 broken pipe/connection reset，未生成完整 20 题产物，不能评分。该失败归因于 rerank 服务稳定性，不归因于候选逻辑。

1. 使用 O3.9.2 shadow BM25 字段和 O3.9.3 候选策略，固定 20 题配置。
2. 保持 reranker `candidate_k=120`，禁止再次使用 240；保留 conflict guard、evidence admission 和 `no-correction` 口径。
3. 比较原配置与增强配置的 correctness、completeness、combined、document recall、invalid extra docs，以及 raw/pre-rerank 和控制题变化。
4. 必须所有 20 题完成并产生完整 route trace/评分文件；若超时或服务错误，立即回退 shadow 配置，不影响生产。

通过条件：raw-miss 至少有目标进入 pre-rerank；控制题 correctness 不下降；整体 combined 不低于同题基线；无 rerank 超时。

### O3.9.5：放行决策

- O3.9.1–O3.9.3 通过且 O3.9.4 完整：再申请 AB50。
- AB50 只有在 correctness、combined 和控制题均不回退时，才讨论扩大到 100 题或 F500。
- 任一阶段失败：保留诊断报告，不切换生产 alias；若 metadata/BM25 有收益而 dense 无收益，继续使用原向量并把优化限定为 BM25/候选层。

本轮放行结论：不申请 AB50。先做 rerank 服务 preflight/小 payload 验证，再重跑 O3.9.4；metadata 只作为独立低权重或尾部 recall lane，不能直接改变主 BM25 排序。

## 不做事项

- 本计划不修改 embedding 向量、不重新切块、不直接重建 Conan 全库。
- 不使用题目级关键词、答案、`expected_doc_ids` 或人工目标文档注入查询。
- 不把离线 Recall 提升直接当作最终 correctness 提升；必须通过 rerank、admission 和生成 smoke 验证。

## 产物与提交

每个子阶段单独生成 JSON/Markdown 报告和可复现脚本；只暂存本阶段文件，执行 `git diff --cached --check` 后提交到本地 `codex/semantic-a0`，推送前等待确认。
