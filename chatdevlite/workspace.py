# -*- coding: utf-8 -*-
"""M4 代码工作区与版本管理模块：文件树管理 + 增量写入 + Git 提交/回滚。"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from .logger import RunLogger


class Workspace:
    """一次开发运行对应一个工作区目录（WareHouse/<项目名>/）。"""

    def __init__(self, root: str | Path, git: bool = True, logger: RunLogger | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.use_git = git
        self.logger = logger
        self._git_ok = False

    # ------------------------------------------------------------ 文件 ----
    def write_file(self, relpath: str, content: str) -> Path:
        """写入（或覆盖）一个文件，返回绝对路径。"""
        target = (self.root / relpath).resolve()
        if self.root.resolve() not in target.parents and target != self.root.resolve():
            raise ValueError(f"非法路径（越出工作区）：{relpath}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if self.logger:
            self.logger.file(f"写入 {relpath}（{len(content)} 字符）")
        return target

    def read_file(self, relpath: str) -> str:
        return (self.root / relpath).read_text(encoding="utf-8")

    def exists(self, relpath: str) -> bool:
        return (self.root / relpath).exists()

    def list_files(self) -> List[str]:
        """列出工作区内全部文件（相对路径，排序）。"""
        out = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                out.append(str(p.relative_to(self.root)).replace("\\", "/"))
        return out

    def file_preview(self, relpath: str, lines: int = 5) -> str:
        text = self.read_file(relpath).splitlines()[:lines]
        return "\n".join(text)

    # ------------------------------------------------------------- Git ----
    def _git(self, *args: str) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                ["git", *args], cwd=str(self.root),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            return proc.returncode, (proc.stdout or proc.stderr or "").strip()
        except FileNotFoundError:
            return 127, "未检测到 git 命令"

    def git_init(self) -> bool:
        if not self.use_git:
            return False
        code, out = self._git("rev-parse", "--is-inside-work-tree")
        if code != 0:
            self._git("init", "-q")
            self._git("config", "user.email", "chatdevlite@example.com")
            self._git("config", "user.name", "ChatDevLite")
            code, out = self._git("rev-parse", "--is-inside-work-tree")
        self._git_ok = (code == 0)
        if self._git_ok:
            self._git("add", "-A")
            if self.logger:
                self.logger.git("Git 工作区已就绪")
        elif self.logger:
            self.logger.warn(f"Git 不可用，跳过版本管理：{out}")
        return self._git_ok

    def git_commit(self, message: str) -> Optional[str]:
        """提交当前全部改动，返回短 commit id（失败返回 None）。"""
        if not (self.use_git and self._git_ok):
            return None
        self._git("add", "-A")
        code, out = self._git("commit", "-q", "-m", message)
        if code != 0 and "nothing to commit" not in out:
            if self.logger:
                self.logger.warn(f"提交失败：{out}")
            return None
        _, rev = self._git("rev-parse", "--short", "HEAD")
        if self.logger:
            self.logger.git(f"提交版本 {rev}：{message}")
        return rev or None

    def git_log(self, n: int = 10) -> List[str]:
        if not (self.use_git and self._git_ok):
            return []
        _, out = self._git("log", f"-{n}", "--pretty=format:%h %ad %s", "--date=format:%Y-%m-%d %H:%M")
        return [ln for ln in out.splitlines() if ln.strip()]

    def rollback(self, rev: str) -> bool:
        """回退到指定版本（git checkout <rev> -- .）。"""
        if not (self.use_git and self._git_ok):
            return False
        code, out = self._git("checkout", rev, "--", ".")
        if self.logger:
            (self.logger.git if code == 0 else self.logger.warn)(
                f"回滚到 {rev}：" + ("成功" if code == 0 else out)
            )
        return code == 0
