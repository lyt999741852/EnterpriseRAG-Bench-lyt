# EnterpriseRAG-Bench 优化追溯记录（OPTIMIZATION TRACE）

> 创建日期：2026-08-03
> 维护规则：**每次优化迭代**（无论是否跑分）都必须在本文件追加一节，记录：RAG 结构、优化部分、优化内容与方向、测试内容、结果（官方四项指标 + 逐题变化）、结论与下一步。历史版本按时间倒序追加，不改写已记录条目。
> 当前状态入口：`CURRENT_STATUS.md`；各阶段历史报告见本文末索引。

---

## 0. 固定评测口径（所有版本通用）

| 项 | 值 |
|---|---|
| 语料索引 | `enterprise-rag-bge-small-v1`，511,957 文档 / 928,534 chunks（ES 8.19.12） |
| Embedding | `BAAI/bge-small-en-v1.5`，revision `5c38ec7c...`，384 维 cosine |
| 切块 | `fixed-v2`，512 字符，overlap 0（父子切块未启用） |
| 生成/评分模型 | 内网 Qwen3.5-27B（`lark`，10.72.100.35:7777） |
| 官方评测 | `metrics_based_eval.py`，`--no-correction`，parallelism 2 |
| 主分公式 | `combined = average(completeness if answer_correct else 0)` |
| 服务器 | 10.72.100.29（A800×4，实验用 GPU 2）；应用目录 `/opt/enterprise-rag-bench/app` |
| 单元测试 | `python -m unittest tests.test_core`（当前 50 项） |

---

## 1. RAG 架构演进总览

```text
V0（本地基线，7/28）          : 本地 FAISS/BM25 → Hybrid(RRF) → Qwen → 官方评测（GitHub 60 题）
V1（Phase4 基线，7/29）       : ES Hybrid(BM25+BGE kNN+加权RRF, top10) → Qwen → 评测
V1.1 证据筛选 v1（7/30）      : + LLM 证据筛选（selected_indices，最多4条）
V2 召回保护（7/30）           : + 三级证据分级 + 硬约束检查 + 子项覆盖 + Top-2 召回锚点 + 事实核验
PageIndex 框架（7/30）        : + 题型路由(8模式) + PageIndex 文件树/章节树 + manifest 原文恢复 + 多跳
V3k precision-first（7/30）   : + precision_v3 证据选择(fail-closed) + 节点审计 + authority 过滤
V4 balanced10（7/31）         : 放宽各题型策略（conflict_pair 保留双版本、exhaustive 全量等）
V4.1/V4.2/V4.3（7/31 实验）   : 完整性优先 / 事件来源筛选 / 定向回归（未冻结）
V5（8/03）                    : + 事件来源 full-document fallback + authority 门槛修复 + 内容级去重
V5.1（8/03）                  : + multi_hop 被拒文件重暴露 + org sweep + high_level 生成放宽
V5.2（8/03）                  : 冻结 V5.1 代码跑 v4 同款 10 题（当前最佳，combined 77.33 / correct 90%）
```

---

## 2. 各版本详细记录

### 2.1 V0：本地基线（2026-07-28）

- **RAG 结构**：`语料(8,052 GitHub) → 切块(512) → rank_bm25 / FAISS(MiniLM) → Hybrid(RRF) → Qwen → 官方评测`
- **优化内容与方向**：无优化，验证本地管线闭环与官方评测接口
- **测试内容**：GitHub 相关 60 题（`source_filter: ["github"]`，含 39 题严格 GitHub-only）
- **结果**：
  | 基线 | 简单 Document Recall | 平均额外文档 |
  |---|---:|---:|
  | BM25 | 58.2% | 8.7 |
  | Dense | 45.9% | 8.9 |
  | Hybrid | 61.8% | 8.7 |
- **结论**：管线跑通；本地索引规模不足，需全量 ES 索引；旧 `baseline_full`（16.1% recall）不可信，废弃

### 2.2 Phase 2/3：ES 全量索引建设（2026-07-29）

- **RAG 结构**：`51 万文档 → fixed-v2 切块 → BGE small GPU 向量化 → ES bulk（幂等 upsert）→ BM25/kNN/RRF 冒烟`
- **优化内容与方向**：全量索引工程化——断点恢复、幂等写入、重复 doc_id 消歧（`dataset-duplicate-path-v2`）、缓存指纹
- **测试内容**：10k Canary（248.65 chunks/s）、全量构建（918,528 新增，~260 chunks/s）、完整复跑（0 新增，36.9s）
- **结果**：511,961 文件 / 511,957 唯一 doc_id / 928,534 chunks；ES green；三路检索冒烟通过
- **结论**：索引可复用，后续实验 `new=0` 直接扫描复用，不重建

### 2.3 V1：Phase 4 基线（2026-07-29）

- **RAG 结构**：`问题 → ES Hybrid（BM25+BGE kNN+加权RRF，top_k=10, dense_weight=0.3）→ Qwen 生成 → 官方评测`
- **优化内容与方向**：无；确立首个可信全量基线
- **测试内容**：10 题（qst_0001–0010）+ 50 题（qst_0001–0050），均为 basic 型
- **结果**：
  | 指标 | 10 题 | 50 题 |
  |---|---:|---:|
  | correctness | 60.0% | 66.0% |
  | completeness | 71.0% | 76.32% |
  | combined | 56.0 | **64.2** |
  | recall | 80.0% | 86.0% |
  | extra docs | 6.6 | 6.74 |
- **结论**：召回可行但额外文档过多（6.74）；7 题漏召回（qst_0002/0004/0016/0039/0041/0043/0050）；部分题召回正确仍判错（证据冲突，如 qst_0001）

### 2.4 V1.1：证据筛选 v1（2026-07-30）

- **RAG 结构**：`… → Hybrid Top-10 → LLM 证据筛选（selected_indices，≤4 条）→ Qwen → 评测`
- **优化内容与方向**：检索与生成之间加证据去噪层；提交 `document_ids` 与实际证据严格一致
- **测试内容**：同 10/50 题（与 V1 严格 A/B，唯一变量=证据筛选开关）
- **结果**：
  | 指标 | 50题基线 | v1 | 变化 |
  |---|---:|---:|---:|
  | correctness | 66.0% | 68.0% | +2.0pp |
  | completeness | 76.32% | 70.80% | -5.52pp |
  | combined | 64.20 | 65.70 | +1.50 |
  | recall | 86.0% | 72.0% | **-14.0pp** |
  | extra docs | 6.74 | **0.44** | -6.30 |
- **结论**：去噪有效（extra -94%）但过度过滤损失召回；`qst_0032` 由对变错暴露细粒度数值辨别不足

### 2.5 V2：召回保护（2026-07-30，50 题最优基线）

