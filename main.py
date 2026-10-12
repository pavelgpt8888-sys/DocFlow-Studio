"""DocFlow Studio — точка входа.

    python3 main.py          графический интерфейс
    python3 main.py --cli    консольное меню
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="docflow", description="DocFlow Studio — генерация PDF-документов из HTML-шаблонов.")
    parser.add_argument("--cli", action="store_true", help="запустить консольный режим")
    parser.add_argument("--template", help="шаблон: id, имя файла или путь (без меню)")
    parser.add_argument("--data", help="CSV или JSON с данными (без меню)")
    parser.add_argument("--record", help="номера записей: 1 или 1,3,5-7")
    parser.add_argument("--all", action="store_true", help="создать PDF для всех записей")
    parser.add_argument("--output", help="папка для результатов (по умолчанию output/)")
    parser.add_argument("--no-open", action="store_true", help="не открывать готовый PDF")
    parser.add_argument("--debug", action="store_true", help="подробный журнал без данных записей")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.cli or args.template or args.data:
        from docflow.cli import main as cli_main
        return cli_main(args, PROJECT_ROOT)
    try:
        from docflow.ui.app import run
    except ImportError:
        print("Не установлен PySide6. Выполните: pip install -r requirements.txt\n"
              "Консольный режим доступен без него: python3 main.py --cli", file=sys.stderr)
        return 1
    return run(PROJECT_ROOT)


if __name__ == "__main__":
    sys.exit(main())
