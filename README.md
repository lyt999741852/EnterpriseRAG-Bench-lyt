# EnterpriseRAG-Bench

企业知识库 RAG 评测与优化项目。仓库提供从语料预处理、混合检索、重排序、证据选择、答案生成到官方评测的完整流水线，并保留可复现的配置、实验记录与历史决策依据。

当前候选主线为 **BGE-small + BM25/dense hybrid RRF + remote reranker + PageIndex + bounded fail-open evidence admission**。最新 F500 候选结果为 correctness **64.00%**、completeness **67.63%**、combined **58.88**、document recall **64.49%**；指标口径、限制与复现材料见[当前状态](docs/CURRENT_STATUS_20260902.md)。

## 能力概览

- SQLite manifest、内容指纹、checkpoint 与断点恢复，保证索引构建可追溯；
- BM25、dense、RRF hybrid、远程 reranker 与相邻 chunk 扩展；
- 按问题文本推断检索模式，使用 PageIndex 进行证据树、节点审计和有界多跳检索；
- 证据选择、事实核验、答案来源审计与提交格式校验；
- 固定题集、独立配置、输出目录与评分报告，支持单变量实验和结果复现。

## 流程

```text
语料 → 切块 / manifest / 向量索引
    → BM25 + dense 检索 → RRF → reranker
    → PageIndex / evidence selector → 生成与事实核验
    → answers.jsonl → 官方评测与实验报告
```

## 架构图

![BGE RAG 端到端架构](docs/assets/bge-rag-end-to-end.png)

系统先以问题文本完成内部检索模式推断，再将关键词、语义和受控扩展查询的候选融合并精排。结构化题型进入 PageIndex；简单事实题则直接进入证据选择与生成，避免不必要的长文档阅读。完整设计与代码映射见 [架构说明](docs/BGE_RAG_ARCHITECTURE_REPORT_20260820.md)。

## PageIndex：从候选到可用证据

![PageIndex 三关两跳证据路由](docs/assets/pageindex-three-gates-two-hops.png)

PageIndex 不把检索片段直接交给生成模型，而是将其作为“应该阅读什么”的线索：

1. **计划证据**：将问题拆为需要直接支持的事实分面，例如实体、时间、版本与状态。
2. **回读原文**：通过 manifest 定位候选文档的完整原文，建立可导航的章节树。
3. **三关审计**：依次确认文档准入、节点直接相关性，以及分面覆盖、权威性和冲突情况。
4. **只补缺口**：首次阅读仍缺少某个分面时，才发起受限的下一跳检索；已确认的证据不会被无关候选替换。
5. **形成闭集**：仅将通过审计的节点交给后续证据选择、事实核验和答案生成，降低错版本、错实体与遗漏约束的风险。

这使检索系统与生成系统分工明确：检索负责召回候选，PageIndex 负责确认原文、章节与证据完备性。Basic、Miscellaneous 与 Info-not-found 等简单路径不进入 PageIndex，而跨段、跨文档、冲突、穷举和全局综合类问题使用这条结构化路径。

## F500 全量评测亮点

以下为 2026-09-02 F500 O4.P3 候选配置在 500 题、官方 `no-correction` 口径下的表现。该结果已完成生成与评分，但仍是候选主线；不同生成模型或 judge 的结果不可直接比较。

| 表现较好的题型 | 题数 | Correctness | Completeness | Combined | 说明 |
|---|---:|---:|---:|---:|---|
| Basic | 175 | 74.86% | 76.96% | 71.32 | 单事实与直接检索链路稳定 |
| Intra-document reasoning | 40 | 60.00% | 71.90% | 59.38 | 同一原文跨章节推理具备较好完整性 |
| Constrained | 30 | 60.00% | 75.37% | 53.65 | 能较好保留时间、状态等限制条件 |
| Miscellaneous | 20 | 95.00% | 94.58% | 92.08 | 非结构化的直接问答表现稳定 |
| High-level | 10 | 70.00% | 73.83% | 60.50 | 支持受控的跨文档高层归纳 |
| Info-not-found | 20 | 95.00% | 95.00% | 95.00 | 证据不足时可保持拒答导向 |

