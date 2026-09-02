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
