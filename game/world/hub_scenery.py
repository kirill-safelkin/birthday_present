"""Оформление центральной площади: три волшебных дерева-входа, стол мозаики, мелкие предметы.

Всё нарисовано кодом (game/graphics/pixel_art.py) и собирается один раз при первом обращении:
картинки общие для всех площадей. Здесь только внешний вид и «геометрия» предметов — где они
стоят и что из них препятствие; ходьба, взаимодействия и порядок отрисовки — в game/world/hub.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import pygame

import config
from game.graphics.pixel_art import (
    SCALE,
    Art,
    Palette,
    Piece,
    glow_sprite,
    mix,
    palette_from,
    sparkle_sprite,
    spline,
)

# --- Палитры ---

BARK: Palette = ((44, 26, 28), (84, 52, 42), (126, 84, 58), (168, 118, 80), (204, 154, 108))
BARK_GREY: Palette = ((40, 30, 42), (76, 58, 66), (112, 88, 88), (150, 122, 112), (186, 160, 142))
LEAVES_DEEP: Palette = ((22, 56, 50), (34, 90, 70), (54, 126, 82), (92, 166, 94), (146, 210, 120))
LEAVES_LUSH: Palette = ((30, 70, 50), (48, 112, 66), (84, 164, 82), (132, 200, 98), (186, 232, 132))
LEAVES_BLUE: Palette = ((28, 48, 58), (52, 82, 90), (82, 120, 112), (122, 158, 132), (170, 196, 156))
MOSS: Palette = ((40, 82, 52), (62, 120, 66), (96, 158, 80), (140, 196, 100), (190, 226, 130))
STONE: Palette = ((52, 54, 74), (92, 94, 118), (132, 134, 156), (170, 172, 190), (208, 210, 224))

RED = (206, 60, 58)
CREAM = (252, 240, 214)
GOLD = (250, 206, 108)
WARM_LIGHT = (255, 214, 130)
DOOR_DARK = (18, 10, 22)
DOOR_WARM = (132, 78, 50)


@dataclass(frozen=True)
class TreeSpec:
    """Где стоит дерево-вход и как к нему подойти: общие размеры для рисунка и для игры."""

    id: str
    cx: int  # середина ствола
    ground: int  # линия земли у ствола: ниже неё дерево не закрывает землю
    door_size: tuple[int, int]  # ширина и высота отверстия
    sign: pygame.Rect  # табличка (холст); надпись рисует слой высокого разрешения
    sign_text: str
    block: pygame.Rect  # препятствие: ствол и крона (с земли в крону не зайти)
    stand: tuple[int, int]  # где стоят ноги Алисы у отверстия
    radius: int  # с такого расстояния от stand вход открывается

    @property
    def door(self) -> pygame.Rect:
        width, height = self.door_size
        return pygame.Rect(round(self.cx - width / 2), round(self.ground - 0.5 - height), width, height)


TREE_SPECS = {
    "sushi": TreeSpec("sushi", 44, 90, (14, 16), pygame.Rect(25, 54, 38, 10), "СУШИ",
                      pygame.Rect(12, 44, 64, 46), (44, 97), 12),
    "forms": TreeSpec("forms", 160, 72, (11, 18), pygame.Rect(123, 35, 74, 11), "ФОРМУЛЯРЫ",
                      pygame.Rect(132, 44, 56, 28), (160, 80), 12),
    "cakes": TreeSpec("cakes", 276, 90, (14, 16), pygame.Rect(249, 54, 54, 10), "ТОРТИКИ",
                      pygame.Rect(244, 44, 64, 46), (276, 97), 12),
}


@dataclass(frozen=True)
class TreeArt:
    """Готовое дерево-вход: его описание, картинка и огоньки, которые на нём мерцают."""

    spec: TreeSpec
    piece: Piece
    lights: tuple[tuple[float, float, config.Color, float], ...] = ()  # огоньки: x, y холста, цвет, радиус
    garland: tuple[Piece, ...] = ()  # свечение лампочек гирлянды тремя группами: мерцают по очереди


def _arch_color(t: float, edge: float) -> config.Color:
    """Внутри дупла: сверху тьма, к полу теплеет; у стенок чуть темнее."""
    color = mix(DOOR_DARK, DOOR_WARM, max(0.0, t - 0.35) ** 1.6 * 1.7)
    return mix(color, DOOR_DARK, max(0.0, 0.45 - edge))


def _door(art: Art, x: float, bottom: float, w: float, h: float, rim: Palette, moss: bool = True) -> pygame.Rect:
    """Дупло-дверца: тёмный проём в живом стволе с неровным краем из коры и мхом сверху."""
    art.arch_rows(lambda t, e: rim[0], x, bottom + 1, w + 3.5, h + 2.5)
    art.arch_rows(lambda t, e: rim[2] if e > 0.0 else rim[1], x, bottom + 0.5, w + 2.5, h + 1.5)
    art.arch_rows(lambda t, e: rim[3], x - 0.3, bottom, w + 1, h + 0.5)  # свет на левой кромке
    art.arch_rows(_arch_color, x, bottom, w, h)
    if moss:
        for k in range(-4, 5):  # мох над входом
            art.ball(MOSS, x + k * w / 8.5, bottom - h + 0.6 + abs(k) * 0.35, 1.5 + (k % 2) * 0.4, outline=False)
    return pygame.Rect(round(x - w / 2), round(bottom - h), round(w), round(h))


def _roots(art: Art, x: float, ground: float, spread: float, palette: Palette, girth: float) -> None:
    """Корни, расходящиеся от ствола по земле."""
    for side, reach, depth in ((-1, 1.0, 0.0), (1, 0.95, 0.0), (-1, 0.62, 3.0), (1, 0.6, 3.0), (-1, 0.32, 5.0), (1, 0.3, 5.0)):
        points = [(x + side * girth * 0.5, ground - 8 + depth * 0.4),
                  (x + side * (girth * 0.9 + spread * reach * 0.4), ground - 2 + depth * 0.2),
                  (x + side * (girth + spread * reach), ground + 1.2 + depth * 0.45)]
        curve = spline(points, 8)
        radii = [max(0.8, 4.6 * (1 - i / len(curve)) * (0.5 + reach / 2) + 0.7) for i in range(len(curve))]
        art.tube(curve, radii, palette, texture=0.0)


def _lantern(art: Art, x: float, y: float, color: config.Color, band: config.Color = CREAM) -> None:
    """Круглый бумажный фонарик с поясом и кисточкой."""
    art.line((60, 40, 40), (x, y - 5), (x, y - 2.6), 0.5)
    art.ball(palette_from(color), x, y, 3.3)
    art.rect_(band, x - 2.6, y - 0.6, 5.2, 1.3)
    art.rect_((70, 50, 40), x - 1.3, y - 3.9, 2.6, 1.0)
    art.line((250, 220, 120), (x, y + 3.2), (x, y + 5.4), 0.5)


def _fish(art: Art, x: float, y: float, color: config.Color) -> None:
    """Рыбка-подвеска: серебристое тельце, хвост, глаз."""
    art.line((70, 60, 50), (x, y - 5), (x, y - 1.6), 0.4)
    art.ellipse(palette_from(color)[1], x, y, 3.0, 1.9)
    art.ellipse(color, x - 0.2, y - 0.2, 2.6, 1.5)
    art.polygon(palette_from(color)[1], [(x + 2.6, y), (x + 4.6, y - 1.7), (x + 4.6, y + 1.7)])
    art.dot((20, 20, 40), x - 1.6, y - 0.4, 2)


def _sign_board(art: Art, rect: pygame.Rect, board: Palette, rope: config.Color, ropes_from: float) -> None:
    """Табличка на двух верёвках: дерево с каймой; надпись рисует слой окна."""
    for x in (rect.left + 3, rect.right - 3):
        art.line(rope, (x, ropes_from), (x, rect.top + 1), 0.6)
    art.rect_(board[0], rect.x - 1, rect.y - 1, rect.w + 2, rect.h + 2, radius=2)
    art.rect_(board[2], rect.x, rect.y, rect.w, rect.h, radius=2)
    art.rect_(board[3], rect.x + 1, rect.y + 0.5, rect.w - 2, 1.0)  # светлая верхняя кромка
    art.rect_(board[1], rect.x + 1, rect.bottom - 1.5, rect.w - 2, 1.0)  # тёмная нижняя
    for x in (rect.left + 2.0, rect.right - 2.0):  # гвоздики
        art.dot(board[4], x, rect.centery, 2)


def _glow_group(points: Sequence[tuple[float, float]], color: config.Color, radius: float, peak: int) -> Piece:
    """Свечение сразу нескольких точек одной картинкой (одной командой вместо нескольких)."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    rect = pygame.Rect(math.floor(min(xs) - radius), math.floor(min(ys) - radius),
                       math.ceil(max(xs) - min(xs) + radius * 2) + 1, math.ceil(max(ys) - min(ys) + radius * 2) + 1)
    art = Art(rect)
    halo = glow_sprite(radius, color, peak)
    for x, y in points:
        art.surface.blit(halo, art.at(x - radius, y - radius), special_flags=pygame.BLEND_RGBA_MAX)
    return Piece(art.surface, rect)


