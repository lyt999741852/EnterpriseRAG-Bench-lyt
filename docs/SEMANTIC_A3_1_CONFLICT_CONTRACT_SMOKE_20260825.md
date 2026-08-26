# Semantic A3.1 conflict 契约单变量 smoke

## 结论

A3.1 selector-only smoke **通过**。在 strict parser 完全不变的前提下，只补充 `conflicts` / `resolved_conflicts` 输出契约：

- `qst_0176`、`qst_0272` 均由原契约的稳定拒绝变为新契约下稳定接纳目标 `[1]`，各累计 **3/3 accepted**。
- 两道既有成功控制继续 accepted，两道既有 fail-closed 控制继续 rejected。
- 同等权威、同为 current/approved、数值互相矛盾且没有优先依据的合成控制累计 **3/3 rejected**。
- 新契约没有通过放宽 parser 绕过冲突：未解决冲突仍进入阻断性 `conflicts`，parser 继续 fail-closed。

该结果只放行独立端到端 A3.2 smoke；尚未修改线上 `src/generator.py`，也不直接运行 Semantic30。

## 单一变量

冻结 `precision_v3` prompt、候选、模型参数与严格 parser 均保持不变，仅追加以下语义约束：

1. `conflicts` 只记录应用 explicit final/current/canonical/applicable-source 优先级后仍未解决的矛盾。
2. 已由明确权威、状态或适用范围解决的差异写入 `resolved_conflicts`，不得阻断 admission。
3. 同等权威且无法确定适用值时，保留 blocking conflict、设置 `coverage_complete=false`，不接纳互相矛盾的具体值。
4. blocking `conflicts` 非空时禁止声明完整覆盖。

没有修改 strict parser 的 `any(conflicts) => []` 规则。

## Smoke 集合

| 角色 | 样本 | 原契约基线 | 新契约结果 | 判定 |
|---|---|---|---|---|
| 修复目标 | `qst_0176` | A3.P：3/3 rejected | 3/3 accepted `[1]`；blocking conflicts 0；resolved 1 | 通过 |
| 修复目标 | `qst_0272` | A3.P：3/3 rejected | 3/3 accepted `[1]`；blocking conflicts 0；resolved 1 | 通过 |
| 成功控制 | `qst_0177` | accepted | accepted `[1]` | 保持 |
| 成功控制 | `qst_0182` | accepted | accepted `[4]` | 保持 |
| 拒答控制 | `qst_0220` | rejected | rejected；accepted 为空；coverage false | 保持 |
| 拒答控制 | `qst_0260` | rejected | rejected；accepted 为空；coverage false | 保持 |
| 未解决冲突控制 | `synthetic_unresolved_equal_authority` | 应拒绝 | 3/3 rejected；blocking conflicts 1；resolved 0 | 通过 |

## 原始响应审计

- 两个目标在新契约下均明确把候选差异放入 `resolved_conflicts`，`conflicts=[]`，并用目标 `[1]` 覆盖全部 facets。
- 合成控制的两个 passage 均声明自己是 current、approved 且具有相同 policy authority，却分别给出 maximum batch size 10 与 20；模型将该差异保留在 `conflicts`，不接纳任一数值。
- 两目标及合成控制的三次原始响应分别逐字节一致，排除本轮 temperature `0.0` 下的偶发输出变化。
- 成功控制与拒答控制各执行一次；结果与原契约基线 admission 状态相同。

## 下一任务：A3.2 端到端 smoke

1. 用精确、可回滚的实验方式将同一 conflict 契约接入独立 runtime 配置，不混入其他生成、检索或 PageIndex 改动。
2. 运行 `qst_0176`、`qst_0272` 与四道冻结控制题的独立答案 smoke。
3. 两目标必须恢复目标文档引用、答案正确且 completeness 提升；四道控制题不得出现答案、引用或 extra 退化。
4. smoke 未通过则回滚并停止 A3；通过后才允许固定 Semantic30 A3 评测。

## 验证

- `python -m py_compile scripts/diag/probe_semantic_precision_selector.py`
- 原契约控制基线：accepted、accepted、rejected、rejected，远端退出码 0。
- 新契约七题 smoke 全部门槛通过，远端退出码 0。
- 两目标与未解决冲突控制补做两次稳定性复放，状态与 raw response 均保持一致，远端退出码 0。
- 原始 JSON 位于冻结运行输出目录，不纳入 Git。
- `git diff --check`
