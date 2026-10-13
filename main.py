"""Точка входа в игру «Алиса и Чучмек»: python main.py"""

import os
import sys

MIN_PYTHON = (3, 10)


def main() -> int:
    if sys.version_info < MIN_PYTHON:
        print(
            f"Нужен Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} или новее, "
            f"сейчас запущен {sys.version.split()[0]}.",
            file=sys.stderr,
        )
        return 1

    # Скрываем приветствие Pygame в консоли; переменная должна быть задана до импорта.
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    try:
        import pygame
    except ModuleNotFoundError as exc:
        if exc.name != "pygame":
            raise
        print(
            "Pygame не установлен для интерпретатора\n"
            f"  {sys.executable}\n"
            "Создайте виртуальное окружение и установите зависимости из папки проекта:\n"
            "  python3 -m venv .venv\n"
            "  .venv/bin/pip install -r requirements.txt\n"
            "и запускайте игру так:\n"
            "  .venv/bin/python main.py",
            file=sys.stderr,
        )
        return 1

    from game.app import run

    try:
        run()
    except pygame.error as exc:
        print(
            f"Не удалось запустить игру, ошибка Pygame/SDL: {exc}\n"
            "Игру нужно запускать в графическом сеансе "
            "(должна быть задана переменная DISPLAY или WAYLAND_DISPLAY).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
