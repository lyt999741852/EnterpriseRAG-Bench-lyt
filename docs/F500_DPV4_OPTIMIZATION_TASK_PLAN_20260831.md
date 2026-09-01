# F500-DPV4 后续优化测试任务计划

## 目标与冻结边界

目标是在不牺牲已经稳定的 Basic、Constrained、Miscellaneous、InfoNotFound 题型的前提下，优先提升 Semantic、Project-related 和 Completeness。当前全量参考线为：correctness 60.60%、completeness 62.57%、combined 55.18、document recall 61.12%。

冻结项：EnterpriseRAG 原始语料、现有 BGE-small 384 维索引、当前切块/manifest、BM25+dense+rerank+PageIndex、已通过的 conflict contract/generation guard，以及 `no-correction` 评分口径。每个实验只改变一个机制。

## 任务清单

### O0：全量错误漏斗复核（只读）

- **目的**：把 500 题错误分为 raw-miss、pre-rerank、post-rerank、selector/citation、generation 五层，避免用 prompt 修复检索问题。
- **范围**：Semantic、Project-related、Completeness 优先，同时抽查健康控制题。
- **产物**：逐题/逐事实漏斗表、目标文档是否进入 top-1000、最终提交证据是否保留。
- **门槛**：每道错误题都有唯一首个失败层；未完成前不启动主链改参。

### O1：通用检索托底基线（只读对照）

- **变量**：原始问题的 BM25+dense 始终保留；任何 query rewrite、answer-intent、路由视图只能追加候选，不能替换或清空基线候选。
- **目的**：验证“通用主检索 + 附加视图”的安全托底是否能避免 route 漂移和控制题回退。
- **指标**：Recall@30/120/240/1000、raw/pre-rerank/final recall、correctness、completeness、combined、控制题回退。
- **门槛**：控制题 correctness 不下降，目标题 raw recall 有净增益；否则停止。

### O2：自适应低置信度候选补召回 smoke

- **变量**：仅当原始 BM25/dense 前若干文档无交集或分数 margin 低时，触发一次轻量 shadow query；不使用官方题型标签，不锁定目标文档。
- **目的**：以低成本覆盖 semantic/project/completeness 的 raw-miss，同时保留所有原始候选。
- **约束**：shadow 候选设总量上限和每文档软上限；PageIndex 多跳证据不得被硬截断。
- **门槛**：目标 raw/pre-rerank recall 提升，Basic、Intra-document、Constrained、InfoNotFound 无回退；通过后才进入 AB50。

### O3：替代 embedding 隔离召回筛选

- **变量**：保持问题集、切块和评测逻辑不变，仅比较 BGE-small、Conan 1792 维和可用的 BGE-large/BGE-M3 索引。
- **范围**：O0 标出的 Semantic/Project/Completeness raw-miss 子集，先不跑 LLM。
- **指标**：Recall@30/120/240/1000、目标分数 margin、索引覆盖率、查询延迟和吞吐。
- **门槛**：新 embedding 在目标子集 Recall@240/1000 有稳定净增益，且索引覆盖完整；否则不重建全量库。

#### O3.1：raw-miss 索引覆盖、BM25、dense 与候选保留复核已完成（2026-08-31）

- 46 道有效 raw-miss 涉及的 61 个 gold 文档在 BGE-small 与 Conan 索引中均存在，排除“索引缺文档”作为主因。
- BGE-small：BM25 top-1000 命中 23/46、dense 命中 5/46、both-miss 23/46；Conan：BM25 25/46、dense 4/46、both-miss 18/46。Semantic 35 题中 BGE dense 4 题、Conan dense 2 题，Conan 未改善核心 semantic raw-miss。
- O0 阶段保留复核显示 raw/pre/post-rerank 均为 0/46，但最终候选恢复 3 题、提交证据仅 2 题（`qst_0191`、`qst_0298`），存在独立的 admission/提交丢失。
- 结论：后续不再优先重建 Conan；应对 `both_miss` 做字段/切块/表示诊断，对 `lexical_only` 做通用 BM25+dense append-only 候选并集，并单独修复最终证据 admission，禁止题目级关键词硬编码。

#### O3.4：索引质量验证已完成（2026-08-31）

- 两套索引均为 green，46 题涉及的 61 个 gold 文档全部存在；目标 chunks 无空 text、无缺失 embedding、无 chunk index gap，抽样向量维度与范数正常。
- 已确认索引质量缺口：BGE 全库没有实际 `title` 值，Conan mapping 无 `title`；BGE 当前目标 chunk 文本中位数约 3,242 字符且 overlap=0，缺少标题/父级上下文拼接。
- 结论：不是灾难性入库失败，而是 chunk/字段表征可能不利于 Semantic dense；下一步用 61 个文档建立“标题/路径+父级上下文+正文”的 BGE 小型对照索引，先测 Recall@30/120/240/1000，不直接重建全库。