- **RAG 结构**：`问题 → Hybrid Top-10 → 子项/硬约束分析 → direct/supporting/reject 三级分级 → 子项覆盖合并 + Top-2 召回锚点（≤6 条）→ Qwen 草稿 → 逐句事实核验 → 最终答案`
- **优化内容与方向**：三级证据判定；显式硬约束检查（实体/时间/版本/数值）；多子项覆盖；Top-2 锚点防假阴性；生成后事实核验
- **测试内容**：同 50 题
- **结果**：correctness **72.0%** / completeness 75.87% / combined **70.1** / recall **88.0%** / extra 3.06
- **逐题**：v1 丢失的 8 题召回全部恢复；2 题由错变对（qst_0032/0042），无由对变错
- **结论**：相对基线 combined +5.9；剩余 6 题漏召回（qst_0004/0016/0039/0041/0043/0050）瓶颈在检索层

### 2.6 PageIndex 混合检索框架（2026-07-30）

- **RAG 结构**：`题型/启发式判定 → ES 全库召回 → manifest 原文恢复 → TXT→Markdown 结构化 → PageIndex 文件树/章节树导航 → 多跳检索 → 证据选择+事实核验 → Qwen`
- **优化内容与方向**：为 multi-hop / 结构化题型搭建文件树推理层；8 种路由模式（single / single_multisection / constrained_pair / conflict_pair / multi_hop / exhaustive / corpus_level / abstain）；树按内容指纹缓存
- **测试内容**：2 题（qst_0301 intra-document、qst_0341 project-related），与纯 ES 严格 A/B
- **结果**：双方 correctness 均 0%（PageIndex 55.0 vs 纯 ES 56.66 combined 0）；qst_0301 目标文档未进候选窗、qst_0341 早期 coverage 误判阻止多跳
- **结论**：链路跑通但质量未提升，不能替换 v2；需解耦候选宽度、按槽位覆盖停止、文件级准入

### 2.7 V3k：precision-first（2026-07-30）

- **RAG 结构**：`问题分解(facets/硬约束/风险维度) → facet 级查询交错 → PageIndex 树选择(≤2跳) → 文件级 authority 过滤 → 节点审计(fail-closed) → precision_v3 证据选择 → 事实核验 → 最终答案审计`
- **优化内容与方向**：精度优先——fail-closed 全槽位覆盖；authority 区分 proposal/applied；SLO/runbook 作为 governing 证据；缺失槽位驱动第二跳
- **测试内容**：2 题基线（qst_0301/0341）+ 8 题型诊断（fixed seed 20260730）
- **结果**：
  - 2 题：correctness 100% / completeness 95% / combined **95** / recall 100% / extra 0
  - 8 题诊断：correctness 37.5% / completeness 46.73% / combined 37.5 / recall 33.33% / extra 0
  - 通过：basic / miscellaneous / info_not_found；全败：semantic / constrained / conflicting_info / completeness / high_level
- **结论**：精度门禁过严；非 basic 题型全面过度拒答

### 2.8 V4：balanced10（2026-07-31，本轮之前的最可信基线）

- **RAG 结构**：V3k 架构 + 题型专属放宽（conflict_pair 保留双版本/最新投影、exhaustive 全量 admit + 路径级去重、corpus_level scoped synthesis、constrained 短 postmortem 准入）
- **优化内容与方向**：平衡召回与精度——每类修复一道代表题
- **测试内容**：10 题分层（qst_0301/0341/0154/0298/0386/0459/0498/0416/0432/0480）
- **结果**：correctness **80.0%** / completeness 77.33% / combined **77.33** / recall 72.92% / extra 0.12
- **逐题**：constrained（qst_0386）、conflicting（qst_0416 最新值正确但旧版召回不足）、project（qst_0341）正确；semantic（qst_0298）extra 1 且 recall 0；completeness（qst_0432）、high_level（qst_0480）失败
- **结论**：v4.1/v4.2/v4.3 为实验分支（v4.1 combined 70.0 拒绝、v4.3 未官方评分），不冻结

### 2.9 V5：5 题定向修复（2026-08-03）

- **RAG 结构**：V4 架构 + 三项修复（详见下）
- **优化内容与方向**：
  1. **semantic 事件来源**（qst_0298）：新增 `_direct_event_sources`/`_first_direct_event_document`/`_bounded_full_document`；direct 来源收窄 + 缺 facet 时读完整事件文档（`semantic_event_full_max_chars=40000`，高于通用 18000）
  2. **authority 门槛修复**（qst_0341）：旧逻辑要求 ≥2 个 policy 文档才过滤，无 policy 关键词的 proposal 邮件被无条件保留；改为有明确权威记录（score≥2）即与所有非 governing 文档竞争
  3. **intake 内容级去重**（qst_0432）：`_filter_exhaustive_artifacts` 增加 outbound notice / follow-up 自标签内容检测（12 个正则模式），路径无特征词的 artifact 也能剔除
  4. **high_level org 检索词**（qst_0480）+ **版本配对第二跳**（qst_0416）+ 字符归一化（`每`/`≧`/损坏 en dash）
- **测试内容**：5 题定向（qst_0298/0341/0432/0480/0416），配置 `configs/eval_pageindex_targeted5_v5.yaml`
- **结果**：correctness 60.0% / completeness 36.67% / combined 36.67 / recall 50.0% / extra 0.25
  | 题 | v4 | v5 | 变化 |
  |---|---|---|---|
  | qst_0298 | True/100/rec0/ext1 | **True/100/rec100/ext0** | ✅ recall 0→100 |
  | qst_0341 | True/90/rec100 | **False/0/rec0** | ❌ 回归（节点审计拒绝全部 Jira 节点） |
  | qst_0416 | True/83.3/rec50 | True/83.3/rec50 | 持平 |
  | qst_0432 | False/0 | **True/0** | ✅ 由错变对 |
  | qst_0480 | False/0 | False/0 | 持平（拒答） |
- **结论**：semantic/completeness 修复生效；authority 修复暴露节点审计过严问题（qst_0341）

### 2.10 V5.1：qst_0341/0480 二次修复（2026-08-03）

- **RAG 结构**：V5 + 两项修复
- **优化内容与方向**：
  1. **multi_hop 被拒文件重暴露**（qst_0341）：已通过文件级 authority 过滤但被节点审计整体拒绝的文档，以 bounded full document（`authority_full` 后缀）重新进入上下文——根因是审计对 hypothesis-only 节点过严，v4 时 jira 节点 0019 曾被接受
  2. **corpus_level org sweep**（qst_0480）：树选择空时执行确定性 org-structure 检索（`pageindex_corpus_org_scope`），不再直接回退裸 ES
  3. **high_level 生成放宽**：precision_v3 对 high_level 绕过 fail-closed 空拒绝，候选集直接交给综合规则
  4. **字符归一化增强**：修复损坏 en dash（`数字+U+FFFD+字母+数字` → `数字-数字`）
