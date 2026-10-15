"""Земля центральной площади: трава, далёкий лес, тропинки, площадка вокруг стола, коврики у дверей.

Рисуется один раз в логическом разрешении холста 320×180 и лежит под всем остальным (деревья,
стол и мелкие предметы — отдельные картинки, см. game/world/hub_scenery.py). Участки из
reserved остаются простой травой двух тонов: на них стоят Лео в корзинке и Чучмек, и им
не нужны ни тропинки, ни цветы под ногами.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

import pygame

import config
from game.graphics.pixel_art import mix, spline

WIDTH, HEIGHT = config.LOGICAL_SIZE
HUD_HEIGHT = 12  # верхняя полоса интерфейса
STATUS_TOP = 168  # нижняя полоса интерфейса

GRASS_COLOR = (150, 186, 120)
GRASS_DARK_COLOR = (136, 172, 108)
GRASS_LIGHT_COLOR = (168, 202, 130)
GRASS_DEEP_COLOR = (116, 156, 100)
GRASS_SHADE_COLOR = (98, 140, 92)
PATH_COLOR = (226, 206, 164)
PATH_LIGHT_COLOR = (240, 224, 186)
PATH_EDGE_COLOR = (190, 164, 120)
PATH_SHADE_COLOR = (204, 182, 140)
PLAZA_COLOR = (214, 198, 170)
PLAZA_EDGE_COLOR = (166, 148, 128)
RUNE_COLOR = (236, 196, 112)
SPAWN_COLOR = (246, 232, 196)

FLOWER_COLORS = ((246, 128, 160), (252, 214, 96), (186, 156, 240), (255, 255, 244), (130, 190, 250))

# Точка у плеча площадки и тропинки: (опорные точки, ширина). Тропинки вьются, а не идут по линейке.
PLAZA_CENTER = (160, 118)
PLAZA_RADII = (49, 28)
PATHS = (
    ([(116, 116), (100, 114), (84, 108), (66, 103), (50, 100), (44, 97)], 13),  # к суши
    ([(204, 116), (220, 114), (238, 110), (256, 104), (270, 100), (276, 97)], 13),  # к тортикам
    ([(122, 100), (130, 92), (144, 86), (160, 83), (176, 86), (190, 92), (198, 100)], 11),  # вокруг стола к формулярам
    ([(160, 166), (160, 154), (160, 140)], 15),  # к точке появления
)
# Коврики у дверей: (центр по x, верх), цвет, кайма.
DOOR_MATS = (
    (44, 92, (196, 74, 70), (250, 232, 210)),
    (160, 77, (126, 132, 150), (206, 212, 226)),
    (276, 92, (232, 130, 176), (255, 236, 244)),
)
SPAWN_MAT = (160, 160)


def render_ground(reserved: Sequence[pygame.Rect] = (), shadows: Sequence[tuple[int, int, int, int]] = (),
                  bar_color: config.Color = (0, 0, 0)) -> pygame.Surface:
    """Готовый фон. reserved — места, где земля остаётся простой травой (корзинка Лео, Чучмек);
    shadows — тени предметов: (x, y, полуширина, полувысота) эллипса на земле;
    bar_color — цвет полос интерфейса сверху и снизу (на холсте они однотонные)."""
    rng = random.Random(7)
    page = pygame.Surface(config.LOGICAL_SIZE)
    page.fill(GRASS_COLOR)
    for x in range(4, WIDTH, 16):  # редкие тёмные травинки, чтобы было видно движение
        for y in range(18 + (x // 16) % 2 * 8, STATUS_TOP, 16):
            page.fill(GRASS_DARK_COLOR, (x, y, 2, 1))
    _forest(page, rng)
    overlay = pygame.Surface(config.LOGICAL_SIZE, pygame.SRCALPHA)
    _light_and_shade(overlay)
    for x, y, rx, ry in shadows:
        _dither_ellipse(overlay, GRASS_SHADE_COLOR, (x, y), (rx, ry), 0.35)
    _plaza(overlay)
    for points, width in PATHS:
        _path(overlay, points, width, rng)
    for x, top, color, trim in DOOR_MATS:
        _mat(overlay, x, top, color, trim)
    _spawn_mat(overlay)
    occupied = _occupied_mask(overlay)
    _scatter(overlay, occupied, rng, reserved)
    for rect in reserved:  # у корзинки и Чучмека — ровная трава без украшений
        overlay.fill((0, 0, 0, 0), rect.inflate(2, 2))
    page.blit(overlay, (0, 0))
    _hedge(page, rng)
    page.fill(bar_color, (0, 0, WIDTH, HUD_HEIGHT))
    page.fill(bar_color, (0, STATUS_TOP, WIDTH, HEIGHT - STATUS_TOP))
    return page


# --- Слои ---

def _forest(page: pygame.Surface, rng: random.Random) -> None:
    """Далёкий лес вдоль верха и по бокам: три ряда крон, чем дальше — тем светлее и синее."""
    top = HUD_HEIGHT
    page.fill((60, 104, 96), (0, top, WIDTH, 32))
    layers = (((84, 130, 118), 18, 11, 16), ((58, 108, 90), 24, 12, 15), ((40, 86, 70), 30, 12, 13))
    for color, y, radius, step in layers:
        for x in range(-6, WIDTH + 10, step):
            r = radius + rng.randint(-2, 3)
            pygame.draw.circle(page, color, (x + rng.randint(-3, 3), y + rng.randint(-3, 3)), r)
        page.fill(color, (0, y + 4, WIDTH, 8))
        for x in range(2, WIDTH, step * 2 + 3):  # тёмные стволы между кронами и светлые просветы
            page.fill(mix(color, (24, 40, 36), 0.45), (x, y + 6, 2, 12))
    for x in range(0, WIDTH, 5):  # переход к траве: тёмные кусты с рваным краем
        height = 38 + (x * 7 % 4) + rng.randint(0, 1)
        pygame.draw.circle(page, (50, 98, 66), (x, height), 5)
    page.fill((50, 98, 66), (0, 38, WIDTH, 5))
    for x in range(0, WIDTH, 3):  # травяная бахрома поверх кустов
        page.fill(GRASS_DEEP_COLOR, (x, 44 + (x * 5 % 3), 2, 2))
    # Боковые деревья у краёв поляны.
    for side in (0, WIDTH):
        for y in range(54, STATUS_TOP, 14):
            pygame.draw.circle(page, (50, 98, 66), (side + (-1 if side == 0 else 1) * 1, y + rng.randint(-2, 2)), 8)
            pygame.draw.circle(page, (74, 126, 82), (side + (3 if side == 0 else -3), y - 2), 4)


def _hedge(page: pygame.Surface, rng: random.Random) -> None:
    """Низкая живая изгородь по нижнему краю с проходом у точки появления."""
    for x in range(-2, WIDTH + 2, 6):
        if 138 <= x <= 182:
            continue
        pygame.draw.circle(page, (50, 98, 66), (x, STATUS_TOP + 1), 5)
    for x in range(-2, WIDTH + 2, 6):
        if 138 <= x <= 182:
            continue
        pygame.draw.circle(page, (88, 142, 86), (x - 1, STATUS_TOP - 1), 3)
        if rng.random() < 0.5:
            page.fill(FLOWER_COLORS[rng.randrange(len(FLOWER_COLORS))], (x, STATUS_TOP - 3, 2, 2))
    page.fill((50, 98, 66), (0, STATUS_TOP + 2, WIDTH, HEIGHT - STATUS_TOP))


def _dither_ellipse(overlay: pygame.Surface, color: config.Color, center: tuple[float, float],
                    radii: tuple[float, float], band: float = 0.3) -> None:
    """Эллипс пятна: внутри сплошной, у края — шахматная россыпь (мягкий переход без полупрозрачности)."""
    cx, cy = center
    rx, ry = radii
    for y in range(max(0, int(cy - ry)), min(HEIGHT, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(WIDTH, int(cx + rx) + 1)):
            d = math.hypot((x - cx) / rx, (y - cy) / ry)
            if d >= 1:
                continue
            if d < 1 - band or ((x + y) % 2 == 0 and d < 1 - band * 0.35) or (x % 2 == 0 and y % 2 == 0):
                overlay.set_at((x, y), color)


def _light_and_shade(overlay: pygame.Surface) -> None:
    """Пятна света в центре поляны и сочной тени по краям."""
    _dither_ellipse(overlay, GRASS_LIGHT_COLOR, (160, 112), (96, 46), 0.4)
    _dither_ellipse(overlay, GRASS_LIGHT_COLOR, (44, 106), (34, 16), 0.5)
    _dither_ellipse(overlay, GRASS_LIGHT_COLOR, (276, 106), (34, 16), 0.5)
    for center, radii in (((14, 150), (36, 18)), ((304, 150), (36, 18)), ((18, 58), (26, 14)), ((302, 58), (26, 14)),
                          ((160, 164), (60, 6))):
        _dither_ellipse(overlay, GRASS_DEEP_COLOR, center, radii, 0.5)


def _plaza(overlay: pygame.Surface) -> None:
    """Каменная площадка вокруг стола: плитка по кольцам и золотые знаки по краю."""
    cx, cy = PLAZA_CENTER
    rx, ry = PLAZA_RADII
    pygame.draw.ellipse(overlay, PLAZA_EDGE_COLOR, (cx - rx - 1, cy - ry - 1, rx * 2 + 2, ry * 2 + 2))
    pygame.draw.ellipse(overlay, PLAZA_COLOR, (cx - rx, cy - ry, rx * 2, ry * 2))
    pygame.draw.ellipse(overlay, PATH_LIGHT_COLOR, (cx - rx + 5, cy - ry + 3, rx * 2 - 10, ry * 2 - 6))
    pygame.draw.ellipse(overlay, PLAZA_COLOR, (cx - rx + 9, cy - ry + 6, rx * 2 - 18, ry * 2 - 12))
    for k in range(24):  # плитки по внешнему кольцу
        a = k * math.tau / 24
        x, y = cx + math.cos(a) * (rx - 3), cy + math.sin(a) * (ry - 2)
        overlay.fill(PLAZA_EDGE_COLOR, (round(x) - 1, round(y), 3, 1))
        x, y = cx + math.cos(a + 0.13) * (rx - 7), cy + math.sin(a + 0.13) * (ry - 4)
        overlay.fill(PATH_SHADE_COLOR, (round(x), round(y), 2, 1))
    for k in range(12):  # золотые знаки
        a = k * math.tau / 12 + math.pi / 12
        x, y = round(cx + math.cos(a) * (rx - 5)), round(cy + math.sin(a) * (ry - 3))
        overlay.fill(RUNE_COLOR, (x, y - 1, 1, 3))
        overlay.fill(RUNE_COLOR, (x - 1, y, 3, 1))


def _path(overlay: pygame.Surface, points: Sequence[tuple[float, float]], width: float, rng: random.Random) -> None:
    """Тропинка вдоль кривой: светлая середина, тёмная кайма и мелкие камешки."""
    curve = spline(points, 10)
    for color, extra in ((PATH_EDGE_COLOR, 1.0), (PATH_COLOR, 0.0)):
        for x, y in curve:
            pygame.draw.circle(overlay, color, (round(x), round(y)), round(width / 2 + extra))
    for x, y in curve:
        pygame.draw.circle(overlay, PATH_LIGHT_COLOR, (round(x - 1), round(y - 1)), round(width / 2 - 3))
    for x, y in curve[::2]:
        for _ in range(2):
            px = round(x + rng.uniform(-width / 2 + 2, width / 2 - 2))
            py = round(y + rng.uniform(-width / 2 + 2, width / 2 - 2))
            overlay.fill(PATH_SHADE_COLOR if rng.random() < 0.6 else PATH_EDGE_COLOR, (px, py, 2, 1))


def _mat(overlay: pygame.Surface, cx: int, top: int, color: config.Color, trim: config.Color) -> None:
    """Коврик у входа в дерево: тут Алиса стоит, когда заходит."""
    rect = pygame.Rect(cx - 10, top, 20, 8)
    pygame.draw.rect(overlay, mix(color, (30, 20, 30), 0.5), rect.inflate(2, 2), border_radius=2)
    pygame.draw.rect(overlay, color, rect, border_radius=2)
    pygame.draw.rect(overlay, trim, rect.inflate(-4, -4), 1)
    overlay.fill(mix(color, (255, 255, 255), 0.4), (rect.left + 2, rect.top + 1, rect.width - 4, 1))


def _spawn_mat(overlay: pygame.Surface) -> None:
    x, y = SPAWN_MAT
    pygame.draw.ellipse(overlay, PATH_EDGE_COLOR, (x - 13, y - 5, 26, 10))
    pygame.draw.ellipse(overlay, SPAWN_COLOR, (x - 12, y - 4, 24, 8))
    pygame.draw.ellipse(overlay, PATH_LIGHT_COLOR, (x - 8, y - 3, 16, 5), 1)


def _occupied_mask(overlay: pygame.Surface) -> pygame.mask.Mask:
    """Где уже лежит тропинка, площадка или коврик: там цветы не растут."""
    return pygame.mask.from_surface(overlay, 200)


def _scatter(overlay: pygame.Surface, occupied: pygame.mask.Mask, rng: random.Random, reserved: Sequence[pygame.Rect]) -> None:
    """Цветы, травинки и камешки на свободной земле; ничего не лежит на тропинках и под деревьями."""
    keep_out = [pygame.Rect(10, 44, 70, 48), pygame.Rect(244, 44, 70, 48), pygame.Rect(130, 44, 62, 30),
                pygame.Rect(126, 82, 68, 54)]
    keep_out += list(reserved)

    def free(x: int, y: int, margin: int = 2) -> bool:
        if not (8 <= x < WIDTH - 8 and 52 <= y < STATUS_TOP - 2):
            return False
        if any(rect.inflate(margin * 2, margin * 2).collidepoint(x, y) for rect in keep_out):
            return False
        for dx in (-margin, 0, margin):
            for dy in (-margin, 0, margin):
                if 0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT and occupied.get_at((x + dx, y + dy)):
                    return False
        return True

    for _ in range(420):  # травинки: тёмный и светлый пучок
        x, y = rng.randrange(8, WIDTH - 8), rng.randrange(52, STATUS_TOP - 2)
        if free(x, y, 1):
            tuft = GRASS_DEEP_COLOR if rng.random() < 0.55 else GRASS_LIGHT_COLOR
            overlay.fill(tuft, (x, y, 1, 3))
            overlay.fill(tuft, (x + 2, y + 1, 1, 2))
            overlay.fill(mix(tuft, (255, 255, 220), 0.25), (x + 1, y, 1, 2))
    for _ in range(190):  # цветы: крестик из лепестков и серединка
        x, y = rng.randrange(8, WIDTH - 8), rng.randrange(52, STATUS_TOP - 2)
        if free(x, y, 3):
            color = FLOWER_COLORS[rng.randrange(len(FLOWER_COLORS))]
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                overlay.set_at((x + dx, y + dy), color)
            overlay.set_at((x, y), (250, 210, 90) if color != FLOWER_COLORS[1] else (214, 120, 60))
    for _ in range(46):  # камешки
        x, y = rng.randrange(8, WIDTH - 8), rng.randrange(52, STATUS_TOP - 2)
        if free(x, y, 2):
            overlay.fill((176, 178, 190), (x, y, 2, 1))
            overlay.set_at((x, y + 1), (110, 112, 130))
    for _ in range(26):  # клевер
        x, y = rng.randrange(8, WIDTH - 8), rng.randrange(52, STATUS_TOP - 2)
        if free(x, y, 2):
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                overlay.set_at((x + dx * 2, y + dy * 2), (96, 150, 90))