#### O3.5：索引质量 A/B 小型对照索引已建立（2026-08-31）

- A：`o34_quality_a_bge_small_20260831`，61 docs / 120 chunks，当前 text-only `512/0`。
- B：`o34_quality_b_bge_small_20260831`，61 docs / 149 chunks，加入 source path、文件名 title、首行 section context，使用 `448/64`。
- 两个索引均 green、计数正确、384 维 BGE 向量一致；尚未接入主链。
- 下一步只做 46 题 doc-level Recall@30/120/240/1000 对照，验证上下文/overlap 是否真正改善 raw-miss。

#### O3.6：A/B 隔离索引 Recall 对照已完成（2026-09-01）

- 46 道有效 raw-miss、61 个 gold 文档的隔离对照中，A（正文 `512/0`）与 B（路径/文件名/首段上下文，`448/64`）dense `@30` 均为 95.65%，`@120/240/1000` 均为 100%。
- 全体 dense 平均首个 gold rank 为 A 6.70、B 6.54；Semantic 35 题为 A 7.51、B 7.69。B 的逐题 dense rank 改善 14 题、变差 17 题、持平 15 题，未形成稳定增益。
- BM25 平均首个 rank 由 1.61 小幅改善至 1.52（Semantic 1.74→1.63），但不足以证明应全量重建 B 索引；延迟中位数约 27.5/28.8 ms（A/B，排除 A 冷启动均值影响）。
- 结论：不直接按 B 方案重建全量索引；索引完整性不是主因。后续优先做通用查询表示与 dense+BM25 append-only 候选托底，并复核 admission/最终证据保留。
- 详细结果见 `docs/INDEX_QUALITY_AB_RECALL_20260901.md`。

#### O3.7：原题并集、多视图追加与 admission 托底回放已完成（2026-09-01）

- 固定回放 46 个有效 raw-miss：生产 top-120 的原题 BM25+dense、原题 append-only 并集（扩至 240）和已有多视图追加（扩至 360）均为 0% gold 命中；`final_before_generation` 为 3/46，追加 8 个 admission reserve 后仍为 3/46。
- 470 道有效题控制回放：原题 base @120 为 86.81%，append-only 并集 @240 为 88.51%；低一致触发多视图 @360 为 89.57%，始终追加上界为 89.79%。相同 @120 不变，说明 append-only 不破坏原始前段候选。
- Semantic 125 题：base @120 64.00%，原题并集 @240 68.00%，条件多视图 @360 69.60%；这只是候选容量/覆盖上界，不等价于 correctness 提升。
- admission reserve 在 470 题上将 final-before-generation 命中从 73.62% 提到 80.00%，但对 raw-miss 无恢复；候选保留是独立损失层，不能替代召回源。
- 结论：保留“原题两路前段 + 附加视图 append-only + 条件触发”的设计原则，不直接合入主链。下一步扩大 dense/BM25 召回窗口并做 46 题 + 控制题的 pre-rerank smoke，再决定是否进入 RAG 小样本。
- 详细结果见 `docs/O3_7_UNION_MULTIVIEW_ADMISSION_REPLAY_20260901.md`。

#### O3.8：top-240/500 扫描与 wide-rerank smoke 已完成（2026-09-01）

- 当前 BGE-small 生产索引只读扫描：46 个有效 raw-miss 的原题 dense∪BM25 命中为 @120 0%、@240 17.39%（8/46）、@500 32.61%（15/46）。470 道有效题并集命中为 @120 88.51%、@240 91.28%、@500 93.19%；Semantic 125 题为 68.00%→75.20%→80.80%。
- 20 题 `candidate_k=500 + reranker candidate_k=240` smoke 在 rerank 服务超时退出，仅完成 2/20，无评分文件；确认直接扩大 rerank 输入不可行，未进入主链。
- 结论：扩大 pre-rerank 召回窗口有效，但必须保持 rerank 输入 120。下一步实现“BM25/dense 各 top-500 + 前段 120 不变 + 尾部 append-only reserve（每文档 chunk cap）”并在同一 20 题复测 raw/pre-rerank 与控制题，再决定是否评分。
- 详细结果见 `docs/O3_8_TOPK_SWEEP_WIDE_RERANK_20260901.md`。

#### O3.9：Metadata/BM25 增强与 top-500 候选测试计划（2026-09-01）

