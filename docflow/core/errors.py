"""Исключения ядра DocFlow.

Все сообщения пишутся по-русски и предназначены для показа пользователю.
Они никогда не содержат значения полей записей — только имена файлов,
названия полей и номера строк.
"""


class DocFlowError(Exception):
    """Базовая ошибка, текст которой можно показать пользователю."""


class DataLoadError(DocFlowError):
    """Файл данных не удалось прочитать или разобрать."""


class TemplateError(DocFlowError):
    """Шаблон отсутствует, повреждён или содержит неверный синтаксис."""


class ValidationError(DocFlowError):
    """Запись не прошла проверку обязательных полей или чисел."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


class RenderError(DocFlowError):
    """WeasyPrint не смог создать PDF."""


class RendererUnavailableError(RenderError):
    """Не установлены системные библиотеки WeasyPrint (Pango)."""
