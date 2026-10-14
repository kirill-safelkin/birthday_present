"""Вторая часть испытания тортов: кладовая-лабиринт, где прячется сбежавшая клубника.

Только раскладка — стены, старт, клубника и маршрут — без отрисовки и без случайностей:
кладовая всегда одна и та же. Четыре стеллажа стоят «змейкой» (проход то снизу, то
сверху), поэтому путь к клубнике — несколько поворотов. Ширина каждого прохода с запасом
больше «ног» Алисы (FOOT_SIZE), а MAZE_ROUTE — маршрут, по которому лабиринт гарантированно
проходится; его используют тесты и проверка в окне.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from game.world.collision import FOOT_SIZE, CollisionMap

# Где могут стоять ноги Алисы. Сверху — задняя стена кладовой, снизу — полоса подсказок,
# слева — дверь из кондитерской, в которой стоит Чучмек.
MAZE_BOUNDS = pygame.Rect(40, 50, 270, 114)


@dataclass(frozen=True)
class MazeWall:
    kind: str  # что нарисовать: "jars", "sacks", "trays" или "boxes"
    rect: pygame.Rect  # основание стеллажа — им же проверяются столкновения


# Проходы между стеллажами — 36 px в ширину и 30 px под или над стеллажом при «ногах» 12×6.
MAZE_WALLS = (
    MazeWall("jars", pygame.Rect(76, MAZE_BOUNDS.top, 22, 84)),  # проход снизу
    MazeWall("sacks", pygame.Rect(134, 80, 22, MAZE_BOUNDS.bottom - 80)),  # проход сверху
    MazeWall("trays", pygame.Rect(192, MAZE_BOUNDS.top, 22, 84)),  # проход снизу
    MazeWall("boxes", pygame.Rect(250, 80, 22, MAZE_BOUNDS.bottom - 80)),  # проход сверху
)
MAZE_START = (58, 66)  # у двери из кондитерской
STRAWBERRY_POSITION = (292, 104)  # в дальнем углу, выше окна реплик
STRAWBERRY_REACH = 16  # поймать можно только из последнего закутка
STRAWBERRY_OBSTACLE = pygame.Rect(287, 100, 10, 4)  # на клубнику нельзя наступить
# Предусмотренный маршрут от старта до клубники: вниз, под первым стеллажом, вверх, над
# вторым, вниз, под третьим, вверх, над четвёртым — и к клубнике.
MAZE_ROUTE = (
    MAZE_START,
    (58, 152),
    (116, 152),
    (116, 66),
    (174, 66),
    (174, 152),
    (232, 152),
    (232, 66),
    (290, 66),
    (290, 90),
)


def maze_collision(foot_size: tuple[int, int] = FOOT_SIZE) -> CollisionMap:
    """Столкновения кладовой. foot_size крупнее настоящего — чтобы проверить запас в проходах."""
    return CollisionMap(MAZE_BOUNDS, [wall.rect for wall in MAZE_WALLS] + [STRAWBERRY_OBSTACLE], foot_size)


def strawberry_in_reach(x: float, y: float) -> bool:
    """Стоит ли Алиса (точка под ногами) достаточно близко, чтобы поймать клубнику."""
    return math.dist((x, y), STRAWBERRY_POSITION) <= STRAWBERRY_REACH
