"""Загрузка шрифта с поддержкой кириллицы."""

from __future__ import annotations

import pygame

import config


def find_font_path() -> str | None:
    """Возвращает путь к первому установленному шрифту из config.FONT_CANDIDATES.

    None означает встроенный шрифт Pygame (freesansbold.ttf): кириллица в нём
    есть, но он не моноширинный.
    """
    for name in config.FONT_CANDIDATES:
        path = pygame.font.match_font(name)
        if path:
            return path
    return None


def load_font(size: int) -> pygame.font.Font:
    """Загружает шрифт нужного размера в пикселях логического разрешения."""
    return pygame.font.Font(find_font_path(), size)


def render_text(font: pygame.font.Font, text: str, color: config.Color) -> pygame.Surface:
    """Рисует строку без сглаживания: у пиксельного текста не должно быть полупрозрачных краёв."""
    return font.render(text, False, color)
