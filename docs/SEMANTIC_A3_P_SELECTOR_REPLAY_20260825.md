# Semantic A3.P precision-v3 selector 离线复放

## 结论

`qst_0176`、`qst_0272` 在冻结 S1 最终证据上各复放 3 次，严格解析结果均为 `rejected`，误拒稳定复现 **6/6**。两题的模型原始输出实际都接纳了目标证据 `[1]`、覆盖了全部分面并声明 `coverage_complete=true`；清空证据的唯一触发条件是响应同时包含非空 `conflicts`。

根因是字段语义与门控不一致：模型用 `conflicts` 报告“发现但已按来源优先级解决的候选矛盾”，S1 解析器却把任意非空 `conflicts` 都当作“仍未解决的矛盾”，在非 `conflicting_info` 题型上一律 fail-closed。

A3.P 通过，放行一个保持 fail-closed 的 selector 单变量 smoke；不放行直接忽略所有冲突的宽松解析，也不修改 generation。

## 复放边界

- 冻结输入：Semantic30 S1 的 question、`route_trace.jsonl` 与 `final_before_generation.chunk_ids`。
- 候选构造与 S1 一致：前 24 个候选、每文档最多 4 个、最多接纳 10 个。
- 仅用精确 chunk ID 从 ES `_mget` 原文；不执行召回、rerank、PageIndex 或答案生成。
- 使用冻结 `precision_v3` system/user prompt、题型规则、temperature `0.0` 和严格 S1 parser。
- 工具只接收 question ID，不接收 gold document ID 或 answer facts；目标文档位次仅在运行结束后离线核对。
- 原始 prompt、响应和逐次解析保存在忽略的运行输出 JSON 中，不纳入 Git。

## 逐题结果

| 题目 | 题型 | 目标证据 | 三次响应 | 模型声明 | 严格 parser 结果 | 直接触发点 |
|---|---|---|---|---|---|---|
| `qst_0176` | constrained | 候选 `[1]`，含 H200 80GB、两个区域和开放时间 | 三次原始响应 SHA-256 相同 | accepted `[1]`；4/4 facets covered；`coverage_complete=true` | 三次均 `[]` | `conflicts` 列出 `[1]/[2]/[16]` 日期差异，同时说明已选择 `[1]` 作为 final source；parser 仍因列表非空清空。 |
| `qst_0272` | basic | 候选 `[1]`，含 canonical company-wide policy 与 72 business hours | 三次原始响应 SHA-256 相同 | accepted `[1]`；1/1 facet covered；`coverage_complete=true` | 三次均 `[]` | `conflicts` 列出其他 SLA，同时明确 `[1]` 是 canonical company-wide source；parser 仍因列表非空清空。 |

两题的 prompt hash 在各自三次调用中保持不变；每题三次原始响应也逐字节相同。因此该现象不是 temperature 或服务抖动导致的偶发失败。

## 根因链

```text
目标 chunk 位于候选 [1]
        ↓
模型 accepted_indices=[1]
        ↓
全部 facets 被 [1] 覆盖，coverage_complete=true
        ↓
模型同时记录“已识别并已选择优先来源”的 conflicts
        ↓
strict parser: any(conflicts) => []
        ↓
fail_closed=true => 空证据 => 拒答
```

模型选择与 coverage 判断本身正确，失败发生在 selector JSON 到 admitted evidence 的解析门。

## 下一任务：A3.1 单变量 smoke

建议只改变 conflict 输出契约，不直接放宽 parser：

1. 将 `conflicts` 明确定义为“应用 final/current/canonical 优先级后仍无法解决的矛盾”。
2. 已按明确来源优先级解决的候选差异记入 `resolved_conflicts` 或 `rejected`，不得放入阻断性的 `conflicts`。
3. parser 继续对非空的未解决 `conflicts` fail-closed，保留原安全边界。
4. 先对两道目标与冲突敏感控制题运行独立 smoke；目标必须恢复 `[1]`，控制题不得把真正未解决的冲突误放行，才考虑 Semantic30。

不采用“只要 `coverage_complete=true` 就忽略所有 conflicts”的方案，因为它会把真正未解决的具体数值、日期或版本矛盾带入生成。

## 验证

- `python -m py_compile scripts/diag/probe_semantic_precision_selector.py`
- 远端完整复放退出码 0：`qst_0176` 三次 rejected；`qst_0272` 三次 rejected。
- 两题三次均取得完整 raw response 和严格解析字段；结果文件：`a3p_selector_replay.json`（运行输出，不提交）。
- `git diff --check`
