# RAG 联调控制台

独立的可视化联调应用。它不修改、运行或写入仓库现有的 RAG 代码和产物；仅通过版本化、只读的 HTTP 调试 API 使用已发布的 RAG 服务。

## 运行模式

- `pinned`：指定已发布 RAG 版本，供 daily-50 与 full-500 可重复评测。
- `live`：调用用户选择的最新已发布 RAG 服务，供单题联调；每次运行也保存版本指纹。

详细边界、接口和开发顺序见 [开发设计](docs/DEVELOPMENT_DESIGN.md)，实现状态与提交追踪见 [TODO](TODO.md)。
前端操作、题库导入与批量测试见 [使用说明](docs/USER_GUIDE.md)。
真实服务发布、预检和验收见 [M5 联调手册](docs/M5_RELEASE_AND_PRECHECK.md)。

## 真实服务接入

设置 `RAG_DEBUG_API_URL` 后，控制台会通过 HTTP 调用独立发布的只读调试服务；未设置时维持本地 mock，绝不会直接导入当前仓库 RAG。

```powershell
$env:RAG_DEBUG_API_URL = "http://published-rag-host:port"
python -m backend.app.server --host 127.0.0.1 --port 8090
```
