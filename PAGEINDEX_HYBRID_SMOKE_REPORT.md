# ES + PageIndex 混合检索框架首轮报告

日期：2026-07-30

## 已搭建框架

检索链路为：问题类型/启发式判定 -> 证据数量模式 -> ES 全库候选召回 -> 原始 TXT 恢复与结构化 Markdown 转换 -> PageIndex 文件树/章节树导航 -> 必要时追加一跳 ES 检索 -> 证据选择与事实核验 -> Qwen 回答。

- ES 使用现有全量索引 `enterprise-rag-bge-small-v1`：511,957 个文档，928,534 个分块。
- PageIndex 只处理 ES 返回的候选文档，不建立第二套 51 万文档向量索引。
- 原始文档通过 `manifest.sqlite3` 按 `doc_id` 恢复，避免用 ES 分块反拼长文档。
- TXT 按来源转换为 Markdown 层级；无显式标题的文档生成稳定的合成章节。
- PageIndex 树按文档内容指纹落盘缓存，重复测试无需重建。
- 路由支持 single、single_multisection、constrained_pair、conflict_pair、multi_hop、exhaustive、corpus_level 和 abstain 模式。
- 每题写出 `route_trace.jsonl`，记录候选文件、选中节点、追加查询、跳数和停止判断。
- PageIndex Markdown 解析器按需隔离加载，避免其 LiteLLM/tokenizers 依赖污染 BGE 运行环境。

## 严格 A/B 测试

两组只保留 PageIndex 开关这一变量，检索 top-k、Qwen、BGE、生成器、事实核验和最大 6 个上下文证据块完全一致。

测试题：

- `qst_0301`：同文档多章节推理，预期 1 个文档。
- `qst_0341`：项目类多文档推理，预期 2 个文档。

| 指标 | 纯 ES | ES + PageIndex |
|---|---:|---:|
| 官方 correctness | 0.00% | 0.00% |
| 官方 completeness | 56.66% | 51.66% |
| 文档召回 | 75.00% | 75.00% |
| 平均错误额外文档 | 2.5 | 3.0 |
| correctness × completeness | 0.0 | 0.0 |

结论：框架和路由链路已跑通，但首轮质量未提升，当前版本不能替换已有 v2 方案，也不应直接跑 50/500 题。

## 逐题诊断

### qst_0301

- ES 已召回目标文档，文档召回 100%。
- PageIndex 只检查了最前 3 个候选文件，目标文档未进入文件树候选集。
- 树判断返回 coverage incomplete 和两个正确方向的补充查询，但该类型当前最大跳数为 0，因此没有执行追加检索。
- 最终漏答 `eviction_rate > 0.5%` 和 `P99 > 2x baseline`，completeness 33.33%。

### qst_0341

- 初始 ES 只召回 2 个目标文档中的 1 个，文档召回 50%。
- PageIndex 从 8 个候选文件中选择 2 个文件、10 个章节，但其中第二个文件不是目标文档。
- 树判断过早返回 coverage complete，导致多跳检索没有启动。
- 错误章节引入 `quota_exceeded`、客户端重试为主因和 `+75%` 等冲突细节；官方判 correctness 为 0，错误额外文档从基线 3 增到 4。

## 下一版应优先修正

1. 将“所需证据文档数”和“第一层候选搜索宽度”解耦：单文档答案也应在更宽候选集中寻找正确文件。
2. 停止条件改为问题槽位覆盖：例如原因、临时策略、SLO 验证三类槽位全部有经核验证据才能停止，不能只信一次 LLM 的 `coverage_complete`。
3. 多跳题先做问题分解，对每个缺失槽位独立生成 ES 查询；只有新增文档通过实体、时间、区域和版本约束才纳入上下文。
4. PageIndex 节点不能简单置顶后与全部 ES 结果合并；应做文件级准入和反证检查，未通过时回退纯 ES。
5. 建立错误证据惩罚：quota/overload、提案/最终批准、历史/当前版本等冲突字段必须显式判别，宁可删去未经一致证据支持的具体数字。
6. 修正后先按题型抽取小样本测试，再进入 50 题；当前两题样本只证明链路可运行，不足以估计总体分数。

## 产物

- `src/pageindex_router.py`：证据规划、TXT 结构适配、manifest 原文恢复、PageIndex 树缓存与导航、多跳路由。
- `src/pipeline.py`：混合路由接入、任意题号子集、路由轨迹持久化。
- `configs/eval_pageindex_smoke_es_only.yaml`：纯 ES 对照配置。
- `configs/eval_pageindex_smoke_hybrid.yaml`：严格匹配证据预算的混合配置。
- `outputs/pageindex_smoke_es_only_20260730/`：纯 ES 答案与官方评分。
- `outputs/pageindex_smoke_hybrid_matched_20260730/`：混合答案、路由轨迹与官方评分。
