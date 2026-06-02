# 🤖 AI Agent Collaboration Platform

基于大语言模型的多智能体协作开发平台，模拟真实软件公司的多部门协同工作流程。

## ✨ 核心特性

- **5 个 AI 智能体角色**：产品经理、UI设计师、后端开发、前端开发、质量工程师（测试+安全审计合并）
- **3 个人工审批节点**：PRD审批 → 设计审批 → 前端审批，支持通过/驳回/局部重跑
- **多向协商机制**：智能体之间可发起协商请求，自动触发下游重跑
- **输出质量保证**：结构化检查 + LLM 评分 + 自动重试（评分不达标时）
- **多 LLM 支持**：DeepSeek、OpenAI、智谱AI（10个模型）、Moonshot、通义千问、自定义
- **推理模型适配**：自动检测 glm-5、deepseek-reasoner、o1 等，3x 放大 max_tokens
- **Token 节省 55-65%**：合并 QA + 增量复查 + 指纹去重 + 智能修复分流
- **LLM 成本追踪**：输入/输出/推理 Token 分项统计和 RMB 费用估算
- **交付质量门控**：测试和安全审计双通过才算可交付，不通过自动进入修复循环（最多3轮）
- **实时协作**：WebSocket 双向心跳推送，NAT/代理下稳定不丢线
- **项目交付**：一键打包下载 ZIP（含文档、前后端代码、测试报告）
- **数据持久化**：项目数据自动保存，服务器重启后可恢复
- **JSON 容错解析**：5 层降级 + 嵌套展开 + 代码文件兜底提取
- **代理兼容**：自动绕过 Windows 系统代理，不影响 LLM 连接

## 🏗️ 系统架构

```
用户需求
   │
   ▼
┌──────────────────────────────────────────────┐
│              编排器 (Orchestrator)             │
│    流程调度 · 审批等待 · 协商解决 · 修复循环    │
│    指纹去重 · 智能分流 · Token 节省追踪         │
└──┬────────┬────────┬────────┬────────────────┘
   │        │        │        │
   ▼        ▼        ▼        ▼
 产品经理  UI设计   后端开发   前端开发     质量工程师
   │        │        │        │        (测试+审计合并)
   ▼        ▼        ▼        ▼             ▼
  PRD    UI规范   API+DB+代码  页面+组件   测试+安全报告
   │                                                    │
   ├─ ⏸️ PRD审批 ── ⏸️ 设计审批 ── ⏸️ 前端审批 ─────────┤
   │      人工审批节点，支持通过/驳回/局部重跑               │
   └────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
├── app.py                  # FastAPI 主入口 + 健康检查
├── config.py               # 配置管理
├── requirements.txt        # Python 依赖
├── agents/                 # 智能体
│   ├── base.py             # 基类（流式/协商/质量检查/JSON 5层容错）
│   ├── pm.py               # 产品经理 → PRD文档
│   ├── ui_designer.py      # UI设计师 → UI规范
│   ├── backend_dev.py      # 后端开发 → API + DB + 代码
│   ├── frontend_dev.py     # 前端开发 → 页面 + 组件
│   └── qa_engineer.py      # 质量工程师 → 测试+安全审计（合并）
├── core/                   # 核心模块
│   ├── blackboard.py       # 共享黑板（Agent通信/审批/协商/指纹去重缓存）
│   ├── orchestrator.py     # 编排器（流程调度/审批/修复循环/Token节省）
│   ├── llm_provider.py     # LLM 提供商（多平台/推理模型/代理绕过/成本追踪）
│   ├── quality.py          # 质量检查（结构验证 + LLM评分）
│   ├── cache.py            # 响应缓存 + 上下文压缩
│   ├── delivery.py         # 交付打包器（ZIP + 交付报告）
│   └── persistence.py      # 数据持久化（JSON + 热重载恢复）
├── routers/                # API 路由
│   ├── project.py          # 项目管理（CRUD/Fork/启动/停止）
│   ├── approval.py         # 审批管理（决策/历史/快照/重跑选项）
│   ├── delivery.py         # 交付管理（打包/下载）
│   ├── llm_config.py       # LLM 配置（CRUD/连接测试/缓存统计）
│   └── ws.py               # WebSocket 实时通信
└── static/                 # 前端（Vue3 单页应用）
    ├── index.html
    ├── css/style.css
    └── js/app.js
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- 至少一个 LLM API Key（推荐 DeepSeek）

### 安装

```bash
git clone https://github.com/financia0x00001/ai-agent-platform.git
cd ai-agent-platform
pip install -r requirements.txt
```

### 启动

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 即可使用。

### 配置 LLM

1. 打开页面后点击左侧「LLM设置」
2. 选择提供商（如 DeepSeek），填入 API Key
3. 设为默认

### 使用流程

1. **创建项目** → 填写项目名称和需求描述
2. **启动工作流** → 智能体按流程协作
3. **审批节点** → 查看产出物，选择通过/驳回/局部重跑
4. **交付下载** → 工作流完成后一键下载 ZIP

## 🔄 工作流程

```
需求分析 → 产品经理输出PRD
    │
    ▼
