# Semantic A3.2 conflict 契约端到端 smoke

## 结论

A3.2 **未通过并已回滚**。selector-only A3.1 的契约在端到端 runtime 中可以修复两个目标题，但对成功控制题 `qst_0182` 造成回归，因此没有进入固定 Semantic30。

修正后的末尾契约版本结果：

- `qst_0176`：恢复目标文档引用，答案给出 H200 80GB、两个区域和 `2026-04-06 09:00 UTC`；recall 100%，extra 0。
- `qst_0272`：恢复目标文档引用，答案给出 72 business hours；recall 100%，extra 0。
- `qst_0177`：成功控制保持目标文档引用和答案。
- `qst_0182`：从基线正确答案/目标引用退化为 fail-closed 拒答，recall 0%；控制门槛失败。
- `qst_0220`、`qst_0260`：仍保持拒答，未出现 extra。

六题简单平均 recall 为 50%，平均 invalid extra docs 为 0；因控制题退化，未执行官方评分，也未运行 Semantic30。

## 实验变量与回滚

- 独立配置：`semantic_a32_conflict_contract_smoke_20260826`。
- PageIndex OFF、S1 检索/rerank/预算保持不变、题目并发 1。
- 唯一行为变量：在 precision-v3 用户模板末尾追加 `conflicts` / `resolved_conflicts` 契约。
- 首次将同一契约插入模板中段时，`qst_0176` 仍拒答；该尝试不作为最终结果。
- 将契约移到模板末尾后，`qst_0176` 单题复验通过，随后六题 smoke 暴露 `qst_0182` 控制回归。
- 已执行可回滚脚本恢复远端 `src/generator.py`，备份文件已清理；未修改本地 `src/generator.py`。

## 判定

A3.1 的 selector-only 结论仍成立，但不能直接推广为通用 runtime prompt 契约。`qst_0182` 表明该契约对 Basic 路由的长候选集合或冲突解释存在副作用；下一步只能先做 `qst_0182` 的离线 selector 输入/输出审计，设计题型限定或更窄的契约，再提出新的单变量 smoke。

## 下一任务：A3.3

1. 对基线和失败 runtime 的 `qst_0182` final candidate 集合做精确差异审计。
2. 只复放 selector，记录是否因新增契约声明冲突、`coverage_complete` 或候选排序变化而清空。
3. 在没有证据前，不把契约应用到 Basic 全路由；A3 保持停止状态。

## 验证

- A3.2 独立 pipeline 两次运行均退出码 0；最终修正版六题输出完整。
- 修正版简单指标：`average_recall_pct=50.0`、`average_invalid_extra_docs=0.0`。
- 目标题与控制题逐题对照完成。
- 远端 runtime 补丁已回滚，`src/generator.py` 语法检查通过。
- 原始运行 JSON 位于忽略的 `outputs/semantic_a32_conflict_contract_smoke_20260826/`，不纳入 Git。
