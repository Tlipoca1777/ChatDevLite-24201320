#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ChatDevLite-24201320 命令行入口。

用法示例：
    python main.py                                  # 用默认需求跑一遍（离线 mock 后端）
    python main.py -t "做一个命令行待办事项应用" -n TodoApp
    python main.py -t "做一个计算器" --backend openai --model deepseek-flash --base-url https://api.deepseek.com
    python main.py -t "做一个猜数字游戏" --backend ollama --model qwen2.5:7b
    python main.py --show-config                    # 只看配置，不运行
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from chatdevlite.config import load_config           # noqa: E402
from chatdevlite.llm import LLMError, create_llm     # noqa: E402
from chatdevlite.logger import RunLogger             # noqa: E402
from chatdevlite.orchestration import ChatChain      # noqa: E402
from chatdevlite.utils import text_table             # noqa: E402
from chatdevlite.workspace import Workspace          # noqa: E402

BANNER = r"""
  ____ _           _   ____              _     _ _
 / ___| |__   __ _| |_|  _ \  _____   __| |   (_) |_ ___
| |   | '_ \ / _` | __| | | |/ _ \ \ / /| |   | | __/ _ \
| |___| | | | (_| | |_| |_| |  __/\ V / | |___| | ||  __/
 \____|_| |_|\__,_|\__|____/ \___| \_/  |_____|_|\__\___|
        ChatDevLite-24201320 · 最小可用的多智能体软件开发框架
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chatdevlite",
        description="ChatDevLite：一句话需求 -> 多智能体协作 -> 可运行软件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-t", "--task", default="做一个命令行待办事项应用",
                   help="用一句自然语言描述软件需求")
    p.add_argument("-n", "--name", default="ChatDevLite-Demo",
                   help="生成软件的名称（工作区目录名）")
    p.add_argument("-c", "--config", default=str(ROOT / "config"),
                   help="配置目录（默认 ./config）")
    p.add_argument("-b", "--backend", choices=["mock", "openai", "ollama"],
                   help="覆盖配置中的模型后端")
    p.add_argument("-m", "--model", help="覆盖模型名称")
    p.add_argument("--base-url", help="覆盖 OpenAI 兼容接口地址")
    p.add_argument("--timeout", type=int, help="覆盖单次模型调用的超时秒数（默认 120）")
    p.add_argument("--rounds", type=int, help="覆盖每个子任务的最大对话轮数")
    p.add_argument("--no-git", action="store_true", help="关闭 Git 版本管理")
    p.add_argument("--quiet", action="store_true", help="只输出最终结果")
    p.add_argument("--show-config", action="store_true", help="打印配置后退出")
    return p


def print_summary(summary: dict, logger: RunLogger, root: Path) -> None:
    print("\n" + "=" * 64)
    print(" 运行汇总")
    print("=" * 64)
    rows = [
        (str(i + 1), r["name"], r["instructor"] + " ↔ " + r["assistant"],
         str(r.get("rounds", "-")), "跳过" if r["status"] == "skipped" else "完成")
        for i, r in enumerate(summary["subtasks"])
    ]
    print(text_table(rows, ("#", "子任务", "对话角色", "轮数", "状态")))

    print("\n工作区文件：")
    for f in summary["files"]:
        print(f"  - {f}")

    if summary["commits"]:
        print("\nGit 版本记录（最新在前）：")
        for line in summary["commits"]:
            print(f"  * {line}")

    print(f"\n工作区目录：{root}")
    print(f"运行日志   ：{logger.logfile}")
    print(f"参与智能体 ：{', '.join(summary['agents'])}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[错误] 加载配置失败：{exc}", file=sys.stderr)
        return 2

    # 命令行覆盖配置
    if args.backend:
        cfg.model.backend = args.backend
        cfg.model.resolve_credentials()
    if args.model:
        cfg.model.name = args.model
    if args.base_url:
        cfg.model.base_url = args.base_url
    if args.timeout:
        cfg.model.timeout = max(10, args.timeout)
    if args.rounds:
        cfg.runtime.max_rounds = max(1, args.rounds)
    if args.no_git:
        cfg.runtime.git = False

    print(BANNER)
    if args.show_config:
        print(cfg.describe())
        return 0

    ws_root = ROOT / cfg.runtime.warehouse / args.name
    logger = RunLogger(ws_root / "logs" / cfg.runtime.log_name, echo=not args.quiet)
    workspace = Workspace(ws_root, git=cfg.runtime.git, logger=logger)

    try:
        llm = create_llm(cfg.model)
    except LLMError as exc:
        logger.warn(str(exc))
        return 3

    logger.run(f"模型后端：{llm.name}")
    model_label = "内置离线桩（mock）" if cfg.model.backend == "mock" else cfg.model.name
    print(f"[配置] 后端={cfg.model.backend}  模型={model_label}  "
          f"轮数={cfg.runtime.max_rounds}  超时={cfg.model.timeout}s  "
          f"Git={'开' if cfg.runtime.git else '关'}")
    if llm.endpoint:
        # 打出来便于核对 base_url 填得对不对
        print(f"[配置] 接口={llm.endpoint}")
        logger.run(f"接口地址：{llm.endpoint}")
    print("-" * 64)

    chain = ChatChain(cfg, llm, workspace, logger)
    try:
        summary = chain.run(args.task, args.name)
    except LLMError as exc:
        logger.warn(f"调用模型失败：{exc}")
        return 4
    except KeyboardInterrupt:
        logger.warn("已被用户中断")
        return 130

    print_summary(summary, logger, ws_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