⏸️ PRD审批
    │
    ▼
设计开发 → UI设计师 + 后端开发（并行） → 前端开发
    │
    ▼
⏸️ 设计审批
    │
    ▼
前端阶段 → 指纹去重（输入未变则跳过，省6000 tokens）
    │
    ▼
⏸️ 前端审批
    │
    ▼
质量保障 → 质量工程师（测试+安全审计合并，单次调用）
    │
    ▼
修复循环（最多3轮）
  ├── 智能分流：只修有 Bug 的 Agent
  ├── 指纹去重：输入未变跳过重复修复
  └── 增量复查：R2+ 只重验旧 Bug（节省70%）
    │
    ▼
交付完成 → ZIP下载
```

## 📋 审批操作

| 操作 | 说明 | 效果 |
|------|------|------|
| ✅ 通过 | 满意，继续下一步 | 流程推进到下一阶段 |
| 💬 驳回修改 | 不满意，提修改意见 | 对应智能体根据意见重新生成 |
| 🔄 局部重跑 | 选择特定智能体重跑 | 只重跑选中的智能体，其他不变 |

## 📊 Token 节省策略

| 策略 | 机制 | 节省 |
|------|------|:--:|
| 合并 QA | 测试+安全审计合并为单次调用 | 35%/轮 |
| 增量复查 | 修复循环 R2+ 只验证旧 Bug 是否修复 | 70%/后续轮 |
| 指纹去重 | SHA256 输入指纹，未变化则跳过 Agent 调用 | 6000-13000/次 |
| 智能分流 | 只对有 Bug 的 Agent 触发修复 | 40-50%/修复阶段 |
| 响应缓存 | temperature ≤ 0.3 时 SHA256 Prompt 缓存 | 100%/相同调用 |

综合预计节省 **55-65%** Token（3轮修复项目）。

## 🔧 JSON 容错解析

LLM 输出的 JSON 经常格式不规范。系统内置 5 层降级容错：

1. Markdown 代码块提取 (` ```json ... ``` `)
2. 花括号平衡扫描
3. 首尾截取
4. 自动修复（尾逗号/单引号/注释/无引号Key）
5. 代码文件兜底提取（JSON 全崩时正则提取 path/content 对）

额外支持**嵌套 JSON 自动展开**：如果 LLM 把整个输出套在 `files[0].content` 里，系统自动递归展开为独立代码文件。

## 🔄 交付标准

项目完成不等于可以交付。系统通过 **质量门控** 判定：

```
工作流完成
    │
    ├── 测试通过 + 安全通过 → completed（可交付 ✅）
    ├── 测试失败 或 安全失败 → needs_review（待修复 ⚠️）
    └── 用户手动停止         → stopped