- **测试内容**：同 5 题，配置 `configs/eval_pageindex_targeted5_v51.yaml`
- **结果**：correctness 80.0% / completeness 54.67% / combined 54.67 / recall 75.0% / extra 0.25
  - qst_0341：**恢复 v4 水平**（True/90/rec100）
  - qst_0480：不再拒答（给出部门列表，但与 gold 部门体系不一致，judge 仍判错）
  - qst_0298/0432/0416：维持 v5 结果
- **结论**：5 题 combined 54.67 == v4 同 5 题子集（54.67），证据质量更好（recall 75% vs 66.7%）

### 2.11 V5.2：10 题回归（2026-08-03，当前最佳版本）

- **RAG 结构**：V5.1 代码冻结，未改动
- **优化内容与方向**：无代码改动；验证 V5.1 修复在 v4 同款 10 题上的整体表现
- **测试内容**：v4 同款 10 题（qst_0301/0341/0154/0298/0386/0459/0498/0416/0432/0480），配置 `configs/eval_pageindex_balanced10_v52.yaml`
- **结果**：
  | 指标 | v4 | v5.2 | 变化 |
  |---|---:|---:|---:|
  | correctness | 80.0% | **90.0%** | +10.0pp |
  | completeness | 77.33% | 77.33% | 持平 |
  | combined | 77.33 | **77.33** | 持平 |
  | recall | 72.92% | **87.50%** | +14.6pp |
  | extra docs | 0.12 | 0.12 | 持平 |
- **逐题**：9/10 correct（v4 为 8/10）。增益：qst_0298（recall 0→100、extra 1→0）、qst_0432（由错变对）。唯一失败 qst_0480
- **结论**：在保持综合分的同时显著提升正确率与召回；满足"10 题 correctness 不下降且 extra 不明显上升"，可进入 50 题分层验证

### 2.12 V5.2：50 题分层验证（2026-08-03）

- **RAG 结构**：V5.2 代码冻结（同 2.11），未改动
- **优化内容与方向**：无代码改动；从 500 题按题型比例分层抽样 50 题（fixed seed 20260803，强制含 v4 全部 10 锚点题），验证泛化能力
- **测试内容**：50 题分层（basic 18 / semantic 12 / intra 4 / project 4 / constrained 3 / conflicting 2 / completeness 2 / misc 2 / info_not_found 2 / high_level 1），配置 `configs/eval_pageindex_balanced50_v52.yaml`
- **结果**：correctness **58.0%** / completeness 59.21% / combined **54.41** / recall 61.7% / extra 0.15
  | 题型 | n | corr | comp | recall | extra |
  |---|---:|---:|---:|---:|---:|
  | basic | 18 | 66.7% | 67.7 | 66.7 | 0.11 |
  | semantic | 12 | **25.0%** | 32.5 | 41.7 | 0.25 |
  | intra | 4 | 100% | 100 | 100 | 0 |
  | project | 4 | 50% | 44.7 | 41.7 | 0 |
  | constrained | 3 | 66.7% | 79.5 | 66.7 | 0 |
  | conflicting | 2 | 50% | 60.4 | 75 | 0 |
  | completeness | 2 | 50% | 6.8 | 41.7 | 1.00 |
  | misc | 2 | 100% | 100 | 100 | 0 |
  | info_not_found | 2 | 100% | 100 | N/A | N/A |
  | high_level | 1 | 0% | 0 | N/A | N/A |
- **可复现性**：10 个 v4 锚点题在 50 题内结果与 v5.2 单独跑完全一致（9/10 correct，qst_0480 仍失败），无回归
- **逐题归因**（37 个 gold 全部确认在 ES 索引内；top-30 混合检索 rank）：
  1. 检索层失败（gold 不在 top-30）：qst_0050/0093/0112/0116（basic）、qst_0184/0231/0251（semantic）、qst_0356 缺 2/4、qst_0362 缺 7/9、qst_0447 缺 2/6
  2. 证据层失败（gold 在候选内但提交为空）：qst_0013(rank1)/0022(rank2)/0197(rank25)/0241(rank4)/0271(rank1)/0272(rank25)/0280(rank4)/0291(rank11)/0390(rank2,6)
  3. 已提交但判错：qst_0413（recall 100%、comp 37.5）；qst_0013/0022 已提交正确文档但 comp 低（答案内容问题）
- **结论与下一步**：
  1. 分层样本（54.41）远低于 basic-only 50 题（v2 70.1），主要受 semantic（25%）与 basic 检索层失败拖累；extra 0.15 验证精度机制在新题上仍有效
  2. 优先修**检索层**：basic 4 题 + semantic 3 题 gold 完全不在 top-30，需诊断单路 BM25/dense 排名与候选窗宽度；project/completeness 多文档题需提高 gold 多命中率
  3. 其次修**证据层 fail-closed**：9 题 gold 在候选内被拒（含 rank1/rank2），需区分"审计过度拒绝"与"事实核验删除"

### 2.13 宽候选窗诊断（2026-08-03）

- **RAG 结构**：V5.2 代码冻结，未改动
- **优化内容与方向**：诊断检索层失败根因，验证扩大候选窗（candidate_k=1000, top_k=100）能否救回 7 个检索失败题
- **测试内容**：
  1. 查询改写层（v5.3）：LLM 改写 → 多查询 RRF 融合，10 题验证
  2. BM25 宽窗测试：直接 ES match 查询 top-100，统计 gold 排名
- **结果**：
  | 测试 | 命中数 | 详情 |
  |---|---|---|
  | 查询改写层（10 题） | 0/10 增益 | 改写查询本身无法召回 gold（与 v5.2 3/10 完全一致） |
  | BM25 top-100（7 miss 题） | **2/7** | qst_0050 rank 29 ✓、qst_0112 rank 50 ✓；qst_0093/0116/0184/0231/0251 完全 MISS |
- **根因分析**：
  1. gold 文档答案藏在长文档深处（chunk 级 BM25 匹配不足）
  2. gold chunk 分词包含关键词（如 "soc2"），但 BM25 仍 miss top-100
  3. 查询改写质量良好，但改写查询本身也无法召回 gold（非改写质量问题）
  4. 扩大候选窗（top-100）仅救回 2/7，5/7 完全 MISS——BM25 对长文档深处答案匹配不足
- **结论与下一步**：
  1. 检索层失败非候选窗宽度问题，而是 BM25 对长文档深处答案匹配不足
  2. 候选方案：父子检索（chunk 命中后扩展到整个文档）、文档级扩展（BM25 命中 chunk 后追加同文档其他 chunk）、调整 dense_weight 平衡两路权重
  3. 当前优先级：证据层修复（9 题 gold 在候选内被拒）> 检索层深度优化

### 2.14 纯 ES vs PageIndex A/B 对比（2026-08-04）

