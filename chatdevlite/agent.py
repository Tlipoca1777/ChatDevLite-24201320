# -*- coding: utf-8 -*-
"""M2 智能体模块：Agent 基类 + 记忆流（Memory Stream）。

一个 Agent = 角色定义（系统提示）+ 大模型客户端 + 对话记忆。
"""
from __future__ import annotations

from typing import Dict, List

from .config import Role
from .llm import BaseLLM
from .logger import RunLogger

Message = Dict[str, str]


class Agent:
    """被独立实例化的"虚拟员工"。"""

    def __init__(self, role: Role, llm: BaseLLM, logger: RunLogger | None = None,
                 memory_limit: int = 12):
        self.role = role
        self.llm = llm
        self.logger = logger
        self.memory_limit = max(2, memory_limit)
        # 记忆流：按时间累积的 (user, assistant) 对话
        self.memory: List[Message] = []

    # ------------------------------------------------------------ 属性 ----
    @property
    def name(self) -> str:
        return self.role.key

    @property
    def system_prompt(self) -> str:
        return self.role.system_prompt

    # ------------------------------------------------------------ 行为 ----
    def step(self, message: str) -> str:
        """接收一条（来自指导者/用户的）消息，返回本角色的回复。"""
        self.memory.append({"role": "user", "content": message})
        payload: List[Message] = [{"role": "system", "content": self.system_prompt}]
        payload.extend(self._window())
        reply = self.llm.chat(payload)
        self.memory.append({"role": "assistant", "content": reply})
        if self.logger:
            self.logger.agent(self.name, f"{self.name} 作答（{len(reply)} 字）")
        return reply

    def _window(self) -> List[Message]:
        """记忆流滑动窗口，防止上下文无限增长。"""
        return self.memory[-self.memory_limit:]

    def reset(self) -> None:
        """清空记忆（每个子任务开始时重置，避免历史串味）。"""
        self.memory.clear()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Agent {self.name} rounds={len(self.memory) // 2}>"


class AgentPool:
    """角色库运行时：按角色 key 惰性创建并复用 Agent 实例。"""

    def __init__(self, config, llm: BaseLLM, logger: RunLogger | None = None):
        self.config = config
        self.llm = llm
        self.logger = logger
        self._pool: Dict[str, Agent] = {}

    def get(self, key: str) -> Agent:
        if key not in self._pool:
            role = self.config.role(key)
            self._pool[key] = Agent(
                role=role, llm=self.llm, logger=self.logger,
                memory_limit=self.config.runtime.memory_limit,
            )
        return self._pool[key]

    def keys(self) -> List[str]:
        return list(self._pool)
