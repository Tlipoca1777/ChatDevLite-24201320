# -*- coding: utf-8 -*-
"""M3 协作编排模块（Chat Chain）：把开发流程分解为原子子任务并串接执行。

每个子任务 = 一对「指导者 Instructor + 助手 Assistant」的多轮对话：
    助手先产出成果 -> 指导者评审并下达改进指令 -> 助手迭代，直到达成共识或达到轮数上限。
子任务的产出（制品）会按 artifact 名称写入共享上下文，供后续子任务用 {占位符} 引用。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .agent import AgentPool
from .config import Config, Subtask
from .llm import BaseLLM
from .logger import RunLogger
from .utils import extract_code_blocks, guess_filename, is_done, render_template
from .workspace import Workspace


class ChatChain:
    def __init__(self, config: Config, llm: BaseLLM, workspace: Workspace, logger: RunLogger):
        self.config = config
        self.llm = llm
        self.workspace = workspace
        self.logger = logger
        self.pool = AgentPool(config, llm, logger)
        self.context: Dict[str, str] = {}
        self.records: List[Dict[str, Any]] = []

    # ================================================================ 主流程 ----
    def run(self, task: str, project_name: str) -> Dict[str, Any]:
        self.context = {"task": task, "project": project_name}
        self.logger.run(f"项目 {project_name} 启动，需求：{task}")

        self.workspace.git_init()
        self.workspace.write_file("docs/原始需求.md", f"# 原始需求\n\n> {task}\n")
        self.workspace.git_commit("初始化工作区（写入原始需求）")

        for phase in self.config.phases:
            self.logger.phase(f"{phase.name} 阶段开始（{len(phase.subtasks)} 个子任务）")
            for sub in phase.subtasks:
                self._run_subtask(phase.name, sub)
            rev = self.workspace.git_commit(f"{phase.name}阶段完成")
            self.logger.phase(f"{phase.name} 阶段结束" + (f"（版本 {rev}）" if rev else ""))

        return self._build_summary(project_name, task)

    # ============================================================== 子任务 ----
    def _run_subtask(self, phase_name: str, sub: Subtask) -> None:
        if self._should_skip(sub):
            reason = sub.skip_if.get("artifact", "")
            self.logger.subtask(f"跳过「{sub.name}」（{reason} 满足跳过条件）")
            self.records.append({"phase": phase_name, "name": sub.name, "status": "skipped"})
            return

        self.logger.subtask(f"{sub.name}：{sub.instructor} ↔ {sub.assistant}")
        instruction = render_template(sub.prompt, self.context)
        replies = self._dialogue(sub, instruction)
        final = replies[-1]

        if sub.artifact:
            self.context[sub.artifact] = final

        files: List[str] = []
        if sub.extract_code:
            files = self._write_code_files(replies)
            if not files:
                # 真实模型下最常见的问题：模型没按 ```python 文件名 的格式输出代码块
                self.logger.warn(
                    f"「{sub.name}」没有从回复中提取到任何代码块，工作区未产生代码文件。"
                    f"请检查 config/phases.yaml 中该子任务的提示词是否已强调代码块格式，"
                    f"或到 logs/run.jsonl 查看模型的原始回复。"
                )
        if sub.write:
            self.workspace.write_file(sub.write, final)
            files.append(sub.write)

        self.records.append({
            "phase": phase_name, "name": sub.name, "status": "done",
            "instructor": sub.instructor, "assistant": sub.assistant,
            "rounds": len(replies), "artifact": sub.artifact, "files": files,
        })

    # ------------------------------------------------------------ 对话循环 ----
    def _dialogue(self, sub: Subtask, instruction: str) -> List[str]:
        instructor = self.pool.get(sub.instructor)
        assistant = self.pool.get(sub.assistant)
        rounds = sub.max_rounds or self.config.runtime.max_rounds

        assistant.reset()
        instructor.reset()

        replies: List[str] = []
        message = instruction
        for r in range(1, rounds + 1):
            reply = assistant.step(message)
            self.logger.dialogue(r, instructor.name, assistant.name, message, reply)
            replies.append(reply)
            if is_done(reply) or r >= rounds:
                break
            message = instructor.step(
                f"你的同事 {assistant.name} 提交了如下阶段成果：\n\n{reply}\n\n"
                f"原始任务要求：\n{instruction}\n\n"
                f"请你以 {instructor.name} 的身份，指出成果中的不足，"
                f"并给出下一轮必须完成的具体改进指令（只给指令，不要重复成果本身）。"
            )
        return replies

    # ------------------------------------------------------------ 辅助方法 ----
    def _should_skip(self, sub: Subtask) -> bool:
        cond = sub.skip_if or {}
        key = cond.get("artifact")
        if not key:
            return False
        value = self.context.get(key, "")
        markers = cond.get("contains") or []
        if isinstance(markers, str):
            markers = [markers]
        return any(m and m in value for m in markers)

    def _write_code_files(self, replies: List[str]) -> List[str]:
        """从对话回复中抽取代码块写入工作区（后出现的版本覆盖先前的）。"""
        written: List[str] = []
        for reply in replies:
            for block in extract_code_blocks(reply):
                if block["lang"] not in ("python", "py", ""):
                    continue
                name = guess_filename(block, default="main.py")
                self.workspace.write_file(name, block["code"])
                if name not in written:
                    written.append(name)
        return written

    def _build_summary(self, project_name: str, task: str) -> Dict[str, Any]:
        files = self.workspace.list_files()
        summary = {
            "project": project_name,
            "task": task,
            "agents": [a for a in self.pool.keys()],
            "subtasks": self.records,
            "files": files,
            "commits": self.workspace.git_log(),
        }
        self.logger.done(
            f"开发完成：{len(self.records)} 个子任务，产出 {len(files)} 个文件，"
            f"{len(summary['commits'])} 次版本提交"
        )
        return summary
