# -*- coding: utf-8 -*-
"""M1 配置管理模块：从 config/ 目录加载模型、运行参数、角色库与流程编排配置。

设计目标（对应报告"更好修改"）：
    - 角色、阶段、提示词、模型参数全部由 YAML/JSON 配置驱动；
    - 新增角色或阶段只需改配置文件，不改一行 Python 代码。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .utils import get_env


# --------------------------------------------------------------- 数据结构 ----

@dataclass
class ModelConfig:
    backend: str = "mock"                 # mock | openai | ollama
    name: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    temperature: float = 0.7
    timeout: int = 120
    ollama_host: str = "http://localhost:11434"

    def resolve_credentials(self) -> None:
        """api_key 为空时从环境变量 / .env 补全。"""
        if not self.api_key:
            self.api_key = get_env("OPENAI_API_KEY", "")
        if self.backend == "openai":
            self.base_url = get_env("OPENAI_BASE_URL", self.base_url)
            self.name = get_env("OPENAI_MODEL", self.name)
        if self.backend == "ollama":
            self.ollama_host = get_env("OLLAMA_HOST", self.ollama_host)


@dataclass
class RuntimeConfig:
    max_rounds: int = 2
    memory_limit: int = 12
    warehouse: str = "WareHouse"
    log_name: str = "run.jsonl"
    git: bool = True


@dataclass
class Role:
    key: str
    title: str = ""
    duty: str = ""
    prompt: str = ""

    @property
    def system_prompt(self) -> str:
        return (
            f"# 角色：{self.key}（{self.title}）\n"
            f"职责：{self.duty}\n\n"
            f"{self.prompt.strip()}"
        )


@dataclass
class Subtask:
    name: str
    instructor: str
    assistant: str
    prompt: str = ""
    artifact: str = ""
    extract_code: bool = False
    write: str = ""
    max_rounds: int | None = None
    skip_if: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Phase:
    name: str
    key: str
    subtasks: List[Subtask] = field(default_factory=list)


@dataclass
class Config:
    base_dir: Path
    model: ModelConfig
    runtime: RuntimeConfig
    roles: Dict[str, Role]
    phases: List[Phase]

    # ---------------------------------------------------------- 助手方法 ----
    def role(self, key: str) -> Role:
        """按 key 取角色；不存在时构造一个通用角色，避免运行中断。"""
        if key in self.roles:
            return self.roles[key]
        return Role(key=key, title=key, duty="通用角色", prompt=f"你是软件团队中的 {key}。")

    def describe(self) -> str:
        model_label = "内置离线桩（mock）" if self.model.backend == "mock" \
            else f"{self.model.name} @ {self.model.base_url}"
        lines = [
            f"配置文件目录 : {self.base_dir}",
            f"模型后端     : {self.model.backend}  ->  {model_label}",
            f"对话轮数上限 : {self.runtime.max_rounds}",
            f"角色数量     : {len(self.roles)}  -> {', '.join(self.roles)}",
            f"阶段数量     : {len(self.phases)}",
        ]
        for ph in self.phases:
            names = " -> ".join(s.name for s in ph.subtasks)
            lines.append(f"    - {ph.name}：{names}")
        return "\n".join(lines)


# --------------------------------------------------------------- 加载入口 ----

def _read(path: Path) -> Dict[str, Any]:
    """读取 YAML（优先）或 JSON 配置文件。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "读取 YAML 配置需要 PyYAML，请先执行：pip install -r requirements.txt"
            ) from exc
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _pick(config_dir: Path, stem: str) -> Path | None:
    for ext in (".yaml", ".yml", ".json"):
        p = config_dir / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def load_config(config_dir: str | Path = "config") -> Config:
    """从配置目录加载完整配置。"""
    base = Path(config_dir).resolve()
    if not base.exists():
        raise FileNotFoundError(f"配置目录不存在：{base}")

    raw_model, raw_runtime, raw_roles, raw_phases = {}, {}, {}, {}

    if p := _pick(base, "config"):
        data = _read(p)
        raw_model = data.get("model", {}) or {}
        raw_runtime = data.get("runtime", {}) or {}
    if p := _pick(base, "roles"):
        raw_roles = _read(p).get("roles", {}) or {}
    if p := _pick(base, "phases"):
        raw_phases = _read(p).get("phases", []) or []

    model = ModelConfig(**{k: v for k, v in raw_model.items() if k in ModelConfig.__annotations__})
    model.resolve_credentials()
    runtime = RuntimeConfig(**{k: v for k, v in raw_runtime.items() if k in RuntimeConfig.__annotations__})

    roles = {
        key: Role(
            key=key,
            title=(val or {}).get("title", ""),
            duty=(val or {}).get("duty", ""),
            prompt=(val or {}).get("prompt", ""),
        )
        for key, val in raw_roles.items()
    }

    phases: List[Phase] = []
    for ph in raw_phases:
        subtasks = []
        for st in ph.get("subtasks", []) or []:
            subtasks.append(Subtask(
                name=st.get("name", "子任务"),
                instructor=st.get("instructor", ""),
                assistant=st.get("assistant", ""),
                prompt=st.get("prompt", ""),
                artifact=st.get("artifact", ""),
                extract_code=bool(st.get("extract_code", False)),
                write=st.get("write", ""),
                max_rounds=st.get("max_rounds"),
                skip_if=st.get("skip_if", {}) or {},
            ))
        phases.append(Phase(name=ph.get("name", ""), key=ph.get("key", ""), subtasks=subtasks))

    return Config(base_dir=base, model=model, runtime=runtime, roles=roles, phases=phases)
