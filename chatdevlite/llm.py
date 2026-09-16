# -*- coding: utf-8 -*-
"""大模型接入层：统一 chat(messages) -> str 接口。

支持三种后端（由 config.yaml / 命令行切换）：
    openai  任意 OpenAI 兼容接口（OpenAI / DeepSeek / 通义千问 / 智谱 …），仅用标准库 urllib 实现
    ollama  本地模型（http://localhost:11434）
    mock    离线内置，用于无网络 / 无 Key 时演示与自测整条流水线
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Dict, List

from .config import ModelConfig
from .utils import extract_code_blocks

Message = Dict[str, str]


class LLMError(RuntimeError):
    pass


# ============================================================ 抽象基类 ====

class BaseLLM:
    name = "base"

    @property
    def endpoint(self) -> str:
        """实际请求的接口地址（用于启动时自检，mock 后端为空）。"""
        return ""

    def chat(self, messages: List[Message]) -> str:  # pragma: no cover
        raise NotImplementedError


def _chat_endpoint(base_url: str) -> str:
    """把 base_url 规范化为 chat/completions 端点。

    base_url 写到域名（https://api.deepseek.com）或 /v1（https://api.openai.com/v1）均可，
    已经带 /chat/completions 的也不会重复拼接。
    """
    url = (base_url or "").rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


# ====================================================== OpenAI 兼容后端 ====

class OpenAICompatibleLLM(BaseLLM):
    name = "openai"

    def __init__(self, cfg: ModelConfig):
        if not cfg.api_key:
            raise LLMError(
                "未找到 API Key。请在 .env 中设置 OPENAI_API_KEY，"
                "或在 config.yaml 的 model.api_key 中填写；也可用 --backend mock 先跑通流程。"
            )
        self.cfg = cfg
        self.url = _chat_endpoint(cfg.base_url)

    @property
    def endpoint(self) -> str:
        return self.url

    def chat(self, messages: List[Message]) -> str:
        payload = {
            "model": self.cfg.name,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "stream": False,
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise LLMError(f"接口返回 HTTP {e.code}：{detail}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"无法连接模型服务 {self.url}：{e.reason}") from e
        return data["choices"][0]["message"]["content"]


# ============================================================ Ollama ====

class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self.url = cfg.ollama_host.rstrip("/") + "/api/chat"

    @property
    def endpoint(self) -> str:
        return self.url

    def chat(self, messages: List[Message]) -> str:
        payload = {
            "model": self.cfg.name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise LLMError(f"无法连接 Ollama {self.url}：{e.reason}（请先执行 ollama serve）") from e
        return data["message"]["content"]


# ============================================================== 离线桩 ====

class MockLLM(BaseLLM):
    """离线后端：按角色返回结构化的"像样"回答，并生成真正可运行的代码。

    它的定位是「无网络 / 无 Key 时也能跑通整条流水线」，用于演示与自动化自测；
    接入真实模型时只需把 backend 换成 openai / ollama，其余代码完全不用改。
    """

    name = "mock"
    _ROLE_RE = re.compile(r"#\s*角色：([A-Za-z_]+)")

    def chat(self, messages: List[Message]) -> str:
        system = messages[0].get("content", "") if messages else ""
        user = messages[-1].get("content", "") if messages else ""
        role = (self._ROLE_RE.search(system).group(1) if self._ROLE_RE.search(system) else "Generic")
        # 关键：任务描述可能出现在本子任务的任意一轮 user 消息里（多轮对话时最后一轮往往是评审意见），
        # 因此需要扫描整个会话而不只是最后一条。
        task = self._task_of(messages)
        fixed = ("评审意见" in user) or ("修复" in user)

        if role == "Programmer":
            return _mock_programmer(task, fixed, user)
        if role == "CPO":
            return _mock_manual(task) if "用户手册" in user else _mock_requirement(task)
        if role == "CTO":
            return _mock_design(task)
        if role == "Reviewer":
            return _mock_review()
        if role == "Tester":
            return _mock_test()
        if role == "Designer":
            return "界面采用命令行文本菜单：主菜单 1~4 选项，输入即回显结果。"
        return _mock_requirement(task)

    # ------------------------------------------------------------ 工具 ----
    @staticmethod
    def _task_of(messages: List[Message]) -> str:
        """从整个会话的 user 消息中回溯出原始需求描述。"""
        texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        patterns = (
            r"用户用一句话提出的需求是[：:]\s*(.+)",
            r"用户需求[：:]\s*(.+)",
            r"需求[：:]\s*(.+)",
        )
        for pat in patterns:
            for text in texts:
                m = re.search(pat, text)
                if m:
                    return m.group(1).strip().splitlines()[0]
        return "一个命令行小程序"


# ------------------------------------------------------------- 需求说明 ----

def _mock_requirement(task: str) -> str:
    return f"""《需求说明》
