"""Независимое ядро DocFlow: данные, шаблоны, расчёты, PDF, история.

Модуль не импортирует Qt и пригоден для CLI, GUI и будущих интеграций.
"""

from .engine import DocFlowEngine
from .errors import DocFlowError

__all__ = ["DocFlowEngine", "DocFlowError"]
