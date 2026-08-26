# M5：独立 RAG 调试服务发布与联调

本步骤的目标是将**已冻结、已验证**的 RAG 版本以独立进程/容器发布为调试服务，再让控制台通过 HTTP 访问它。不得把控制台直接连到当前正在修改、重建索引或评测中的 RAG 工作目录。

## 发布前条件

1. 选择一个已完成测试的 RAG Git 提交、配置文件和索引版本，并生成不可变版本 ID 与指纹。
2. 在独立工作目录、容器镜像或单独主机部署该快照；运行账户对 Elasticsearch 索引和语料仅有读权限。
3. 给服务分配独立端口、日志目录和 PageIndex cache；不得复用现有优化实验的输出或缓存目录。
4. 服务实现控制台契约：
   - `GET /debug/versions`
   - `POST /debug/answer`，请求只接受 `question` 和 `rag_version`。
5. `POST /debug/answer` 返回 `answer`、`trace`、`metrics`、`timing_ms`；禁止回传 gold answer、answer facts 或 expected document IDs。

## 预检

先用无 gold 的冒烟问题验证已发布服务：

```powershell
cd D:\EnterpriseRAG-Bench\rag-debug-console
python scripts/preflight_published_rag.py `
  --base-url http://published-rag-host:port `
  --rag-version rag-v2026.08.26-a34 `
  --question "What are the company's data retention requirements?"
```

预检通过后，才设置控制台环境变量并启动控制台：

```powershell
$env:RAG_DEBUG_API_URL = "http://published-rag-host:port"
python -m backend.app.server --host 127.0.0.1 --port 8090
```

## 验收清单

- 预检返回 `status: passed`，并包含真实版本指纹、trace stages 与耗时。
- 控制台健康状态显示 `gateway: published`，而非 `mock`。
- 单题的回答、引用和轨迹来自已发布版本；历史记录保存相同版本 ID。
- `pinned` 测试与 `live` 测试结果可区分；批量运行持有 `rag-evaluation` 锁。
- 在服务与控制台日志中搜索不到 gold 字段。
- 当前 RAG 优化工作未产生写入、重启、配置覆盖或索引操作。

## 当前阻塞

尚未提供独立发布服务的 URL、已发布版本 ID 和运行环境。没有这些输入时，本控制台保持 mock，不能诚实地宣称完成真实 M5 联调。