```

- **needs_review** 项目点击"重新启动"仅重跑 QA + 修复循环，保留已生成的代码和文档
- 最多 **3 轮**修复循环，仍不通过则建议人工介入
- **交付中心**无论 QA 是否通过均可查看完整报告和下载代码

## 🔧 LLM 重试与成本追踪

### 智能重试

遇到以下错误自动重试（最多 3 次，指数退避 + 随机抖动）：

| 错误类型 | 行为 |
|----------|------|
| 429 Rate Limit | 重试，2s → 4s → 8s (±jitter) |
| 5xx Server Error | 重试 |
| Timeout / Connection Error | 重试 |
| 400 / 401 | 不重试，直接报错 |

### 成本追踪

内置主流模型定价表，自动统计：

```
模型: deepseek-chat
API 调用: 12 次
输入 Token: 45,230  输出 Token: 8,912
总 Token: 54,142    预估费用: ¥0.06
```

在交付中心的「LLM 用量」卡片和交付报告 Markdown 中展示。

## ✏️ 审批时编辑产出物

审批等待期间，可直接编辑智能体生成的产出物（PRD、UI规范、代码等），修改后保存，无需驳回重跑：

- 审批面板激活时，产出物右上角出现 **「✏️ 编辑」** 按钮
- 点击进入 textarea 编辑器，支持 JSON 和纯文本格式
- 保存后立即生效，通过审批时使用编辑后的版本

## 🌐 支持的 LLM 平台

| 平台 | 模型列表 | Base URL |
|------|---------|----------|
| DeepSeek | deepseek-chat, deepseek-reasoner | api.deepseek.com |
| OpenAI | gpt-4o, gpt-4o-mini, o1, o1-mini, o3-mini | api.openai.com |
| 智谱AI | glm-4-plus/flash/4/4.5/4.5-air/4.6/4.7/5/5-turbo/5.1 | open.bigmodel.cn |
| Moonshot | moonshot-v1-8k/32k/128k | api.moonshot.cn |
| 通义千问 | qwen-max/plus/turbo | dashscope.aliyuncs.com |
| 自定义 | 任何 OpenAI 兼容接口 | 自定义 |

推理模型（glm-5/5.1, deepseek-reasoner, o1/o3-mini）自动检测并 3x 放大 max_tokens，不超过模型硬上限。

## 🖥️ 生产部署

### Docker（推荐）

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

数据持久化在 `./data` 目录，容器重启不会丢失。

### Systemd 守护进程

```ini
[Unit]
Description=AI Agent Platform
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/ai-agent-platform
ExecStart=/opt/ai-agent-platform/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### WebSocket 连接稳定性

系统实现了双向心跳保活机制，确保通过 NAT/代理（如阿里云、腾讯云等公网映射）时 WebSocket 连接不会因空闲超时断开。

**心跳策略：**
- 服务端每 **30 秒**主动发送 `ping`，客户端立即回复 `pong`
- 客户端每 **20 秒**主动发送 `ping`，服务端立即回复 `pong`
- 服务端 **90 秒**无任何消息则判定超时，主动断开

**重连策略（指数退避）：**
- 初始重连延迟 **1 秒**
- 每次失败延迟翻倍（1s → 2s → 4s → 8s → …）
- 上限 **30 秒**
- 连接成功后自动重置

**关键配置（routers/ws.py）：**

```python
HEARTBEAT_INTERVAL = 30  # 服务端心跳间隔(秒)，低于大部分代理超时(60s)
HEARTBEAT_TIMEOUT = 90   # 客户端无响应超时
```

**代理兼容建议：**
- 如果使用 Nginx 反向代理，确保 WebSocket 升级头正确配置（见上文 Nginx 配置）
- 如果使用云服务商的 NAT 网关，确认其 TCP 空闲超时 ≥ 60 秒（阿里云默认 300s，安全）

## 🛠️ 技术栈

- **后端**：Python 3.10+ / FastAPI / Uvicorn / asyncio
- **前端**：Vue 3 (CDN) / Remix Icon
- **通信**：WebSocket / REST API
- **LLM**：OpenAI 兼容接口（流式输出）

## 📄 License

MIT
