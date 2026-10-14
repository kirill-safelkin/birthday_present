"""Проверка клавиш с учётом раскладки клавиатуры."""

from __future__ import annotations

import pygame


def matches_key(event: pygame.event.Event, key: int, scancode: int) -> bool:
    """True, если событие клавиатуры относится к клавише key.

    Сравниваем и код клавиши, и её физическое положение (скан-код): при нелатинской
    раскладке код буквенной клавиши другой (у D в русской раскладке это «в»),
    а скан-код тот же.
    """
    return event.key == key or getattr(event, "scancode", None) == scancode