# --- Дерево суши ---

def build_sushi_tree() -> TreeArt:
    """Старое «подстриженное облаками» дерево с красно-белыми украшениями."""
    spec = TREE_SPECS["sushi"]
    cx, ground = spec.cx, spec.ground
    art = Art(pygame.Rect(0, 14, 90, 86), seed=11)
    red_white = palette_from((196, 60, 60))
    # Корни и ствол: широкий, чуть изогнутый, с наклоном ветвей в стороны.
    _roots(art, cx, ground, 17, BARK, 11)
    trunk = spline([(cx, ground + 1), (cx - 1, 80), (cx + 1, 70), (cx - 1.5, 60), (cx, 52)], 10)
    art.tube(trunk, [15 - 5 * i / len(trunk) for i in range(len(trunk))], BARK, texture=0.9)
    # Ветви к «подушкам» листвы.
    for points, widths in (
        ([(cx - 3, 62), (cx - 14, 58), (cx - 22, 54), (cx - 27, 52)], (4.2, 3.0, 2.2, 1.6)),
        ([(cx + 3, 58), (cx + 13, 52), (cx + 21, 44), (cx + 24, 40)], (4.2, 3.0, 2.2, 1.6)),
        ([(cx, 56), (cx - 1, 46), (cx + 1, 38), (cx, 32)], (4.4, 3.2, 2.4, 1.8)),
    ):
        curve = spline(points, 8)
        art.tube(curve, [widths[min(3, int(i / len(curve) * 4))] for i in range(len(curve))], BARK, texture=0.4)
    # Три «облачные подушки» листвы с просветами: низкая широкая слева, высокая в середине, небольшая справа.
    art.cluster([(cx - 36, 52, 6), (cx - 30, 49, 8), (cx - 22, 52, 8), (cx - 15, 54, 6.5), (cx - 27, 56, 6.5), (cx - 38, 57, 4.5)], LEAVES_DEEP)
    art.cluster([(cx - 8, 31, 8), (cx, 25, 9.5), (cx + 9, 24, 9.5), (cx + 17, 29, 8), (cx + 2, 34, 9.5), (cx + 11, 34, 8)], LEAVES_DEEP)
    art.cluster([(cx + 23, 44, 7), (cx + 30, 42, 7.5), (cx + 35, 46, 5.5), (cx + 28, 49, 6)], LEAVES_DEEP)
    # Красно-белые бутоны в кроне.
    for x, y in ((cx - 31, 48), (cx - 22, 51), (cx - 4, 27), (cx + 12, 27), (cx + 28, 42), (cx + 5, 33)):
        art.ball(red_white, x, y, 1.7)
        art.dot(CREAM, x - 0.4, y - 0.5, 2)
    # Красно-белая гирлянда флажков, провисающая через крону.
    flags = spline([(cx - 36, 50), (cx - 18, 57), (cx, 59.5), (cx + 18, 56), (cx + 35, 49)], 14)
    art.lines((70, 40, 36), flags, 0.4)
    for i in range(2, len(flags) - 2, 4):
        x, y = flags[i]
        art.polygon(RED if (i // 4) % 2 == 0 else CREAM, [(x - 1.8, y), (x + 1.8, y), (x, y + 4.2)])
    # Подвески: два фонарика и рыбка.
    _lantern(art, cx - 33, 62, RED)
    _lantern(art, cx + 33, 59, (232, 120, 60))
    _fish(art, cx + 27, 62, (150, 190, 220))
    # Табличка «СУШИ».
    sign = spec.sign
    _sign_board(art, sign, ((60, 18, 24), (130, 26, 36), (186, 44, 52), (232, 102, 96), (250, 190, 120)), (90, 60, 40), 50)
    # Дверца и шторка-норэн над ней.
    door = _door(art, cx, ground - 0.5, *spec.door_size, BARK)
    assert door == spec.door
    art.rect_((40, 20, 40), door.left - 0.6, door.top + 3.6, door.w + 1.2, 1.0)  # палочка
    for k in range(3):
        left = door.left + k * door.w / 3
        art.rect_(RED if k != 1 else (230, 90, 80), left + 0.3, door.top + 4.6, door.w / 3 - 0.6, 4.4, radius=1)
        art.circle(CREAM, left + door.w / 6, door.top + 6.4, 0.9)
    # Грибы у корней: красный мухомор и «нигири» — белая шляпка с ломтиком лосося.
    _mushroom(art, cx - 21, ground + 4, 6, RED, dots=True)
    _mushroom(art, cx - 16, ground + 6, 4, RED, dots=True)
    _nigiri_mushroom(art, cx + 21, ground + 5)
    _mushroom(art, cx + 27, ground + 6, 4, (232, 150, 70), dots=True)
    return TreeArt(spec, art.piece(), lights=((cx - 33, 62, (255, 120, 80), 7.0), (cx + 33, 59, (255, 170, 80), 7.0)))


def _mushroom(art: Art, x: float, y: float, height: float, cap: config.Color, dots: bool = False) -> None:
    """Гриб со ножкой и шляпкой; (x, y) — основание ножки."""
    stem = palette_from((236, 224, 200))
    art.rect_(stem[1], x - height * 0.17, y - height * 0.7, height * 0.34, height * 0.72, radius=1)
    art.rect_(stem[3], x - height * 0.17, y - height * 0.7, height * 0.16, height * 0.7)
    cap_palette = palette_from(cap)
    art.ellipse(cap_palette[0], x, y - height * 0.78, height * 0.62 + 0.5, height * 0.4 + 0.5)
    art.ellipse(cap_palette[2], x, y - height * 0.78, height * 0.62, height * 0.4)
    art.ellipse(cap_palette[3], x - height * 0.15, y - height * 0.9, height * 0.38, height * 0.2)
    if dots:
        for dx, dy in ((-0.28, -0.8), (0.1, -0.98), (0.3, -0.7)):
            art.circle(CREAM, x + dx * height, y + dy * height, max(0.5, height * 0.09))


def _nigiri_mushroom(art: Art, x: float, y: float) -> None:
    """Необычный гриб: шляпка как комок риса, сверху ломтик лосося."""
    art.rect_((230, 214, 190), x - 0.9, y - 4.0, 1.8, 4.2, radius=1)
    art.ellipse((200, 190, 170), x, y - 4.3, 4.4, 2.8)
    art.ellipse((250, 248, 240), x, y - 4.7, 4.2, 2.6)
    art.ellipse((246, 130, 96), x, y - 6.0, 3.8, 1.5)
    art.line((255, 190, 150), (x - 2.4, y - 6.2), (x + 2.2, y - 6.2), 0.4)


@lru_cache(maxsize=1)
def sushi_tree() -> TreeArt:
    return build_sushi_tree()


# --- Дерево формуляров ---

def _paper_note(art: Art, x: float, y: float, tilt: float = 0.0, stamp: bool = False) -> None:
    """Бумажка вместо листка: белый прямоугольник со строчками и, может быть, печатью."""
    w, h = 4.0, 5.0
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    cos, sin = math.cos(tilt), math.sin(tilt)
    art.polygon((70, 70, 84), [(x + cx * cos - cy * sin + 0.3, y + cx * sin + cy * cos + 0.3) for cx, cy in corners])
    art.polygon((248, 246, 236), [(x + cx * cos - cy * sin, y + cx * sin + cy * cos) for cx, cy in corners])
    for k in range(3):
        a = (x - 1.3 * cos + (-1.3 + k * 1.1) * -sin, y - 1.3 * sin + (-1.3 + k * 1.1) * cos)
        b = (x + 1.3 * cos + (-1.3 + k * 1.1) * -sin, y + 1.3 * sin + (-1.3 + k * 1.1) * cos)
        art.line((126, 136, 160), a, b, 0.3)
    if stamp:
        art.circle((200, 54, 60), x + 0.9, y + 1.2, 0.9)


def _shelf_fungus(art: Art, x: float, y: float, w: float, palette: Palette) -> None:
    """Трутовик: полукруглая полка на стволе."""
    art.ellipse(palette[0], x, y, w / 2 + 0.5, 2.2)
    art.ellipse(palette[2], x, y - 0.3, w / 2, 1.8)
    art.ellipse(palette[3], x - w * 0.12, y - 0.8, w * 0.32, 0.8)


def build_forms_tree() -> TreeArt:
    """Строгое, перекошенное дерево: извилистый ствол, наросты и бумажки вместо листьев."""
    spec = TREE_SPECS["forms"]
    cx, ground = spec.cx, spec.ground
    art = Art(pygame.Rect(116, 12, 88, 70), seed=23)
    _roots(art, cx, ground, 12, BARK_GREY, 8)
    spine = spline([(cx, ground + 1), (cx - 5, 66), (cx + 3, 58), (cx - 4, 50), (cx + 2, 43), (cx - 1, 36), (cx, 32)], 10)
    art.tube(spine, [9.4 - 3.0 * i / len(spine) for i in range(len(spine))], BARK_GREY, texture=0.8)
    # Наросты со «спиралями» и пачка трутовиков, похожая на стопку бумаг.
    for x, y, r in ((cx - 8.5, 61, 3.8), (cx + 6.5, 53, 3.2), (cx - 7, 47, 2.8), (cx + 7, 66, 2.4)):
        art.ball(BARK_GREY, x, y, r)
        art.ellipse(BARK_GREY[0], x - 0.3, y - 0.2, r * 0.45, r * 0.3, 1)
    for k, (dy, w) in enumerate(((0, 8.0), (-2.6, 7.0), (-5.2, 6.0))):
        _shelf_fungus(art, cx - 2.2 + 11 - 0.4, 63 + dy + 0.0, w, palette_from((226, 196, 140) if k % 2 == 0 else (236, 220, 190)))
    # Угловатые ветви: к краям кроны под прямыми углами.
    for points in (
        [(cx, 40), (cx - 10, 36), (cx - 17, 35), (cx - 22, 28), (cx - 26, 24)],
        [(cx, 38), (cx + 9, 34), (cx + 18, 34), (cx + 22, 26), (cx + 27, 23)],
        [(cx - 1, 36), (cx - 2, 30), (cx + 2, 24)],
    ):
        curve = spline(points, 4)
        art.tube(curve, [max(1.0, 3.0 - 2.0 * i / len(curve)) for i in range(len(curve))], BARK_GREY, texture=0.3)
    art.dy = 3  # крона ниже: верхушка не должна уходить под полосу интерфейса
    # Крона-«пирамида чинов»: три яруса, каждый шире верхнего, края подстрижены под линейку.
    lumps = []
    for y, count, r in ((15.5, 5, 5.6), (21.5, 7, 6.0), (28.0, 9, 6.2)):
        step = 9.2
        for i in range(count):
            x = cx + (i - (count - 1) / 2) * step
            lumps.append((x, y + (1.5 if i in (0, count - 1) else 0), r))
    art.cluster(lumps, LEAVES_BLUE)
    # Бумажки на ветвях и на нитках.
    for x, y, tilt, stamp in ((cx - 32, 29, -0.3, False), (cx - 22, 25, 0.2, True), (cx - 10, 31, -0.1, False),
                              (cx + 4, 32, 0.35, False), (cx + 16, 28, -0.25, True), (cx + 30, 30, 0.2, False),
                              (cx - 18, 19, 0.15, False), (cx + 6, 17, -0.2, False), (cx + 18, 20, 0.3, True),
                              (cx - 4, 24, 0.1, True), (cx - 28, 22, -0.1, False)):
        _paper_note(art, x, y, tilt, stamp)
    for x, y in ((cx - 36, 34), (cx + 36, 34)):
        art.line((60, 56, 70), (x, y), (x, y + 6), 0.3)
        _paper_note(art, x, y + 8, 0.1, stamp=x < cx)
    art.dy = 0
    # Табличка «ФОРМУЛЯРЫ» на верёвках от кроны.
    sign = spec.sign
    _sign_board(art, sign, ((26, 34, 64), (44, 60, 108), (78, 104, 164), (130, 154, 206), (206, 220, 246)), (100, 84, 70), 30)
    door = _door(art, cx, ground - 0.5, *spec.door_size, BARK_GREY, moss=False)
    assert door == spec.door
    # Номерная бляшка над дверью и печать на коре.
    art.rect_((196, 170, 104), cx - 2.6, door.top - 4.0, 5.2, 2.4, radius=1)
    art.dot((80, 64, 40), cx - 1.0, door.top - 2.8, 1)
    art.dot((80, 64, 40), cx + 0.6, door.top - 2.8, 1)
    art.circle((190, 44, 56), cx - 8.4, 53.0, 2.0)
    art.circle((226, 90, 96), cx - 8.6, 52.7, 1.1)
    return TreeArt(spec, art.piece())


@lru_cache(maxsize=1)
def forms_tree() -> TreeArt:
    return build_forms_tree()


# --- Дерево тортиков ---

def _blossom(art: Art, x: float, y: float, petal: config.Color, r: float = 1.1) -> None:
    for k in range(5):
        a = k * math.tau / 5 - 1.2
        art.circle(petal, x + math.cos(a) * r * 1.15, y + math.sin(a) * r * 1.15, r)
    art.circle((255, 224, 120), x, y, r * 0.75)


def _strawberry(art: Art, x: float, y: float) -> None:
    art.line((60, 40, 40), (x, y - 4.5), (x, y - 2), 0.4)
    art.ball(palette_from((222, 48, 66)), x, y, 2.4)
    art.polygon((70, 160, 70), [(x - 1.6, y - 2.3), (x, y - 3.2), (x + 1.6, y - 2.3), (x, y - 1.2)])
    for dx, dy in ((-0.9, -0.2), (0.7, -0.6), (0.1, 0.7), (1.0, 0.6), (-0.7, 1.0)):
        art.dot((255, 230, 150), x + dx, y + dy, 1)


def _candle(art: Art, x: float, base: float, height: float, stripe: config.Color) -> None:
    art.rect_((70, 50, 60), x - 1.2, base - height - 0.5, 2.4, height + 1)
    art.rect_(CREAM, x - 1.0, base - height, 2.0, height)
    for k in range(0, int(height), 3):
        art.rect_(stripe, x - 1.0, base - height + k + 0.5, 2.0, 1.2)
    art.ellipse((255, 150, 60), x, base - height - 1.4, 1.1, 1.8)
    art.ellipse((255, 232, 150), x, base - height - 1.1, 0.6, 1.1)


def build_cakes_tree() -> TreeArt:
    """Самое нарядное дерево: круглая крона в цветах и ягодах, крем по краю, гирлянда и свечки."""
    spec = TREE_SPECS["cakes"]
    cx, ground = spec.cx, spec.ground
    art = Art(pygame.Rect(232, 12, 88, 88), seed=37)
    _roots(art, cx, ground, 16, BARK, 12)
    trunk = spline([(cx, ground + 1), (cx + 1, 80), (cx - 1, 70), (cx, 58)], 10)
    art.tube(trunk, [15.5 - 4 * i / len(trunk) for i in range(len(trunk))], BARK, texture=0.7)
    # «Крем из кондитерского мешка»: ряды сливочных точек по спирали вокруг ствола.
    for k in range(18):
        t = k / 18
        y = 84 - t * 24
        x = cx + math.sin(t * 9.0) * (13.5 - 3 * t)
        art.ball(palette_from((250, 232, 214)), x, y, 1.3, outline=False)
    art.dy = 4  # крона ниже: свечки не должны уходить под полосу интерфейса
    # Круглая крона: большой купол из клубов.
    lumps = [(cx + dx, y, r) for dx, y, r in (
        (-8, 23, 9.5), (4, 21, 10), (15, 25, 9), (-19, 29, 9), (-5, 28, 12), (10, 30, 11.5), (22, 34, 9.5),
        (-25, 38, 9), (-13, 37, 12), (1, 37, 12.5), (15, 40, 11.5), (27, 43, 9),
        (-23, 47, 9.5), (-12, 48, 10.5), (0, 49, 11), (12, 50, 10.5), (23, 51, 9),
    )]
    art.cluster(lumps, LEAVES_LUSH)
    # Сливочная кайма по нижнему краю: белые «капли» разной длины.
    for i, dx in enumerate(range(-30, 31, 5)):
        art.ball(palette_from((252, 238, 232)), cx + dx, 56.5 + (i % 3) * 0.9 - abs(dx) * 0.04, 2.7 - (i % 2) * 0.3)
        if i % 2 == 0:
            art.ball(palette_from((246, 190, 210)), cx + dx + 1.2, 59.3 + (i % 3) * 0.6, 1.5, outline=False)
    # Цветы и ягоды.
    pinks = ((248, 182, 206), (252, 214, 226), (255, 150, 186))
    for k, (dx, y) in enumerate(((-26, 36), (-16, 29), (-4, 24), (8, 23), (17, 29), (26, 38), (-21, 44), (-9, 41), (4, 41),
                                  (14, 46), (24, 46), (-28, 49), (-14, 53), (0, 53), (12, 54), (-2, 31), (20, 36), (-10, 33))):
        _blossom(art, cx + dx, y, pinks[k % 3])
    for dx, y in ((-20, 38), (-7, 46), (6, 33), (19, 43), (-1, 40), (27, 48), (-26, 44)):
        _strawberry(art, cx + dx, y)
    # Гирлянда: тёплые лампочки на проводе через крону.
    wire = spline([(cx - 33, 40), (cx - 18, 49), (cx, 53), (cx + 18, 49), (cx + 33, 41)], 16)
    art.lines((60, 44, 40), wire, 0.4)
    bulbs = []
    for i in range(3, len(wire) - 3, 5):
        x, y = wire[i]
        bulbs.append((x, y + 1.4 + 4))
        art.ball(palette_from(WARM_LIGHT), x, y + 1.4, 1.35, outline=False)
        art.dot((255, 250, 220), x - 0.3, y + 1.0, 1)
    # Свечки на макушке.
    for dx, h, color in ((-12, 7, (240, 110, 150)), (-6, 9, (110, 190, 230)), (0, 10, (250, 190, 90)),
                         (6, 9, (240, 110, 150)), (12, 7, (110, 190, 230))):
        _candle(art, cx + dx, 21.5 + abs(dx) * 0.25, h, color)
    art.dy = 0
    # Табличка «ТОРТИКИ» с вишенками.
    sign = spec.sign
    _sign_board(art, sign, ((92, 20, 62), (150, 40, 100), (206, 76, 142), (244, 150, 192), (255, 214, 232)), (120, 90, 70), 50)
    for x in (sign.left + 1, sign.right - 1):
        art.line((60, 100, 60), (x, sign.top - 1), (x + 1.4, sign.top - 3.4), 0.4)
        art.ball(palette_from((220, 36, 60)), x, sign.top + 0.2, 1.7, outline=False)
    door = _door(art, cx, ground - 0.5, *spec.door_size, BARK, moss=False)
    assert door == spec.door
    # Розовый «глазурный» ободок над входом и клубничка.
    for k in range(-3, 4):
        art.ball(palette_from((250, 170, 200)), cx + k * 2.4, door.top - 0.6 + abs(k) * 0.8, 1.7, outline=False)
    _strawberry(art, cx, door.top - 4.0)
    lights = tuple((cx + dx, 21.5 + 4 + abs(dx) * 0.25 - h - 1.4, (255, 190, 90), 5.0)
                    for dx, h in ((-12, 7), (-6, 9), (0, 10), (6, 9), (12, 7)))
    garland = tuple(_glow_group(bulbs[k::3], WARM_LIGHT, 3.4, 170) for k in range(3))
    return TreeArt(spec, art.piece(), lights=lights, garland=garland)


@lru_cache(maxsize=1)
def cakes_tree() -> TreeArt:
    return build_cakes_tree()


# --- Стол мозаики ---

TABLE_CENTER = (160, 102)  # центр столешницы
TABLE_RX, TABLE_RY = 34, 17  # полуоси столешницы
TABLE_THICKNESS = 8  # толщина обода
SLOT_SIZE = 12  # сторона фрагмента на столе, логических пикселей
# Гнёзда фрагментов: у каждого испытания своё место на столешнице.
MOSAIC_SLOTS = {"sushi": (145, 106), "forms": (160, 96), "cakes": (175, 106)}
WOOD: Palette = ((52, 30, 30), (98, 60, 44), (146, 96, 62), (186, 132, 86), (222, 172, 120))
FRAGMENT_COLORS = {"sushi": (190, 56, 66), "forms": (68, 98, 168), "cakes": (216, 92, 152)}
BOARD_COLOR = (84, 92, 136)
BOARD_EDGE = (36, 38, 62)
RUNE_COLOR = (236, 196, 112)


@dataclass(frozen=True)
class TableArt:
    """Стол мозаики: картинка со столом и пустыми гнёздами, готовые фрагменты, золотая вставка,
    видимая только у собранной мозаики, и «подсказки» — тусклые силуэты на пустых гнёздах."""

    body: Piece
    fragments: dict[str, Piece]
    inlay: Piece
    footprint: tuple[pygame.Rect, ...]  # препятствие под ногами: ступенчатый эллипс
    base_y: int  # линия земли у основания стола


def _fragment(trial_id: str) -> Art:
    """Фрагмент мозаики: квадратная плитка с гранью, тенью и символом своего испытания."""
    art = Art(pygame.Rect(0, 0, SLOT_SIZE, SLOT_SIZE))
    face = FRAGMENT_COLORS[trial_id]
    pal = palette_from(face)
    art.rect_(pal[0], 0, 0, SLOT_SIZE, SLOT_SIZE, radius=1)
    art.rect_(pal[3], 0.5, 0.5, SLOT_SIZE - 1, SLOT_SIZE - 1)  # светлая грань
    art.rect_(pal[1], 1.0, 1.0, SLOT_SIZE - 1.5, SLOT_SIZE - 1.5)  # тень снизу и справа
    art.rect_(face, 1.0, 1.0, SLOT_SIZE - 2.5, SLOT_SIZE - 2.5)
    u = SLOT_SIZE / 10  # символы нарисованы для плитки 10×10
    x = y = SLOT_SIZE / 2 - 0.3 * u
    if trial_id == "sushi":  # ролл: водоросль, рис, лосось, огурчик
        art.circle((24, 40, 36), x, y, 3.3 * u)
        art.circle((250, 248, 240), x, y, 2.6 * u)
        art.circle((248, 128, 96), x, y, 1.45 * u)
        art.dot((110, 176, 90), x + 0.9 * u, y - 0.7 * u, 3)
        art.dot((255, 255, 255), x - 1.3 * u, y - 1.3 * u, 3)
    elif trial_id == "forms":  # лист со строчками и печатью
        art.rect_((60, 70, 110), x - 2.9 * u, y - 3.5 * u, 5.8 * u, 7.2 * u, radius=1)
        art.rect_((250, 248, 238), x - 2.5 * u, y - 3.2 * u, 5.0 * u, 6.6 * u)
        for k in range(3):
            art.line((120, 130, 164), (x - 1.6 * u, y + (-2.2 + k * 1.2) * u), (x + (1.5 - (k == 2) * 1.4) * u, y + (-2.2 + k * 1.2) * u), 0.3 * u)
        art.circle((200, 52, 60), x + 1.0 * u, y + 1.9 * u, 1.2 * u)
        art.dot((250, 220, 220), x + 0.7 * u, y + 1.7 * u, 3)
    else:  # кусочек торта с вишенкой
        art.rect_((120, 70, 60), x - 3.2 * u, y + 2.2 * u, 6.4 * u, 1.0 * u)
        art.polygon((252, 228, 170), [(x - 3 * u, y + 2.2 * u), (x - 3 * u, y - 0.8 * u), (x + 3 * u, y - 0.8 * u), (x + 3 * u, y + 2.2 * u)])
        art.rect_((255, 255, 250), x - 3 * u, y + 0.2 * u, 6 * u, 0.9 * u)
        art.rect_((248, 160, 196), x - 3.2 * u, y - 1.8 * u, 6.4 * u, 1.5 * u, radius=1)
        art.circle((218, 34, 60), x + 0.3 * u, y - 2.5 * u, 1.2 * u)
    return art


def _rune(art: Art, x: float, y: float, kind: int, color: config.Color) -> None:
    """Резной знак на ободе: несколько штрихов, у каждого знака свои."""
    strokes = (
        [((0, -1.6), (0, 1.6)), ((-1.2, -0.6), (1.2, -0.6))],
        [((-1.2, -1.4), (1.2, 1.4)), ((1.2, -1.4), (-1.2, 1.4))],
        [((-1.2, 1.4), (0, -1.5)), ((0, -1.5), (1.2, 1.4))],
        [((-1.2, -1.4), (-1.2, 1.4)), ((-1.2, 0), (1.2, 0)), ((1.2, -1.4), (1.2, 1.4))],
    )[kind % 4]
    for (ax, ay), (bx, by) in strokes:
        art.line(color, (x + ax, y + ay), (x + bx, y + by), 0.4)


def _ellipse_bands(cx: float, cy: float, rx: float, ry: float, thickness: float, step: int = 5):
    """Прямоугольники, повторяющие силуэт стола как препятствие для ног: сверху вниз
    полосы эллипса, затем сплошной обод и полосы нижней дуги. Каждая — по самой узкой стороне."""
    y = cy - ry
    while y < cy:
        edge = max(abs(cy - y), abs(cy - min(y + step, cy)))
        half = rx * math.sqrt(max(0.0, 1 - (edge / ry) ** 2))
        yield pygame.Rect(round(cx - half), round(y), round(half * 2), min(step, round(cy - y)))
        y += step
    yield pygame.Rect(round(cx - rx), round(cy), round(rx * 2), round(thickness))
    y = cy + thickness
    while y < cy + thickness + ry - 3:
        edge = max(abs(y - cy - thickness), abs(min(y + step, cy + thickness + ry) - cy - thickness))
        half = rx * math.sqrt(max(0.0, 1 - (edge / ry) ** 2))
        yield pygame.Rect(round(cx - half), round(y), round(half * 2), step)
        y += step


def build_table() -> TableArt:
    """Круглый стол из массивного дерева на каменном основании среди корней."""
    cx, cy = TABLE_CENTER
    top = Art(pygame.Rect(cx - 46, cy - 22, 92, 60), seed=5)
    ground = cy + TABLE_THICKNESS + TABLE_RY + 1  # линия земли у основания (передний край камня)
    # Корни и каменное основание.
    slab = ground - 6.5
    for side in (-1, 1):
        for reach, y, w in ((42, ground - 1.5, 4.4), (33, ground + 2.0, 3.4)):
            curve = spline([(cx + side * 20, slab - 4), (cx + side * (reach - 7), ground - 4), (cx + side * reach, y)], 8)
            top.tube(curve, [max(0.8, w * (1 - i / len(curve)) + 0.8) for i in range(len(curve))], BARK)
    top.ellipse(STONE[0], cx, slab + 0.9, 38.0, 7.6)
    top.ellipse(STONE[1], cx, slab + 0.4, 37.4, 7.0)
    top.rect_(STONE[1], cx - 37.4, slab - 4, 74.8, 4.4)
    top.ellipse(STONE[2], cx, slab - 0.6, 37.4, 7.0)
    top.ellipse(STONE[3], cx - 4, slab - 2.0, 25, 3.4)
    for k in range(-4, 5):  # вырезанные узоры на камне
        top.dot(STONE[0], cx + k * 7.6, slab + 4.4 - abs(k) * 0.28, 2)
    for x in (cx - 28, cx + 24, cx - 10):  # мох
        top.ball(MOSS, x, slab + 4.0, 2.2, outline=False)
    # Обод стола: цилиндр из досок.
    rim_top, rim_bottom = cy, cy + TABLE_THICKNESS
    top.ellipse(WOOD[0], cx, rim_bottom + 0.6, TABLE_RX + 0.6, TABLE_RY + 0.6)
    top.rect_(WOOD[0], cx - TABLE_RX - 0.6, rim_top, TABLE_RX * 2 + 1.2, TABLE_THICKNESS + 0.6)
    top.ellipse(WOOD[1], cx, rim_bottom, TABLE_RX, TABLE_RY)
    top.rect_(WOOD[1], cx - TABLE_RX, rim_top, TABLE_RX * 2, TABLE_THICKNESS)
    for i in range(-TABLE_RX, TABLE_RX, 1):  # свет слева, тень справа
        t = (i + TABLE_RX) / (TABLE_RX * 2)
        color = mix(WOOD[3], WOOD[1], min(1.0, t * 1.5)) if t < 0.5 else mix(WOOD[2], WOOD[1], (t - 0.5) * 2)
        top.line(color, (cx + i + 0.5, rim_top + 1.0), (cx + i + 0.5, rim_bottom + TABLE_RY * math.sqrt(max(0.0, 1 - (i / TABLE_RX) ** 2)) - 0.6), 0.5)
    for k in range(-6, 7):  # швы досок
        x = cx + k * 5.4
        edge = TABLE_RY * math.sqrt(max(0.0, 1 - ((x - cx) / TABLE_RX) ** 2))
        top.line(WOOD[0], (x, rim_top + 1), (x, rim_bottom + edge - 0.5), 0.4)
    for k in range(-3, 4):  # рунические знаки на ободе
        x = cx + k * 9.0
        edge = TABLE_RY * math.sqrt(max(0.0, 1 - ((x - cx) / TABLE_RX) ** 2))
        _rune(top, x, rim_top + edge + TABLE_THICKNESS * 0.4, k + 3, RUNE_COLOR)
    # Столешница: тёплое дерево с годовыми кольцами и вдавленная доска мозаики.
    top.ellipse(WOOD[0], cx, cy, TABLE_RX + 0.6, TABLE_RY + 0.6)
    top.ellipse(WOOD[3], cx, cy, TABLE_RX, TABLE_RY)
    top.ellipse(WOOD[2], cx + 0.8, cy + 0.6, TABLE_RX - 1.2, TABLE_RY - 0.8)
    top.ellipse(RUNE_COLOR, cx, cy, TABLE_RX - 2.2, TABLE_RY - 1.6, 1)
    top.ellipse(BOARD_EDGE, cx, cy, TABLE_RX - 3.0, TABLE_RY - 2.1)
    top.ellipse(BOARD_COLOR, cx, cy + 0.4, TABLE_RX - 3.8, TABLE_RY - 2.8)
    for k in range(16):  # ромбики по краю доски
        a = k * math.tau / 16 + 0.2
        x, y = cx + math.cos(a) * (TABLE_RX - 7.4), cy + 0.4 + math.sin(a) * (TABLE_RY - 5.0)
        top.polygon(mix(BOARD_COLOR, RUNE_COLOR, 0.45), [(x, y - 1.1), (x + 1.1, y), (x, y + 1.1), (x - 1.1, y)])
    fragments, hints = {}, []
    for trial_id, (x, y) in MOSAIC_SLOTS.items():
        half = SLOT_SIZE / 2
        top.rect_(BOARD_EDGE, x - half - 0.8, y - half - 0.8, SLOT_SIZE + 1.6, SLOT_SIZE + 1.6, radius=1)
        top.rect_((46, 50, 82), x - half, y - half, SLOT_SIZE, SLOT_SIZE)
        top.rect_((84, 88, 124), x - half + 0.2, y + half - 1.0, SLOT_SIZE - 0.4, 0.8)  # нижняя кромка гнезда светлее
        tile = _fragment(trial_id)
        fragments[trial_id] = Piece(tile.surface, pygame.Rect(round(x - half), round(y - half), SLOT_SIZE, SLOT_SIZE))
        # Подсказка в пустом гнезде: тусклый серый силуэт будущего фрагмента.
        ghost = pygame.transform.grayscale(tile.surface)
        ghost.fill((90, 100, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
        ghost.set_alpha(110)
        top.surface.blit(ghost, top.at(x - half, y - half))
    # Золотая вставка собранной мозаики: рамка доски и лучи между фрагментами.
    inlay = Art(top.rect)
    inlay.ellipse(RUNE_COLOR, cx, cy + 0.4, TABLE_RX - 3.8, TABLE_RY - 2.8, 2)
    centers = list(MOSAIC_SLOTS.values())
    for i, a in enumerate(centers):
        b = centers[(i + 1) % 3]
        inlay.line((255, 230, 150), a, b, 0.9)
        inlay.line((196, 142, 60), (a[0], a[1] + 0.8), (b[0], b[1] + 0.8), 0.4)
    body = top.piece()
    footprint = tuple(_ellipse_bands(cx, cy, TABLE_RX, TABLE_RY, TABLE_THICKNESS)) + (
        pygame.Rect(cx - 24, round(ground) - 7, 48, 7),  # каменное основание
    )
    return TableArt(body, fragments, inlay.piece(), footprint, ground)


@lru_cache(maxsize=1)
def table() -> TableArt:
    return build_table()


# --- Мелкие предметы поляны ---

@dataclass(frozen=True)
class Prop:
    """Предмет на поляне: картинка, где он стоит (середина низа) и препятствие под ногами."""

    piece: Piece
    foot: tuple[int, int]
    blocker: pygame.Rect | None = None
    glow: tuple[tuple[float, float], ...] = ()  # где у предмета светится (холст)
    flat: bool = False  # низкая мелочь у земли: вшивается в землю (уменьшенной), а не рисуется отдельно

    @property
    def sort_y(self) -> int:
        return self.foot[1]


FLOWER_PETALS = ((246, 128, 160), (252, 214, 96), (186, 156, 240), (255, 255, 244), (130, 190, 250))


def _canvas_for(foot: tuple[int, int], width: int, height: int, seed: int, pad: int = 3) -> Art:
    """Картинка предмета: width×height над точкой foot (середина низа), с запасом pad по краям."""
    return Art(pygame.Rect(foot[0] - width // 2 - pad, foot[1] - height - pad, width + pad * 2, height + pad * 2 + 2), seed)


def bush(foot: tuple[int, int], width: int, height: int, seed: int, palette: Palette = LEAVES_LUSH,
         blossoms: tuple[config.Color, ...] = (), blocked: bool = True) -> Prop:
    """Куст: холмик из клубов листвы, по желанию в цветах."""
    art = _canvas_for(foot, width, height, seed)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x, y - 0.6, width / 2 + 1, 2.4)  # тень у земли
    lumps = []
    count = max(3, round(width / 4.5))
    for i in range(count):
        t = (i + 0.5) / count
        r = height * (0.34 + 0.2 * math.sin(t * math.pi)) * art.rng.uniform(0.9, 1.1)
        lumps.append((x - width / 2 + t * width, y - r - art.rng.uniform(0, height * 0.28) * math.sin(t * math.pi), r))
    art.cluster(lumps, palette, 0.8)
    for k, color in enumerate(blossoms):
        for _ in range(max(2, width // 6)):
            fx = x + art.rng.uniform(-width * 0.4, width * 0.4)
            fy = y - art.rng.uniform(height * 0.25, height * 0.85)
            if blossoms:
                _blossom(art, fx, fy, color, 0.8)
    blocker = pygame.Rect(x - width // 2 + 2, y - 4, width - 4, 4) if blocked else None
    return Prop(art.piece(), foot, blocker)


def mushroom_cluster(foot: tuple[int, int], seed: int, caps: tuple[config.Color, ...], size: float = 1.0) -> Prop:
    """Группа из трёх-четырёх грибов разного роста."""
    art = _canvas_for(foot, 18, 14, seed)
    x, y = foot
    art.ellipse((20, 44, 30, 110), x, y - 0.4, 8.5, 1.8)
    spots = ((-4.4, 0.4, 5.0), (0.2, 1.0, 7.4), (4.6, 0.0, 4.2), (-1.4, -0.2, 3.4))
    for i, (dx, dy, h) in enumerate(spots[: 3 + (seed % 2)]):
        _mushroom(art, x + dx * size, y + dy, h * size, caps[i % len(caps)], dots=(i % 2 == 0))
    return Prop(art.piece(), foot, None, (), True)


def fern(foot: tuple[int, int], seed: int, size: float = 1.0) -> Prop:
    """Папоротник: веер изогнутых вай с зубчиками."""
    art = _canvas_for(foot, round(20 * size), round(14 * size), seed)
    x, y = foot
    for k, angle in enumerate((-72, -48, -22, 0, 22, 48, 72)):
        reach = (9 + 4 * math.cos(math.radians(angle))) * size
        a = math.radians(angle)
        tip = (x + math.sin(a) * reach, y - 2 - math.cos(a) * reach * 0.8)
        mid = (x + math.sin(a) * reach * 0.45, y - 1 - math.cos(a) * reach * 0.62)
        curve = spline([(x, y), mid, tip], 8)
        dark = LEAVES_DEEP if k % 2 else MOSS
        art.lines(dark[1], curve, 0.7)
        for i in range(2, len(curve) - 1, 2):
            px, py = curve[i]
            scale = 1.0 - i / len(curve) * 0.6
            for side in (-1, 1):
                art.line(dark[3] if side < 0 else dark[2], (px, py), (px + side * 2.2 * scale, py - 0.9 * scale), 0.5)
    return Prop(art.piece(), foot, flat=True)


def rock(foot: tuple[int, int], width: int, height: int, seed: int, mossy: bool = True) -> Prop:
    """Валун из нескольких камней, сверху мох."""
    art = _canvas_for(foot, width, height, seed)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x + 1, y - 0.4, width / 2 + 1.5, 2.2)
    for dx, dy, r in ((-width * 0.22, -height * 0.34, height * 0.4), (width * 0.2, -height * 0.3, height * 0.34),
                      (0, -height * 0.5, height * 0.48)):
        art.ball(STONE, x + dx, y + dy, r)
    if mossy:
        for dx, dy, r in ((-width * 0.1, -height * 0.95, 2.2), (width * 0.12, -height * 0.9, 1.8), (-width * 0.3, -height * 0.6, 1.5)):
            art.ball(MOSS, x + dx, y + dy, r, outline=False)
    return Prop(art.piece(), foot, pygame.Rect(x - width // 2 + 1, y - 4, width - 2, 4))


def stump(foot: tuple[int, int], seed: int, paper: bool = False) -> Prop:
    """Пенёк с годовыми кольцами; у «формулярного» — стопка бумаг сверху."""
    art = _canvas_for(foot, 14, 20 if paper else 11, seed)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x + 1, y - 0.4, 8.5, 2.0)
    art.rect_(BARK[0], x - 6.4, y - 8.4, 12.8, 8.4, radius=2)
    art.rect_(BARK[2], x - 5.6, y - 8, 11.2, 7.6, radius=2)
    art.rect_(BARK[3], x - 5.4, y - 8, 3.2, 7.4)
    art.rect_(BARK[1], x + 3.2, y - 8, 2.2, 7.6)
    art.ellipse(BARK[0], x, y - 8.2, 6.6, 2.9)
    art.ellipse(WOOD[4], x, y - 8.4, 6.0, 2.5)
    art.ellipse(WOOD[3], x, y - 8.4, 4.2, 1.7, 1)
    art.ellipse(WOOD[2], x, y - 8.4, 2.2, 0.9, 1)
    if paper:
        for k, (dx, tilt) in enumerate(((0, 0.0), (0.8, 0.07), (-0.6, -0.05), (0.3, 0.05))):
            art.polygon((70, 70, 84), [(x - 4.4 + dx, y - 9.4 - k * 1.5), (x + 4.6 + dx, y - 9.6 - k * 1.5),
                                       (x + 4.6 + dx, y - 10.8 - k * 1.5), (x - 4.4 + dx, y - 10.6 - k * 1.5)])
            art.polygon((248 - k * 4, 246 - k * 4, 236 - k * 4), [(x - 4.2 + dx, y - 9.6 - k * 1.5), (x + 4.4 + dx, y - 9.8 - k * 1.5),
                                                                 (x + 4.4 + dx, y - 10.6 - k * 1.5), (x - 4.2 + dx, y - 10.4 - k * 1.5)])
        art.circle((200, 54, 60), x + 2.0, y - 15.6, 1.2)
        art.ball(palette_from((120, 120, 140)), x - 2.6, y - 16.2, 1.8)  # пресс-папье
        art.polygon((250, 246, 236), [(x + 6.2, y - 6), (x + 9.6, y - 3), (x + 6.4, y - 2.6)])  # улетевший листок
    return Prop(art.piece(), foot, pygame.Rect(x - 6, y - 4, 12, 4))


def flowers(foot: tuple[int, int], seed: int, count: int = 5, width: int = 14) -> Prop:
    """Высокие цветы на стебельках с листьями."""
    art = _canvas_for(foot, width, 13, seed)
    x, y = foot
    for _ in range(count):
        fx = x + art.rng.uniform(-width / 2 + 2, width / 2 - 2)
        h = art.rng.uniform(5, 10)
        art.line(MOSS[1], (fx, y), (fx + art.rng.uniform(-1, 1), y - h), 0.5)
        art.polygon(MOSS[2], [(fx, y - h * 0.4), (fx + 2.2, y - h * 0.6), (fx + 0.4, y - h * 0.2)])
        _blossom(art, fx, y - h, FLOWER_PETALS[art.rng.randrange(len(FLOWER_PETALS))], 1.0)
    return Prop(art.piece(), foot, flat=True)


def lantern_post(foot: tuple[int, int], seed: int, color: config.Color = WARM_LIGHT) -> Prop:
    """Столб с крюком и фонарём: тёплый огонёк в стекле."""
    art = Art(pygame.Rect(foot[0] - 10, foot[1] - 36, 20, 38), seed)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x + 1, y - 0.4, 5, 1.8)
    spine = [(x, y), (x + 0.2, y - 12), (x - 0.2, y - 24), (x, y - 30)]
    art.tube(spine, [2.0, 1.7, 1.5, 1.4], BARK)
    art.line(BARK[1], (x, y - 30), (x + 4.8, y - 30), 0.9)  # крюк
    art.line(BARK[1], (x + 4.8, y - 30), (x + 4.8, y - 27.4), 0.4)
    lx, ly = x + 4.8, y - 23.2
    art.rect_((60, 40, 40), lx - 3.2, ly - 4.4, 6.4, 1.4, radius=1)  # крышка
    art.polygon((60, 40, 40), [(lx - 3.6, ly - 3.0), (lx + 3.6, ly - 3.0), (lx + 2.0, ly - 5.8), (lx - 2.0, ly - 5.8)])
    art.rect_(mix(color, (255, 255, 255), 0.5), lx - 2.7, ly - 3.0, 5.4, 6.8, radius=1)
    art.rect_(color, lx - 2.0, ly - 2.4, 4.0, 5.6, radius=1)
    art.rect_((255, 250, 220), lx - 1.0, ly - 1.4, 2.0, 3.0, radius=1)
    art.rect_((60, 40, 40), lx - 3.4, ly + 3.6, 6.8, 1.2, radius=1)
    for gx in (-2.7, 0, 2.7):
        art.line((60, 40, 40), (lx + gx, ly - 3.0), (lx + gx, ly + 3.8), 0.3)
    return Prop(art.piece(), foot, pygame.Rect(x - 2, y - 3, 4, 3), glow=((lx, ly),))


def crystals(foot: tuple[int, int], seed: int, hue: tuple[config.Color, config.Color]) -> Prop:
    """Куст светящихся кристаллов — три призмы с мягким ореолом."""
    art = _canvas_for(foot, 20, 22, seed, pad=4)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x, y - 0.5, 7.5, 2.0)
    for k, (dx, h, w) in enumerate(((-3.8, 8, 2.6), (0.4, 13, 3.4), (4.2, 7, 2.4))):
        base, light = hue[k % 2], mix(hue[k % 2], (255, 255, 255), 0.55)
        dark = mix(hue[k % 2], (20, 16, 50), 0.5)
        px = x + dx
        art.polygon(dark, [(px - w / 2, y), (px - w / 2, y - h + 2.2), (px, y - h), (px + w / 2, y - h + 2.2), (px + w / 2, y)])
        art.polygon(base, [(px - w / 2, y), (px - w / 2, y - h + 2.2), (px, y - h), (px, y)])
        art.polygon(light, [(px - w / 2 + 0.5, y - 1), (px - w / 2 + 0.5, y - h + 2.6), (px - 0.4, y - h + 0.8)])
        art.dot((255, 255, 255), px - w * 0.2, y - h + 2.6, 2)
    halo = glow_sprite(9, mix(hue[0], (255, 255, 255), 0.3), 60)
    under = pygame.Surface(art.surface.get_size(), pygame.SRCALPHA)
    under.blit(halo, art.at(x - 9, y - 16))
    under.blit(art.surface, (0, 0))
    art.surface = under
    return Prop(art.piece(), foot, pygame.Rect(x - 6, y - 3, 12, 3))


def mailbox(foot: tuple[int, int], seed: int) -> Prop:
    """Почтовый ящик на кривом столбе: красный флажок поднят, из щели торчит письмо."""
    art = Art(pygame.Rect(foot[0] - 11, foot[1] - 24, 22, 26), seed)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x + 1, y - 0.4, 4.5, 1.6)
    art.tube([(x, y), (x + 0.4, y - 7), (x - 0.3, y - 13)], [1.7, 1.5, 1.4], BARK_GREY)
    art.rect_((30, 40, 80), x - 5.6, y - 21, 11.2, 8.6, radius=3)
    art.rect_((68, 100, 176), x - 5.0, y - 20.6, 10.0, 7.6, radius=3)
    art.rect_((120, 160, 220), x - 4.6, y - 20.4, 3.4, 6.8, radius=2)
    art.rect_((30, 40, 80), x - 3.0, y - 16.4, 6.0, 1.4)
    art.polygon((250, 246, 236), [(x - 2.2, y - 16.0), (x + 2.4, y - 16.6), (x + 2.6, y - 14.2), (x - 2.0, y - 14.0)])
    art.rect_((60, 40, 40), x + 4.0, y - 25, 1.0, 6.6)  # флажок
    art.rect_(RED, x + 4.6, y - 25.2, 3.6, 2.4)
    return Prop(art.piece(), foot, pygame.Rect(x - 2, y - 3, 4, 3))


def signpost(foot: tuple[int, int], seed: int) -> Prop:
    """Столб с нелепыми стрелками в разные стороны."""
    art = Art(pygame.Rect(foot[0] - 14, foot[1] - 34, 28, 36), seed)
    x, y = foot
    art.ellipse((20, 44, 30, 120), x + 1, y - 0.4, 4.5, 1.6)
    art.tube([(x, y), (x - 0.4, y - 12), (x + 0.3, y - 26), (x, y - 32)], [1.8, 1.6, 1.5, 1.3], BARK_GREY)
    for dy, direction, color in ((-27, 1, (214, 150, 80)), (-21, -1, (120, 160, 120)), (-15, 1, (200, 110, 110))):
        tip = x + direction * 9
        base = x - direction * 4
        art.polygon((50, 36, 30), [(base, y + dy - 2.8), (tip - direction * 2.4, y + dy - 2.8), (tip + direction * 0.6, y + dy),
                                   (tip - direction * 2.4, y + dy + 2.8), (base, y + dy + 2.8)])
        art.polygon(color, [(base + direction * 0.4, y + dy - 2.2), (tip - direction * 2.8, y + dy - 2.2), (tip - direction * 0.2, y + dy),
                            (tip - direction * 2.8, y + dy + 2.2), (base + direction * 0.4, y + dy + 2.2)])
        art.line(mix(color, (40, 30, 30), 0.6), (base + direction * 1.2, y + dy), (tip - direction * 3.2, y + dy), 0.3)
    return Prop(art.piece(), foot, pygame.Rect(x - 2, y - 3, 4, 3))


# --- Расстановка ---

def build_props() -> tuple[Prop, ...]:
    """Всё мелкое на поляне, по группам: у каждого дерева — своё, вокруг стола и по краям — общее."""
    pink = ((246, 128, 160), (255, 210, 226))
    items = [
        # Суши: кусты по бокам ствола, грибы и папоротник.
        bush((17, 92), 20, 12, 1, LEAVES_DEEP, blocked=False),
        bush((72, 92), 18, 11, 2, LEAVES_DEEP, blocked=False),
        fern((74, 96), 3, 0.9),
        fern((8, 104), 4, 0.8),
        mushroom_cluster((66, 100), 5, ((206, 60, 58), (232, 150, 70))),
        # Формуляры: почта и бумаги (нелепый указатель стоит на перекрёстке, ниже).
        mailbox((126, 76), 6),
        signpost((72, 122), 7),
        stump((196, 74), 8, paper=True),
        bush((131, 72), 12, 9, 9, LEAVES_BLUE, blocked=False),
        bush((189, 72), 12, 9, 10, LEAVES_BLUE, blocked=False),
        # Тортики: цветущие кусты и сладкие грибы.
        bush((247, 92), 20, 12, 11, LEAVES_LUSH, pink, blocked=False),
        bush((305, 92), 20, 12, 12, LEAVES_LUSH, pink, blocked=False),
        mushroom_cluster((253, 101), 13, ((246, 150, 190), (255, 230, 240), (240, 110, 150))),
        mushroom_cluster((298, 100), 14, ((255, 214, 110), (246, 150, 190))),
        fern((312, 106), 15, 0.8),
        # Вокруг стола.
        crystals((122, 130), 16, ((110, 220, 240), (170, 140, 250))),
        crystals((199, 128), 17, ((250, 160, 220), (255, 214, 120))),
        mushroom_cluster((131, 142), 18, ((120, 160, 250), (186, 140, 250)), 0.9),
        mushroom_cluster((190, 143), 19, ((250, 130, 170), (255, 220, 120)), 0.9),
        lantern_post((112, 124), 20),
        lantern_post((208, 122), 21),
        # Нижние края поляны.
        rock((26, 150), 16, 10, 22),
        bush((20, 162), 26, 13, 23, LEAVES_LUSH),
        stump((64, 134), 24),
        flowers((46, 152), 25, 6, 16),
        fern((30, 130), 26, 1.0),
        mushroom_cluster((88, 154), 27, ((130, 170, 250), (240, 130, 170))),
        lantern_post((96, 150), 28),
        lantern_post((224, 150), 29),
        crystals((250, 134), 30, ((250, 160, 220), (170, 140, 250))),
        flowers((274, 154), 31, 6, 16),
        fern((296, 130), 32, 1.0),
        mushroom_cluster((236, 158), 33, ((250, 190, 90), (240, 110, 110))),
        rock((300, 148), 34, 16, 10),
        bush((300, 162), 26, 13, 35, LEAVES_LUSH, pink),
    ]
    return tuple(items)


@lru_cache(maxsize=1)
def props() -> tuple[Prop, ...]:
    return build_props()


def prop_obstacles() -> list[pygame.Rect]:
    return [prop.blocker for prop in props() if prop.blocker is not None]


# --- Свечение и огоньки ---

@lru_cache(maxsize=None)
def glow(radius: float, color: config.Color, peak: int) -> Piece:
    """Мягкое свечение; место на холсте задаёт тот, кто его выводит (rect нужного размера)."""
    image = glow_sprite(radius, color, peak)
    size = round(radius) * 2
    return Piece(image, pygame.Rect(0, 0, size, size))


@lru_cache(maxsize=None)
def firefly(level: int) -> Piece:
    """Светлячок: чем больше level (1…3), тем ярче и крупнее ореол."""
    image = pygame.Surface((8, 8), pygame.SRCALPHA)
    pygame.draw.circle(image, (255, 240, 150, 28 * level), (4, 4), 1 + level)
    image.fill((255, 250, 200, 255), (3, 3, 2, 2))
    return Piece(image, pygame.Rect(0, 0, 4, 4))


@lru_cache(maxsize=None)
def sparkle(color: config.Color, size: int = 2) -> Piece:
    image = sparkle_sprite(color, size)
    side = image.get_width()
    return Piece(image, pygame.Rect(0, 0, side // SCALE + 1, side // SCALE + 1))


@lru_cache(maxsize=None)
def door_ring(tree: str) -> Piece:
    """Светлая арка вокруг отверстия: подсказывает, что сюда можно войти."""
    spec = TREE_SPECS[tree]
    width, height = spec.door_size
    rect = spec.door.inflate(10, 10)
    art = Art(rect)
    x, bottom = spec.cx, spec.ground - 0.5
    art.arch_rows(lambda t, e: (255, 238, 150, 255), x, bottom + 2.2, width + 5.0, height + 4.4)
    art.arch_rows(lambda t, e: (0, 0, 0, 0), x, bottom + 2.2, width + 2.6, height + 2.4)
    return art.piece()


@lru_cache(maxsize=1)
def table_ring() -> Piece:
    """Светлое кольцо вокруг стола, когда к нему можно обратиться."""
    cx, cy = TABLE_CENTER
    art = Art(pygame.Rect(cx - 44, cy - 24, 88, 62))
    art.ellipse((255, 238, 150), cx, cy + 5, TABLE_RX + 5, TABLE_RY + 9, 2)
    return art.piece()


@lru_cache(maxsize=1)
def badge() -> Piece:
    """Золотая звёздочка: испытание пройдено."""
    art = Art(pygame.Rect(0, 0, 9, 9))
    points = []
    for k in range(10):
        r = 4.2 if k % 2 == 0 else 1.9
        a = -math.pi / 2 + k * math.pi / 5
        points.append((4.5 + math.cos(a) * r, 4.6 + math.sin(a) * r))
    art.polygon((120, 80, 20), [(x + 0.0, y + 0.4) for x, y in points])
    art.polygon(GOLD, points)
    art.polygon((255, 244, 190), [(4.5 + (x - 4.5) * 0.45, 4.4 + (y - 4.6) * 0.45) for x, y in points])
    return art.piece()


# --- Подробный фон ---

BACKDROP_RECT = pygame.Rect(0, 12, config.LOGICAL_SIZE[0], 156)  # между полосами интерфейса


def static_items() -> tuple[tuple[int, Piece], ...]:
    """Неподвижное, что стоит на земле: деревья и крупные предметы — (линия земли, картинка) по порядку глубины."""
    items = [(art.spec.ground, art.piece) for art in (sushi_tree(), forms_tree(), cakes_tree())]
    items += [(prop.sort_y, prop.piece) for prop in props() if not prop.flat]
    return tuple(sorted(items, key=lambda item: item[0]))


def build_backdrop(ground: pygame.Surface) -> Piece:
    """Земля (холст, увеличенный вдвое) с неподвижными деревьями и предметами поверх — одной картинкой.

    Слой высокого разрешения выводит её одной непрозрачной командой под персонажами, вместо
    сорока отдельных картинок каждый кадр; те, кто должен закрыть персонажа, рисуются поверх него
    заново (HubScene._draw_in_front)."""
    rect = BACKDROP_RECT
    image = pygame.Surface((rect.w * SCALE, rect.h * SCALE))
    image.blit(pygame.transform.scale(ground.subsurface(rect), image.get_size()), (0, 0))
    for _, piece in static_items():
        image.blit(piece.image, ((piece.rect.x - rect.x) * SCALE, (piece.rect.y - rect.y) * SCALE))
    return Piece(image, rect)
