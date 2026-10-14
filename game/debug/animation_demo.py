"""Тестовый экран анимации: временный персонаж, которым можно управлять с клавиатуры.

Открывается клавишей A с экрана проверки. Это техническая проверка, а не локация игры.
"""

from __future__ import annotations

import pygame

import config
from game.graphics.animation import TALK, Direction
from game.world.character import Character
from game.graphics.fonts import load_font, render_text
from game.core.input import matches_key

SCREEN_WIDTH, SCREEN_HEIGHT = config.LOGICAL_SIZE
# Пол — шахматка из клеток 16×16: на ней видно движение и размер игрового пикселя.
FLOOR_RECT = pygame.Rect(8, 52, SCREEN_WIDTH - 16, 96)
TILE_SIZE = 16
FLOOR_COLORS: tuple[config.Color, config.Color] = ((34, 38, 58), (40, 45, 68))
FLOOR_BORDER_COLOR: config.Color = (70, 78, 110)
INFO_FONT_SIZE = 9
FONT_SIZE = 10
HINTS_TOP = 153

# Backspace — назад: ESC закрывает всю игру, а буквы заняты ходьбой.
BACK_KEY = pygame.K_BACKSPACE
REACT_KEY = pygame.K_SPACE
HINTS = (
    "Стрелки/WASD — ходьба  Пробел — реакция  T — речь",
    "Backspace — назад  F11 — экран  ESC — выход",
)
DIRECTION_NAMES = {
    Direction.DOWN: "вниз",
    Direction.UP: "вверх",
    Direction.LEFT: "влево",
    Direction.RIGHT: "вправо",
}


def _is_talk_key(event: pygame.event.Event) -> bool:
    return matches_key(event, pygame.K_t, pygame.KSCAN_T)


class AnimationDemo:
    """Пол, временный персонаж, сведения о его состоянии и подсказки по управлению."""

    def __init__(self) -> None:
        self.character = Character("Манекен")
        # Персонаж стоит в центре пола: позиция — точка под ногами.
        self.character.set_position(FLOOR_RECT.centerx, FLOOR_RECT.centery + self.character.rect.height // 2)
        self.is_finished = False  # пора вернуться на экран проверки

        self._info_font = load_font(INFO_FONT_SIZE)
        font = load_font(FONT_SIZE)
        title = render_text(font, "Тест анимации", config.TITLE_COLOR)
        # Статичные надписи рендерятся один раз, в кадре их только копируют на холст.
        self.labels: list[tuple[pygame.Surface, pygame.Rect]] = [
            (title, title.get_rect(topright=(SCREEN_WIDTH - 4, 3))),
        ]
        for index, text in enumerate(HINTS):
            hint = render_text(font, text, config.HINT_COLOR)
            top = HINTS_TOP + index * font.get_linesize()
            self.labels.append((hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, top))))
        self._floor = _render_floor(FLOOR_RECT.size)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == BACK_KEY:
                self.is_finished = True
                return
            if event.key == REACT_KEY:
                self.character.react()
                return
            if _is_talk_key(event):
                if self.character.state == TALK:
                    self.character.stop()
                else:
                    self.character.talk()
                return
        self.character.handle_event(event)

    def update(self, dt: float) -> None:
        self.character.update(dt)
        self._keep_on_floor()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND_COLOR)
        surface.blit(self._floor, FLOOR_RECT)
        self.character.draw(surface)
        line_height = self._info_font.get_linesize()
        for row, text in enumerate(self.info_lines()):
            surface.blit(render_text(self._info_font, text, config.TEXT_COLOR), (4, 3 + row * line_height))
        for image, rect in self.labels:
            surface.blit(image, rect)

    def info_lines(self) -> list[str]:
        """Координаты, направление и состояние анимации персонажа для левого верхнего угла."""
        character = self.character
        x, y = character.pixel_position
        player = character.player
        return [
            f"координаты: {x}, {y}",
            f"направление: {DIRECTION_NAMES[character.direction]}",
            f"состояние: {character.state}",
            f"кадр {player.frame_index + 1}/{len(player.animation.frames)}",
        ]

    def _keep_on_floor(self) -> None:
        """Не даёт персонажу уйти с пола. Это граница тестового экрана, а не система столкновений."""
        rect = self.character.rect
        inside = rect.clamp(FLOOR_RECT)
        if inside != rect:
            self.character.set_position(self.character.x + inside.x - rect.x, self.character.y + inside.y - rect.y)


def _render_floor(size: config.Size) -> pygame.Surface:
    floor = pygame.Surface(size)
    for row in range(0, size[1], TILE_SIZE):
        for column in range(0, size[0], TILE_SIZE):
            color = FLOOR_COLORS[(row // TILE_SIZE + column // TILE_SIZE) % 2]
            floor.fill(color, (column, row, TILE_SIZE, TILE_SIZE))
    pygame.draw.rect(floor, FLOOR_BORDER_COLOR, floor.get_rect(), 1)
    return floor