1. 软件类型与目标用户：面向初学者的命令行（CLI）小工具，目标用户为普通个人用户。
2. 功能清单：
   1) 启动后显示欢迎信息与操作菜单；
   2) 支持核心业务操作（围绕「{task}」）；
   3) 对非法输入给出友好提示，不崩溃；
   4) 支持退出命令。
3. 验收标准：
   - 使用 Python 标准库，`python main.py` 可直接运行；
   - 功能清单中每一项均可用一次手动测试验证；
   - 异常输入不会导致程序异常退出。
任务完成。"""


# ------------------------------------------------------------- 技术方案 ----

def _mock_design(task: str) -> str:
    return f"""《技术方案》
1. 技术栈：Python 3.10+，仅使用标准库（sys），不引入第三方依赖。
2. 文件与模块划分：
   - main.py：程序入口，包含 main() 主循环与业务函数；
   - README.md：用户手册（由文档阶段生成）。
3. 核心数据结构与关键流程：
   - 以「读取输入 → 解析命令 → 分发处理 → 输出结果」为主循环；
   - 业务逻辑抽成独立函数，便于单元测试；
   - 使用 try/except 统一处理输入与运算异常。
4. 接口签名（示例）：
   - def main() -> int
   - def handle(command: str) -> str
任务完成。"""


# --------------------------------------------------------------- 评审 ----

def _mock_review() -> str:
    return """代码评审结果
| 问题 | 严重级别 | 修改建议 |
| --- | --- | --- |
| 缺少对 KeyboardInterrupt 的处理，Ctrl+C 会抛栈 | 低 | 在 main() 外层包裹 try/except |
| 未对空输入做统一兜底 | 中 | 解析前先 strip 并判断空串 |
| 业务函数缺少文档字符串 | 低 | 为每个公开函数补充 docstring |
结论：存在 3 处待改进项，建议修复后再提交。任务完成。"""


# --------------------------------------------------------------- 测试 ----

def _mock_test() -> str:
    return """测试报告
| 用例 | 输入 | 预期输出 | 结果 |
| --- | --- | --- | --- |
| UC-1 | 正常业务输入 | 得到正确结果 | 通过 |
| UC-2 | 空输入 | 给出提示不崩溃 | 通过 |
| UC-3 | 非法字符 | 给出提示不崩溃 | 通过 |
| UC-4 | 退出命令 | 正常结束进程 | 通过 |
结论：4/4 用例通过，测试通过。任务完成。"""


# --------------------------------------------------------------- 手册 ----

def _mock_manual(task: str) -> str:
    return f"""# 用户手册

## 项目简介
本程序围绕「{task}」实现，是一个只用 Python 标准库编写的命令行小工具，
界面简洁、无需安装任何第三方依赖。

## 环境要求
- Python 3.10 或更高版本
- 任意支持 UTF-8 的终端（Windows / macOS / Linux）

## 安装与运行
```bash
# 无需安装依赖，直接运行
python main.py
```

## 使用示例
```text
$ python main.py
> help        # 查看可用命令
> 输入业务命令 # 按提示操作
> quit        # 退出程序
```

## 常见问题
1. 中文显示为乱码？
   请确认终端编码为 UTF-8（Windows 可执行 `chcp 65001`）。
2. 提示 `python 不是内部或外部命令`？
   请将 Python 加入系统 PATH，或改用 `py main.py`。

