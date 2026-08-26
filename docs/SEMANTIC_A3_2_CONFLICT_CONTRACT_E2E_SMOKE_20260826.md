# Semantic A3.2 conflict 契约端到端 smoke

## 结论

A3.2 **通过并已回滚实验补丁**。selector-only A3.1 的契约在端到端 runtime 中修复两个目标题，四道控制题均保持预期；随后才允许进入固定 Semantic30。

修正后的末尾契约版本结果：

- `qst_0176`：恢复目标文档引用，答案给出 H200 80GB、两个区域和 `2026-04-06 09:00 UTC`；recall 100%，extra 0。
- `qst_0272`：恢复目标文档引用，答案给出 72 business hours；recall 100%，extra 0。
- `qst_0177`：成功控制保持目标文档引用和答案。
- `qst_0182`：保持基线正确答案和目标文档引用，recall 100%，extra 0。
- `qst_0220`、`qst_0260`：仍保持拒答，未出现 extra。

六题简单平均 recall 为 66.7%，平均 invalid extra docs 为 0；控制门槛通过，尚未运行固定 Semantic30。

## 实验变量与回滚

- 独立配置：`semantic_a32_conflict_contract_smoke_20260826`。
- PageIndex OFF、S1 检索/rerank/预算保持不变、题目并发 1。
- 唯一行为变量：在 precision-v3 用户模板末尾追加 `conflicts` / `resolved_conflicts` 契约，并确保追加字节与 selector-only 复放一致。
- 首次应用脚本少一个换行，造成 runtime prompt 与 selector-only prompt 不同；该中间尝试不作为最终结果。
- 修正为完全一致的末尾字节后，q176 单题和六题 smoke 均通过。
- 已执行可回滚脚本恢复远端 `src/generator.py`，备份文件已清理；未修改本地 `src/generator.py`。

## 判定

A3.1 的 selector-only 结论可推广到端到端 runtime，但前提是 prompt 字节精确一致；q182 的中间回归来自实验脚本字节差异，不是契约对 Basic 路由的业务副作用。

## 下一任务：A3.4

1. 在独立配置中将已验证的末尾契约接入固定 Semantic30。
2. 保存 answers、trace、simple metrics 与官方 no-correction 评分，和 S1 严格对照。
3. 仅当 selector drop 改善且 extra 不恶化时继续；否则回滚并停止 A3。

## 验证

- A3.2 独立 pipeline 三次运行均退出码 0；最终修正版六题输出完整。
- 修正版简单指标：`average_recall_pct=66.7`、`average_invalid_extra_docs=0.0`。
- 目标题与控制题逐题对照完成。
- 远端 runtime 补丁已回滚，`src/generator.py` 语法检查通过。
- 原始运行 JSON 位于忽略的 `outputs/semantic_a32_conflict_contract_smoke_20260826/`，不纳入 Git。
