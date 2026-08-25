# RAG 优化任务清单（2026-08-25）

## 运行约定

- 工作分支：`codex/semantic-a0`。
- 冻结对照：500 题 BGE + PageIndex no-correction **55.18**；Semantic30 S1（PageIndex OFF）综合 **45.56**；AB50 PageIndex ON **59.34**。
- 不重建或覆盖 BGE ES、manifest、冻结输出和历史 cache；每个新实验使用独立的 YAML、`pipeline.name`、output 与 PageIndex cache。
- 线上链路只接收 question ID 与 question。`expected_doc_ids`、真实题型和评分结果只能用于运行结束后的离线诊断。
- 不在配置、脚本、日志或本文件中写入密钥。远端访问和 rerank 仅通过环境变量提供认证。

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
| A1.1 | 待开始 | 在固定 Semantic30、PageIndex OFF 上运行 bridge query。 | raw-miss 目标文档命中增加；综合分 **>45.56**；Invalid Extra Docs 相比 S1 不恶化超过 0.10。失败则删除该实验分支，不叠加改动。 | 实验 YAML、结果报告与 trace 清单。 |
| A2 | 待开始 | 将通过的 bridge 结果以低权重 RRF 候选接入，限制每文档 chunk 数，无 hard document lock。 | 召回与综合均提升，extra 在门槛内；独立于 A1 记录。 | 实验 YAML、实现、测试、报告。 |
| A3.A | 已完成 | 对 A0 的 2 个 selector drop 和 4 个 generation gap 做逐题离线证据审计。 | 2 题确认为 selector 误拒；1 题为 final chunk 缺事实且有 extra 污染；3 题为正确答案与 completeness 扣分不一致；干净生成缺口为 0。 | `scripts/diag/audit_semantic_selector_generation.py`；`docs/SEMANTIC_A3_A_SELECTOR_GENERATION_AUDIT_20260825.md`。 |
| A3.P | 待开始 | 仅对 `qst_0176`、`qst_0272` 复放冻结最终证据下的 selector 输入输出，定位误拒来源。 | 两题均能稳定复现误拒，并能定位到 selector 规则或解析；不得读取 gold facts 构造在线输入，不运行生成。 | 离线 probe、原始响应摘要、诊断报告。 |
| A3 | 待 A3.P | 仅在 A3.P 通过后，对 selector 做单变量 smoke；generation 路线当前不放行。 | 证据覆盖改善且 extra 可控；不得与 A1/A2 混合调参。 | 独立 YAML、实现、测试、报告。 |
| B1.A | 已完成 | 对 AB50 的 Basic 子集做离线覆盖审计。 | 18 题中 3 题为文档已命中、答案正确但完整性不足；4 题为检索/引用问题，排除在生成改动外。 | `scripts/diag/audit_basic_coverage.py`；`docs/BASIC_AB50_B1_AUDIT_20260825.md`。 |
| B1 | 未通过，已停止 | Basic：生成前事实清单与引用覆盖审计，不改检索权重。固定 Smoke10 中 3 个目标题完整度均未改善，且存在非 Basic 对照退化。 | 仅完成 Smoke10；不满足 Basic 改善门槛，未运行 AB50。 | 配置、最小应用/回滚脚本、失败报告。 |
| B2.A | 已完成 | 对 AB50 的 Project 子集做逐目标文档的离线阶段覆盖审计。 | 4 题：1 个 generation coverage gap、3 个 retrieval/citation gap；已区分 raw、rerank、final 与 submitted 覆盖。 | `scripts/diag/audit_project_coverage.py`；`docs/PROJECT_AB50_B2_DIAGNOSTIC_20260825.md`。 |
| B2.P | 未通过，已停止 | Project 锚点 probe 资格检查：完整题干与分面锚点查询已在 AB50 基线执行，重复 BGE 查询不构成新变量。 | `qst_0350` 为 rerank 后段丢弃；`qst_0356/0362` 在已执行锚点下仍 raw 覆盖不足。 | `docs/PROJECT_B2P_PROBE_ELIGIBILITY_20260825.md`。 |
| B2 | 未通过，已停止 | Project：不直接接入统一项目名、组件名、路径/版本词法锚点。 | 不存在可隔离且未被基线覆盖的锚点变量；不运行 smoke/AB50。 | B2.A/B2.P 诊断报告。 |
| B3.A | 已完成 | 对 AB50 的 Completeness 子集做逐目标文档的离线阶段覆盖审计。 | 2 题均为检索/引用缺口，但一题是 selector/citation 缩减，另一题同时为 raw/rerank/final 缺口。 | `scripts/diag/audit_project_coverage.py`；`docs/COMPLETENESS_AB50_B3_DIAGNOSTIC_20260825.md`。 |
| B3.P | 已完成 | 将 Completeness 的 selector/citation 与 raw/rerank 路径分开只读验证。 | `qst_0432` 不具备独立检索变量；`qst_0447` 的多分面计划被单文档模式抵消，放行 question-only 多文档计划候选。 | `docs/COMPLETENESS_B3P_ISOLATED_PROBES_20260825.md`。 |
| B3.1 | 未通过，已停止 | 对题干规划出多个独立分面及多环境硬约束的问题，启用多文档证据计划；不强制 benchmark 题型。 | Smoke10 已完成，但 `qst_0447` 仍为 0% recall/0% completeness/extra 1；所有控制题无变化，不运行 AB50。 | 独立配置、精确应用/回滚脚本、失败报告。 |
| A4/B4 | 待开始 | 仅合并 A、B 中各自通过的开关，接回 PageIndex ON 主链。 | AB50 无退化，Semantic 改善；分层 100 对 58.83 有可重复净增益。 | 合流 YAML、回归报告、测试。 |
| F500 | 待开始 | 新的完整 500 题候选评测。 | 仅在 A4/B4 全通过后启动；保存 answers、配置、日志、官方 no-correction 明细与逐题 trace；不覆盖 55.18 快照。 | 新快照、报告、复现说明。 |
| FC | 待开始 | 提交前官方 correction 复评。 | 与 no-correction 隔离保存，不混比；给出最终差异说明。 | `official_correction/` 产物索引与报告。 |

## 当前执行顺序

1. A0.0/A0.1 已完成，A1.P 未通过并已停止；不创建 A1/A2 主链配置。
2. B1.A 已完成；B1 Smoke10 未通过，已回滚实验规则，不运行 AB50。
3. B2 与 B3.1 均已停止；A3.A 已完成，下一任务为 A3.P，仅复放 `qst_0176`、`qst_0272` 的 selector 输入输出。
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
