"""Рисование пиксельных декораций программно, вдвое подробнее логического холста.

Объект мира рисуется в координатах холста 320×180 (дробные тоже можно), а пикселей в нём
вдвое больше по каждой оси (SCALE): детали получаются такой же густоты, как кадры
персонажей 64×64 на площади (32×32 логических пикселя). Готовая картинка выводится слоем
высокого разрешения как обычный кадр (HiResLayer.sprite), а без слоя уменьшается до
логического размера (Piece.draw).

Здесь только инструменты рисования — шарообразные «клубы» листвы, изогнутые стволы и ветви,
арки, мягкое свечение; сами деревья, стол и мелкие предметы площади собирает
game/world/hub_scenery.py. Всё детерминировано: случайность берётся из random.Random с
заданным зерном, поэтому площадь выглядит одинаково при каждом запуске.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

import pygame

import config
from game.graphics.hires import HiResLayer, scale_sprite

FADE_LEVELS = 8  # ступеней прозрачности у Piece.faded
SCALE = 2  # пикселей картинки на один логический пиксель холста

Point = tuple[float, float]
Palette = tuple[config.Color, config.Color, config.Color, config.Color, config.Color]
# Палитра из пяти ступеней: контур, тень, основной тон, свет, блик.
LIGHT_DIRECTION = (-0.5, -0.65)  # откуда падает свет: сверху слева


def mix(a: config.Color, b: config.Color, t: float) -> config.Color:
    """Цвет между a и b: t=0 — a, t=1 — b."""
    return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t), round(a[2] + (b[2] - a[2]) * t))


def palette_from(base: config.Color, dark: config.Color = (22, 18, 38), light: config.Color = (255, 250, 220)) -> Palette:
    """Пять ступеней одного цвета: от контура до блика."""
    return (mix(base, dark, 0.7), mix(base, dark, 0.38), base, mix(base, light, 0.32), mix(base, light, 0.62))


def spline(points: Sequence[Point], steps: int = 10) -> list[Point]:
    """Плавная кривая через опорные точки (Катмулл-Ром): шаги между соседними точками."""
    if len(points) < 3:
        return [points[0], points[-1]] if len(points) == 2 else list(points)
    padded = [points[0], *points, points[-1]]
    result: list[Point] = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            result.append(tuple(
                0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                       + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3)
                for j in range(2)
            ))
    result.append(points[-1])
    return result


@dataclass(eq=False)
class Piece:
    """Готовая картинка (в SCALE раз подробнее холста) и прямоугольник холста, куда она ложится."""

    image: pygame.Surface
    rect: pygame.Rect
    _small: pygame.Surface | None = field(default=None, repr=False)
    _levels: dict[int, pygame.Surface] = field(default_factory=dict, repr=False)

    def faded(self, alpha: int) -> pygame.Surface:
        """Картинка с прозрачностью alpha, округлённой до одной из FADE_LEVELS ступеней.

        Ступени готовятся один раз и хранятся: слой высокого разрешения при alpha < 255 копирует
        и пересчитывает картинку каждый кадр, а мерцание свечения не заметит разницы в 1/8."""
        level = round(max(0, min(255, alpha)) / 255 * FADE_LEVELS)
        if level >= FADE_LEVELS:
            return self.image
        image = self._levels.get(level)
        if image is None:
            image = self._levels[level] = self.image.copy()
            image.fill((255, 255, 255, round(level * 255 / FADE_LEVELS)), special_flags=pygame.BLEND_RGBA_MULT)
        return image

    def draw(self, canvas: pygame.Surface, hires: HiResLayer | None, alpha: int = 255,
             center: tuple[float, float] | None = None) -> None:
        """Со слоем высокого разрешения — исходная картинка, иначе она же, уменьшенная до холста.

        center — вывести картинку серединой в эту точку холста вместо своего места."""
        rect = self.rect
        if center is not None:
            rect = rect.copy()
            rect.center = (round(center[0]), round(center[1]))
        if hires is not None:
            if alpha > 0:
                hires.sprite(self.faded(alpha), rect)
            return
        if self._small is None:
            self._small = scale_sprite(self.image, self.rect.size)
        canvas.blit(self._small, rect, special_flags=pygame.BLEND_PREMULTIPLIED)


class Art:
    """Прозрачная картинка, на которой рисуют в координатах холста (rect — её место на холсте)."""

    def __init__(self, rect: pygame.Rect | tuple[int, int, int, int], seed: int = 0) -> None:
        self.rect = pygame.Rect(rect)
        self.surface = pygame.Surface((self.rect.w * SCALE, self.rect.h * SCALE), pygame.SRCALPHA)
        self.rng = random.Random(seed)
        self.dy = 0.0  # сдвиг по вертикали для всего, что рисуется дальше (крону удобно опустить целиком)

    def piece(self, crop: bool = True) -> Piece:
        """Готовая картинка. По умолчанию обрезана до нарисованного (с целыми логическими границами):
        пустые поля стоят времени — слой высокого разрешения копирует прозрачные пиксели так же, как и закрашенные."""
        if not crop:
            return Piece(self.surface, self.rect)
        box = self.surface.get_bounding_rect()
        if not box.width or not box.height:
            return Piece(self.surface, self.rect)
        left, top = box.left // SCALE, box.top // SCALE
        right, bottom = -(-box.right // SCALE), -(-box.bottom // SCALE)
        area = pygame.Rect(left * SCALE, top * SCALE, (right - left) * SCALE, (bottom - top) * SCALE)
        image = self.surface.subsurface(area).copy()
        return Piece(image, pygame.Rect(self.rect.x + left, self.rect.y + top, right - left, bottom - top))

    # --- Координаты ---

    def at(self, x: float, y: float) -> tuple[int, int]:
        """Точка холста в пикселях картинки."""
        return round((x - self.rect.x) * SCALE), round((y + self.dy - self.rect.y) * SCALE)

    def length(self, value: float) -> int:
        return max(1, round(value * SCALE))

    # --- Примитивы ---

    def dot(self, color: config.Color, x: float, y: float, size: int = 1) -> None:
        """Квадратик size×size пикселей картинки (а не холста) с центром в (x, y)."""
        px, py = self.at(x, y)
        self.surface.fill(color, (px - size // 2, py - size // 2, size, size))

    def circle(self, color: config.Color, x: float, y: float, r: float) -> None:
        pygame.draw.circle(self.surface, color, self.at(x, y), self.length(r))

    def ellipse(self, color: config.Color, x: float, y: float, rx: float, ry: float, width: int = 0) -> None:
        px, py = self.at(x, y)
        rect = pygame.Rect(0, 0, self.length(rx) * 2, self.length(ry) * 2)
        rect.center = (px, py)
        pygame.draw.ellipse(self.surface, color, rect, width)

    def rect_(self, color: config.Color, x: float, y: float, w: float, h: float, radius: int = 0) -> None:
        px, py = self.at(x, y)
        pygame.draw.rect(self.surface, color, (px, py, self.length(w), self.length(h)), border_radius=radius)

    def polygon(self, color: config.Color, points: Sequence[Point]) -> None:
        pygame.draw.polygon(self.surface, color, [self.at(*p) for p in points])

    def line(self, color: config.Color, a: Point, b: Point, width: float = 0.5) -> None:
        pygame.draw.line(self.surface, color, self.at(*a), self.at(*b), max(1, round(width * SCALE)))

    def lines(self, color: config.Color, points: Sequence[Point], width: float = 0.5) -> None:
        pygame.draw.lines(self.surface, color, False, [self.at(*p) for p in points], max(1, round(width * SCALE)))

    # --- Составные формы ---

    def ball(self, palette: Palette, x: float, y: float, r: float, *, outline: bool = True) -> None:
        """Шар со ступенчатой тенью: свет сверху слева (кусок кроны, плод, шляпка)."""
        ox, oy = LIGHT_DIRECTION
        if outline:
            self.circle(palette[0], x, y, r + 0.5)
        self.circle(palette[1], x, y, r)
        self.circle(palette[2], x + ox * r * 0.3, y + oy * r * 0.3, r * 0.82)
        self.circle(palette[3], x + ox * r * 0.5, y + oy * r * 0.5, r * 0.5)
        if r >= 2.5:
            self.circle(palette[4], x + ox * r * 0.62, y + oy * r * 0.62, r * 0.22)

    def tube(self, spine: Sequence[Point], radii: Sequence[float], palette: Palette, texture: float = 0.0) -> None:
        """Изогнутая труба переменной толщины: ствол, ветвь, корень. radii — по точкам оси.

        texture > 0 добавляет тёмные продольные полосы коры (доля от радиуса по ширине).
        """
        spine, radii = _dense(spine, radii)
        ox, oy = LIGHT_DIRECTION
        shades = ((0.5, 0.0, 1.0, 0), (0.0, 0.0, 1.0, 1), (0.0, 0.0, 0.82, 2), (0.0, 0.0, 0.5, 3))
        for extra, _, scale, level in shades:
            for (x, y), r in zip(spine, radii):
                shift = 0.0 if level < 2 else (0.18 if level == 2 else 0.34) * r
                self.circle(palette[level], x + ox * shift, y + oy * shift, r * scale + extra)
        if texture > 0:
            self._bark(spine, radii, palette, texture)

    def _bark(self, spine: Sequence[Point], radii: Sequence[float], palette: Palette, density: float) -> None:
        count = max(2, round(len(spine) * density))
        for _ in range(count):
            i = self.rng.randrange(1, len(spine) - 1)
            j = min(len(spine) - 1, i + self.rng.randrange(2, 6))
            side = self.rng.uniform(-0.75, 0.75)
            color = palette[0] if side > -0.2 else palette[1]
            points = []
            for k in range(i, j + 1):
                x, y = spine[k]
                nx, ny = _normal(spine, k)
                points.append((x + nx * side * radii[k], y + ny * side * radii[k]))
            self.lines(color, points, 0.5)

    def cluster(self, lumps: Sequence[tuple[float, float, float]], palette: Palette, texture: float = 1.0) -> None:
        """Крона из шарообразных клубов, нарисованных сзади вперёд (верхние — дальше)."""
        for x, y, r in sorted(lumps, key=lambda lump: lump[1]):
            self.ball(palette, x, y, r)
            for _ in range(round(r * texture * 1.4)):  # листочки: светлые на свету, тёмные в тени
                angle = self.rng.uniform(0, math.tau)
                dist = r * math.sqrt(self.rng.random()) * 0.82
                px, py = x + math.cos(angle) * dist, y + math.sin(angle) * dist
                lit = (px - x) * LIGHT_DIRECTION[0] + (py - y) * LIGHT_DIRECTION[1] > 0
                self.dot(palette[3] if lit else palette[0], px, py, 2)

    def arch_rows(self, color_for_row, x: float, bottom: float, w: float, h: float) -> None:
        """Арка (прямоугольник с полукруглым верхом) построчно; цвет строки — color_for_row(t, edge),
        где t от 0 (верх) до 1 (низ), а edge — расстояние от края арки, 0..1."""
        px, bottom_px = self.at(x, bottom)
        width, height = self.length(w), self.length(h)
        radius = width / 2
        top = bottom_px - height
        for row in range(height):
            dy = row + 0.5
            if dy < radius:
                half = math.sqrt(max(0.0, radius * radius - (radius - dy) ** 2))
            else:
                half = radius
            if half <= 0:
                continue
            t = row / max(1, height - 1)
            left = round(px - half)
            right = round(px + half)
            for column in range(left, right):
                edge = min(column + 0.5 - (px - half), (px + half) - column - 0.5) / max(1.0, half)
                self.surface.set_at((column, top + row), color_for_row(t, edge))

    def shade(self, shape: pygame.Rect | tuple, color: config.Color, alpha: int, ellipse: bool = True) -> None:
        """Полупрозрачная тень на уже нарисованном: ложится только на непрозрачные пиксели картинки.

        shape — прямоугольник в координатах холста (x, y, w, h); тень — вписанный эллипс или он сам."""
        x, y, w, h = shape
        tmp = pygame.Surface(self.surface.get_size(), pygame.SRCALPHA)
        rect = pygame.Rect(*self.at(x, y), self.length(w), self.length(h))
        (pygame.draw.ellipse if ellipse else pygame.draw.rect)(tmp, (*color, alpha), rect)
        tmp.blit(self.surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        tmp.set_alpha(None)
        # BLEND_RGBA_MIN оставил от тени цвет и альфу, не больше, чем у картинки; кладём как есть.
        self.surface.blit(tmp, (0, 0))

    def speckle(self, shape: pygame.Rect | tuple, color: config.Color, count: int, size: int = 2) -> None:
        """Россыпь точек внутри прямоугольника холста; точки кладутся только на нарисованное."""
        x, y, w, h = shape
        for _ in range(count):
            px = self.rng.uniform(x, x + w)
            py = self.rng.uniform(y, y + h)
            ix, iy = self.at(px, py)
            if 0 <= ix < self.surface.get_width() and 0 <= iy < self.surface.get_height():
                if self.surface.get_at((ix, iy)).a == 255:
                    self.surface.fill(color, (ix, iy, size, size))


def _dense(spine: Sequence[Point], radii: Sequence[float], step: float = 0.8) -> tuple[list[Point], list[float]]:
    """Ось и радиусы с шагом не больше step: редкие опорные точки не должны давать «бусы» из кругов."""
    points: list[Point] = [spine[0]]
    widths: list[float] = [radii[0]]
    for (x0, y0), (x1, y1), r0, r1 in zip(spine, spine[1:], radii, radii[1:]):
        count = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
        for k in range(1, count + 1):
            t = k / count
            points.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            widths.append(r0 + (r1 - r0) * t)
    return points, widths


def _normal(spine: Sequence[Point], index: int) -> Point:
    """Единичная нормаль к оси в точке index."""
    a = spine[max(0, index - 1)]
    b = spine[min(len(spine) - 1, index + 1)]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return -dy / length, dx / length


def glow_sprite(radius: float, color: config.Color, peak: int, steps: int = 0) -> pygame.Surface:
    """Мягкое круглое свечение (в SCALE раз подробнее холста): цвет color, непрозрачность в центре peak.

    steps > 0 даёт не плавный градиент, а ступени — под пиксельную графику."""
    size = round(radius * SCALE) * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x + 0.5 - center, y + 0.5 - center) / center
            if d >= 1:
                continue
            strength = (1 - d) ** 2
            if steps:
                strength = math.ceil(strength * steps) / steps
            surface.set_at((x, y), (*color, round(peak * strength)))
    return surface


def sparkle_sprite(color: config.Color, size: int = 3) -> pygame.Surface:
    """Маленькая четырёхлучевая звёздочка из пикселей картинки; size — длина луча."""
    side = size * 2 + 1
    surface = pygame.Surface((side, side), pygame.SRCALPHA)
    for k in range(-size, size + 1):
        fade = 1 - abs(k) / (size + 1)
        shade = mix((255, 255, 255), color, 1 - fade) if abs(k) else (255, 255, 255)
        surface.set_at((size + k, size), (*shade, round(255 * (0.4 + 0.6 * fade))))
        surface.set_at((size, size + k), (*shade, round(255 * (0.4 + 0.6 * fade))))
    return surface
