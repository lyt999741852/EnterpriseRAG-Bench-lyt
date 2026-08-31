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
