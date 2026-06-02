# 多智能体协作系统 - 项目上下文

> 保存时间: 2026-06-02
> 最后更新: 2026-06-02 (推理模型适配 + 代理绕过修复 + 智谱模型列表更新 + 功能文档补全)
> 用途: 新对话窗口加载上下文，避免重复工作

---

## 一、项目概述

多智能体协作系统，模拟公司多部门协同工作。6个角色智能体依次协作完成软件开发全流程：
- 产品经理 → UI设计师 → 后端开发 + 前端开发(并行) → 代码测试 → 安全审计

技术栈: Python + FastAPI + WebSocket + Vue3 + DeepSeek API(支持多LLM)

---

## 二、项目目录结构

```
d:\ai\AI智能体\
├── app.py                    # FastAPI主入口
├── config.py                 # 配置管理 + LLM配置持久化
├── requirements.txt          # Python依赖
├── README.md                 # 项目文档
├── core/
│   ├── blackboard.py         # 黑板模式 - 智能体间共享通信
│   ├── orchestrator.py       # 编排器 - 流程控制/审批/协商
│   ├── llm_provider.py       # LLM调用核心(多提供商+缓存+成本追踪)
│   ├── quality.py            # 输出质量保证模块
│   ├── cache.py              # 缓存优化(SHA256哈希+TTL+LRU)
│   ├── persistence.py        # 数据持久化(JSON文件存储)
│   └── delivery.py           # 项目打包+交付报告生成
├── agents/
│   ├── base.py               # 智能体基类(run/质量检查/协商/JSON容错)
│   ├── pm.py                 # 产品经理
│   ├── ui_designer.py        # UI设计师
│   ├── backend_dev.py        # 后端开发
│   ├── frontend_dev.py       # 前端开发
│   ├── tester.py             # 代码测试
│   └── auditor.py            # 安全审计
├── routers/
│   ├── project.py            # 项目管理API(创建/启动/停止/删除)
│   ├── ws.py                 # WebSocket实时通信
│   ├── approval.py           # 审批API
│   ├── delivery.py           # 交付API
│   └── llm_config.py         # LLM配置API + 缓存统计
├── static/
│   ├── index.html            # Vue3前端HTML模板
│   ├── css/style.css         # 暗色主题样式
│   └── js/app.js             # Vue3前端逻辑
└── data/                     # 运行时数据目录(JSON持久化)
```

---

## 三、核心架构

### 3.1 黑板模式 (Blackboard Pattern)
- 文件: `core/blackboard.py`
- `ArtifactType` 枚举: 定义所有产出物类型(prd/ui_spec/api_design/db_schema/frontend_code/backend_code/test_report/security_report/bug_list/fix_history/negotiation_log/usage_report)
- `ApprovalPoint` 枚举: 3个审批点(after_prd/after_design/after_frontend)
- `Blackboard` 类: 共享状态、事件系统、审批等待/决议、协商日志
- **重要**: `set_artifact()` 方法已增加 ValueError 容错，未知key不会崩溃

### 3.2 编排器 (Orchestrator)
- 文件: `core/orchestrator.py` (314行)
- 阶段式执行: requirement → design_dev → qa → fix → done
- 审批等待: 3个审批点可暂停等待人工决策
- 协商解决: `_resolve_negotiations(max_rounds=2)` 统一处理
- 修复循环: QA不通过时自动修复，最多3轮
- `retry_qa()`: needs_review项目仅重跑QA+修复

### 3.3 智能体基类 (BaseAgent)
- 文件: `agents/base.py` (274行)
- `run()` 方法: 执行→协商处理→质量检查→自动重试→LLM质量评分
- `can_negotiate`: 是否支持协商(后端/前端/测试/审计已启用)
- `enable_llm_quality_check`: 是否启用LLM质量评分
- `_process_negotiations()`: 从输出中提取协商请求写入黑板
- `_check_quality()`: 结构化质量检查+自动重试
- `_llm_quality_check()`: LLM评分(仅评分不阻断)

