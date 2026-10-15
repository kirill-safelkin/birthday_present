"""Отрисовка тарелки и готовых блюд испытания суши: только геометрия Pygame, без логики заказов.

Что считать готовым блюдом, решает SushiOrders (order_complete); здесь известно лишь,
как выглядит тарелка и каждое из трёх блюд. Всё рисуется на логическом холсте 320×180
простыми формами: тарелка 36×10, блюдо целиком помещается над её центром.
"""

from __future__ import annotations

import math

import pygame

# Тарелка: светло-голубая керамика, насыщенный синий контур, чуть более светлый ободок.
PLATE_COLOR = (186, 218, 244)  # поверхность
PLATE_RIM_COLOR = (150, 196, 234)  # плоский край вокруг углубления
PLATE_EDGE_COLOR = (58, 112, 182)  # внешний контур
PLATE_INNER_RIM_COLOR = (226, 242, 255)  # тонкий ободок углубления
PLATE_SHADOW_COLOR = (132, 94, 64)  # тень на столе под тарелкой
FOOD_SHADOW_COLOR = (120, 160, 204)  # тень еды на тарелке
PLATE_SIZE = (36, 10)

RICE_COLOR = (250, 250, 244)
RICE_SHADE_COLOR = (200, 206, 218)
SALMON_COLOR = (246, 128, 88)
SALMON_DARK_COLOR = (206, 84, 56)
SALMON_STREAK_COLOR = (255, 214, 190)
NORI_COLOR = (30, 58, 40)
NORI_LIGHT_COLOR = (62, 98, 68)
CUCUMBER_COLOR = (64, 156, 72)
CUCUMBER_CORE_COLOR = (200, 238, 172)
AVOCADO_COLOR = (92, 148, 44)
AVOCADO_FLESH_COLOR = (206, 224, 112)
SPARK_COLOR = (255, 226, 120)
SPARK_CORE_COLOR = (255, 252, 226)

# Сколько длится золотистая вспышка над готовым блюдом (в секундах).
FINISH_EFFECT_SECONDS = 0.35

NIGIRI = "nigiri_salmon"
MAKI = "maki_cucumber"
ROLL = "roll_salmon_avocado"


def plate_rect(table: pygame.Rect) -> pygame.Rect:
    """Где лежит тарелка: по центру стола, чуть выше середины."""
    rect = pygame.Rect((0, 0), PLATE_SIZE)
    rect.center = (table.centerx, table.centery - 1)
    return rect


def draw_plate(surface: pygame.Surface, plate: pygame.Rect) -> None:
    """Керамическая тарелка сверху: тень, край с контуром, светлый ободок и углубление.

    Порядок важен: сначала всё залитое, потом контур и ободок — они остаются видны."""
    pygame.draw.ellipse(surface, PLATE_SHADOW_COLOR, plate.move(0, 2))
    pygame.draw.ellipse(surface, PLATE_RIM_COLOR, plate)
    well = plate.inflate(-6, -4)
    pygame.draw.ellipse(surface, PLATE_COLOR, well)
    pygame.draw.ellipse(surface, PLATE_INNER_RIM_COLOR, well, 1)
    pygame.draw.ellipse(surface, PLATE_EDGE_COLOR, plate, 1)


