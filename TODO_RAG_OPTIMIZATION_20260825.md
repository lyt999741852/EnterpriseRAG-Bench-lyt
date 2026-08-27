# RAG 优化任务清单（2026-08-25）

## 运行约定

- 工作分支：`codex/semantic-a0`。
- 冻结对照：500 题 BGE + PageIndex no-correction **55.18**；Semantic30 S1（PageIndex OFF）综合 **45.56**；AB50 PageIndex ON **59.34**。
- 不重建或覆盖 BGE ES、manifest、冻结输出和历史 cache；每个新实验使用独立的 YAML、`pipeline.name`、output 与 PageIndex cache。
- 线上链路只接收 question ID 与 question。`expected_doc_ids`、真实题型和评分结果只能用于运行结束后的离线诊断。
- 不在配置、脚本、日志或本文件中写入密钥。远端访问和 rerank 仅通过环境变量提供认证。
- 打榜评估以官方综合分、答案正确性/完整性和目标证据召回为主；`invalid_extra_docs` 仅作诊断指标，不作为单独的硬性淘汰条件。只有在额外文档实际造成答案错误、引用污染或官方分数下降时，才阻断合流。

## Git 提交规则

每个完成且验证通过的任务都遵循以下顺序：

1. 记录任务产物、验证命令和结果到本文件或对应报告。
2. 仅审阅本任务允许提交的文件：`git diff -- <file...>` 与 `git status --short`。
3. 仅暂存允许提交的文件：`git add -- <file...>`；绝不使用 `git add .`。
4. 提交到当前 `codex/semantic-a0` 分支，提交信息说明任务和验证结果。
5. 向用户报告提交 hash、文件清单和验证结果，等待明确确认后才执行 `git push origin codex/semantic-a0`。

现有工作区的其他修改、删除和未跟踪文件均为隔离内容，不属于下表的允许提交范围。

## 任务队列

