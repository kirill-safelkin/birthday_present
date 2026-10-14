"""Простые столкновения: границы площадки и прямоугольные препятствия.

Сталкиваются «ноги» персонажа — небольшой прямоугольник у точки под ногами (x, y),
а не весь кадр: так персонаж может зайти головой «за» дерево, но не пройти сквозь ствол.
Движение считается отдельно по x и по y, поэтому у стены персонаж скользит вдоль неё,
а не застревает при ходьбе по диагонали. Проверка учитывает весь путь за шаг (заметание),
а не только конечную точку, поэтому большой dt не «протаскивает» сквозь тонкие препятствия.
"""

from __future__ import annotations

from collections.abc import Iterable

import pygame

FOOT_SIZE = (12, 6)  # ширина и высота «ног» в логических пикселях
_EPSILON = 1e-6


class CollisionMap:
    """Границы, в которых должны оставаться ноги персонажа, и препятствия внутри них."""

    def __init__(
        self,
        bounds: pygame.Rect | tuple[int, int, int, int],
        obstacles: Iterable[pygame.Rect | tuple[int, int, int, int]] = (),
        foot_size: tuple[int, int] = FOOT_SIZE,
    ) -> None:
        self.bounds = pygame.Rect(bounds)
        self.obstacles = [pygame.Rect(obstacle) for obstacle in obstacles]
        self.half_width = foot_size[0] / 2
        self.foot_height = foot_size[1]

    def foot_box(self, x: float, y: float) -> tuple[float, float, float, float]:
        """Ноги персонажа в точке (x, y): (лево, верх, право, низ)."""
        return x - self.half_width, y - self.foot_height, x + self.half_width, y

    def is_free(self, x: float, y: float) -> bool:
        """Можно ли стоять в точке (x, y): ноги внутри границ и не задевают препятствия."""
        left, top, right, bottom = self.foot_box(x, y)
        bounds = self.bounds
        if left < bounds.left - _EPSILON or right > bounds.right + _EPSILON:
            return False
        if top < bounds.top - _EPSILON or bottom > bounds.bottom + _EPSILON:
            return False
        return not any(
            obstacle.left < right - _EPSILON
            and obstacle.right > left + _EPSILON
            and obstacle.top < bottom - _EPSILON
            and obstacle.bottom > top + _EPSILON
            for obstacle in self.obstacles
        )

    def move(self, x: float, y: float, dx: float, dy: float) -> tuple[float, float]:
        """Новая позиция после попытки сдвинуться на (dx, dy): упирается в препятствия и границы."""
        x = self._move_x(x, y, dx)
        y = self._move_y(x, y, dy)
        return x, y

    def _move_x(self, x: float, y: float, dx: float) -> float:
        if dx == 0:
            return x
        top, bottom = y - self.foot_height, y
        target = x + dx
        for obstacle in self.obstacles:
            if not (obstacle.top < bottom - _EPSILON and obstacle.bottom > top + _EPSILON):
                continue  # препятствие выше или ниже ног
            if dx > 0 and obstacle.left >= x + self.half_width - _EPSILON:
                target = min(target, obstacle.left - self.half_width)
            elif dx < 0 and obstacle.right <= x - self.half_width + _EPSILON:
                target = max(target, obstacle.right + self.half_width)
        return min(max(target, self.bounds.left + self.half_width), self.bounds.right - self.half_width)

    def _move_y(self, x: float, y: float, dy: float) -> float:
        if dy == 0:
            return y
        left, right = x - self.half_width, x + self.half_width
        target = y + dy
        for obstacle in self.obstacles:
            if not (obstacle.left < right - _EPSILON and obstacle.right > left + _EPSILON):
                continue  # препятствие левее или правее ног
            if dy > 0 and obstacle.top >= y - _EPSILON:
                target = min(target, obstacle.top)
            elif dy < 0 and obstacle.bottom <= y - self.foot_height + _EPSILON:
                target = max(target, obstacle.bottom + self.foot_height)
        return min(max(target, self.bounds.top + self.foot_height), self.bounds.bottom)