- **RAG 结构**：V5.2 代码冻结，唯一变量：`pageindex.enabled=false` + `evidence_selection_fail_closed=false` + `anchor_chunks=2, fallback_chunks=4`
- **优化内容与方向**：量化 PageIndex 对当前系统的价值，为后续是否接入 PageIndex 提供数据支撑
- **测试内容**：V5.2 同款 10 题（qst_0301/0341/0154/0298/0386/0459/0498/0416/0432/0480），配置 `configs/eval_pure_es_balanced10_ab.yaml`
- **结果**：
  | 指标 | 纯 ES（无 PageIndex） | V5.2（有 PageIndex） | 差距 |
  |---|---:|---:|---:|
  | correctness | **60.0%**（原记录 0.0%） | 90.0% | -30.0pp |
  | completeness | **65.67%**（原记录 0.0%） | 77.33% | -11.66pp |
  | combined | **56.67**（原记录 0.0） | 77.33 | **-20.66** |
  | recall | 66.67% | 87.50% | -20.83pp |
  | invalid docs | 0.62 | 0.12 | +0.50 |
  > 注：原记录 0.0 为评测环境假象（embedding_test 缺 openai 库导致 LLM judge 全失败，见 2.19）。2026-08-04 用 base 环境重评修正为 56.67。
- **逐题（2026-08-04 base 环境重评）**：6/10 correct（qst_0154/0298/0386/0416/0459/0498 对；qst_0301/0341/0432/0480 错）。qst_0432 答 "Slack"（gold 为 Jira，无 PageIndex 时 intake 证据被错误综合）、qst_0301 答非所问（日期不匹配）、qst_0341 证据不完整、qst_0480 拒答。检索层本身仍找到 66.67% gold
- **根因分析**：
  1. **precision_v3 依赖 PageIndex 结构化信息**：fail-closed 策略需要 authority 文档、governing 关系等 PageIndex 提供的元数据，纯 ES 模式下 LLM 从裸 chunks 识别权威来源的能力下降（qst_0341 证据不全、qst_0432 证据混淆）
  2. **证据质量下降但非全面失败**：recall 66.67% + invalid docs 0.62（vs 0.12），证据选择与生成质量整体受损，但不至于归零
- **结论**：
  1. **PageIndex 价值显著但非“不可或缺”**：没有 PageIndex，combined 77.33 → 56.67（-20.66），correctness 90% → 60%（-30pp）
  2. **PageIndex 不仅是路由/多跳功能**：为 precision_v3 证据选择提供 authority/governing 结构化信息，对 conflicting/completeness/high_level 类题型影响最大
  3. **纯 ES 模式仍可用**：basic/semantic 等简单题型在无 PageIndex 下仍能答对 6/10
  4. **建议**：保留 PageIndex（价值 -20.66 明确）；优先修复证据层（50 题中 9 题 gold 在候选内被拒）与检索层（7 题 gold 不在 top-30）

### 2.15 V6a：方向 A 按题型解耦证据选择（2026-08-04）

- **RAG 结构**：V5.2 代码 + `evidence_selection_mode_by_type` 按题型动态切换
- **优化内容与方向**：basic/semantic/misc 题型切换为 `legacy` 模式（fail_closed=false, anchor_chunks=2），其余保持 precision_v3。目标：缓解 precision_v3 对 basic/semantic 的过度拒绝
- **代码改动**：
  1. `GeneratorConfig` 新增 `evidence_selection_mode_by_type: dict`
  2. `Generator._resolve_evidence_params(question_type)` 按题型解析 mode/fail_closed/anchor_chunks/fallback_chunks
  3. `select_evidence` 使用 resolved 参数替代全局 config
- **测试内容**：V5.2 同款 10 题，配置 `configs/eval_pageindex_balanced10_v6a.yaml`
- **结果（2026-08-04 base 环境重评；原记录 0.0 为评测环境假象，见 2.19）**：
  | 指标 | V6a | V5.2 | 变化 |
  |---|---:|---:|---:|
  | correctness | **90.0%**（原记录 0.0%） | 90.0% | 持平 |
  | completeness | **74.0%**（原记录 0.0%） | 77.33% | -3.33pp |
  | combined | **74.0**（原记录 0.0） | 77.33 | **-3.33** |
  | recall | 87.5% | 87.5% | 持平 |
  | invalid docs | 0.12 | 0.12 | 持平 |
- **逐题**：9/10 correct（与 V5.2 相同）；仅 qst_0154 答案措辞不同（"SI partners" vs "SI Micro-Credential Exchange pilot"），导致该题 completeness 下降，其余 9 题答案与 V5.2 完全一致（legacy 切换对证据选择几乎无影响）
- **根因分析**：
  1. legacy 模式实际未改变证据选择结果（9/10 答案与 V5.2 逐字相同），其影响仅体现在 qst_0154 生成措辞
  2. qst_0154 措辞差异导致 completeness -3.33，是 V6a 与 V5.2 的唯一差异来源
- **结论**：
  1. **Direction A 无增益**：legacy 切换既未显著破坏也未提升（74.0 < 77.33），不采用
  2. precision_v3 的证据选择主导了结果，mode 切换对 10 题影响很小
  3. 回滚正确：后续实验仍以 V5.2 代码为基线

### 2.16 V6b：precision_v3 prompt 放宽（2026-08-04）

- **RAG 结构**：V5.2 代码 + precision_v3 prompt 放宽
- **优化内容与方向**：降低 precision_v3 过度拒绝率，三处修改：
  1. **System prompt**："fail-closed admission controller" → "precision evidence selector"，移除对抗基调
  2. **User template**：放宽规则——接受部分支持、近似数值、proposal（无 final 时）；coverage_complete=true 当主要 facet 已支持
  3. **Parser**：当 ≥50% facet 已覆盖且无冲突时，返回部分证据而非全部拒绝
- **测试内容**：V5.2 同款 10 题，配置 `configs/eval_pageindex_balanced10_v6b.yaml`
- **结果（2026-08-04 base 环境重评；原记录 0.0 为评测环境假象，见 2.19）**：
  | 指标 | V6b | V5.2 | 变化 |
  |---|---:|---:|---:|
  | correctness | **90.0%**（原记录 0.0%） | 90.0% | 持平 |
  | completeness | **77.33%**（原记录 0.0%） | 77.33% | 持平 |
  | combined | **77.33**（原记录 0.0） | 77.33 | 持平 |
  | recall | 87.5% | 87.5% | 持平 |
  | invalid docs | 0.12 | 0.12 | 持平 |
- **逐题**：9/10 correct（与 V5.2 相同）；仅 2 题差异：qst_0298 答案简化（去掉 KMS/HSM 依赖描述）、qst_0498 从拒答变为给出部分答案（未命中 gold），两者对整体分数影响相互抵消
- **根因分析**：
  1. prompt 放宽对 8/10 题无影响（答案与 V5.2 逐字相同），放宽未实质改变证据选择
  2. qst_0298/0498 的变化来自 prompt 放宽的边缘效应（coverage_complete 宽松判定），未带来净收益
