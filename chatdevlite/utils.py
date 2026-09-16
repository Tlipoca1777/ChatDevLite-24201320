# -*- coding: utf-8 -*-
"""通用工具：.env 读取、模板渲染、代码块抽取。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

# ---------------------------------------------------------------- .env ----

def _project_root() -> Path:
    """项目根目录（chatdevlite/ 的上一级）。"""
    return Path(__file__).resolve().parent.parent


def load_dotenv(path: str | os.PathLike | None = None) -> Dict[str, str]:
    """极简 .env 解析器（不依赖第三方库）。

    未指定 path 时，依次查找：当前工作目录/.env、项目根目录/.env（先命中的优先）。
    已存在的同名环境变量优先，不会被文件覆盖。
    """
    if path is not None:
        candidates = [Path(path)]
    else:
        candidates = [Path.cwd() / ".env", _project_root() / ".env"]

    env: Dict[str, str] = {}
    for p in candidates:
        if not p.exists():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            env.setdefault(key, value)
    return env


def get_env(key: str, default: str = "") -> str:
    """读取环境变量：进程环境 > .env 文件 > 默认值。"""
    if os.environ.get(key):
        return os.environ[key]
    return load_dotenv().get(key, default)


# ------------------------------------------------------------- 模板渲染 ----

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_template(template: str, mapping: Mapping[str, Any]) -> str:
    """把 {key} 替换为 mapping[key]；未命中的占位符替换为空串，不会抛异常。"""
    def _sub(m: re.Match) -> str:
        value = mapping.get(m.group(1), "")
        return "" if value is None else str(value)

    return _PLACEHOLDER_RE.sub(_sub, template or "")


# ------------------------------------------------------------- 代码抽取 ----

_FENCE_RE = re.compile(r"```([A-Za-z0-9_+\-]*)[ \t]*([^\n`]*)\n(.*?)```", re.DOTALL)
_FILENAME_RE = re.compile(r"^[\w./\\-]+\.[A-Za-z0-9]{1,6}$")


def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """从大模型回复中抽取 ``` 代码块。

    支持两种写法：
        ```python main.py   -> lang=python, name=main.py
        ```python           -> lang=python, name=""
    """
    blocks: List[Dict[str, str]] = []
    for m in _FENCE_RE.finditer(text or ""):
        lang = (m.group(1) or "").strip().lower()
        info = (m.group(2) or "").strip().lstrip(":").strip()
        blocks.append({"lang": lang, "name": info, "code": m.group(3).rstrip() + "\n"})
    return blocks


def guess_filename(block: Mapping[str, str], default: str = "main.py") -> str:
    """推断代码块对应的文件名。"""
    name = (block.get("name") or "").strip().strip("`")
    if name and _FILENAME_RE.match(name):
        return name
    return default


def is_done(reply: str, markers: Iterable[str] = ("<DONE>", "任务完成", "已完成全部需求")) -> bool:
    """判断助手是否宣告任务结束。"""
    return any(mk in (reply or "") for mk in markers)


def text_table(rows: List[Tuple[str, ...]], headers: Tuple[str, ...]) -> str:
    """生成一个简易的等宽文本表格（用于终端输出）。"""
    cols = len(headers)
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(str(row[i])))
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(cells: Tuple[str, ...]) -> str:
        return "| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    out = [line, fmt(headers), line]
    out += [fmt(tuple(str(c) for c in r)) for r in rows]
    out.append(line)
    return "\n".join(out)
