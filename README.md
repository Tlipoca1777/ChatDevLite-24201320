# ChatDevLite-24201320

> 最小可用的多智能体软件开发框架 —— 一句话需求，驱动一支"虚拟 AI 软件公司"产出可运行代码。

本项目是 [ChatDev](https://github.com/OpenBMB/ChatDev) 的轻量化重写版本（课程实验《软件项目管理》实验一），
对应《项目范围说明书》中 **ChatDevLite-24201320** 的落地实现。设计目标是 **更简约、更完备、更好修改**。

---

## 1. 它做什么

```
用户一句话需求  ──►  设计(Chat Chain) ──► 编码 ──► 测试 ──► 文档  ──►  可运行软件 + 日志 + Git 版本
```

你只需要：

```bash
python main.py -t "做一个命令行待办事项应用" -n TodoApp
```

框架会自动让 CEO、CPO、CTO、程序员、评审员、测试员等智能体通过多轮对话协作，
在工作区 `WareHouse/TodoApp/` 下产出可运行代码、需求/设计/测试文档与用户手册，并自动做 Git 版本管理。

## 2. 快速开始

```bash
# ① 安装依赖（仅需 PyYAML，其余全部为标准库）
pip install -r requirements.txt

# ② 直接运行（默认走离线 mock 后端，无需联网、无需 API Key）
python main.py

# ③ 指定需求与软件名
python main.py -t "做一个简易计算器" -n CalcApp

# ④ 查看配置（不运行）
python main.py --show-config
```

运行结束后会打印子任务表、产出文件、Git 版本记录，日志位于
`WareHouse/<软件名>/logs/run.jsonl`（结构化 JSONL，可回放）。

## 3. 接入真实大模型

### 3.1 OpenAI 兼容接口（OpenAI / DeepSeek / 通义千问 / 智谱 …）

**第 1 步：生成 `.env` 文件**（这一步不涉及你的 Key，只是把模板复制一份）

```powershell
# PowerShell / CMD（Windows）
copy .env.example .env

# Git Bash / macOS / Linux
cp .env.example .env
```

**第 2 步：打开 `.env`，把 Key 填进去**（用记事本或 VS Code 编辑）

```ini
OPENAI_API_KEY=sk-你的真实Key        # ← 只改等号右边这一处
```

> ⚠️ Key 是写进**文件内容**里的，不是写进命令里。
> `.env` 已被 `.gitignore` 忽略，不会误提交。

**第 3 步：运行**（以 DeepSeek 为例）

```bash
python main.py -t "做一个待办事项应用" \
    --backend openai \
    --model deepseek-flash \
    --base-url https://api.deepseek.com
```

> `.env` 会在「当前目录」和「项目根目录」两处自动查找，所以从哪个目录运行都能读到。
> `--base-url` 写到域名或 `/v1` 为止即可，程序会自动补上 `/chat/completions`。

**常用服务商参数**（2026-09 核对）

| 服务 | `--base-url` | `--model` |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` / `deepseek-v4-pro` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

> 本文档编写时 DeepSeek 官方 `base_url` 为 `https://api.deepseek.com`（不带 `/v1`），
> 模型名为 `deepseek-flash` 与 `deepseek-v4-pro`。各家接口若有更新，请以官方文档为准。

### 3.2 本地 Ollama

```bash
ollama serve                  # 另开一个终端
ollama pull qwen2.5:7b
python main.py -t "做一个猜数字游戏" --backend ollama --model qwen2.5:7b
```

> 三种后端（`mock` / `openai` / `ollama`）共用同一个 `chat(messages) -> str` 接口，
> 切换后端**不需要修改任何业务代码**。

### 3.3 跑真实模型不成功？先看这四条

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `未找到 API Key` | `.env` 不存在，或 Key 行仍是占位符 | 检查 `.env` 里 `OPENAI_API_KEY=` 右边是否已换成真实 Key |
| `接口返回 HTTP 401` | Key 无效 / 复制时带了空格 | 重新复制 Key，注意别带引号和尾随空格 |
| `接口返回 HTTP 404` | `--base-url` 写错 | 对照上表；程序会自动补 `/chat/completions`，**不要**自己写到这一层 |
| 一直卡在「代码编写」不动 | 模型响应慢或请求被挂起 | 加大超时 `--timeout 300`；先用 `--rounds 1` 减少轮次 |
| 跑完了但工作区没有 `main.py` | 模型没按 ` ```python 文件名 ` 格式输出代码块 | 见下方提示，框架会主动告警 |

> 运行结束后如果出现 `「代码编写」没有从回复中提取到任何代码块` 的告警，
> 请打开 `WareHouse/<软件名>/logs/run.jsonl`，搜索该子任务的 `"level": "agent_detail"` 记录，
> 里面保存了模型的**原始回复**，据此再去微调 `config/phases.yaml` 里的提示词。

## 4. 目录结构

```
ChatDevLite-24201320/
├── main.py                   # 命令行入口（CLI）
├── requirements.txt
├── .env.example
├── config/                   # ① 全部配置都在这里（YAML 驱动）
│   ├── config.yaml           #    模型参数 + 运行参数
│   ├── roles.yaml            #    角色库（新增角色只改这里）
│   └── phases.yaml           #    Chat Chain 阶段与子任务编排
├── chatdevlite/              # ② 核心框架（六条主干，对应报告 M1~M6）
│   ├── config.py             #    M1 配置管理
│   ├── agent.py              #    M2 智能体（Agent 基类 + 记忆流）
│   ├── orchestration.py      #    M3 协作编排（Chat Chain）
│   ├── workspace.py          #    M4 代码工作区与 Git 版本管理
│   ├── logger.py             #    M6 日志与交互
│   ├── llm.py                #    大模型接入（openai / ollama / mock）
│   └── utils.py
└── WareHouse/                # ③ 每次运行生成的工作区（代码 + 文档 + 日志）
    └── <软件名>/
```

## 5. 功能模块（对应《项目范围说明书》）

| 编号 | 模块 | 说明 | 代码 |
| --- | --- | --- | --- |
| M1 | 配置管理 | 加载模型/角色/流程配置，支持多 LLM 后端 | `config.py` |
| M2 | 智能体 | Agent 基类、角色库、记忆流 | `agent.py` |
| M3 | 协作编排 | 原子子任务、"指导者—助手"多轮对话、阶段上下文传递 | `orchestration.py` |
| M4 | 工作区与版本管理 | 文件树、增量写入、Git 提交与回滚 | `workspace.py` |
| M5 | 质量保障 | 代码评审（静态）+ 系统测试（动态）+ 缺陷修复回路 | 见 `phases.yaml` 测试阶段 |
| M6 | 日志与交互 | JSONL 日志、终端实时进度、CLI 入口 | `logger.py` / `main.py` |

## 6. 如何"更好修改"

- **加一个角色**：在 `config/roles.yaml` 里新增一段 `角色名: {title, duty, prompt}` 即可。
- **加一个阶段 / 子任务**：在 `config/phases.yaml` 的 `phases` 数组里追加即可，
  支持 `instructor` / `assistant` / `prompt` / `extract_code` / `write` / `skip_if` 等字段。
- **换模型 / 换后端**：只改 `config.yaml` 或命令行参数。
- **改提示词**：全部集中在 `config/*.yaml`，无需翻代码。

`phases.yaml` 子任务字段说明：

| 字段 | 含义 |
| --- | --- |
| `instructor` / `assistant` | 该子任务对话的指导者与助手角色（来自 `roles.yaml`） |
| `prompt` | 首轮指令，可用 `{task}` `{project}` 及之前产出的 `{requirement}` `{design}` `{code}` 等占位符 |
| `artifact` | 把助手最终产出存入共享上下文的名字，供后续子任务引用 |
| `extract_code` | 是否从回复中抽取 ```` ```python 文件名 ```` 代码块并写入工作区 |
| `write` | 把最终产出直接写成某文件（如 `docs/测试报告.md`） |
| `skip_if` | 满足条件则跳过该子任务，如 `{artifact: review, contains: [评审通过]}` |

## 7. 实验环境

- 硬件：普通 PC（CPU i5 / 内存 8GB 及以上）
- 操作系统：Windows / macOS / Linux
- 软件：Python 3.10+、Git（可选）、PyYAML

## 8. 已知限制（后续增量方向）

1. 当前为 **MVP 增量**：只实现"设计→编码→测试→文档"主干，尚无 Web 可视化界面（计划在增量 3 补齐）；
2. `mock` 后端为离线演示桩，产出为内置模板，接入真实模型后由 LLM 实际生成；
3. 暂不支持多文件复杂项目的依赖自动安装，仅面向标准库小工具。