任务完成。
"""


# ------------------------------------------------------------- 代码生成 ----

_CALC_KEYWORDS = ("计算", "calculator", "算数", "四则", "加减乘除")
_TODO_KEYWORDS = ("待办", "todo", "任务清单", "清单", "记事")


def _pick_program(task: str) -> str:
    low = task.lower()
    if any(k in task or k in low for k in _CALC_KEYWORDS):
        return "calculator"
    if any(k in task or k in low for k in _TODO_KEYWORDS):
        return "todo"
    return "generic"


def _mock_programmer(task: str, fixed: bool, user: str = "") -> str:
    if fixed:
        # 「修复」必须保持原程序不变，因此直接从上下文里的既有代码复用，只补加固说明
        original = _extract_program_from(user)
        if not original:
            original = _program_generic()
        body = original
        if body.startswith("# -*- coding: utf-8 -*-"):
            body = body.split("\n", 1)[1]
        code = (
            "# -*- coding: utf-8 -*-\n"
            "# v1.1  根据评审意见修复：\n"
            "#   1) 输入统一 strip 并兜底空串；2) 补充 KeyboardInterrupt 处理；\n"
            "#   3) 为公开函数补充文档字符串。\n"
            + body
        )
        return (
            "已按评审意见完成修复，主要修改：\n"
            "1) 输入统一 strip 并兜底空串；\n"
            "2) 关键分支补充异常处理；\n"
            "3) 补充函数文档字符串。\n\n"
            "```python main.py\n" + code + "```\n\n任务完成。"
        )

    kind = _pick_program(task)
    code = {"calculator": _program_calculator,
            "todo": _program_todo,
            "generic": _program_generic}[kind]()
    return (
        f"已按技术方案实现「{task}」，仅使用 Python 标准库，入口为 main.py。\n\n"
        "```python main.py\n" + code + "```\n\n任务完成。"
    )


def _extract_program_from(text: str) -> str:
    """从一段文本中取出第一段 python 代码块（用于"修复时保持原程序不变"）。"""
    for block in extract_code_blocks(text or ""):
        if block["lang"] in ("python", "py", "") and block["code"].strip():
            return block["code"]
    return ""


def _program_calculator() -> str:
    return '''# -*- coding: utf-8 -*-
"""简易计算器：支持加、减、乘、除，输入形如  3 + 5 。"""
import sys

# 运算符 -> 计算函数
OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


def calc(a: float, op: str, b: float) -> float:
    """执行一次二元运算，非法运算符或除零会抛出异常。"""
    if op not in OPS:
        raise ValueError(f"不支持的运算符：{op}")
    if op == "/" and b == 0:
        raise ZeroDivisionError("除数不能为 0")
    return OPS[op](a, b)


def evaluate(line: str) -> str:
    """把一行文本解析成算式并返回结果字符串。"""
    parts = line.split()
    if len(parts) != 3:
        return "格式错误，请按  数字 运算符 数字  输入（例如 3 + 5）。"
    try:
        a, op, b = float(parts[0]), parts[1], float(parts[2])
        return f"= {calc(a, op, b):g}"
    except (ValueError, ZeroDivisionError) as exc:
        return f"计算失败：{exc}"


def main() -> int:
    print("=== 简易计算器 ===")
    print("输入 `数字 运算符 数字` 回车计算，输入 q 退出。")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\n已退出。")
            return 0
        if line.lower() in ("q", "quit", "exit"):
            print("再见！")
            return 0
        if not line:
            continue
        print(evaluate(line))


if __name__ == "__main__":
    sys.exit(main())
'''


def _program_todo() -> str:
    return '''# -*- coding: utf-8 -*-
"""待办清单：内存版极简 TODO，命令 add / list / done / quit。"""
import sys


def main() -> int:
    todos = []
    print("=== 待办清单 ===")
    print("命令：add 内容 | list | done 序号 | quit")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\n已退出。")
            return 0
        if not line:
            continue
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()

        if cmd in ("quit", "exit", "q"):
            print("已退出。")
            return 0
        elif cmd == "add":
            if not arg:
                print("请输入待办内容，例如：add 写实验报告")
                continue
            todos.append({"text": arg, "done": False})
            print(f"已添加 [{len(todos)}] {arg}")
        elif cmd == "list":
            if not todos:
                print("暂无待办。")
                continue
            for i, t in enumerate(todos, 1):
                mark = "x" if t["done"] else " "
                print(f"  {i}. [{mark}] {t['text']}")
        elif cmd == "done":
            try:
                idx = int(arg)
                todos[idx - 1]["done"] = True
                print(f"已完成 [{idx}] {todos[idx - 1]['text']}")
            except (ValueError, IndexError):
                print("序号无效，请先 list 查看。")
        else:
            print(f"未知命令：{cmd}")


if __name__ == "__main__":
    sys.exit(main())
'''


def _program_generic() -> str:
    return '''# -*- coding: utf-8 -*-
"""猜数字小游戏：在 1~100 之间随机取一个数，由玩家猜。"""
import random
import sys


def main() -> int:
    answer = random.randint(1, 100)
    print("=== 猜数字 ===")
    print("我已经想好了一个 1~100 的整数，输入 q 退出。")
    tries = 0
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\n已退出。")
            return 0
        if line.lower() in ("q", "quit", "exit"):
            print(f"答案是 {answer}，再见。")
            return 0
        try:
            guess = int(line)
        except ValueError:
            print("请输入一个整数。")
            continue
        tries += 1
        if guess < answer:
            print("太小了 ↑")
        elif guess > answer:
            print("太大了 ↓")
        else:
            print(f"猜对了！共用了 {tries} 次。")
            return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# ============================================================== 工厂 ====

def create_llm(cfg: ModelConfig) -> BaseLLM:
    """根据配置创建大模型客户端。"""
    backend = (cfg.backend or "mock").lower()
    if backend == "openai":
        return OpenAICompatibleLLM(cfg)
    if backend == "ollama":
        return OllamaLLM(cfg)
    return MockLLM()
