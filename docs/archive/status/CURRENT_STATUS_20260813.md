# EnterpriseRAG-Bench 当前状态

更新时间：2026-08-13（Asia/Shanghai）

## 当前主线

当前已经回退到 **BGE-small + remote rerank** 数据集和 RAG 链路继续优化。
Qwen3/Conan 向量库已经完成一致性审计和 50 题评测，但端到端质量显著低于
BGE，因此不再作为当前主线；其配置、缓存、评测结论和构建脚本保留用于追溯。

新会话按以下顺序阅读：

1. `CURRENT_STATUS.md`：当前决策和下一步；
2. `docs/PROJECT_STRUCTURE_AND_RAG_CODE_MAP_20260813.md`：目录、核心代码和切块实现；
3. `docs/archive/ledgers/RAG_TEST_RECORD_THROUGH_20260812.md`：统一测试台账（已续记至 2026-08-13）；
4. `OPTIMIZATION_TRACE.md`：早期完整实验细节；
5. `docs/backups/BGE_RAG_ROLLBACK_SNAPSHOT_20260812.md`：BGE 回退保护点；
6. `docs/archive/`：历史报告、过时交接和向量重建记录。

## 当前可信最佳

| 基线 | 题集 | correctness | completeness | combined | recall | extra |
|---|---:|---:|---:|---:|---:|---:|
| V5.2 | 10 | 90.0% | 77.33% | 77.33 | 87.50% | 0.12 |
| V5.2 | 50 | 58.0% | 59.21% | 54.41 | 61.70% | 0.15 |
| P1 partial-open | 50 | 60.0% | 59.19% | 54.66 | 59.81% | 0.19 |
| **BGE + remote rerank（当前主线）** | **50** | **62.0%** | **66.49%** | **58.74** | **66.19%** | **0.17** |

主线配置：`configs/eval_pageindex_balanced50_bge_rerank_cpu.yaml`。
后续复跑必须使用新的 `pipeline.name`/输出目录，并设置
`pipeline.read_existing_index: true`，不能覆盖历史最佳产物。

## 当前 RAG 链路

`ES BM25 + BGE dense（RRF，dense=0.3） -> remote rerank（120 -> 30） -> EvidencePlanner 按题型路由 -> PageIndex 树/节点审计/最多两跳 -> precision_v3 证据选择 -> 事实核验 -> final audit`

- basic / miscellaneous / info-not-found 不进入 PageIndex；
- semantic / reasoning / constrained / conflicting / project / completeness /
  high-level 按不同预算进入 PageIndex；
- 多视图、semantic 外部 evidence quota、semantic 绕过 PageIndex、选择性
  PageIndex 均未证明有净增益。

## 最近实验结论

### Qwen3/Conan（已退出主线）

| 实验 | correctness | completeness | combined | recall | extra |
|---|---:|---:|---:|---:|---:|
| Q3-A，无 rerank | 42.0 | 43.64 | 37.41 | 40.78 | 0.23 |
| Q3-B，remote rerank | 40.0 | 40.05 | 36.41 | 43.85 | 0.15 |

- Qwen3 索引的 3,084,120 条 ES 记录全部可以剥离任意层 `__pN` 后追溯到
  1,075,100 个当前缓存基础 chunk；不是旧版本混入。
- query instruction 在 basic-18 上没有可测增益。
- dense 0.5 在 Qwen3 basic-18 上有局部改善，但仍远低于 BGE。
- 主要风险是 Conan 512-token 窗口导致 embedding 写入阶段递归二分，物理
  子片段会影响候选召回和上下文完整性。

### BGE B1（不采用）

basic-18 将 dense 权重从 0.3 提到 0.5 后：correctness 72.22、
completeness 75.46、combined 70.83、recall 72.22、extra 0.17。
相对历史 BGE basic 主链，正确率持平但完整度和召回下降，因此继续使用
`dense_weight: 0.3`。

## 下一步建议

保持 BGE 主链 `dense_weight=0.3`，优先做严格单变量的候选深度消融：

1. rerank 前 hybrid 候选深度 `candidate_k: 240 -> 480`；
2. 其余参数、题集、服务时段和生成链路不变；
3. 先跑 basic-18，只有召回和端到端分数有明确提升才扩到分层 50 题；
4. 不覆盖旧索引、PageIndex cache 或历史输出。
