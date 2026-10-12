"""Превращение HTML в PDF через WeasyPrint без сетевых запросов."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from .errors import RenderError, RendererUnavailableError

log = logging.getLogger(__name__)
_weasyprint = None


def _prepare_library_path() -> None:
    """Python с python.org не видит библиотеки Homebrew — подсказываем путь."""
    if sys.platform != "darwin":
        return
    extra = [p for p in ("/opt/homebrew/lib", "/usr/local/lib") if os.path.isdir(p)]
    current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = [p for p in current.split(":") if p]
    for p in extra:
        if p not in parts:
            parts.append(p)
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


def load_weasyprint():
    global _weasyprint
    if _weasyprint is None:
        _prepare_library_path()
        try:
            import weasyprint  # noqa: PLC0415 — тяжёлый импорт откладываем
        except (ImportError, OSError) as exc:
            raise RendererUnavailableError(
                "Не удалось запустить WeasyPrint. Установите системные библиотеки командой "
                "«brew install pango» и перезапустите приложение."
            ) from exc
        _weasyprint = weasyprint
    return _weasyprint


def is_available() -> bool:
    try:
        load_weasyprint()
        return True
    except RendererUnavailableError:
        return False


class BlockedResourceError(Exception):
    pass


def is_allowed_url(url: str, allowed_dirs: list[Path]) -> bool:
    """Разрешены только data: и локальные файлы внутри папки шаблона."""
    parsed = urlparse(url)
    if parsed.scheme == "data":
        return True
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path)).resolve()
        allowed = [Path(d).resolve() for d in allowed_dirs]
        return path.is_file() and any(d in path.parents for d in allowed)
    return False


def make_url_fetcher(allowed_dirs: list[Path]):
    weasyprint = load_weasyprint()

    def blocked(url: str):
        log.warning("Заблокирован внешний ресурс со схемой %s", urlparse(url).scheme or "?")
        raise BlockedResourceError("Внешние ресурсы запрещены")

    if hasattr(weasyprint, "URLFetcher"):  # WeasyPrint 68+
        class LocalOnlyFetcher(weasyprint.URLFetcher):
            def fetch(self, url, headers=None):
                if not is_allowed_url(url, allowed_dirs):
                    blocked(url)
                return super().fetch(url, headers)

        return LocalOnlyFetcher(allowed_protocols={"file", "data"}, allow_redirects=False)

    def fetcher(url: str, *args, **kwargs):  # pragma: no cover — старые версии
        if not is_allowed_url(url, allowed_dirs):
            blocked(url)
        return weasyprint.default_url_fetcher(url, *args, **kwargs)

    return fetcher


def render_pdf(html: str, base_dir: Path, target: str | Path | BinaryIO) -> None:
    weasyprint = load_weasyprint()
    base_dir = Path(base_dir).resolve()
    try:
        document = weasyprint.HTML(
            string=html,
            base_url=base_dir.as_uri() + "/",
            url_fetcher=make_url_fetcher([base_dir]),
        )
        document.write_pdf(target)
    except RendererUnavailableError:
        raise
    except Exception as exc:  # WeasyPrint бросает разнообразные исключения
        log.error("Ошибка WeasyPrint: %s", type(exc).__name__)
        raise RenderError("Не удалось создать PDF. Проверьте разметку шаблона.") from exc
