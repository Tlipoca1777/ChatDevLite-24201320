# -*- coding: utf-8 -*-
"""ChatDevLite —— 最小可用的多智能体软件开发框架。

模块划分（对应实验报告中的 M1~M6）：
    config        配置管理模块      （M1）
    agent         智能体模块        （M2）
    orchestration 协作编排模块      （M3）
    workspace     代码工作区/版本管理（M4）
    llm           大模型接入（质量保障阶段的评审/测试依赖它）
    logger        日志与交互        （M6）
"""

__version__ = "0.1.0"
__all__ = ["config", "llm", "agent", "orchestration", "workspace", "logger", "utils"]
