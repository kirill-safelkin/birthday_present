"""Временный персонаж-манекен, нарисованный программно.

Используется, пока у персонажа нет своих кадров: игра запускается и без PNG.
Направление взгляда видно по голове: два глаза — вниз, затылок — вверх,
профиль с одним глазом — влево и вправо. Это не графика игры.
"""

from __future__ import annotations

import pygame

import config
from game.graphics.animation import IDLE, REACT, TALK, WALK, Animation, AnimationSet, Direction

FRAME_SIZE: config.Size = (16, 26)

OUTLINE_COLOR: config.Color = (30, 28, 46)
SKIN_COLOR: config.Color = (232, 196, 158)
HAIR_COLOR: config.Color = (96, 66, 52)
PANTS_COLOR: config.Color = (128, 98, 74)  # светлее пола, чтобы ноги не сливались с ним
MOUTH_COLOR: config.Color = (150, 58, 70)
MARK_COLOR: config.Color = (255, 224, 150)
DEFAULT_SHIRT_COLOR: config.Color = (84, 140, 196)

IDLE_FPS = 2
WALK_FPS = 8
TALK_FPS = 6
REACT_FPS = 10

# Ожидание: две трети времени персонаж стоит ровно, треть — «выдыхает» (голова и туловище ниже на пиксель).
IDLE_POSES = ({}, {}, {"upper_shift": 1})
# Ходьба: ноги поднимаются по очереди, а когда обе на земле, туловище опускается на пиксель.
WALK_POSES = ({"lifted_leg": "left"}, {"upper_shift": 1}, {"lifted_leg": "right"}, {"upper_shift": 1})
TALK_POSES = ({"mouth_open": True}, {})
# Реакция: подпрыгивает с восклицательным знаком и приземляется; играет один раз.
REACT_POSES = (
    {},
    {"jump": 2, "mark": True},
    {"jump": 3, "mark": True},
    {"jump": 2, "mark": True},
    {"mark": True},
    {"mark": True},
)
# Состояние, позы его кадров, скорость и цикличность.
STATES = (
    (IDLE, IDLE_POSES, IDLE_FPS, True),
    (WALK, WALK_POSES, WALK_FPS, True),
    (TALK, TALK_POSES, TALK_FPS, True),
    (REACT, REACT_POSES, REACT_FPS, False),
)


def placeholder_animations(shirt_color: config.Color = DEFAULT_SHIRT_COLOR) -> AnimationSet:
    """Анимации idle, walk, talk и react во всех четырёх направлениях."""
    built: dict[tuple[str, Direction], Animation] = {}
    # Вправо — зеркальное отражение влево, поэтому рисуются только три направления.
    for direction in (Direction.DOWN, Direction.UP, Direction.LEFT):
        for state, poses, fps, loop in STATES:
            frames = [_draw_figure(direction, shirt_color, **pose) for pose in poses]
            built[state, direction] = Animation(frames, fps, loop)
            if direction is Direction.LEFT:
                built[state, Direction.RIGHT] = built[state, direction].flipped()

    # Резерв на самый крайний случай — стоящий персонаж лицом к игроку.
    animations = AnimationSet(default=built[IDLE, Direction.DOWN])
    for (state, direction), animation in built.items():
        animations.add(state, animation, direction)
    return animations


def _draw_figure(
    direction: Direction,
    shirt_color: config.Color,
    *,
    lifted_leg: str | None = None,
    upper_shift: int = 0,
    jump: int = 0,
    mouth_open: bool = False,
    mark: bool = False,
) -> pygame.Surface:
    """Один кадр манекена 16×26. upper_shift опускает голову и туловище, jump поднимает всю фигуру."""
    surface = pygame.Surface(FRAME_SIZE, pygame.SRCALPHA)
    ground = -jump
    for leg_x, side in ((5, "left"), (9, "right")):
        # Поднятая нога короче: снизу под ней видна пустота.
        length = 5 if lifted_leg == side else 7
        pygame.draw.rect(surface, PANTS_COLOR, (leg_x, 19 + ground, 2, length))

    top = 4 + upper_shift + ground
    # Туловище заходит под голову на один ряд, чтобы контуры не сливались в двойную линию.
    _draw_outlined(surface, shirt_color, pygame.Rect(4, top + 7, 8, 8))
    _draw_outlined(surface, SKIN_COLOR, pygame.Rect(4, top, 8, 8))
    _draw_face(surface, direction, top, mouth_open)

    if mark:
        pygame.draw.line(surface, MARK_COLOR, (14, 1), (14, 3))
        surface.set_at((14, 5), MARK_COLOR)
    return surface


def _draw_outlined(surface: pygame.Surface, color: config.Color, rect: pygame.Rect) -> None:
    pygame.draw.rect(surface, OUTLINE_COLOR, rect)
    pygame.draw.rect(surface, color, rect.inflate(-2, -2))


def _draw_face(surface: pygame.Surface, direction: Direction, top: int, mouth_open: bool) -> None:
    """Волосы, глаза и рот внутри головы 8×8 с верхним краем top."""
    pygame.draw.line(surface, HAIR_COLOR, (5, top + 1), (10, top + 1))
    if direction is Direction.UP:
        # Вид со спины: затылок целиком.
        pygame.draw.rect(surface, HAIR_COLOR, (5, top + 1, 6, 6))
    elif direction is Direction.DOWN:
        surface.set_at((6, top + 4), OUTLINE_COLOR)
        surface.set_at((9, top + 4), OUTLINE_COLOR)
        if mouth_open:
            pygame.draw.line(surface, MOUTH_COLOR, (7, top + 6), (8, top + 6))
    else:
        # Профиль влево; вправо получается отражением кадра.
        pygame.draw.rect(surface, HAIR_COLOR, (8, top + 1, 3, 4))
        surface.set_at((6, top + 4), OUTLINE_COLOR)
        if mouth_open:
            surface.set_at((5, top + 6), MOUTH_COLOR)