| ID | 状态 | 工作内容 | 验证/通过门槛 | 允许提交的新增或修改文件 |
|---|---|---|---|---|
| A0.0 | 已完成 | 安全运行前置：以环境变量认证，核验远端 ES、reranker、LLM、manifest，以及 S1 30 题产物完整性。 | LLM、reranker、ES 均可用；S1 有 30 条 answer、trace、score；不使用含硬编码凭据的旧远程工具。 | `scripts/remote/_remote.py`、`scripts/remote/a0_preflight_semantic30.sh`。 |
| A0.1 | 已完成 | 对 S1 完成离线失败分桶。 | 30 题均有唯一 bucket：`raw_miss`、`rrf_or_rerank_drop`、`selector_drop`、`generation_gap` 或 `fully_successful`；输出汇总与逐题 JSON。 | `scripts/diag/audit_semantic_failure_layers.py`；`docs/SEMANTIC30_S1_A0_DIAGNOSTIC_20260825.md`。 |
| A1.P | 未通过，已停止 | 以单条、问题文本约束的 bridge query 对 9 道 raw-miss 做只读 BGE dense probe。 | 9 条有效 query 的目标文档命中为 **0/9**；不满足继续 A1/A2 的条件。 | `scripts/diag/probe_semantic_bridge_raw_miss.py`；`docs/SEMANTIC_A1_BRIDGE_PROBE_20260825.md`。 |
| A1.0 | 待开始 | 增加单一、受约束的 Semantic bridge query：只能提取题干已有实体、系统、事件与时序/因果关系，不能猜答案或锁定文档。 | 10 题串行冒烟完成，答案/trace/checkpoint 完整，无索引写入。 | 新配置、实现、测试、冒烟报告。 |
| A1.1 | 待开始 | 在固定 Semantic30、PageIndex OFF 上运行 bridge query。 | raw-miss 目标文档命中增加；综合分 **>45.56**。Invalid Extra Docs 仅记录，除非已证实造成答案错误、引用污染或官方分数下降。失败则删除该实验分支，不叠加改动。 | 实验 YAML、结果报告与 trace 清单。 |
| A2 | 待开始 | 将通过的 bridge 结果以低权重 RRF 候选接入，限制每文档 chunk 数，无 hard document lock。 | 召回与综合均提升；extra 仅作污染诊断；独立于 A1 记录。 | 实验 YAML、实现、测试、报告。 |
| A3.A | 已完成 | 对 A0 的 2 个 selector drop 和 4 个 generation gap 做逐题离线证据审计。 | 2 题确认为 selector 误拒；1 题为 final chunk 缺事实且有 extra 污染；3 题为正确答案与 completeness 扣分不一致；干净生成缺口为 0。 | `scripts/diag/audit_semantic_selector_generation.py`；`docs/SEMANTIC_A3_A_SELECTOR_GENERATION_AUDIT_20260825.md`。 |
| A3.P | 已完成 | 对 `qst_0176`、`qst_0272` 各复放 3 次冻结 selector 输入输出。 | 误拒稳定复现 6/6：模型均 accepted 目标 `[1]`、完整覆盖全部 facets，但 strict parser 因非空 `conflicts` 清空证据。 | `scripts/diag/probe_semantic_precision_selector.py`；`docs/SEMANTIC_A3_P_SELECTOR_REPLAY_20260825.md`。 |
| A3.1 | 已完成，通过 | 仅补充 conflict 输出契约：已解决差异写入 `resolved_conflicts`；未解决矛盾继续进入阻断性 `conflicts`；strict parser 不变。 | 两目标各 3/3 恢复 `[1]`；成功/拒答控制均保持；同权威未解决冲突 3/3 拒绝。 | `scripts/diag/probe_semantic_precision_selector.py`；`docs/SEMANTIC_A3_1_CONFLICT_CONTRACT_SMOKE_20260825.md`。 |
| A3.2 | 已完成，通过 | conflict 契约末尾字节与 selector-only 复放对齐后，运行两目标加四控制端到端 smoke。 | 六题 recall 66.7%、extra 0；两目标及 q182 恢复，四控制无退化。 | `scripts/remote/apply_semantic_a32_conflict_contract.py`；`scripts/diag/prepare_semantic_a32_smoke.py`；`docs/SEMANTIC_A3_2_CONFLICT_CONTRACT_E2E_SMOKE_20260826.md`。 |
| A3.3 | 已完成 | 对 q182 的候选集合和 runtime/selector prompt 对齐做离线差异审计。 | 候选 30 chunk 完全相同；根因为应用脚本少一个换行；修正后 q182 通过。 | `docs/SEMANTIC_A3_3_Q182_PROMPT_ALIGNMENT_20260826.md`。 |
| A3.4 | 已完成 | 将已验证 conflict 契约接入固定 Semantic30，单独评测 selector drop 是否改善。 | 官方 combined 由 45.56 提升至 52.22（+6.66）；correctness 56.67%、completeness 60.21%、recall 60.0%；q176/q272 恢复，q0208 保持恢复。Invalid Extra Docs 仅作诊断。 | 独立配置、应用/回滚脚本、`docs/SEMANTIC_A3_4_CONFLICT_CONTRACT_FULL_SMOKE_20260826.md`。 |
| A3 | 已完成 | 仅在 A3.2/A3.3 通过后运行固定 Semantic30；generation gap 仍不处理。 | selector 诊断和官方 Semantic30 评分通过；下一步接回 PageIndex ON 做 AB50 回归；extra 仅作为污染诊断。 | 独立 YAML、结果与报告。 |
| B1.A | 已完成 | 对 AB50 的 Basic 子集做离线覆盖审计。 | 18 题中 3 题为文档已命中、答案正确但完整性不足；4 题为检索/引用问题，排除在生成改动外。 | `scripts/diag/audit_basic_coverage.py`；`docs/BASIC_AB50_B1_AUDIT_20260825.md`。 |
| B1 | 未通过，已停止 | Basic：生成前事实清单与引用覆盖审计，不改检索权重。固定 Smoke10 中 3 个目标题完整度均未改善，且存在非 Basic 对照退化。 | 仅完成 Smoke10；不满足 Basic 改善门槛，未运行 AB50。 | 配置、最小应用/回滚脚本、失败报告。 |
| B2.A | 已完成 | 对 AB50 的 Project 子集做逐目标文档的离线阶段覆盖审计。 | 4 题：1 个 generation coverage gap、3 个 retrieval/citation gap；已区分 raw、rerank、final 与 submitted 覆盖。 | `scripts/diag/audit_project_coverage.py`；`docs/PROJECT_AB50_B2_DIAGNOSTIC_20260825.md`。 |
| B2.P | 未通过，已停止 | Project 锚点 probe 资格检查：完整题干与分面锚点查询已在 AB50 基线执行，重复 BGE 查询不构成新变量。 | `qst_0350` 为 rerank 后段丢弃；`qst_0356/0362` 在已执行锚点下仍 raw 覆盖不足。 | `docs/PROJECT_B2P_PROBE_ELIGIBILITY_20260825.md`。 |
| B2 | 未通过，已停止 | Project：不直接接入统一项目名、组件名、路径/版本词法锚点。 | 不存在可隔离且未被基线覆盖的锚点变量；不运行 smoke/AB50。 | B2.A/B2.P 诊断报告。 |
| B3.A | 已完成 | 对 AB50 的 Completeness 子集做逐目标文档的离线阶段覆盖审计。 | 2 题均为检索/引用缺口，但一题是 selector/citation 缩减，另一题同时为 raw/rerank/final 缺口。 | `scripts/diag/audit_project_coverage.py`；`docs/COMPLETENESS_AB50_B3_DIAGNOSTIC_20260825.md`。 |
| B3.P | 已完成 | 将 Completeness 的 selector/citation 与 raw/rerank 路径分开只读验证。 | `qst_0432` 不具备独立检索变量；`qst_0447` 的多分面计划被单文档模式抵消，放行 question-only 多文档计划候选。 | `docs/COMPLETENESS_B3P_ISOLATED_PROBES_20260825.md`。 |
| B3.1 | 未通过，已停止 | 对题干规划出多个独立分面及多环境硬约束的问题，启用多文档证据计划；不强制 benchmark 题型。 | Smoke10 已完成，但 `qst_0447` 仍为 0% recall/0% completeness/extra 1；所有控制题无变化，不运行 AB50。 | 独立配置、精确应用/回滚脚本、失败报告。 |
| A3.5 | 已完成（局部残留） | 在 generation/final audit 提示词增加直接答案保护，避免不同范围证据把已命中的值改写成未知。 | 六题隔离回归 6/6 完成，qst_0298 直答恢复；完整 AB50 中 qst_0298 仍有过度限定，记录为后续定向优化项。 | `scripts/remote/apply_semantic_a35_generation_conflict_guard.py`；`scripts/diag/run_semantic_a35_generation_smoke.py`；对应配置与报告。 |
| A4/B4 | 已通过 | PageIndex ON AB50 conflict-contract + generation guard 回归。 | 50/50 完成；combined 59.41（基线 59.34，+0.07）、correctness 64.00% 不下降、completeness 66.50%、recall 63.89%；invalid extra 仅作诊断。 | `docs/SEMANTIC_A3_5_GENERATION_CONFLICT_GUARD_AB50_20260826.md`；`configs/eval_pageindex_ab50_semantic_conflict_guard_r3_20260826.yaml`。 |
| R1 | 已完成 | AB50 route trace 检索层分桶。 | raw miss 5、RRF/rerank drop 2、selector/PageIndex drop 7、generation gap 10；见检索审计报告。 | `docs/SEMANTIC_RETRIEVAL_AB50_LAYER_AUDIT_20260826.md`。 |
| R2 | 已完成（不合流） | reranker candidate pool 120→180。 | 12 题 correctness 25.00%→41.67%、recall 28.01%→42.59%；qst_0093 恢复但 qst_0356 回退，不运行 AB50。 | `configs/eval_pageindex_retrieval_pool_smoke12_20260826.yaml`；对应 cfggen。 |
| R3 | 已完成（不合流） | 通用 semantic_evidence_quota 多分面检索。 | 8 题 correctness 37.50%→50.00%，但关键 qst_0197/qst_0447/qst_0356/qst_0362 未改善，提升主要来自既有 selector 恢复，不运行 AB50。 | `configs/eval_pageindex_facet_quota_smoke8_20260826.yaml`；对应 cfggen。 |
| R4 | 已完成（不放行） | raw-miss 单条 bridge query 只读探针。 | 5/5 未命中目标文档；不接入 bridge query，转向索引/embedding 和词法锚点诊断。 | `outputs/pageindex_ab50_semantic_conflict_guard_r3_20260826/raw_miss_bridge_probe.json`（远端/本地实验产物）；审计报告。 |
| R5 | 已完成（不放行） | 组合验证：候选池扩大（`candidate_k=180`）后按分面/文档保留。 | 12 题与 candidate_k-only 完全同分：correctness 41.67%、completeness 45.62%、combined 40.28、recall 42.59%；逐题 final 文档集合无实质变化，不运行 AB50。 | `configs/eval_pageindex_combined_retrieval_smoke12_20260826.yaml`；对应 cfggen；检索审计报告。 |
| R6 | 已完成（不放行） | raw-miss embedding/索引覆盖与词法锚点诊断。 | 5/5 目标 chunk 存在且为 BGE-small 384 维；同模型 dense top-200 命中 0/5，BM25 原题/锚点 top-200 命中 0/5；目标分数低于 top-200 边界约 0.10–0.21。live Conan 1792 维与 BGE 索引不兼容，不接入主链。 | `scripts/diag/audit_raw_miss_embedding_lexical.py`；`docs/RAW_MISS_EMBEDDING_LEXICAL_AUDIT_20260826.md`；机器结果 JSON。 |
| R7 | 已完成（不放行） | raw-miss 题干派生词法实体/数字/版本锚点变体探针。 | 5 题中仅 qst_0231 的 `patient+connector` 组合进入 BM25 top-200（rank 38），恢复 1/5；无稳定单锚点规则，暂不接入主链。 | `scripts/diag/probe_raw_miss_lexical_anchor_variants.py`；`docs/RAW_MISS_LEXICAL_ANCHOR_VARIANTS_20260827.md`；机器结果 JSON。 |
| F500 | 待开始（门禁已解除） | 新的完整 500 题候选评测。 | A4/B4 已达到 combined 与 correctness 门槛；需单独创建 F500 快照并运行，不能与 AB50 结果混比。 | 新快照、报告、复现说明。 |
| FC | 待开始 | 提交前官方 correction 复评。 | 与 no-correction 隔离保存，不混比；给出最终差异说明。 | `official_correction/` 产物索引与报告。 |