状态已更新为“审计与 shadow 对照完成，smoke 待 rerank 服务稳定后重跑”：BGE/Conan manifest gold 覆盖 100%，生产索引 metadata 字段实际覆盖 0%；版本化 BGE shadow `o391_bge_meta_bm25_20260901` 已完成 928,534 条回填且无 bulk failure。shadow text-only 复现 O3.8 raw-miss union @500=32.61%（15/46）；metadata 单路 bool_should 仅到 34.78%（16/46）但控制题 union @500 降至 88.51%，append union 无增益，因此 metadata 暂不改变主 BM25 排序。临时 append-only reserve（rerank 固定 120）已应用/回滚，两次 20 题 smoke 因 rerank broken pipe/connection reset 未形成完整产物，未申请 AB50。详见 `docs/O3_9_METADATA_BM25_SHADOW_20260901.md`。

- 先做只读 metadata 来源审计，再建立版本化 BGE shadow index，补充 `title/file_path/section_context/lexical_context`；第一阶段不重算向量、不切换生产 alias。
- 在同一 46 个 raw-miss 上复测 metadata-enhanced BM25，并保持原题 dense/BM25 各 top-500；候选采用前段 120 保持 + 尾部 append-only reserve，每文档 chunk cap，rerank 输入固定 120。
- 20 题 RAG smoke 仅在 metadata 覆盖、bulk 无失败、top-500 候选覆盖复现 O3.8 且无前段回退后执行；检查 raw/pre-rerank、最终 admission、no-correction 指标和控制题。
- 通过门槛：gold metadata 覆盖 100%、全库字段覆盖率 ≥99%、top-500 union 至少 15/46 raw-miss 候选覆盖、rerank 无超时、控制题 correctness 不下降、同题 combined 不低于基线。
- 失败时保留诊断并回退 shadow，不进入 AB50/F500；详细步骤见 `docs/O3_9_METADATA_BM25_TOP500_PLAN_20260901.md`。

#### S1：通用 Semantic 查询视图离线回放（2026-09-01）

- 仅从问题文本生成 `event`、`relation`、`object_time` 三类通用视图，不注入答案、gold 文档或隐藏实体。
- Semantic 125 题的多视图集合并集上限由 Recall@500=80.8% 提升到 81.6%，@120 由 68.0% 提升到 69.6%；345 道控制题 @500 由 97.68% 提升到 98.26%。
- 代表性 qst_0247 仍未进入任一视图的 top-500，说明简单槽位改写不能解决“问题描述事件、文档使用具体实体/标题”的表达鸿沟；多视图平均耗时约 2.7–2.9 秒/题。
- 结论：S1 不放行 RAG smoke，不进入主链；下一步转 S2 文档级 chunk 聚合与首段/header 定位。详见 `docs/S1_SEMANTIC_GENERIC_VIEWS_20260901.md`。

#### S2：文档级 chunk 聚合与 header-first 回放（2026-09-01）

- 原始 dense/BM25 top-500 按 `doc_id` 聚合后，Semantic 文档候选 Top-30=47.2%，控制题=91.88%。
- 对 `chunk_index=0` 增加低/高权重 header lane 后，Semantic Top-30 降至 36.0%，控制题降至 86.38%/85.22%；qst_0247 仍未进入 header dense/BM25 top-500。
- 结论：简单提升首 chunk 权重不可泛化，已否决；文档级聚合方向保留，但需要独立的 document-profile（标题/摘要/主题）表示，再命中文档后展开事实 chunks。S2 暂不进入 RAG smoke。详见 `docs/S2_DOCUMENT_LEVEL_HEADER_20260901.md`。

### O4：文档/分面软融合 smoke

- **前置**：仅在 O1/O2 证明候选已进入池后执行。
- **变量**：在 rerank 前做 document-level soft pooling，并保留不同分面/文档的候选；不使用 strict drop、不锁定额外文档。
- **目的**：解决 Project-related 和 Completeness 的多文档/多分面覆盖，不重复扩大无效候选池。
- **门槛**：多跳题 completeness 和 recall 提升，且 `qst_0350` 类证据不因全局 chunk cap 被截断。

#### O4.P3 已完成（2026-08-31）

- 50 题 `no-correction`：correctness 72.00%、completeness 72.28%、combined 67.30、document recall 72.93%。
- 相对同题 BGE-small 基线：correctness +4.00 pp、combined +5.17、recall +2.54 pp。
- 通过项：basic/intra-document 有收益，constrained 无正确率回退，selector 不再因 fail-closed 清空全部证据。
- 未通过项：semantic correctness 无提升，project raw recall 下降，`qst_0413` conflicting_info 回退；因此暂不放行 F500。
- 下一步：先做 conflict 契约单变量回归，再做 semantic/project raw-miss 的通用 shadow 候选补召回；额外文档数量只记录，不作为阻断门槛。

#### O4.P3.1 已完成（2026-08-31）