### 3.4 LLM提供商
- 文件: `core/llm_provider.py`
- 支持: DeepSeek/OpenAI/智谱/Moonshot/通义千问/自定义
- 缓存: temperature<0.3时自动缓存(SHA256 Prompt哈希)
- 成本追踪: Token用量+人民币费用
- 流式输出: `chat_stream_with_retry()` 支持SSE

### 3.5 缓存系统
- 文件: `core/cache.py`
- `ResponseCache`: SHA256哈希缓存，TTL过期(1小时)，LRU淘汰(最大500条)
- `ContextCompressor`: 产出物压缩+修复上下文摘要
- `get_cache()`: 全局单例

### 3.6 质量保证
- 文件: `core/quality.py`
- `QUALITY_CHECKS`: 6个agent的结构检查配置
- `QualityChecker.check_structure()`: 必填字段+类型检查
- `QualityChecker.llm_check()`: LLM评分(1-10分)

---

## 四、关键功能

### 4.1 人工审批 (Human-in-the-Loop)
- 3个审批点: PRD审批 → 设计审批 → 前端审批
- 审批操作: 通过(approve) / 驳回修改(reject) / 局部重跑(rerun)
- 审批时前端显示审批面板，可查看/编辑产出物
- 审批历史+快照记录

### 4.2 多向协商
- 任何智能体可在输出中发起协商请求
- 编排器统一收集并解决协商(max_rounds=2)
- 协商日志实时推送到前端

### 4.3 交付系统
- ZIP打包所有产出物
- 自动生成交付报告(HTML)
- 下载时RFC 5987编码处理中文文件名

### 4.4 数据持久化
- JSON文件存储在 `data/` 目录
- 服务器重启后自动恢复项目状态
- 运行中项目标记为 `interrupted`

### 4.5 前端功能
- 项目列表(创建/启动/停止/删除)
- 工作台(实时日志+智能体状态)
- 审批面板(查看/编辑/决策)
- 交付中心(打包/下载)
- LLM配置管理(支持连接测试、缓存统计)
- 协商日志查看
- Toast 通知(轻量级消息提示)
- 项目搜索(按名称/需求过滤)
- 健康检查(前端自动检测API状态)

### 4.6 项目 Fork
- 基于已有项目创建副本，可复制所有产出物
- 适用于同类型项目的快速启动
- API: `POST /api/projects/fork`

### 4.7 产出物编辑
- 审批阶段可手动编辑产出物内容
- API: `PUT /api/projects/{id}/artifacts/{type}`
- 修改后自动持久化

### 4.8 QA 重试 (needs_review)
- 已完成但 QA 未通过的项目，第二次启动仅重跑 QA+修复
- 保留已有的 PRD/设计/代码等产出物
- `orchestrator.retry_qa()` 无需从头开始

### 4.9 推理模型支持 (2026-06-02)
- 自动检测推理模型(glm-5/5.1, deepseek-reasoner, o1/o3 等)
- 推理模型自动放大 `max_tokens`（3倍），避免推理消耗过多导致无输出
- 跟踪 `reasoning_tokens` 并纳入用量统计
- `content` 为空时降级返回推理内容尾部 500 字符
- 流式输出无实际内容时记录 warning 日志

### 4.10 代理绕过 (2026-06-02)
- `AsyncOpenAI` 客户端通过 `httpx.AsyncClient(trust_env=False)` 绕过系统代理
- 修复 Windows 系统代理导致 `APIConnectionError` 的问题
- 错误提示细化：区分超时/代理/一般连接错误

---

## 五、已修复的BUG历史

| BUG | 位置 | 修复方案 |
|-----|------|----------|
| WebSocket `NameError: cb_id` | routers/ws.py | 变量名修正 |
| ZIP下载 `UnicodeEncodeError` | routers/delivery.py | RFC 5987 `filename*=UTF-8''` 编码 |
| 服务器热重载丢数据 | routers/project.py | 添加 `interrupted` 状态 |
| `ValueError: 'usage_report' is not a valid ArtifactType` | core/blackboard.py + routers/project.py | 枚举添加 `USAGE_REPORT` + `set_artifact` 容错 |
| Windows 代理导致 LLM 连接失败 | core/llm_provider.py | `httpx.AsyncClient(trust_env=False)` 绕过系统代理 |
| 推理模型 `max_tokens` 不足导致空输出 | core/llm_provider.py | 推理模型自动 3x 放大 `max_tokens` + 降级兜底 |