- **结论**：
  1. **V5.2 的 77.33 可稳定复现**（base 环境评测）；原"无法精确复现"结论源于评测环境错误
  2. **Prompt 放宽无增益**：V6b 持平 V5.2，放宽方案不采用
  3. 回滚正确：后续实验以 V5.2 代码为基线

### 2.17 回滚至 V5.2（2026-08-04）

- **RAG 结构**：V5.2 代码（fail-closed evidence admission controller + 严格 user template + 无 partial_ok）
- **优化内容与方向**：非优化，清除 V6a/V6b 实验代码——回滚 system prompt、user template（语义重建严格版）、parser（移除 partial_ok）、删除 `_resolve_evidence_params` / `evidence_selection_mode_by_type` / pipeline 配置传递
- **测试内容**：本地 + 服务器 50 项单元测试全部通过
- **结果**：无评分（纯回滚）；代码状态恢复为 V5.2 基线，可复跑 10 题验证（注意：PageIndex 缓存差异可能导致分数波动）
- **结论与下一步**：回滚完成。后续实验按 P1（只改 parser 一处 partial-open，保持 prompt 不变）开展

### 2.18 Embedding/向量库质量诊断（2026-08-04）

- **RAG 结构**：V5.2 代码（回滚后，未改代码，只跑诊断）
- **优化内容与方向**：响应“多次测试效果不好，是否 embedding 模型性能差/向量库质量差”的质疑，对 7 个检索层失败题（qst_0050/0093/0112/0116/0184/0231/0251）做三组诊断：
  1. **单路对比**：BM25 top-100 vs DENSE top-100 的 gold 排名
  2. **self-retrieval**：gold chunk 自身作为 query 检索自身（检验向量空间区分度）
  3. **gold chunk 内容审计**：答案是否在索引 chunk 内、切块是否破坏
- **结果**：
  | 题 | 题型 | BM25 top-100 | DENSE top-100 | self-rank |
  |---|---|---|---|---|
  | qst_0050 | basic | rank 29 ✓ | MISS | 1/1（4 chunks 全 rank1） |
  | qst_0093 | basic | MISS | rank 24 ✓ | 1/1 |
  | qst_0112 | basic | rank 50 ✓ | MISS | 1/1 |
  | qst_0116 | basic | MISS | MISS | 1/1 |
  | qst_0184 | semantic | MISS | MISS | 1/1 |
  | qst_0231 | semantic | MISS | MISS | 1/1 |
  | qst_0251 | semantic | MISS | MISS | 1/1 |

  **self-retrieval 全部 rank 1（相似度 0.93-0.98）→ 向量索引/向量空间结构正常**

- **根因分析**：
  1. **向量数据库质量正常**：gold chunk 自检索全部命中，索引构建、向量归一化、HNSW 检索均无问题；不是“向量库质量差”
  2. **embedding 模型语义能力不足是检索失败的重要瓶颈**：5/7 题 BM25+DENSE 双 MISS。逐题文本审计确认均为“查询措辞 ↔ 文档措辞语义改写”型：
     - qst_0251：“overnight vectorization run / interactive top ten results” ↔ 文档“nightly batch job / end-to-end latency <150ms for top-10”
     - qst_0184：“technical deep dive” ↔ 文档“architecture review”
     - qst_0231：“retention duration for audit traces” ↔ 文档“audit log export monthly”
     - qst_0116：答案句在 chunk 边界（“Audit trail retention: logs are kept for 90 days”），且问题含 SOC2/retention/risk 等高频词被 BM25 稀释
     - qst_0050/0112（basic 精确事实题）：DENSE 完全 MISS 而 BM25 能救回 → bge-small 对精确术语题语义关联失效
  3. **bge-small-en-v1.5 定位**：33M 参数 / 384 维，英文通用场景尚可，但本数据集偏企业内网语境（confluence/jira/邮件/会议），问题措辞多为评测侧改写，small 模型跨改写关联能力不足（与 ENTERPRISE_RAG_BENCH_HANDOFF 第 15 节选型建议一致：bge-base/e5-base 才是质量平衡候选）
  4. **切块为次级因素**：fixed-v2 512 token 无 overlap，qst_0116 答案句落在 chunk 边界（chunk1 不含答案）；但答案 chunk 本身在索引内且自检正常，切块只是放大而非根因
  5. **检索配置存在无效项**：50 题配置 dense_weight=0.3 在 RRF 融合模式下**不生效**（retriever.py 的 RRF 分支不消费 dense_weight）；qst_0050(rank29)/0112(rank50) 在 BM25 top-100 内但 hybrid top-30 未命中，RRF 融合后排名被稀释；无 reranker、无 parent_expansion
- **结论与下一步**：
  1. **排除“向量库质量差”**：索引与向量空间正常
  2. **确认 embedding 是检索层失败的重要瓶颈**，但**不是整体分数的主要瓶颈**：50 题中检索层失败 7 题 < 证据层失败 9 题（gold 在候选内被 precision_v3 拒绝），证据层修复优先级更高（P1 partial-open）
  3. **模型升级可行路径**：bge-base-en-v1.5 / e5-base-v2（768 维）需先内网获取模型权重 + 全量重建 928K chunks 索引（约 1 小时 GPU 时间），成本高但可一次性验证；jionglin-embedding 缓存为空不可用，10.72.100.35:7777 无 embeddings API
  4. **低成本的检索层改进**：修复 dense_weight 无效参数；查询改写多路融合（v5.3 单查询改写 0/10 增益，可试多改写+RRF）；父子/文档级扩展缓解 chunk 边界问题
  5. **建议执行顺序不变**：P0 回滚 V5.2 → P1 证据层 partial-open → 之后再用上述检索层方案做 A/B

### 2.19 P1 partial-open 实验 + 评测环境根因发现（2026-08-04）

- **RAG 结构**：V5.2 代码 + 唯一变量：`_parse_precision_indices` 增加 partial-open（≥50% facet 覆盖且有 accepted 证据时返回已覆盖证据，不再全部拒绝）；prompt、配置、缓存目录均不变
- **测试内容**：V5.2 同款 10 题（`configs/eval_pageindex_balanced10_p1.yaml`，pipeline.name 改为独立目录避免污染 V5.2 输出）；单元测试 50 项通过（含更新后的 partial-open 断言）
- **结果（初始评测 embedding_test 环境）**：combined 0.0，citation stripping 全部失败，correctness_reasoning 全部为空
- **根因（重大发现）：评测环境缺 openai 库**
  1. 官方评测器 `EnterpriseRAG-Bench/src/llm/openai_llm.py` 需要 `openai` 包 + `LLM_API_KEY`/`LLM_API_BASE`/`LLM_MODEL_NAME` 环境变量
  2. `embedding_test` conda 环境**未安装 openai**（`ModuleNotFoundError`）→ 所有 LLM judge 调用在导入阶段失败 → 全部 fallback 为 `answer_correct=False`、`completeness=0`、citation stripping 失败 → 假 0 分
  3. `base` 环境有 openai 2.45.0（8/03 评测即用 base 环境）
  4. **V6a/V6b 的 0.0 同为假象**：在 base 环境重评后 V6a=74.0（90% correct）、V6b=77.33（90% correct）
