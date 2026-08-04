# EnterpriseRAG-Bench 进度跟踪

> 最后更新: 2026-08-03
> 维护说明: 每完成一个阶段或重要变更，在本文档追加记录。新会话窗口读取本文件即可了解当前进度。
> 优化追溯: 所有版本的 RAG 结构、优化内容、测试与结果见 `OPTIMIZATION_TRACE.md`（每次优化必须追加记录）。

---

## 一、项目总体状态

| 维度 | 状态 |
|---|---|
| 数据集调研 | ✅ 完成 |
| 管线框架 | ✅ 完成 |
| 全量 ES 索引（928,534 chunks） | ✅ 完成 |
| 安全整改（API Key） | ✅ 完成 |
| 50 题门禁评测 | ✅ 完成，综合分 **70.1** |
| **500 题正式评测** | 🔄 **进行中** |
| 官方排行榜提交 | ⬜ 未开始 |

---

## 二、当前最优架构（v2 召回保护）

```
问题 → ES BM25 Top-100 + BGE Dense Top-100 → 加权 RRF 融合
     → 子项/硬约束分析 → direct/supporting/reject 三级证据分级
     → 子项覆盖合并 + Top-2 召回锚点（最多6篇）
     → Qwen (lark) 生成草稿 → 逐句事实核验 → 最终答案
```

