# -*- coding: utf-8 -*-
"""M6 日志与交互模块：结构化 JSONL 日志 + 终端实时进度。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_LEVEL_TAG = {
    "run": "\033[1;36m[运行]\033[0m",
    "phase": "\033[1;34m[阶段]\033[0m",
    "subtask": "\033[1;35m[子任务]\033[0m",
    "agent": "\033[0;37m[智能体]\033[0m",
    "file": "\033[1;32m[产物]\033[0m",
    "git": "\033[1;33m[版本]\033[0m",
    "warn": "\033[1;33m[警告]\033[0m",
    "done": "\033[1;32m[完成]\033[0m",
}


class RunLogger:
    """一次运行对应一个 RunLogger。

    - 控制台：人类可读的进度输出（可用 echo=False 关闭）
    - 文件：WareHouse/<项目>/logs/run.jsonl，每行一条 JSON 记录，便于回放与统计
    """

    def __init__(self, logfile: str | Path, echo: bool = True, verbose: bool = True):
        self.logfile = Path(logfile)
        self.logfile.parent.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self.verbose = verbose
        self.records: list[dict] = []

    # ------------------------------------------------------------ 基础 ----
    def _emit(self, level: str, message: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "message": message,
            **fields,
        }
        self.records.append(record)
        with self.logfile.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self.echo and level != "agent_detail":
            tag = _LEVEL_TAG.get(level, f"[{level}]")
            print(f"{tag} {message}", flush=True)

    # ------------------------------------------------------------ 分场景 ----
    def run(self, message: str, **f: Any) -> None:
        self._emit("run", message, **f)

    def phase(self, message: str, **f: Any) -> None:
        self._emit("phase", message, **f)

    def subtask(self, message: str, **f: Any) -> None:
        self._emit("subtask", message, **f)

    def agent(self, role: str, message: str, **f: Any) -> None:
        self._emit("agent", message, role=role, **f)

    def file(self, message: str, **f: Any) -> None:
        self._emit("file", message, **f)

    def git(self, message: str, **f: Any) -> None:
        self._emit("git", message, **f)

    def warn(self, message: str, **f: Any) -> None:
        self._emit("warn", message, **f)

    def done(self, message: str, **f: Any) -> None:
        self._emit("done", message, **f)

    def dialogue(self, round_no: int, instructor: str, assistant: str,
                 request: str, reply: str) -> None:
        """完整记录一轮对话（写入 JSONL，控制台只给摘要）。"""
        self._emit(
            "agent_detail",
            f"第 {round_no} 轮对话",
            round=round_no, instructor=instructor, assistant=assistant,
            request=request, reply=reply,
        )
        if self.echo and self.verbose:
            short = reply.strip().replace("\n", " ")
            if len(short) > 60:
                short = short[:60] + "…"
            print(f"    ├─ {instructor} → {assistant}：{short}", flush=True)

    # ------------------------------------------------------------ 统计 ----
    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r["level"]] = counts.get(r["level"], 0) + 1
        return counts