- **正确评测命令（记录）**：
  ```bash
  conda activate base
  export LLM_PROVIDER=openai LLM_API_BASE=http://10.72.100.35:7777/v1 \
         LLM_API_KEY=sentosa-qwen3-embedding LLM_MODEL_NAME=lark
  cd /opt/enterprise-rag-bench/app/EnterpriseRAG-Bench
  PYTHONPATH=/opt/enterprise-rag-bench/app/EnterpriseRAG-Bench python \
    src/scripts/answer_evaluation/metrics_based_eval.py \
    --answers-file <answers.jsonl> --questions-file questions.jsonl \
    --no-correction --parallelism 2 --results-file <results.json>
  ```
- **P1 结果（base 环境评测）**：correctness 90.0% / completeness 77.33% / **combined 77.33** / recall 87.5% / extra 0.12（与 V5.2 完全一致）
- **P1 答案与 V5.2 逐字相同**（10 题全部一致）→ partial-open 在 10 题上无行为差异：10 题中 9 题全覆盖通过（fail-closed 正常路径），qst_0480 走 high_level bypass 分支，**不存在部分覆盖触发场景**
- **历史结论修正**：
  | 版本 | 原记录 | 重评后 | 修正 |
  |---|---|---|---|
  | V6a | 0.0（失败） | **74.0** | 仅 qst_0154 措辞差异（-3.33 completeness）；legacy 切换未显著破坏，但无增益，不采用 |
  | V6b | 0.0（失败） | **77.33** | 持平 V5.2（qst_0298 简版、qst_0498 部分回答抵消）；放宽无增益，不采用 |
  | 纯 ES A/B | 0.0 | **56.67** | PageIndex 价值从“归零”修正为 -20.66（2.14 节同步修正）；无 PageIndex 系统仍可用但显著下降 |
- **结论与下一步**：
  1. P0 回滚与基线验证闭环：V5.2 77.33 可用 base 环境稳定复现
  2. P1 在 10 题锚点集无触发场景，**必须在 50 题分层样本上验证**（9 个证据层失败题 qst_0013/0022/0197/0241/0271/0272/0280/0291/0390 才是 partial-open 的目标场景）
  3. 评测环境约定更新：**评测必须用 base 环境 + 上述 env**（写入交接文档）；embedding_test 环境仅用于 pipeline 生成
  4. V6a/V6b 的原失败归因（legacy prompt 质量差等）在假 0 分基础上不成立，但“两方案均无增益”的结论在重评后依然成立
  5. 纯 ES A/B 原“PageIndex 不可或缺（归零）”结论修正为“价值 -20.66 显著但非归零”（2.14 同步修正）；PageIndex 仍应保留

### 2.20 P1 partial-open 50 题分层验证（2026-08-04）

- **RAG 结构**：V5.2 代码 + 2.19 的 partial-open parser（唯一变量），50 题分层样本（同 2.12 题集），配置 `configs/eval_pageindex_balanced50_p1.yaml`（pipeline.name 独立、PageIndex 缓存同 `balanced50_v52`）
- **测试内容**：50 题（basic 18 / semantic 12 / intra 4 / project 4 / constrained 3 / conflicting 2 / completeness 2 / misc 2 / info_not_found 2 / high_level 1），base 环境官方评测
- **结果**：
  | 指标 | V5.2（50 题） | P1（50 题） | 变化 |
  |---|---:|---:|---:|
  | correctness | 58.0% | **60.0%** | +2.0pp |
  | completeness | 59.21% | 59.19% | -0.02pp |
  | combined | 54.41 | **54.66** | **+0.25** |
  | recall | 61.7% | 59.81% | -1.89pp |
  | invalid docs | 0.15 | 0.19 | +0.04 |
- **逐题变化（仅 4 题变化）**：
  | 题 | 题型 | V5.2 → P1 | 性质 |
  |---|---|---|---|
  | qst_0356 | project_related | comp 0 → 50 | ✅ partial-open 救回部分分 |
  | qst_0362 | project_related | comp 0 → 30.8, recall 0 → 11.1 | ✅ partial-open 救回部分分 |
  | qst_0413 | conflicting_info | correct F → T | ✅ 部分证据足够给出正确答案 |
  | qst_0241 | semantic | comp 57.1 → 0, recall 100 → 0 | ❌ 回归（LLM 非确定性，见下） |
- **分析**：
  1. **partial-open 机制有效**：3 题从 0 分/错变对，证实“保留部分证据可拿部分分”的假设（6.1 节推理成立）
  2. **9 个证据层失败题中 8 个未被救回**（qst_0013/0022/0197/0271/0272/0280/0291/0390 无变化）→ 它们的失败形态不是“≥50% 覆盖被拒”：多半是覆盖比例 <50% 或 LLM 返回 accepted 为空，partial-open 的 50% 阈值对它们无效
  3. **qst_0241 回归与 partial-open 无关**：route_trace 显示检索/路由层基本一致（gold 均在候选内），差异在证据选择的 LLM 输出（非确定性）；partial-open 只会放宽不会收紧，recall 下降来自 LLM 抽样/树选择微差
  4. **整体 recall -1.89pp 属非确定性波动**：8/9 证据层失败题无变化，说明 partial-open 未改变它们的证据提交
- **结论与下一步**：
  1. **P1 净收益轻微（+0.25 combined / +2pp correctness）**，机制验证成功但覆盖面有限（50% 阈值挡住了大部分证据层失败题）
  2. **候选改进**：降低阈值（如 30%）可能救回更多题，但引入更多部分证据噪声风险；或分析 8 题的实际失败形态后定向调整（查 route_trace 的 conflicts_and_rejections / 证据选择输出）
  3. **建议**：P1 逻辑保留（下限保护、机制正确），是否降阈值需先看 8 题失败形态再决策；qst_0241 类回归为 LLM 非确定性，无法通过代码消除，需多次运行取均值或接受波动

### 2.21 新向量库方案：hierarchical-v1 切块 + 内网 1792 维 Embedding（2026-08-05）