---

## 六、当前状态

### 已完成
- ✅ 多智能体协作架构(6角色)
- ✅ Web界面(Vue3 + FastAPI)
- ✅ 多LLM提供商支持(DeepSeek/OpenAI/智谱/Moonshot/通义千问/自定义)
- ✅ 智谱AI模型列表已更新(glm-4.5~5.1, 共10个模型)
- ✅ 推理模型支持(glm-5, deepseek-reasoner, o1等, 自动3x放大max_tokens)
- ✅ 人工审批系统(3审批点)
- ✅ 多向协商机制
- ✅ 输出质量保证(结构检查+LLM评分+自动重试)
- ✅ 缓存命中优化(SHA256+TTL+LRU)
- ✅ 交付系统(ZIP+交付报告)
- ✅ 数据持久化(JSON, 热重载恢复)
- ✅ 成本追踪(Token+人民币)
- ✅ 项目Fork + 产出物编辑 + QA重试
- ✅ LLM连接测试端点
- ✅ 健康检查端点
- ✅ 代理绕过(trust_env=False)
- ✅ Toast通知 + 项目搜索
- ✅ README.md + PROJECT_CONTEXT.md

### 待完成/可改进
- ⬜ GitHub推送(已commit到本地，未推送)
- ⬜ 前端页面可能有其他小问题需要实际测试验证
- ⬜ 缓存命中率统计前端展示

---

## 七、运行方式

```bash
cd d:\ai\AI智能体
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

前端通过 http://localhost:8000 访问(静态文件由FastAPI托管)

---

## 八、重要注意事项

1. **不要在项目目录下创建临时Python检查文件** — 会导致uvicorn热重载，服务器断开
2. **监控API只用 CheckCommandStatus 查看日志** — 不要运行额外的Python脚本
3. **API Key安全** — .gitignore 已配置排除 data/ 目录和 .env 文件
4. **智谱API** — 密钥配置文件 `智谱.txt`，Base URL: `https://open.bigmodel.cn/api/paas/v4`；可用模型: glm-4-plus 到 glm-5.1
5. **Windows代理问题** — 本机有 Clash/V2Ray 代理，已通过 `trust_env=False` 绕过；若遇到连接失败先检查代理状态
6. **推理模型注意事项** — glm-5/5.1 等推理模型约75%的completion tokens用于内部推理，`max_tokens` 建议≥2000，系统已自动3x放大
7. **GitHub推送** — 需要有效的 GitHub PAT 配置

---

## 九、关键代码片段

### ArtifactType 枚举 (core/blackboard.py)
```python
class ArtifactType(str, Enum):
    USER_REQUIREMENT = "user_requirement"
    PRD = "prd"
    UI_SPEC = "ui_spec"
    API_DESIGN = "api_design"
    DB_SCHEMA = "db_schema"
    FRONTEND_CODE = "frontend_code"
    BACKEND_CODE = "backend_code"
    TEST_REPORT = "test_report"
    SECURITY_REPORT = "security_report"
    BUG_LIST = "bug_list"
    FIX_HISTORY = "fix_history"
    NEGOTIATION_LOG = "negotiation_log"
    USAGE_REPORT = "usage_report"  # 最近添加，修复500错误
```

### set_artifact 容错 (core/blackboard.py)
```python
def set_artifact(self, artifact_type: ArtifactType | str, content: Any):
    key = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
    now = time.time()
    if key in self.artifacts:
        self.artifacts[key].content = content
        self.artifacts[key].updated_at = now
    else:
        try:
            at = ArtifactType(key) if isinstance(artifact_type, str) else artifact_type
        except ValueError:
            at = ArtifactType.NEGOTIATION_LOG  # 容错：未知key用默认枚举值
        self.artifacts[key] = Artifact(
            artifact_type=at,
            content=content,
            created_at=now,
            updated_at=now,
        )
```