def draw_food_shadow(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Мягкая тень под едой, чтобы белое и светлое не сливалось с голубой тарелкой."""
    pygame.draw.ellipse(surface, FOOD_SHADOW_COLOR, rect)


def _draw_nigiri(surface: pygame.Surface, x: int, y: int) -> None:
    """Подушечка риса и ломтик лосося сверху с тонкими светлыми прожилками."""
    draw_food_shadow(surface, pygame.Rect(x - 11, y - 1, 22, 6))
    rice = pygame.Rect(x - 8, y - 2, 16, 7)
    pygame.draw.ellipse(surface, RICE_SHADE_COLOR, rice)
    pygame.draw.ellipse(surface, RICE_COLOR, rice.inflate(-2, -2).move(0, -1))
    salmon = pygame.Rect(x - 10, y - 6, 20, 6)
    pygame.draw.rect(surface, SALMON_DARK_COLOR, salmon.move(0, 1), border_radius=3)
    pygame.draw.rect(surface, SALMON_COLOR, salmon, border_radius=3)
    for dx in (-5, 0, 5):
        pygame.draw.line(surface, SALMON_STREAK_COLOR, (x + dx - 1, salmon.bottom - 2), (x + dx + 1, salmon.top + 1))


def _draw_maki_slice(surface: pygame.Surface, x: int, y: int, filling: tuple[tuple[int, int, int], ...]) -> None:
    """Разрезанный ролл: нори снаружи, рис, в центре начинка (один или два цвета)."""
    pygame.draw.circle(surface, NORI_COLOR, (x, y), 5)
    pygame.draw.circle(surface, NORI_LIGHT_COLOR, (x, y), 5, 1)
    pygame.draw.circle(surface, RICE_COLOR, (x, y), 4)
    for index, color in enumerate(filling):
        if len(filling) == 1:
            pygame.draw.circle(surface, color, (x, y), 2)
        else:
            surface.fill(color, (x - 2 + index * 2, y - 2, 2, 4))


def _draw_maki(surface: pygame.Surface, x: int, y: int) -> None:
    """Три ломтика маки с огурцом: два спереди, один сзади — видно поперечное сечение."""
    draw_food_shadow(surface, pygame.Rect(x - 14, y - 2, 28, 7))
    for dx, dy in ((0, -3), (-7, 0), (7, 0)):
        _draw_maki_slice(surface, x + dx, y + dy, (CUCUMBER_COLOR,))
        pygame.draw.circle(surface, CUCUMBER_CORE_COLOR, (x + dx, y + dy), 1)


def _draw_roll(surface: pygame.Surface, x: int, y: int) -> None:
    """Три ломтика ролла: в центре лосось (оранжевый блок) и авокадо (зелёный полумесяц)."""
    draw_food_shadow(surface, pygame.Rect(x - 14, y - 2, 28, 7))
    for dx, dy in ((0, -3), (-7, 0), (7, 0)):
        cx, cy = x + dx, y + dy
        pygame.draw.circle(surface, NORI_COLOR, (cx, cy), 5)
        pygame.draw.circle(surface, NORI_LIGHT_COLOR, (cx, cy), 5, 1)
        pygame.draw.circle(surface, RICE_COLOR, (cx, cy), 4)
        pygame.draw.rect(surface, SALMON_COLOR, (cx - 2, cy - 2, 3, 4))
        pygame.draw.circle(surface, AVOCADO_COLOR, (cx + 1, cy), 2)
        surface.set_at((cx + 1, cy), AVOCADO_FLESH_COLOR)


DISH_DRAWERS = {NIGIRI: _draw_nigiri, MAKI: _draw_maki, ROLL: _draw_roll}


def draw_dish(surface: pygame.Surface, recipe_id: str, center: tuple[int, int]) -> None:
    """Готовое блюдо заказа recipe_id над центром тарелки (center — центр тарелки)."""
    DISH_DRAWERS[recipe_id](surface, center[0], center[1] - 1)


def draw_sparks(surface: pygame.Surface, center: tuple[int, int], progress: float) -> None:
    """Золотистая вспышка над блюдом; progress от 0 (началась) до 1 (погасла)."""
    if not 0 <= progress < 1:
        return
    size = round(math.sin(progress * math.pi) * 3)
    if size < 1:
        return
    for dx, dy in ((-9, -7), (0, -10), (9, -7)):
        x, y = center[0] + dx, center[1] + dy
        pygame.draw.line(surface, SPARK_COLOR, (x - size, y), (x + size, y))
        pygame.draw.line(surface, SPARK_COLOR, (x, y - size), (x, y + size))
        surface.set_at((x, y), SPARK_CORE_COLOR)