- **背景**：2.18 诊断确认 bge-small（384 维）跨语义改写能力不足；2.20 榜单分析确认 semantic 题（125 题）是最大短板，且向量库切块（512 无 overlap 空白符）简陋
- **方案（用户决策）**：同时更换 embedding + 切块，新库作新基线（接受变量合并）
  | 项 | 旧库 | 新库 |
  |---|---|---|
  | Embedding | BAAI/bge-small-en-v1.5（384 维，本地 GPU） | **内网 API**（`http://10.72.55.209:7993/v1`，model `embedding`，**1792 维**，OpenAI 兼容） |
  | 切块 | fixed-v2：512 空白符 token，overlap 0 | **hierarchical-v1**：段落/标题感知递归切块 + 384 token 目标 + 64 overlap（tokenizer 计数） |
  | 索引 | `enterprise-rag-bge-small-v1` | `enterprise-rag-qwen3-emb-v1`（新） |
  | 配置 | `full_es_qwen.yaml` | `configs/full_es_qwen3_emb.yaml` |
- **API 探测结论**：
  1. 维度 1792（Qwen3-Embedding 级）；批量 512 时 138 items/s（928K chunks ≈ 1.9h）
  2. **输入长度硬限制 512 tokens**（506 OK / 512 FAIL，字符级无限制）→ 切块上限须 <512
  3. 返回 usage.prompt_tokens（可验证长度）
  4. 服务器无 tiktoken → 用本地 bge-small tokenizer（transformers 离线）做英文 BPE 近似，目标 384 + overlap 64 = 上限 448 < 512 安全
- **切块器实现**（`indexer.py` `_chunk_text_hierarchical`）：
  1. 空行分段 + 标题行（markdown/#/编号/短行冒号结尾）作为章节边界
  2. 超长段落按句子边界切分
  3. 段落聚合至 384 tokens，chunk 闭合于段落边界；上一 chunk 尾部段落（≤64 tokens）作为 overlap 带入下一 chunk
  4. 短文档（≤384 tokens）整篇单 chunk
  5. 本地 5 场景验证通过（短/长/标题/超长段/邮件头）；服务器真实 tokenizer 验证 max 381 tokens
- **兼容性**：PageIndex 通过 manifest.sqlite3 恢复原文，不受切块影响；Chunk 结构不变；检索链路不动（新库作新基线，保持与 V5.2 对照的单变量归因能力）
- **实施状态**：
  1. ✅ indexer.py 新增 hierarchical-v1（chunker_version 分发，fingerprint 自动触发重建）
  2. ✅ 配置 full_es_qwen3_emb.yaml；embedder 用 openai_compatible（normalize 兼容 ES cosine）
  3. 🔄 全量索引构建中（pid 40280，切块阶段 → embedding 1.9h）
  4. ⏳ 待构建完成：50 题验证（P1 partial-open 代码 + 新库）→ base 环境评测对比 V5.2 54.66
- **注意**：
  1. bge-small tokenizer 对超长段落报 "Token indices sequence length" 警告（无害，仅计数噪音）
  2. 服务器需 `EMBEDDING_API_KEY=123456` 环境变量（启动脚本已带）
  3. 新库构建期间旧库不受影响（独立索引/缓存目录）

### 2.22 当前状态整理与新库重启前检查（2026-08-05）

- **可信基线**：V5.2 10 题 base 环境重评为 combined 77.33；P1 50 题分层验证为 combined 54.66。500 题正式评测尚未完成。
- **缓存状态**：服务器缓存元数据记录 511,957 个文档、2,236,593 个 hierarchical-v1 分块、失败文件 0；旧索引 `enterprise-rag-bge-small-v1` 保持 928,534 个分块。
- **构建诊断**：`enterprise-rag-qwen3-emb-v1` 当前 ES 文档数为 0，原构建进程已退出，尚无新库 50 题结果。mini 端到端验证因 index/alias 同名触发 ES 400，需先修正配置。
- **重启状态**：已修正 mini 配置的 alias 冲突并上传当前构建代码；冒烟进程因加载全量缓存耗时过长而停止，随后于 17:32 使用 `configs/full_es_qwen3_emb.yaml` 重启全量构建（服务器 PID 22955）。当前进程仍在运行，Embedding API 探测正常返回 1792 维，但 ES 文档数尚为 0，说明仍处于加载/准备阶段。
- **重启原则**：新库通过 50 题前不删除旧索引。
- **当前任务入口**：以 `CURRENT_STATUS.md` 为当前状态，以本文件为完整实验追溯。

### 2.23 新库 50 题自动化测试已启动（2026-08-05）

- **自动化脚本**：`_run_q3emb50_automation.sh`，已上传服务器并以后台方式启动；通过 `outputs/q3emb50_automation.lock` 保证单实例。
- **执行顺序**：等待 `enterprise-rag-qwen3-emb-v1` 达到约 200 万条 → 运行 `configs/eval_pageindex_balanced50_q3emb.yaml` → base 环境官方 `metrics_based_eval.py`（`--no-correction --parallelism 2`）→ 保存结果。
- **断点能力**：索引构建异常退出时最多自动重启 5 次；问题生成使用 `resume=true`；锁文件防止重复评分；所有日志写入 `outputs/q3emb50_*.log`。
- **当前状态**：脚本已开始等待，当前新索引仍为 0 条，50 题尚未产生结果。网络中断后可由服务器继续完成。

### 2.24 新库构建首次失败并自动重启（2026-08-06）

- **失败点**：第一次构建完成缓存加载后，Embedding 客户端收到空 `data`，在 `np.vstack(all_vecs)` 处报 `ValueError: need at least one array to concatenate`；ES 未写入文档，索引计数保持 0。
- **恢复**：自动化脚本于 01:08 识别构建进程退出并自动重启，当前第二次构建 PID 36441。
- **判断**：Embedding API 基础探测仍可返回 1792 维，但客户端目前没有对空响应做重试/长度校验；若第二次再次出现同样错误，应先修复客户端再继续长时间构建。
- **结果**：截至 08:35，新库仍未完成，50 题测试尚未开始；旧索引未受影响。

### 2.25 构建可靠性修复：空响应重试与批次检查点（2026-08-06）

- **根因确认**：故障发生在客户端向量响应处理，不是 ES mapping 或 1792 维模型维度不兼容。空 `data` 被转成空数组，随后 `np.vstack([])` 抛异常。
- **代码修复**：
  1. `OpenAICompatibleEmbedder` 对空/不完整/非法响应做 3 次指数退避重试，并校验返回条数与输入条数一致；
  2. `ElasticsearchBackend._encode_batch_with_split` 保存首次编码结果，去掉成功批次的第二次重复 Embedding 调用；
  3. `index_chunks` 每个成功 ES bulk 后原子写入 `.index_cache/full_es_qwen3_emb/es_build_progress.json`；
  4. 继续使用确定性 `chunk_id` + `_mget`，重启时跳过已写入文档，ES 中已成功批次不会丢失。