- 4 题 conflict-contract smoke：correctness 75.00%、completeness 73.96%、combined 70.83、recall 87.50%。
- `qst_0413` 仍错误且 recall=100%，证明 selector 的 `resolved_conflicts` 契约单独不足以修复作用域/批准人判断。
- 控制题 `qst_0322`、`qst_0386` 均正确，未发现通用回退。
- 下一步：O4.P3.2 仅改 fact verification/final audit 的生成阶段 guard；若仍失败，记录 selector 原始 JSON 和最终证据片段，定位到具体再解释层。

#### O4.P3.2 已完成（2026-08-31）

- 4 题生成 guard smoke：correctness 75.00%、completeness 73.96%、combined 61.46、recall 87.50%。
- `qst_0413` 从错误修复为正确，证明作用域优先规则在生成阶段有效。
- `qst_0322` 控制题由正确回退为错误，证明全局 fact verification/final audit guard 过宽，暂不放行。
- 下一步：O4.P3.3 将 guard 限定为 `conflicting_info` 题型，复测同一 4 题后再考虑冲突题 AB50。

#### O4.P3.3 已完成（2026-08-31）

- 4 题题型限定 guard smoke：correctness 100.00%、completeness 73.96%、combined 73.96、recall 87.50%。
- `qst_0413` 保持正确，`qst_0322/qst_0386` 控制题均无回退，证明 guard 作用域应限定为 `conflicting_info`。
- 仍有风险：`qst_0413` completeness 仅 12.5%，答案包含与 gold facts 不一致的 5 business days/infra-manager 额外断言，但 DPV4 judge 未判错。
- 下一步：O4.P3.4 增加冲突题确定性事实约束和独立裁判复核，通过后再扩大到 conflict AB50。

#### O4.P3.4 已完成（2026-08-31）

- 4 题确定性约束 smoke：DPV4 裁判 correctness 100.00%、combined 86.46；独立 Qwen 裁判 correctness 75.00%、combined 48.96。
- 通过项：`qst_0413` 的冲突时长/批准人错误句被删除；`qst_0386/qst_0416` 保持正确；检索 recall 无变化，说明收益来自生成后约束。
- 重要发现：question-only 路由将 `qst_0413` 误判为 constrained，需保留非 gold 的冲突意图兜底；DPV4 与 Qwen 的分数差异确认自评偏高风险。
- 下一步：字段级批准人/时长约束 + 冲突题 AB50 双裁判复测，暂不合入主链/F500。

#### O4.P3.4 AB50 双裁判复测已完成（2026-08-31）

- 50 题答案统一由 DPV4 生成；DPV4 裁判 correctness 78.00%、completeness 76.11%、combined 71.20、recall 76.12%。
- 独立 Qwen/Lark 裁判 correctness 68.00%、completeness 68.61%、combined 59.68、recall 76.12%；与 DPV4 逐题 correctness 一致 45/50（90%）。
- `qst_0413`、`qst_0416` 两道 `conflicting_info` 均被两裁判判正确；`qst_0413` 的冲突批准人/时长扩写已被约束删除，但独立裁判 completeness 仅 12.50%。
- 结论：冲突 guard 的安全收益得到复现，但 DPV4 自评偏高且独立裁判未显示整体 correctness 提升；不放行全局/F500，保留为冲突题限定分支。后续优先回到 semantic/project raw-miss 与通用候选覆盖。

### O5：题型局部生成优化（检索通过后）

- **Semantic**：要求基于证据回答，不将“未找到”当作默认结论；不得伪造缺失事实。
- **Project-related**：要求按项目/实体/时间归并证据，并保留来源。
- **Completeness**：按问题分面逐项覆盖，允许适量额外文档。
- **Conflicting_info**：保留竞争证据；来源优先级解决的冲突进入 `resolved_conflicts`，只有未解决冲突阻断。
- **Intra-document**：强化多事实合并和证据链检查。
- **Constrained**：增加结构和格式校验。
- **验证**：使用 DPV4 生成后，再用独立裁判模型复评，避免同一 LLM 生成/评分偏差。

## 执行顺序与放行规则

1. O0 → O1：先完成全量错误归因和通用托底对照。
2. O2 与 O3 可并行，但只读/独立运行；不得同时修改主链。
3. O2/O3 任一通过后，再做 O4；O4 通过后才做 O5。
4. 每个实验先跑 10–20 题诊断集，再跑 AB50；AB50 通过后才允许 100 题，最后才申请 F500。
5. F500 放行条件：combined 不低于冻结线 55.18、correctness 不低于 60.60%，且健康控制题无回退。
6. 每个任务完成后单独写报告、检查 diff、只暂存本任务文件并提交；推送前等待确认。

## 优先级判断

最高优先级：O0、O1、O2（通用 raw-miss 托底）。

第二优先级：O3（embedding/index 只读筛选）和 O4（多文档软融合）。

最后才做：O5（提示词和生成层）。本轮 F500 已显示 DPV4 能改善生成层，但不能替代检索召回优化。
