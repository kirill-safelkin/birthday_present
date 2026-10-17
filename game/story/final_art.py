"""Оформление праздничного финала: вечерняя поляна, стол с тортом и суши, фонарики, шарики.

Только рисование, никакой логики сцены (её ведёт game/story/final_scene.py). Всё собирается
программно один раз (finale_art) и дальше только выводится:
- небо и поляна — картинки холста 320×180 (пиксельное окружение, как в других сценах);
- стол, торт, шарики, фонарики и свечение — Piece (game/graphics/pixel_art.py): вдвое подробнее
  холста, выводятся слоем высокого разрешения как обычные кадры;
- суши на тарелках — те же функции, что рисуют готовые блюда испытания суши
  (game/trials/sushi_dishes.py), поэтому они выглядят так же, как в игре;
- фрагменты — плитки мозаики с площади (game/world/hub_scenery.py): те самые, что игрок собрал.

Подарка здесь нет: только убранство праздника. Случайность — random.Random с зерном, поэтому
поляна выглядит одинаково при каждом запуске.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache

import pygame

import config
from game.graphics.pixel_art import Art, Piece, glow_sprite, mix, palette_from, spline
from game.trials import sushi_dishes
from game.world import hub_scenery

WIDTH, HEIGHT = config.LOGICAL_SIZE
HORIZON = 98  # где небо заканчивается, а поляна начинается
RUG_CENTER = (160, 104)
RUG_RADII = (108, 14)

# Стол: верхняя плоскость — трапеция (дальний край уже), скатерть свисает спереди.
TABLE_BACK = (104, 75, 216)  # y и края дальней кромки
TABLE_FRONT = (88, 90, 232)  # y и края передней кромки
TABLE_BOTTOM = 101  # низ скатерти
TABLE_RECT = pygame.Rect(84, 58, 152, 52)
CAKE_CENTER_X = 160
CAKE_BASE_Y = 88  # низ подставки торта на столе
# Где на столе стоят блюда: центр тарелки (суши), (слева, справа).
PLATE_CENTERS = ((122, 84), (198, 84))
PLATE_DISHES = (sushi_dishes.ROLL, sushi_dishes.NIGIRI)
# Центр над тортом, где собираются три фрагмента, и их места вокруг него.
EMBLEM_CENTER = (160, 36)
EMBLEM_SPOTS = {"sushi": (143, 38), "forms": (160, 27), "cakes": (177, 38)}

# Палитра вечера.
SKY_STOPS = (
    (0, (20, 16, 54)), (30, (42, 28, 88)), (58, (86, 48, 126)), (78, (160, 78, 138)),
    (90, (232, 128, 130)), (HORIZON + 2, (252, 184, 132)),
)
STAR_COLORS = ((255, 248, 224), (214, 226, 255), (255, 214, 232))
CLOTH = (252, 244, 226)
CLOTH_SHADE = (228, 212, 196)
CLOTH_DARK = (196, 176, 172)
ROSE = (240, 118, 158)
ROSE_DARK = (196, 74, 118)
GOLD = (236, 190, 92)
GOLD_DARK = (176, 128, 52)
GRASS = ((84, 136, 104), (66, 112, 92), (50, 90, 80), (38, 68, 66))
FOLIAGE = ((22, 40, 58), (30, 58, 74), (42, 84, 90), (74, 128, 112))
WARM_LIGHT = (255, 214, 140)
FLOWER_COLORS = ((248, 130, 170), (255, 220, 110), (255, 250, 238), (150, 200, 250), (210, 160, 250))
BALLOON_COLORS = ((240, 110, 160), (250, 206, 90), (110, 190, 240), (176, 130, 236), (120, 222, 170), (248, 140, 100))
LANTERN_COLORS = ((236, 82, 92), (250, 170, 70), (244, 120, 170), (120, 190, 240), (250, 214, 100))

# Гирлянды флажков: от края страницы к концам ленточки с названием.
GARLANDS = (((2, 7), (112, 12), 10), ((208, 12), (318, 7), 10))
GARLAND_FLAG_COUNT = 9


def garland_point(garland: int, s: float) -> tuple[float, float]:
    """Точка гирлянды (0 — левая, 1 — правая): s от 0 (у края) до 1 (у ленточки или края справа)."""
    (x0, y0), (x1, y1), sag = GARLANDS[garland]
    return x0 + (x1 - x0) * s, y0 + (y1 - y0) * s + math.sin(math.pi * s) * sag


# Фонарики висят на гирляндах: (гирлянда, доля длины, длина подвеса, цвет).
LANTERN_SPECS = (
    (0, 0.26, 17, 0), (0, 0.72, 13, 1),
    (1, 0.28, 13, 4), (1, 0.74, 17, 2),
)
# Шарики привязаны к столу: (откуда привязаны, где парит, цвет).
BALLOON_SPECS = (
    ((100, 80), (88, 52), 0), ((100, 80), (100, 45), 1), ((100, 80), (111, 54), 2),
    ((220, 80), (209, 54), 3), ((220, 80), (220, 45), 4), ((220, 80), (232, 52), 5),
)
CANDLES = ((155, 55), (160, 56), (165, 55))  # куда ставятся свечи торта (низ свечи)


@dataclass(frozen=True)
class Lantern:
    piece: Piece
    glow: Piece
    attach: tuple[float, float]
    sway: float  # сдвиг фазы покачивания


@dataclass(frozen=True)
class Balloon:
    piece: Piece
    center: tuple[float, float]


@dataclass(frozen=True)
class FinaleArt:
    sky: pygame.Surface
    land: pygame.Surface
    stars: tuple[tuple[int, int, config.Color], ...]  # мерцающие звёзды: место и цвет
    table: Piece
    cake: Piece
    plates: tuple[Piece, ...]
    flame_frames: tuple[Piece, ...]
    flame_spots: tuple[tuple[int, int], ...]
    cake_glow: Piece
    lanterns: tuple[Lantern, ...]
    balloons: tuple[Balloon, ...]
    tiles: dict[str, Piece]
    emblem_glow: Piece
    motes: tuple[tuple[float, float, float, float], ...]  # огоньки-светлячки: x, y, радиус облёта, фаза
    lights: tuple[tuple[int, int], ...]  # огоньки в листве
    vignette: pygame.Surface
    lamps: tuple[tuple[Piece, Piece], ...]  # фонари на шестах у краёв поляны: картинка и её свечение


def _gradient(y: float) -> config.Color:
    for (y0, c0), (y1, c1) in zip(SKY_STOPS, SKY_STOPS[1:]):
        if y <= y1:
            return mix(c0, c1, (y - y0) / (y1 - y0))
    return SKY_STOPS[-1][1]


def _soft_glow(width: int, height: int, color: config.Color, peak: int) -> pygame.Surface:
    """Мягкое пятно света (овал) нужного размера: маленький радиальный градиент, растянутый сглаживанием."""
    return pygame.transform.smoothscale(glow_sprite(16, color, peak), (width, height))


def _build_sky(rng: random.Random) -> tuple[pygame.Surface, tuple[tuple[int, int, config.Color], ...]]:
    """Закат переходит в ночь: ступенчатый градиент с шахматным сглаживанием между ступенями."""
    levels = 20
    step = 256 // levels
    bayer = ((0.0, 0.5), (0.75, 0.25))
    rows = bytearray()
    for y in range(HEIGHT):
        exact = _gradient(y)
        pair = []
        for threshold in bayer[y % 2]:  # рисунок строки зависит только от чётности y и x
            pair.append(bytes(min(255, max(0, int(channel / step + threshold) * step + 4)) for channel in exact))
        rows += (pair[0] + pair[1]) * (WIDTH // 2)
    raw = pygame.image.frombuffer(bytes(rows), config.LOGICAL_SIZE, "RGB")
    sky = pygame.Surface(config.LOGICAL_SIZE)  # в формате экрана: вывод на холст без пересчёта цвета
    sky.blit(raw, (0, 0))
    # Тёплое сияние над горизонтом и прозрачные облака.
    glow = _soft_glow(300, 110, (255, 178, 130), 120)
    sky.blit(glow, glow.get_rect(center=(160, HORIZON + 6)))
    for x, y, w, h, color in ((34, 74, 70, 5, (112, 62, 138)), (232, 66, 80, 5, (118, 64, 140)),
                              (120, 84, 56, 4, (186, 98, 140)), (262, 82, 52, 4, (200, 108, 140))):
        pygame.draw.ellipse(sky, color, (x, y, w, h))
        pygame.draw.ellipse(sky, mix(color, (255, 190, 160), 0.35), (x + 4, y, w - 14, max(1, h // 2)))
    stars = []
    for _ in range(70):
        x, y = rng.randrange(WIDTH), int(rng.random() ** 1.6 * 70)
        color = rng.choice(STAR_COLORS)
        if rng.random() < 0.2:
            stars.append((x, y, color))
        sky.set_at((x, y), mix(color, _gradient(y), 0.15 if rng.random() < 0.6 else 0.5))
    return sky, tuple(stars)


def _tree(land: pygame.Surface, rng: random.Random, side: int) -> list[tuple[int, int]]:
    """Дерево у края поляны: тёмный ствол и крона в углу, на кроне — огоньки гирлянд."""
    trunk_x = 10 if side < 0 else WIDTH - 10
    trunk = pygame.Rect(trunk_x - 7, 24, 14, HORIZON + 24 - 24)
    pygame.draw.rect(land, (44, 32, 52), trunk)
    pygame.draw.rect(land, (66, 48, 70), (trunk.x, trunk.y, 4, trunk.height))
    for y in range(30, 120, 6):  # кора
        land.fill((32, 22, 40), (trunk.x + 7 + (y % 3) * 2, y, 1, 4))
    lights = []
    lumps = []
    for _ in range(26):
        x = trunk_x + side * rng.uniform(-6, 52)
        y = rng.uniform(-6, 46)
        lumps.append((x, y, rng.uniform(9, 17)))
    for x, y, r in sorted(lumps, key=lambda lump: lump[1]):
        for color, shrink, dx, dy in ((FOLIAGE[0], 1.0, 0, 0), (FOLIAGE[1], 0.86, -1, -1),
                                      (FOLIAGE[2], 0.55, -2, -3)):
            pygame.draw.circle(land, color, (round(x + dx), round(y + dy)), round(r * shrink))
        for _ in range(int(r)):
            angle = rng.uniform(0, math.tau)
            dist = r * math.sqrt(rng.random()) * 0.7
            land.set_at((round(x + math.cos(angle) * dist), round(y - abs(math.sin(angle)) * dist * 0.8)),
                        FOLIAGE[3] if rng.random() < 0.4 else FOLIAGE[0])
    for _ in range(11):  # огоньки гирлянды, спрятанной в листве
        lights.append((round(trunk_x + side * rng.uniform(-2, 54)), round(rng.uniform(6, 44))))
    return lights


def _build_land(rng: random.Random) -> tuple[pygame.Surface, tuple[tuple[int, int], ...]]:
    """Холмы, лес вдалеке, поляна с травой и цветами, ковёр, деревья по краям."""
    land = pygame.Surface(config.LOGICAL_SIZE, pygame.SRCALPHA)
    # Дальний гребень и ёлки на нём.
    ridge = [(x, HORIZON - 7 - round(3 * math.sin(x / 31) + 2 * math.sin(x / 13 + 1))) for x in range(0, WIDTH + 1, 4)]
    pygame.draw.polygon(land, (78, 56, 124), [(0, HORIZON + 2), *ridge, (WIDTH, HORIZON + 2)])
    for x in range(0, WIDTH, 5):
        base = HORIZON - 7 - round(3 * math.sin(x / 31) + 2 * math.sin(x / 13 + 1))
        height = rng.randrange(5, 12)
        pygame.draw.polygon(land, (58, 42, 106), [(x, base + 2), (x + 3, base + 2), (x + 1.5, base - height)])
    for x, y in ridge[::2]:
        land.set_at((x, y), (176, 100, 146))
    # Средние холмы.
    pygame.draw.ellipse(land, (52, 78, 104), (-60, HORIZON - 12, 210, 36))
    pygame.draw.ellipse(land, (46, 70, 98), (170, HORIZON - 10, 230, 34))
    # Поляна.
    for y in range(HORIZON, HEIGHT):
        t = (y - HORIZON) / (HEIGHT - HORIZON)
        base = mix(GRASS[0], GRASS[3], t ** 0.8)
        pygame.draw.line(land, base, (0, y), (WIDTH, y))
        if (y // 3) % 2 == 0:  # полосы свежескошенной травы
            pygame.draw.line(land, mix(base, GRASS[0], 0.12), (0, y), (WIDTH, y))
    for _ in range(520):  # травинки
        x, y = rng.randrange(WIDTH), rng.randrange(HORIZON + 2, HEIGHT)
        shade = rng.choice((GRASS[0], GRASS[2], GRASS[3]))
        land.fill(shade, (x, y - 1, 1, 2))
    # Тёплый свет фонариков ложится на траву вокруг ковра.
    land.set_clip(pygame.Rect(0, HORIZON, WIDTH, HEIGHT - HORIZON))
    pool = _soft_glow(280, 84, (255, 196, 120), 120)
    land.blit(pool, pool.get_rect(center=(160, 108)))
    land.set_clip(None)
    # Ковёр для пикника под столом: розовый край, золотая лента, кремовая середина.
    cx, cy = RUG_CENTER
    rx, ry = RUG_RADII
    pygame.draw.ellipse(land, (34, 60, 62), (cx - rx - 3, cy - ry + 3, (rx + 3) * 2, ry * 2 + 2))  # тень
    pygame.draw.ellipse(land, ROSE_DARK, (cx - rx, cy - ry, rx * 2, ry * 2))
    pygame.draw.ellipse(land, ROSE, (cx - rx + 2, cy - ry + 1, rx * 2 - 4, ry * 2 - 3))
    pygame.draw.ellipse(land, GOLD, (cx - rx + 6, cy - ry + 3, rx * 2 - 12, ry * 2 - 7))
    pygame.draw.ellipse(land, (255, 238, 208), (cx - rx + 8, cy - ry + 4, rx * 2 - 16, ry * 2 - 9))
    for k in range(40):  # ромбики на розовой ленте
        a = k * math.tau / 40
        x, y = cx + math.cos(a) * (rx - 3), cy + math.sin(a) * (ry - 1.4)
        land.fill(GOLD if k % 2 else (255, 238, 208), (round(x), round(y), 2, 1))
    pygame.draw.ellipse(land, mix(ROSE, (255, 238, 208), 0.45), (cx - rx + 16, cy - ry + 6, rx * 2 - 32, ry * 2 - 13), 1)
    for k in range(26):  # цветочки по внутреннему кругу ковра
        a = k * math.tau / 26 + 0.1
        x, y = cx + math.cos(a) * (rx - 16), cy + math.sin(a) * (ry - 6.5)
        land.fill(ROSE if k % 2 else GOLD, (round(x) - 1, round(y), 3, 1))
        land.fill(ROSE if k % 2 else GOLD, (round(x), round(y) - 1, 1, 3))
    # Цветы на траве.
    for _ in range(110):
        x, y = rng.randrange(4, WIDTH - 4), rng.randrange(HORIZON + 6, HEIGHT - 2)
        if ((x - cx) / (rx + 8)) ** 2 + ((y - cy) / (ry + 5)) ** 2 < 1:
            continue
        color = rng.choice(FLOWER_COLORS)
        land.set_at((x, y + 1), GRASS[3])
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            land.set_at((x + dx, y + dy), color)
        land.set_at((x, y), (255, 214, 96) if color != FLOWER_COLORS[1] else (240, 150, 90))
    lights = _tree(land, rng, -1) + _tree(land, rng, 1)
    # Кусты с цветами в нижних углах.
    for bx, by in ((18, 156), (302, 158), (62, 170), (262, 172), (104, 178), (216, 179), (-2, 176), (324, 174)):
        for dx, dy, r in ((-8, 2, 7), (6, 3, 8), (0, -3, 8)):
            pygame.draw.circle(land, (30, 62, 66), (bx + dx, by + dy), r)
            pygame.draw.circle(land, (50, 100, 88), (bx + dx - 1, by + dy - 2), r - 2)
        for _ in range(16):
            x, y = bx + rng.randrange(-12, 12), by + rng.randrange(-8, 6)
            color = rng.choice(FLOWER_COLORS)
            land.fill(color, (x, y, 2, 2))
            land.set_at((x, y), (255, 255, 244))
    return land, tuple(lights)


def _build_vignette() -> pygame.Surface:
    """Лёгкое затемнение к краям и низу: взгляд идёт к столу. Полупрозрачная картинка размером с холст
    (считается вчетверо меньшей и растягивается сглаживанием)."""
    small = pygame.Surface((WIDTH // 4, HEIGHT // 4), pygame.SRCALPHA)
    for y in range(small.get_height()):
        for x in range(small.get_width()):
            dx, dy = (x * 4 - WIDTH / 2) / (WIDTH / 2), (y * 4 - 92) / 92
            edge = max(0.0, (dx * dx * 0.8 + dy * dy * 0.7) - 0.45)
            small.set_at((x, y), (12, 8, 32, min(120, round(edge * 150))))
    return pygame.transform.smoothscale(small, config.LOGICAL_SIZE)


def _build_lamp() -> tuple[Piece, Piece]:
    """Фонарь на деревянном шесте у края поляны: тёплый шар на крючке и мягкое свечение."""
    art = Art(pygame.Rect(-8, 0, 16, 44), seed=2)
    art.rect_((70, 46, 52), -0.9, 14, 1.8, 30)
    art.rect_((110, 76, 70), -0.9, 14, 0.8, 30)
    art.ellipse((52, 34, 46), 0, 44.2, 3.0, 0.9)
    art.line((70, 46, 52), (0, 14), (3.2, 12.4), 0.5)
    art.ellipse(GOLD_DARK, 3.2, 12.0, 4.4, 1.0)
    art.ball(palette_from((250, 190, 90), dark=(90, 40, 30), light=(255, 255, 220)), 3.2, 7.6, 4.2, outline=True)
    art.rect_((255, 244, 190), 2.2, 5.4, 2.0, 4.4)
    art.dot(GOLD, 3.2, 3.2, 2)
    return art.piece(), Piece(glow_sprite(18, (255, 206, 120), 130), pygame.Rect(-15, -10, 36, 36))


# --- Стол ---

def _build_table() -> Piece:
    art = Art(TABLE_RECT, seed=3)
    by0, bx0, bx1 = TABLE_BACK[1], TABLE_BACK[0], TABLE_BACK[2]
    fy, fx0, fx1 = TABLE_FRONT[1], TABLE_FRONT[0], TABLE_FRONT[2]
    # Скатерть спереди: складки, золотая кромка, розовые фестоны.
    art.rect_(CLOTH, fx0, fy, fx1 - fx0, TABLE_BOTTOM - fy)
    k = 0
    for x in range(fx0, fx1, 8):
        art.rect_(CLOTH_SHADE if k % 2 == 0 else mix(CLOTH, CLOTH_SHADE, 0.4), x, fy, 4.4, TABLE_BOTTOM - fy)
        art.rect_(CLOTH_DARK, x + 4, fy + 1, 0.5, TABLE_BOTTOM - fy - 1)
        k += 1
    art.rect_(mix(CLOTH_DARK, CLOTH, 0.3), fx0, fy, fx1 - fx0, 1.6)  # тень под кромкой стола
    for x in range(fx0, fx1, 8):
        art.ellipse(ROSE, x + 4, TABLE_BOTTOM - 0.6, 4.2, 3.6)
        art.ellipse(ROSE_DARK, x + 4, TABLE_BOTTOM - 0.3, 4.2, 3.6, 1)
        art.dot(GOLD, x + 4, TABLE_BOTTOM - 1.5, 2)
    art.line(GOLD, (fx0, TABLE_BOTTOM - 4), (fx1, TABLE_BOTTOM - 4), 0.5)
    # Бока скатерти на краях стола.
    art.polygon(CLOTH_SHADE, [(fx0, fy), (bx0, by0), (bx0 - 1, by0 + 14), (fx0 - 1, TABLE_BOTTOM)])
    art.polygon(CLOTH_SHADE, [(fx1, fy), (bx1, by0), (bx1 + 1, by0 + 14), (fx1 + 1, TABLE_BOTTOM)])
    # Столешница.
    top = [(bx0, by0), (bx1, by0), (fx1, fy), (fx0, fy)]
    art.polygon(CLOTH_DARK, top)
    art.polygon(CLOTH, [(bx0 + 1, by0 + 1), (bx1 - 1, by0 + 1), (fx1 - 1, fy - 1), (fx0 + 1, fy - 1)])
    art.polygon(mix(CLOTH, (255, 255, 255), 0.5), [(bx0 + 3, by0 + 1), (bx0 + 36, by0 + 1), (fx0 + 20, fy - 1), (fx0 + 1, fy - 1)])
    art.line(GOLD, (fx0, fy), (fx1, fy), 0.7)
    art.line(GOLD_DARK, (bx0, by0), (bx1, by0), 0.4)
    # Дорожка с ромбиками вдоль стола.
    runner = [(bx0 + 6, 79), (bx1 - 6, 79), (fx1 - 9, 87.5), (fx0 + 9, 87.5)]
    art.polygon(ROSE_DARK, runner)
    art.polygon(ROSE, [(runner[0][0] + 0.6, 79.6), (runner[1][0] - 0.6, 79.6), (runner[2][0] - 0.6, 86.9), (runner[3][0] + 0.6, 86.9)])
    art.line(GOLD, runner[0], runner[1], 0.5)
    art.line(GOLD, runner[3], runner[2], 0.5)
    for i in range(11):
        t = (i + 0.5) / 11
        x = runner[0][0] + (runner[1][0] - runner[0][0]) * t
        x2 = runner[3][0] + (runner[2][0] - runner[3][0]) * t
        xm = (x + x2) / 2
        art.polygon(mix(ROSE, CLOTH, 0.55), [(xm, 81.6), (xm + 1.6, 83.3), (xm, 85.0), (xm - 1.6, 83.3)])
    # Конфетти на скатерти.
    rng = random.Random(9)
    for _ in range(26):
        x = rng.uniform(bx0 + 6, bx1 - 6)
        y = rng.uniform(by0 + 2, fy - 1)
        art.rect_(rng.choice(BALLOON_COLORS), x, y, 1.2, 0.7)
    # Букеты по краям стола.
    for vx in (101, 219):
        _vase(art, vx, 82)
    # Чашки с блюдцами.
    for cx in (141, 179):
        _cup(art, cx, 87)
    return art.piece()


def _vase(art: Art, x: float, y: float) -> None:
    art.ellipse((92, 120, 150), x, y + 0.4, 3.4, 1.0)
    art.rect_((170, 214, 244), x - 2.2, y - 5, 4.4, 5.2, radius=1)
    art.rect_((220, 244, 255), x - 1.6, y - 4.6, 1.0, 3.8)
    for dx, dy, color in ((-3.2, -9.2, FLOWER_COLORS[0]), (0.2, -11.0, FLOWER_COLORS[1]), (3.4, -8.6, FLOWER_COLORS[3]),
                          (-1.2, -7.2, FLOWER_COLORS[4]), (2.0, -6.8, FLOWER_COLORS[0])):
        art.line((60, 130, 80), (x + dx * 0.3, y - 5), (x + dx, y + dy + 1), 0.5)
        art.ball(palette_from(color), x + dx, y + dy, 2.1, outline=False)
        art.dot((255, 236, 150), x + dx, y + dy, 2)


def _cup(art: Art, x: float, y: float) -> None:
    art.ellipse((190, 180, 200), x, y + 0.6, 4.6, 1.5)
    art.ellipse((255, 252, 246), x, y + 0.2, 4.2, 1.2)
    art.rect_((255, 252, 246), x - 2.4, y - 3.4, 4.8, 3.2, radius=1)
    art.rect_((240, 150, 178), x - 2.4, y - 2.0, 4.8, 0.9)
    art.ellipse((200, 120, 150), x, y - 3.4, 2.4, 0.8)
    art.circle((255, 252, 246), x + 3.0, y - 1.8, 1.0)


# --- Торт ---

def _build_cake() -> tuple[Piece, Piece, tuple[Piece, ...]]:
    """Трёхъярусный торт на золотой подставке: розовый крем, фестоны, клубника, свечи.

    Возвращает торт, мягкое свечение над ним и три кадра пламени свечи."""
    cx, base = CAKE_CENTER_X, CAKE_BASE_Y
    art = Art(pygame.Rect(cx - 26, base - 50, 52, 54), seed=5)
    # Подставка с ножкой и золотой тарелкой.
    art.ellipse(GOLD_DARK, cx, base - 0.4, 9.5, 2.1)
    art.rect_(GOLD_DARK, cx - 2.2, base - 5, 4.4, 4.6)
    art.rect_(GOLD, cx - 1.4, base - 5, 1.6, 4.4)
    plate_y = base - 6.0
    art.ellipse(GOLD_DARK, cx, plate_y + 0.9, 21.5, 4.0)
    art.ellipse(GOLD, cx, plate_y, 21.5, 3.8)
    art.ellipse((255, 240, 190), cx - 2, plate_y - 0.5, 17, 2.6)
    # Ярусы снизу вверх: ширина, высота, цвет коржа, цвет глазури.
    tiers = (
        (36.0, 11.0, (250, 170, 198), (255, 250, 244)),
        (25.0, 9.5, (255, 244, 230), (248, 150, 186)),
        (16.0, 8.5, (244, 128, 168), (255, 250, 244)),
    )
    y = plate_y - 0.4
    tops = []
    for width, height, body, glaze in tiers:
        half = width / 2
        ry = 2.6 + width / 24
        pal = palette_from(body, dark=(120, 50, 90), light=(255, 255, 255))
        # Цилиндр яруса: тень с краёв, свет слева.
        art.rect_(pal[1], cx - half, y - height, width, height)
        art.ellipse(pal[1], cx, y, half, ry)
        art.rect_(pal[2], cx - half + 1, y - height, width - 2.5, height)
        art.ellipse(pal[2], cx - 0.5, y, half - 1.2, ry - 0.2)
        art.rect_(pal[3], cx - half + 1.2, y - height + 0.5, width * 0.22, height - 1)
        # Слой бисквита у основания и жемчужинки.
        art.rect_((242, 200, 140), cx - half + 0.4, y - 2.0, width - 0.8, 1.6)
        for k in range(int(width // 3.0)):
            px = cx - half + 2 + k * (width - 4) / max(1, width // 3.0 - 1)
            art.dot((255, 252, 244), px, y + ry * 0.55 * math.sqrt(max(0.0, 1 - ((px - cx) / half) ** 2)) - 0.4, 2)
        # Верх яруса и стекающая глазурь с фестонами.
        top_y = y - height
        art.ellipse(glaze, cx, top_y, half, ry)
        art.ellipse(mix(glaze, (255, 255, 255), 0.5), cx - 1.2, top_y - 0.3, half * 0.7, ry * 0.6)
        art.ellipse(mix(glaze, pal[0], 0.35), cx, top_y, half, ry, 1)
        drips = max(5, int(width // 4.2))
        for k in range(drips):
            px = cx - half + (k + 0.5) * width / drips
            drop = 2.4 + 1.6 * ((k * 7) % 3) / 2
            edge = ry * math.sqrt(max(0.0, 1 - ((px - cx) / half) ** 2))
            art.rect_(glaze, px - 1.5, top_y + edge - 1.0, 3.0, drop, radius=1)
            art.circle(glaze, px, top_y + edge + drop - 0.6, 1.6)
        tops.append((top_y, half, ry, glaze))
        y = top_y + 0.6
    # Клубника на «полках» нижних ярусов и крупная — на самом верху; золотые звёздочки на втором ярусе.
    for px, py in ((cx - 13.0, tops[0][0] + 0.6), (cx + 13.0, tops[0][0] + 0.6), (cx - 8.0, tops[1][0] + 0.2), (cx + 8.0, tops[1][0] + 0.2)):
        _strawberry(art, px, py)
    for k in range(5):
        px = cx - 8 + k * 4
        art.dot(GOLD, px, tops[1][0] + 6.4 + (k % 2) * 1.4, 2)
    # Свечи.
    for px, py in CANDLES:
        _candle(art, px, py, (px * 3) % 3)
    cake = art.piece()
    glow = Piece(glow_sprite(15, (255, 200, 120), 120), pygame.Rect(cx - 15, CANDLES[1][1] - 24, 30, 30))
    flames = tuple(Piece(_flame_image(variant), pygame.Rect(0, 0, 5, 7)) for variant in range(3))
    return cake, glow, flames


def _candle(art: Art, x: float, y: float, kind: int) -> None:
    """Свеча в полоску: яркая, с тёмной обводкой, чтобы не терялась в белом креме."""
    palettes = (((232, 64, 110), (255, 240, 244)), ((64, 140, 236), (240, 248, 255)), ((246, 190, 52), (255, 250, 232)))
    body, stripe = palettes[int(kind) % 3]
    art.rect_(mix(body, (40, 10, 40), 0.55), x - 1.3, y - 8.4, 2.6, 8.6)
    art.rect_(body, x - 0.9, y - 8.0, 1.8, 8.0)
    for k in range(3):
        art.rect_(stripe, x - 0.9, y - 7.2 + k * 2.4, 1.8, 0.9)
    art.rect_((50, 34, 36), x - 0.2, y - 9.4, 0.4, 1.2)


def _strawberry(art: Art, x: float, y: float, big: bool = False) -> None:
    r = 2.7 if big else 2.1
    art.polygon((140, 14, 40), [(x - r, y - r * 0.5), (x + r, y - r * 0.5), (x, y + r * 1.3)])
    art.ball(palette_from((226, 40, 70), dark=(110, 10, 40)), x, y - r * 0.2, r, outline=False)
    art.polygon((226, 40, 70), [(x - r * 0.8, y), (x + r * 0.8, y), (x, y + r * 1.3)])
    for dx, dy in ((-0.9, -0.5), (0.9, -0.5), (0, 0.5), (-0.6, 1.1), (0.7, 1.0)):
        art.dot((255, 226, 150), x + dx * r * 0.7, y + dy * r * 0.8, 1)
    art.polygon((70, 160, 80), [(x - r * 0.8, y - r), (x, y - r * 0.6), (x + r * 0.8, y - r), (x, y - r * 1.5)])
    art.dot((255, 250, 250), x - r * 0.45, y - r * 0.5, 2)


FLAME_FRAMES = (
    ("..O..", ".OOO.", ".OYO.", ".OYO.", "..W.."),
    (".O...", ".OO..", ".OYO.", ".OYO.", "..W.."),
    ("...O.", "..OO.", ".OYO.", ".OYO.", "..W.."),
)
FLAME_COLORS = {"O": (255, 150, 56), "Y": (255, 222, 110), "W": (255, 252, 230)}


def _flame_image(variant: int) -> pygame.Surface:
    """Огонёк свечи: три слегка разных кадра (качается влево и вправо), из пикселей холста."""
    image = pygame.Surface((5, 7), pygame.SRCALPHA)
    for row, line in enumerate(FLAME_FRAMES[variant]):
        for column, mark in enumerate(line):
            if mark in FLAME_COLORS:
                image.set_at((column, row + 1), FLAME_COLORS[mark])
    return image


# --- Блюда ---

def _build_plates() -> tuple[Piece, ...]:
    """Тарелки с готовыми суши — тем, что рисует испытание суши, один в один, но целиком на столе."""
    pieces = []
    for (cx, cy), recipe in zip(PLATE_CENTERS, PLATE_DISHES):
        image = pygame.Surface((42, 28), pygame.SRCALPHA)
        plate = pygame.Rect(0, 0, *sushi_dishes.PLATE_SIZE)
        plate.center = (21, 19)
        sushi_dishes.draw_plate(image, plate)
        sushi_dishes.draw_dish(image, recipe, plate.center)
        pieces.append(Piece(image, pygame.Rect(cx - 21, cy - 19, 42, 28)))
    return tuple(pieces)


# --- Украшения ---

def _build_lantern(color_index: int, hang: float) -> tuple[Piece, Piece]:
    """Бумажный фонарик на верёвочке длиной hang: ребристый шар, золотые крышечки, кисточка."""
    color = LANTERN_COLORS[color_index]
    pal = palette_from(color, dark=(70, 20, 40), light=(255, 255, 230))
    art = Art(pygame.Rect(-8, 0, 16, int(hang) + 20), seed=color_index)
    cx = 0.0
    art.line((120, 90, 70), (cx, 0), (cx, hang), 0.4)
    top = hang + 1.0
    art.rect_(GOLD_DARK, cx - 2.2, top, 4.4, 1.4)
    art.rect_(GOLD, cx - 1.8, top, 2.0, 1.0)
    art.ellipse(pal[0], cx, top + 6.4, 4.9, 5.6)
    art.ellipse(pal[1], cx, top + 6.4, 4.6, 5.3)
    art.ellipse(pal[2], cx - 0.4, top + 6.4, 4.0, 5.0)
    art.ellipse(pal[3], cx - 1.0, top + 5.6, 2.2, 3.4)
    for dx in (-2.8, 0.0, 2.8):  # рёбра
        art.line(pal[1], (cx + dx * 0.55, top + 1.4), (cx + dx, top + 6.4), 0.35)
        art.line(pal[1], (cx + dx, top + 6.4), (cx + dx * 0.55, top + 11.4), 0.35)
    art.dot(pal[4], cx - 1.8, top + 4.0, 2)
    art.rect_(GOLD_DARK, cx - 2.2, top + 11.2, 4.4, 1.3)
    art.rect_(GOLD, cx - 1.8, top + 11.2, 2.0, 0.9)
    art.line(ROSE, (cx, top + 12.4), (cx, top + 15.4), 0.5)
    art.dot(GOLD, cx, top + 15.8, 2)
    glow = Piece(glow_sprite(15, mix(color, WARM_LIGHT, 0.5), 130), pygame.Rect(-15, int(top) - 9, 30, 30))
    return art.piece(), glow


def _build_balloon(anchor: tuple[float, float], center: tuple[float, float], color_index: int) -> Balloon:
    color = BALLOON_COLORS[color_index]
    pal = palette_from(color, dark=(60, 20, 70), light=(255, 255, 255))
    x0, y0 = min(anchor[0], center[0]) - 9, center[1] - 10
    art = Art(pygame.Rect(int(x0), int(y0), 20 + int(abs(anchor[0] - center[0])), int(anchor[1] - y0) + 2), seed=color_index)
    bx, by = center
    art.ellipse(pal[0], bx, by, 6.0, 7.2)
    art.ellipse(pal[1], bx, by, 5.5, 6.7)
    art.ellipse(pal[2], bx - 0.4, by - 0.3, 4.9, 6.1)
    art.ellipse(pal[3], bx - 1.2, by - 1.4, 3.0, 4.0)
    art.ellipse(pal[4], bx - 2.0, by - 2.6, 1.0, 1.6)
    art.polygon(pal[1], [(bx - 1.1, by + 7.0), (bx + 1.1, by + 7.0), (bx, by + 8.4)])
    string = spline([(bx, by + 8.2), (bx + (anchor[0] - bx) * 0.2 + 1.5, by + (anchor[1] - by) * 0.4),
                     (bx + (anchor[0] - bx) * 0.7 - 1.5, by + (anchor[1] - by) * 0.75), anchor], 6)
    art.lines((236, 230, 240), string, 0.35)
    return Balloon(art.piece(), center)


LAMP_POSITIONS = ((36, 130), (284, 132))  # где стоят основания шестов


def _build_lamps() -> tuple[tuple[Piece, Piece], ...]:
    lamps = []
    for x, y in LAMP_POSITIONS:
        piece, glow = _build_lamp()
        # Шест нарисован от основания (0, 44): фонарь висит на крючке правее шеста, поэтому
        # сдвигаем на 3 пикселя влево — шар окажется над точкой LAMP_POSITIONS.
        piece.rect.move_ip(x - 3, y - 44)
        glow.rect.move_ip(x - 3, y - 44)
        lamps.append((piece, glow))
    return tuple(lamps)


def _build_emblem_glow() -> Piece:
    return Piece(glow_sprite(30, (255, 232, 150), 150), pygame.Rect(EMBLEM_CENTER[0] - 30, EMBLEM_CENTER[1] - 30, 60, 60))


@lru_cache(maxsize=1)
def finale_art() -> FinaleArt:
    """Вся неподвижная графика финала; собирается при первом обращении и дальше только выводится."""
    rng = random.Random(21)
    sky, stars = _build_sky(rng)
    land, lights = _build_land(rng)
    cake, cake_glow, flames = _build_cake()
    lanterns = []
    for index, (garland, share, hang, color) in enumerate(LANTERN_SPECS):
        x, y = garland_point(garland, share)
        piece, glow = _build_lantern(color, hang)
        piece.rect.move_ip(round(x), round(y))  # картинки нарисованы от точки подвеса (0, 0)
        glow.rect.move_ip(round(x), round(y))
        lanterns.append(Lantern(piece, glow, (x, y), index * 1.7))
    balloons = tuple(_build_balloon(anchor, center, color) for anchor, center, color in BALLOON_SPECS)
    tiles = dict(hub_scenery.table().fragments)
    motes = tuple((rng.uniform(20, 300), rng.uniform(50, 160), rng.uniform(3, 9), rng.uniform(0, math.tau)) for _ in range(24))
    return FinaleArt(
        sky, land, stars, _build_table(), cake, _build_plates(), flames,
        tuple((x, y - 9) for x, y in CANDLES), cake_glow, tuple(lanterns), balloons,
        tiles, _build_emblem_glow(), motes, lights, _build_vignette(), _build_lamps(),
    )