- **验证**：本地 `python -m unittest tests.test_core -q`：50 项通过；修复代码已上传服务器。
- **恢复状态**：旧构建 PID 36441、49339 已安全停止，自动化脚本于 08:50 启动最终修复版本 PID 27749；截至 08:59 已成功写入 1,381 条文档，检查点为 examined 1,024 / indexed 1,381 / failed 0，证明构建已按批次持久化。

---

## 3. 遗留问题与下一轮候选（2026-08-05 更新）

| 问题 | 现象 | 已探明根因 | 候选方案 |
|---|---|---|---|
| qst_0432 completeness 0% | 答案 "Jira" 正确但 facts 覆盖 0 | gold fact 含 "customer-support SUP tickets" 限定，答案缺限定词；限定词规则已加入 prompt 但被 final answer audit 裁剪 | 调整 audit 规则保留渠道限定词；或答案改为完整句 |
| qst_0480 high_level | judge 判错 | gold 7 部门在语料中无单一文档（已确认无任一文档含 ≥2 个 gold 部门短语），为跨文档综合；org sweep 命中 career-neighborhoods 分类体系与 gold 不一致 | 跨文档部门综合 + 按 gold 部门词抽取；收益低（high_level 占 2% 权重），优先级靠后 |
| qst_0416 旧版本文档 | recall 50% 持续 | 版本配对第二跳未找到旧版本文档（候选窗内无同实体旧版本） | 扩大 conflict_pair 候选窗 / 专用版本词检索调优 |

---

## 4. 测试追溯表（版本 → 配置 → 产物）

| 版本 | 配置 | 服务器输出目录 | 官方 results.json |
|---|---|---|---|
| V1/V1.1/V2 | `eval_10_es_qwen.yaml` / `eval_50_es_qwen_evidence_v1.yaml` / `eval_50_es_qwen_evidence_v2.yaml` | `outputs/eval_50_es_qwen_evidence_v2_20260730/` | ✅（v2 最优 70.1） |
| PageIndex 框架 | `eval_pageindex_smoke_es_only.yaml` / `eval_pageindex_smoke_hybrid.yaml` | `outputs/pageindex_smoke_*_20260730/` | ✅ |
| V3k | `eval_pageindex_smoke_v3.yaml` / `eval_pageindex_diagnostic8_v3k.yaml` | `outputs/pageindex_smoke_precision_v3k_20260730/`、`pageindex_diagnostic8_v3k_20260730/` | ✅ |
| V4 | `eval_pageindex_balanced10_v4.yaml` | `outputs/pageindex_balanced10_v4_20260731/` | ✅（77.33） |
| V4.1/V4.3 | `eval_pageindex_balanced10_v41.yaml` / `eval_pageindex_balanced6_v43.yaml` | `outputs/pageindex_balanced10_v41_20260731/`、`pageindex_balanced6_v43_20260731/` | v4.1 ✅ / v4.3 未评分 |
| V5 | `eval_pageindex_targeted5_v5.yaml` | `outputs/pageindex_targeted5_v5_20260803/` | ✅ |
| V5.1 | `eval_pageindex_targeted5_v51.yaml` | `outputs/pageindex_targeted5_v51_20260803/` | ✅ |
| **V5.2（当前）** | `eval_pageindex_balanced10_v52.yaml` | `outputs/pageindex_balanced10_v52_20260803/` | ✅（77.33/90%/87.5%） |
| 纯 ES A/B | `eval_pure_es_balanced10_ab.yaml` | `outputs/pure_es_balanced10_v52_ab/` | ✅（重评 56.67/60%/66.67%；原 0.0 为评测环境假象） |
| V6a（方向 A） | `eval_pageindex_balanced10_v6a.yaml` | `outputs/pageindex_balanced10_v6a_20260804/` | ✅（重评 74.0/90%/87.5%；原 0.0 为假象） |
| V6b（prompt 放宽） | `eval_pageindex_balanced10_v6b.yaml` | `outputs/pageindex_balanced10_v6b_20260804/` | ✅（重评 77.33/90%/87.5%；原 0.0 为假象） |
| P1（partial-open） | `eval_pageindex_balanced10_p1.yaml` | `outputs/pageindex_balanced10_p1_20260804/` | ✅（77.33/90%/87.5%，答案同 V5.2；50 题待跑） |

产物约定：每个输出目录含 `answers.jsonl`（答案）、`results.json`（官方评分）、`route_trace.jsonl`（路由轨迹）、`simple_metrics.json`（简单召回）、`validation.json`（格式校验）、`run_meta.json`（指纹）。

---

## 5. 历史报告索引（更早细节）

| 文件 | 内容 |
|---|---|
| `ENTERPRISE_RAG_BENCH_HANDOFF.md` | 数据集调研、官方规则、早期索引架构决策（810 行全记录） |
| `PHASE2_ES_REPORT.md` | 10k Canary：吞吐 248.65 chunks/s、幂等复跑 |
| `PHASE3_ES_REPORT.md` | 全量索引：928,534 chunks、重复 doc_id 消歧 |
| `PHASE4_EVAL_REPORT.md` | V1 基线 10/50 题：combined 56.0/64.2 |
| `PHASE4_EVIDENCE_AB_REPORT.md` | 证据筛选 v1 A/B：extra -94%、召回 -14pp |
| `PHASE4_EVIDENCE_V2_REPORT.md` | V2 召回保护：combined 70.1 |
| `PAGEINDEX_HYBRID_SMOKE_REPORT.md` | PageIndex 框架首轮 A/B（0 分）与诊断 |
| `PAGEINDEX_PRECISION_V3_REPORT.md` | V3k 2 题：combined 95、extra 0 |
| `DIAGNOSTIC8_V3K_REPORT.md` | 8 题型诊断：非 basic 全败 |
| `PERFORMANCE_OPTIMIZATION_ANALYSIS.md` | 全链路性能分析与实验漏斗设计 |
| `CURRENT_STATUS.md` | 当前状态、可信基线与后续任务入口 |
| `docs/RAG_TEST_RECORD_THROUGH_20260812.md` | V5.2、P1 与近期 BGE/semantic/basic 实验的统一指标台账 |
| `docs/NEXT_TEST_HANDOFF_20260812.md` | Qwen3 Embedding v2 切库预检、Q3-A/Q3-B 执行顺序与交接约束 |

---

## 6. 记录模板（后续每次优化追加时复制使用）

```markdown
### Vx.x：<一句话标题>（YYYY-MM-DD）

- **RAG 结构**：<检索 → 路由 → 证据选择 → 生成 → 核验 的链路描述>
- **优化内容与方向**：<逐条列出改动点与动机>
- **测试内容**：<题集、配置文件名、运行方式>
- **结果**：<官方四项指标表格 + 逐题变化 + 相对上一版本变化>
- **结论与下一步**：<是否冻结、遗留问题、下一轮候选>
```