本轮总分为 correctness **64.00%**、completeness **67.63%**、combined **58.88**、document recall **64.49%**，相对上一轮 DPV4 F500 参考线的 combined 提升 **1.87**。Semantic、Project-related 与 Completeness 仍是后续优化重点；完整分题型结果、基线对照与限制见 [F500 O4.P3 记录](docs/F500_BGE_DPV4_O4P3_20260902.md)。

## 快速开始

### 1. 安装依赖

建议使用独立 Python 环境，并安装项目依赖：

```powershell
python -m pip install -r requirements.txt
```

完整运行需要可访问的 Elasticsearch、embedding、reranker、LLM 与官方评测环境。服务地址和认证信息必须通过安全环境变量提供，禁止写入配置或脚本。

### 2. 运行自动化测试

```powershell
python -m unittest discover -s tests -v
```

### 3. 执行实验

选择一个已有配置运行；每次新实验必须使用独立的配置、`pipeline.name`、输出目录与 PageIndex cache，不能覆盖冻结基线。

```powershell
python -m src.pipeline configs/eval_pageindex_full500_bge_dpv4_o4p3_20260901.yaml
```

结果、题集、评分口径和复现步骤见 [F500 O4.P3 复现清单](docs/F500_BGE_DPV4_O4P3_REPRO_20260902.md)。

## 目录结构

```text
src/                                  主 RAG 实现
tests/                                自动化测试
configs/                              可复现实验配置、题集清单与快照
scripts/                              启动、诊断、远程运行与评分脚本
docs/                                 当前说明、实验报告与历史归档
deploy/                               部署文件
experiments/conan_rag/                隔离的 Conan 研究快照
packages/bge500_rag_pageindex_core/   BGE500 精简代码包
packages/portable_rag/                通用轻量 RAG 示例
rag-debug-console/                    独立调试控制台
```

## 文档入口

| 需要了解的内容 | 入口 |
|---|---|
| 当前候选主线、冻结边界与下一步 | [当前状态](docs/CURRENT_STATUS_20260902.md) |
| 可用于汇报的已验证结论 | [有效实验测试汇总](docs/VALID_EXPERIMENT_TEST_SUMMARY_20260901.md) |
| 测试时间、结果与证据索引 | [实验时间线](docs/EXPERIMENT_TIMELINE_20260902.md) |
| 后续单变量实验门禁 | [优化路线](docs/OPTIMIZATION_ROADMAP_20260902.md) |
| 项目材料范围与安全排除项 | [项目移交清单](docs/PROJECT_TRANSFER_MANIFEST_20260902.md) |
| 所有项目文档 | [文档总入口](docs/README.md) |

历史状态、早期计划、旧架构快照和原始台账均保留在 [docs/archive/](docs/archive/README.md)，仅用于追溯，不应替代当前结论。

## 实验规范

1. 在线链路仅使用问题文本；题型、参考答案、gold facts 与 gold document IDs 只能用于离线诊断和评分。
2. 每次实验只改变一个机制，并记录题集、模型/judge、唯一变量、配置、输出、完成时间与结论。
3. 不同题集、生成模型或 judge 的分数不可直接比较；系统能力优先引用同口径 F500 结果。
4. 所有密钥、内部地址、语料、题集、索引缓存和大体积输出均不纳入项目材料。

## 本地数据与缓存

以下目录和文件是本地运行资产，不应作为代码或文档的一部分处理：

- `corpus/`、`questions.jsonl`、`extra_questions.jsonl`；
- `.index_cache/`、`.pageindex_cache/`、`outputs/`；
- `.env`、压缩包、临时目录与受限历史材料。

缓存目录中包含 manifest、chunk、检索索引和配置指纹。语料、切块、embedding 或索引配置变化后，应创建新的缓存而不是复用不匹配的历史产物。

## 已知限制

- 全量运行依赖外部服务与官方评分环境，无法仅凭本地代码完成；
- F500 候选主线仍需独立复核，尤其需要监控 fail-open evidence admission 带来的额外引用文档；
- Conan、轻量示例和调试控制台为独立资产，不应替代主线 `src/` 的实现与实验结论。
