# 🤖 AI Agent Collaboration Platform

基于大语言模型的多智能体协作开发平台，模拟真实软件公司的多部门协同工作流程。

## ✨ 核心特性

- **6 个 AI 智能体角色**：产品经理、UI设计师、前端开发、后端开发、代码测试、安全审计
- **3 个人工审批节点**：PRD审批 → 设计审批 → 前端审批，支持通过/驳回/局部重跑
- **多 LLM 支持**：DeepSeek、OpenAI、智谱AI、Moonshot、通义千问等，通过 OpenAI 兼容接口接入
- **实时协作**：WebSocket 推送智能体状态、日志、审批事件
- **项目交付**：一键打包下载 ZIP（含文档、前后端代码、测试报告）
- **数据持久化**：项目数据自动保存，服务器重启后可恢复

## 🏗️ 系统架构

```
用户需求
   │
   ▼
┌──────────────────────────────────────────┐
│            编排器 (Orchestrator)           │
│       控制流程 / 分配任务 / 汇总结果        │
└──┬───────┬───────┬───────┬───────┬───────┘
   │       │       │       │       │
   ▼       ▼       ▼       ▼       ▼
 产品经理  UI设计  前端开发  后端开发  测试+审计
   │       │       │       │       │
   ▼       ▼       ▼       ▼       ▼
  PRD    UI规范   前端代码  API+代码  测试/安全报告
   │                                           │
   ├── ⏸️ PRD审批 ── ⏸️ 设计审批 ── ⏸️ 前端审批 ──┤
   │        人工审批节点，支持驳回修改和局部重跑     │
   └─────────────────────────────────────────────┘
```

## 📁 项目结构

```
├── app.py                  # FastAPI 主入口
├── config.py               # 配置管理
├── requirements.txt        # Python 依赖
├── agents/                 # 智能体
│   ├── base.py             # 基类（流式输出 / 反馈修改 / JSON解析）
│   ├── pm.py               # 产品经理 → PRD文档
│   ├── ui_designer.py      # UI设计师 → UI规范
│   ├── backend_dev.py      # 后端开发 → API + 代码
│   ├── frontend_dev.py     # 前端开发 → 页面 + 组件
│   ├── tester.py           # 代码测试 → 测试报告
│   └── auditor.py          # 安全审计 → 安全报告
├── core/                   # 核心模块
│   ├── blackboard.py       # 共享黑板（智能体通信 + 审批状态）
│   ├── orchestrator.py     # 编排器（流程控制 + 审批暂停）
│   ├── llm_provider.py     # LLM 提供商（多平台支持）
│   ├── delivery.py         # 交付打包器
│   └── persistence.py      # 数据持久化
├── routers/                # API 路由
│   ├── project.py          # 项目管理
│   ├── approval.py         # 审批管理
│   ├── delivery.py         # 交付管理
│   ├── llm_config.py       # LLM 配置
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
⏸️ PRD审批（通过 / 驳回修改 / 局部重跑）
    │
    ▼
设计开发 → UI设计师 + 后端开发（并行）
    │
    ▼
⏸️ 设计审批
    │
    ▼
前端开发
    │
    ▼
⏸️ 前端审批
    │
    ▼
质量保障 → 代码测试 + 安全审计（并行）
    │
    ▼
修复循环（最多3轮）
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

## 🌐 支持的 LLM 平台

| 平台 | 默认模型 | Base URL |
|------|---------|----------|
| DeepSeek | deepseek-chat | api.deepseek.com |
| OpenAI | gpt-4o | api.openai.com |
| 智谱AI | glm-4-plus | open.bigmodel.cn |
| Moonshot | moonshot-v1-128k | api.moonshot.cn |
| 通义千问 | qwen-max | dashscope.aliyuncs.com |
| 自定义 | 自定义 | 自定义 |

所有平台通过 OpenAI 兼容接口接入，支持流式输出。

## 🖥️ 生产部署

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

## 🛠️ 技术栈

- **后端**：Python 3.10+ / FastAPI / Uvicorn / asyncio
- **前端**：Vue 3 (CDN) / Remix Icon
- **通信**：WebSocket / REST API
- **LLM**：OpenAI 兼容接口（流式输出）

## 📄 License

MIT