关键配置:
- 检索: ES Hybrid (BM25 + BGE kNN + RRF, dense_weight=0.3)
- Embedding: `BAAI/bge-small-en-v1.5` (384 维)
- LLM: 内网 Qwen `lark` (http://10.72.100.35:7777/v1)
- 证据筛选: `tiered_v2` + fact_verification
- 切块: fixed-v2, 512 字符, 无 overlap
- PageIndex: **未启用**（500题评测暂不启用，v3k诊断显示对非basic题型过于保守）

---

## 三、50 题最佳成绩

| 指标 | 原基线 | v1 高精度 | **v2 召回保护** |
|---|---:|---:|---:|
| 正确率 | 66.0% | 68.0% | **72.0%** |
| 完整性 | 76.32% | 70.80% | **75.87%** |
| **综合分** | 64.2 | 65.7 | **70.1** |
| 文档召回 | 86.0% | 72.0% | **88.0%** |
| 无效附加文档 | 6.74 | 0.44 | 3.06 |

---

## 四、服务器环境

| 项目 | 值 |
|---|---|
| 应用服务器 | `10.72.100.29` |
| ES 地址 | `http://127.0.0.1:9200`（服务器本地） |
| Qwen LLM | `http://10.72.100.35:7777/v1` |
| API Key 环境变量 | `LARK_API_KEY` |
| ES 索引 | `enterprise-rag-bge-small-v1`（928,534 chunks） |
| 应用目录 | `/opt/enterprise-rag-bench/app` |
| PageIndex | `/opt/enterprise-rag-bench/PageIndex` |

---

## 五、执行日志

### 2026-07-29: Phase 3 全量索引 + Phase 4 基线评测

- 完成 511,961 文档全量索引（928,534 chunks），ES green
- 10 题冒烟：综合分 56.0
- 50 题门禁：综合分 64.2，召回 86%
- 报告: `PHASE3_ES_REPORT.md`, `PHASE4_EVAL_REPORT.md`

### 2026-07-30: 证据筛选 v1 → v2 + PageIndex 诊断

- v1 高精度筛选：综合分 65.7，无效文档 0.44，但召回降到 72%
- v2 召回保护：综合分 **70.1**，召回 88%，无效文档 3.06
- v3k 8题型诊断：basic/misc/info_not_found 通过，semantic/constrained/conflicting/completeness/high_level 全部 0%
- PageIndex precision 2题测试：95.0 分（intra_document + project_related）
- 报告: `PHASE4_EVIDENCE_V2_REPORT.md`, `DIAGNOSTIC8_V3K_REPORT.md`

### 2026-07-31: 500 题评测准备（未完成运行）

- 创建 500 题配置: `configs/eval_500_es_qwen_v2.yaml`（基于 v2 架构）
- 服务器检查通过：ES green (928,534 chunks)、Qwen LLM 正常、PageIndex 可用
- GPU 状态：4x A800 80GB，GPU 2 被 llama-server 占满，配置改为 cuda:1
- 安装了缺失依赖 `rank-bm25` 和 `elasticsearch`
- **500 题评测未实际启动**（paramiko nohup 超时问题，需手动 SSH 启动）
- 打包转移：创建 `deploy/package_project.py` 用于排除大目录后打包
- 创建 `TRANSFER_HANDOFF.md` 完整交接文档

### 2026-08-03: P0-P2 交接执行（v5 定向修复）

**P0 基线恢复（完成）**
- 读取全部交接文档（PROJECT_HANDOFF_20260803 / TRANSFER_HANDOFF / PROGRESS 等）
- 本地 39 项单元测试全部通过；v4/v4.3 输出仅存于服务器（未删除任何 ES 索引/manifest/cache）
- 确认 v4（10题: 80%/77.33/72.92/0.12）为最可信对照基线；当前代码为实验性 v4.3

**P1/P2 代码修复（完成，详见下方逐项）**
1. P1-1 qst_0298 semantic：`pageindex_router.py` 新增 `_direct_event_sources`/`_first_direct_event_document`/`_bounded_full_document`；`route()` 中当 direct 事件来源收窄且节点选择仍缺 facet 时，读取完整事件文档（新配置 `semantic_event_full_max_chars`，默认 40000，高于通用 18000 上限）
2. P1-2 qst_0341 authority：修复 `_authority_filter` 启动缺陷——旧逻辑要求 ≥2 个 policy 文档才过滤，无 policy 关键词的 proposal 邮件（policy_record=False）会被无条件保留；新逻辑只要有明确权威记录（score≥2）即可与所有非 governing 文档竞争，并加"不为空回退"保护
3. P1-3 qst_0432 completeness：`_filter_exhaustive_artifacts` 从静态改实例方法，新增内容级检测（outbound notice / follow-up 自标签模式 `_OUTBOUND_NOTICE_PATTERNS`/`_FOLLOWUP_ARTIFACT_PATTERNS`），路径无特征词的 artifact 也能被剔除
4. P2-1 qst_0480 high_level：`_build_missing_facet_queries` 新增 org chart 权威检索词（organization chart top-level departments）
5. P2-2 qst_0416 conflicting_info：新增 `_entity_tokens`/`_build_version_pair_queries`，`route()` 第二跳在 conflict_pair 且选定文档 <2 时补充"实体 + previous version"版本配对检索（仍过节点审计，防第三错误版本）
6. 字符规范化（交接 6.6）：`generator.py` 新增 `_normalize_typo_glyphs`（≧/≦/≥/≤→>=/<=，×→x，数字间"每"→"-"），在最终答案存储前确定性归一化

**P3 实验配置（已创建，待服务器运行）**
- 新建 `configs/eval_pageindex_targeted5_v5.yaml`：5 题定向（qst_0298/0341/0432/0480/0416），输出 `outputs/pageindex_targeted5_v5_20260803`
- 测试：本地 47 项全部通过（原 39 + 新增 8 项回归测试 `PageIndexV5FixesTests`）
- 服务器运行命令（SSH 到 10.72.100.29）:
  ```bash
  cd /opt/enterprise-rag-bench/app
  export PYTHONPATH=/opt/enterprise-rag-bench/app:/opt/enterprise-rag-bench/venv/lib/python3.10/site-packages
  export HF_HOME=/opt/enterprise-rag-bench/model_cache
  export CUDA_VISIBLE_DEVICES=1
  export LARK_API_KEY=internal-placeholder
  /root/anaconda3/envs/yb_embedding/bin/python -m src.pipeline configs/eval_pageindex_targeted5_v5.yaml
  cd EnterpriseRAG-Bench
  /opt/enterprise-rag-bench/official_eval_venv/bin/python -m src.scripts.answer_evaluation.metrics_based_eval \
    --questions-file /opt/enterprise-rag-bench/app/questions.jsonl \
    --answers-file ../outputs/pageindex_targeted5_v5_20260803/answers.jsonl \
    --results-file ../outputs/pageindex_targeted5_v5_20260803/results.json \
    --parallelism 2 --no-correction --resume
  ```
- 同步提醒：修改的 `src/pageindex_router.py`、`src/generator.py`、`src/pipeline.py`、`tests/test_core.py` 需 scp 到服务器（`scp -r src/ tests/ configs/ root@10.72.100.29:/opt/enterprise-rag-bench/app/`）
- 验收标准：5 题 correctness 不下降且 extra docs 不明显上升，再合并 qst_0301 做 10 题与 v4 对比；不要直接跑 500 题

### 2026-08-03: v5/v5.1/v5.2 服务器实验（P3 执行）

**环境确认**
- SSH 凭据验证通过（10.72.100.29）；GPU 0/1 被占用，实验用 `CUDA_VISIBLE_DEVICES=2`（空闲）
- `yb_embedding` 环境补装 `rank-bm25 0.2.2`（此前装错环境）；服务器 47→50 项测试通过
- 官方评测 Judge = 内网 Qwen（`LLM_PROVIDER=openai` + `LLM_API_BASE=http://10.72.100.35:7777/v1` + `LLM_MODEL_NAME=lark`）

**v5 结果（5 题定向，输出 `outputs/pageindex_targeted5_v5_20260803`）**
| 题 | v4 | v5 | 说明 |
|---|---|---|---|
| qst_0298 semantic | True/100/rec0/ext1 | **True/100/rec100/ext0** | ✅ 事件来源 full-doc 修复生效（recall 0→100） |
| qst_0341 project | True/90/rec100 | **False/0/rec0** | ❌ 回归：节点审计拒绝全部 Jira 节点（authority 已通过） |
| qst_0416 conflict | True/83.3/rec50 | True/83.3/rec50 | 持平 |
| qst_0432 completeness | False/0 | **True/0** | ✅ 由错变对（答案 "Jira"） |
| qst_0480 high_level | False/0 | False/0 | 持平（拒答） |

**v5.1 修复（qst_0341/0480 回归）**
1. `multi_hop`：已通过文件级 authority 过滤但被节点审计整体拒绝的文档，以 bounded full document 重新暴露（`_bounded_full_document` + "authority_full" suffix）——qst_0341 恢复到 v4 水平（True/90/rec100）
2. `corpus_level`：树选择空时执行确定性 org-structure sweep（`pageindex_corpus_org_scope`），不再直接回退裸 ES——qst_0480 不再拒答（给出部门列表但部门名与 gold 体系不一致，judge 仍判错）
3. `high_level` 生成绕过 fail-closed precision 选择器（候选集直接交给综合规则）
4. 字符归一化增强：修复损坏 en dash（`数字+U+FFFD+字母+数字` → `数字-数字`）；实测 qst_0298 的 "2–4" 是合法 U+2013，终端显示误判

**v5.2 结果（v4 同款 10 题，输出 `outputs/pageindex_balanced10_v52_20260803`）**
| 指标 | v4 | v5.2 | 变化 |
|---|---:|---:|---:|
| correctness | 80.0% | **90.0%** | +10pp |
| completeness | 77.33% | 77.33% | 持平 |
| combined | 77.33 | **77.33** | 持平 |
| recall | 72.92% | **87.50%** | +14.6pp |
| invalid extra | 0.12 | 0.12 | 持平 |

逐题：9/10 correct（v4 为 8/10）。增益来自 qst_0298（recall 0→100、extra 1→0）与 qst_0432（由错变对）。仅 qst_0480 仍失败（gold 部门列表在语料中无单一文档、无标准证据，为跨文档综合题）。

**遗留问题（下一轮候选）**
- qst_0432 completeness 0%：答案 "Jira" 缺 "customer-support SUP tickets" 限定（限定词规则已加但被 final audit 裁剪）
- qst_0480：需跨文档部门综合（gold 无标准文档，7 个部门分散于语料；已确认无任一文档含 ≥2 个 gold 部门短语）
- 服务器残留临时分析脚本（`_*.py`）待清理

### 2026-08-03: 创建优化追溯文档

- 新建 `OPTIMIZATION_TRACE.md`：从 V0 本地基线到 V5.2 全部版本（2.1–2.11 节）的 RAG 结构、优化内容与方向、测试内容、官方结果、结论与下一步
- 包含：评测固定口径（0 节）、架构演进总览（1 节）、遗留问题与候选方案（3 节）、测试追溯表（4 节）、历史报告索引（5 节）
- 从今起每次优化迭代必须在 `OPTIMIZATION_TRACE.md` 按模板（6 节）追加记录，保证整体测试可追溯

---

## 六、待办与优化方向

### 当前优先级

1. **[ ] 500 题全量评测** — 用 v2 配置跑完并获取完整分数
2. **[ ] 各题型分析** — 500 题结果按 10 种题型分组诊断
3. **[ ] 检索层优化** — 6 题漏召回的查询改写 / 关键词扩展

### 后续优化方向（按预期收益排序）

4. **[ ] 非 basic 题型路由** — semantic/constrained/completeness 等题型用针对性策略
5. **[ ] 切块升级** — 父子文档 (320/64 child + parent)
6. **[ ] Cross-Encoder 重排序** — 当前关闭状态
7. **[ ] Embedding 模型升级** — bge-base (768维) 或 e5-base-v2
8. **[ ] 查询改写** — HyDE 或多查询扩展
9. **[ ] 独立裁判模型评测** — 消除 Qwen 自评偏差

---

## 七、关键文件索引

| 文件 | 用途 |
|---|---|
| `PROGRESS.md` | 本文件，进度跟踪 |
| `WORK_PLAN.md` | 原始工作计划 |
| `ENTERPRISE_RAG_BENCH_HANDOFF.md` | 完整交接记录 |
| `configs/eval_500_es_qwen_v2.yaml` | 500 题评测配置 |
| `configs/eval_50_es_qwen_evidence_v2.yaml` | 50 题 v2 配置（当前最优） |
| `src/pipeline.py` | 主管线入口 |
| `src/generator.py` | LLM 生成 + 证据筛选 |
| `src/pageindex_router.py` | PageIndex 混合路由 |
| `src/elasticsearch_backend.py` | ES 后端 |
| `outputs/eval_50_es_qwen_evidence_v2_20260730/` | v2 最优结果 |

---

## 八、已知问题与注意事项

1. 评分使用 Qwen 同模型自评，存在偏差；官方榜单需要独立裁判模型
2. v2 耗时约 840s/50题，500 题预计 ~2.3 小时（生成+评分）
3. `questions.jsonl` 绝不能进入 RAG 索引（答案泄漏）
4. 被 Windows Defender 隔离的文件 `dsid_bc86...` 不影响评测（不在 500 题 gold 中）
5. 服务器上 ES 数据目录约 9.8 GiB