## 当前执行顺序

1. A0.0/A0.1 已完成，A1.P 未通过并已停止；不创建 A1/A2 主链配置。
2. B1.A 已完成；B1 Smoke10 未通过，已回滚实验规则，不运行 AB50。
3. B2 与 B3.1 均已停止；A3.A/A3.P/A3.1/A3.2/A3.3/A3.4/A3.5、A4/B4 及 R1–R7 检索诊断已完成。候选池扩大、分面配额及其组合均未通过合流门槛；R7 仅发现 1 个可恢复的实体对，下一步做低权重组合锚点最小 smoke，F500 继续停止。
4. A 与 B 的 pipeline 最多各运行一个，总题目并发不超过 2，官方评分始终串行。
5. 每完成一个任务，先按“Git 提交规则”提交其允许文件，再等待用户确认推送。

## 任务记录

| 日期 | ID | 结论 | 验证 | Commit | Push |
|---|---|---|---|---|---|
| 2026-08-25 | A0.1（工具） | 已新增离线诊断工具。 | `python -m py_compile scripts/diag/audit_semantic_failure_layers.py` 通过。 | d967a56 | 已推送 |
| 2026-08-25 | A0.0 | 服务、manifest 和 S1 产物均健康；无活动评测进程。 | 只读远端预检全部通过。 | 本次提交 | 待确认 |
| 2026-08-25 | A0.1（执行） | 30 题完整归因：raw 9、RRF/rerank 3、selector 2、generation 4、成功 12。 | 生成并取回 `failure_layers.json`；见 A0 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | A1.P | 9 条 bridge query 均有效生成，但目标文档命中为 0/9，已停止该路线。 | 生成并取回 `a1_bridge_probe.json`；见 A1 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B1.A | AB50 Basic：成功 11、生成覆盖缺口 3、检索/引用缺口 4。 | 生成并取回 `basic_coverage_audit.json`；见 B1 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B1 | Smoke10 未通过：三个 Basic 目标题完整度仍为 80/75/50；不启动 AB50。 | 10 answer、10 trace、10 官方 no-correction 评分；见 B1 Smoke 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B2.A | Project 逐文档诊断完成：1 生成缺口、3 检索/引用缺口；不直接接入统一锚点。 | 4 题逐阶段覆盖审计；见 B2 Project 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B2.P | 锚点 probe 资格未通过：完整题干与分面查询已在基线执行，B2 停止。 | 只读检查基线路由 trace；见 B2.P 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B3.A | Completeness：两题均为检索/引用缺口，但失败层不同；不混合调参。 | 2 题逐阶段覆盖审计；见 B3 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B3.P | 两条隔离诊断完成：仅 `qst_0447` 放行多分面多文档计划候选。 | 只读检查 PageIndex plan、follow-up、selected docs 及 rerank 位次；见 B3.P 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | B3.1 | Smoke10 未通过：目标和 8 个控制题均与基线无变化；已回滚，不运行 AB50。 | 10 answer、10 trace、10 官方 no-correction 评分；见 B3.1 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | A3.A | 六题审计完成：2 个 selector 真实误拒；4 个 generation gap 中 1 个为 chunk 覆盖/污染，3 个为评分完整性不一致，生成优化目标为 0。 | 冻结 S1 精确 chunk 审计；见 A3.A 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | A3.P | 两题各复放 3 次均稳定误拒；模型实际接纳目标并完成覆盖，strict parser 因已解决冲突仍列入 `conflicts` 而清空证据。 | 6 次 selector-only 调用、原始响应逐次一致；见 A3.P 报告。 | 本次提交 | 待确认 |
| 2026-08-25 | A3.1 | conflict 契约单变量 smoke 通过：两目标稳定恢复，四道冻结控制保持，同权威未解决冲突稳定拒绝。 | 七题 smoke + 三类稳定性复放；见 A3.1 报告。 | 本次提交 | 待确认 |
| 2026-08-26 | A3.2 | 端到端 smoke 通过：q176/q272/q182 恢复，q177 保持，q220/q260 保持拒答；已回滚 runtime 补丁。 | 精确对齐版本六题 pipeline，recall 66.7%、extra 0；见 A3.2 报告。 | 本次提交 | 待确认 |
| 2026-08-26 | A3.3 | q182 候选集合无变化，根因是应用脚本少一个换行；修正后 selector 与 runtime 字节对齐。 | 5 次 selector 复放 + q182 单题端到端；见 A3.3 报告。 | 本次提交 | 待确认 |
| 2026-08-26 | A3.4 | 完整 Semantic30 conflict contract 重跑并完成官方 no-correction 评分：combined 52.22，较 S1 45.56 提升 6.66；q176/q272/q0208 恢复。 | 30 条 answers/trace/simple_metrics/results；见 A3.4 报告。 | 待提交 | 待确认 |
| 2026-08-26 | A3.5/A4/B4 | generation guard 六题隔离回归完成；AB50 通过整体门槛：combined 59.41（基线 59.34），correctness 64.00% 不下降；qst_0298 完整 AB50 仍有单题过度限定残留。 | 6 题生成隔离 + 50 条 answers/trace/simple_metrics/results，官方 no-correction；见 A3.5 报告。 | 待提交 | 待确认 |
| 2026-08-26 | R1–R4 | 完成 AB50 检索层分桶、candidate_k=180 smoke、facet quota smoke 和 raw-miss bridge probe；未放行任何变量进入 AB50。 | R1–R4 诊断产物与官方子集评分；见检索审计报告。 | 待提交 | 待确认 |
| 2026-08-26 | R5 | 候选池扩大 + rerank 后分面/文档保留组合 smoke 无增益；与 candidate_k-only 结果一致，未放行 AB50。 | 12 条 answers/trace/simple_metrics/results；官方 no-correction：combined 40.28、correctness 41.67%、recall 42.59%；见检索审计报告。 | 待提交 | 待确认 |
| 2026-08-26 | R6 | raw-miss 目标文档均在 BGE ES 中，但同模型 dense/BM25 top-200 均未命中；确认排序/表征相关性瓶颈，未放行主链。 | 5 题 ES、dense、BM25、词法锚点只读探针；见 Raw-miss 诊断报告。 | 待提交 | 待确认 |
| 2026-08-27 | R7 | 题干派生词法锚点变体仅恢复 qst_0231（1/5），其余 raw miss 无变体命中；未放行主链。 | 5 题单锚点/实体对 BM25 top-200 探针；见词法锚点变体报告。 | 待提交 | 待确认 |
