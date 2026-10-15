"""Слой высокого разрешения: персонажи и текст рисуются прямо в окне, а не на холсте 320×180.

Мир рисуется на логическом холсте и увеличивается до окна ближайшим соседом (Display.present):
у травы, дорожек и порталов остаются ровные пиксели. Персонажи и текст на холсте теряли
детали: кадр 64×64 уменьшался до 32×32 (площадь) или 48×48 (вступление) ближайшим соседом —
пропадали три пикселя исходника из четырёх или каждый четвёртый ряд, — а потом увеличивался
вместе с холстом; буквы шрифта в 9–10 пикселей холста увеличивались грубыми ступеньками.

Сцена, которая умеет больше (Scene.supports_hires), получает вместе с холстом HiResLayer —
очередь команд в логических координатах холста. Display выполняет их по порядку сразу после
увеличения холста — в той же области окна (viewport) и той же трансформацией (ViewTransform):
- sprite() — исходный кадр, масштабированный сразу до своего размера в окне (scale_sprite);
- text() — строка шрифтом без засечек размера окна со сглаживанием (game/graphics/fonts.py),
  при необходимости повёрнутая (перевёрнутые таблички в кондитерской);
- logical() — логическая графика поверх уже выведенных команд (см. ниже);
- fill() и rect() — заливка части экрана (вспышка, затемнение) и прямоугольник или рамка
  заливками окна — без увеличения картинки;
- torn() — кадр «сбоя»: холст с командами, порванный горизонтальными полосами;
- group() — неподвижная панель из команд (лист письма): собирается в картинку размера окна
  один раз и дальше выводится одним копированием, проявляется целиком.

Порядок слоёв. Всё, что на холсте, лежит под командами слоя. Поэтому логическую графику,
которая должна оказаться поверх персонажа или текста (дерево перед Алисой, окно диалога),
сцена рисует через logical(canvas, area), где area — прямоугольник холста, за который это
рисование не выходит. Если там ещё нет команд слоя, рисовать можно прямо на холсте (так
и делается: это бесплатно). Иначе рисование идёт на прозрачную «заплатку», обрезанную
по area, и она выводится своей командой, ближайшим соседом, как холст, — то есть ровно
в свою очередь. Строгий режим (strict=True, для тестов) проверяет, что рисование
действительно не выходит за area.
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace

import pygame

import config
from game.graphics.fonts import TextFonts, TextMetrics, TextStyle

# Сколько масштабированных кадров и строк держать готовыми: при переполнении вытесняются
# давно не использованные. Кэш очищается и при смене масштаба (полный экран, другой размер
# окна): старые размеры больше не понадобятся.
CACHE_LIMIT = 512


@dataclass(frozen=True)
class ViewTransform:
    """Перевод логических координат холста в пиксели окна: область окна, куда выведен холст.

    Та же геометрия, что у увеличенного холста (fit_viewport), поэтому команды слоя ложатся
    ровно на свои места мира при любом размере окна, в полноэкранном режиме и с полями.
    """

    viewport: pygame.Rect
    logical_size: config.Size = config.LOGICAL_SIZE

    @property
    def scale(self) -> float:
        """Пикселей окна на логический пиксель. Пропорции 16:9 сохраняются, поэтому по обеим осям одинаково."""
        return self.viewport.width / self.logical_size[0]

    def x(self, x: float) -> int:
        return self.viewport.x + round(x * self.viewport.width / self.logical_size[0])

    def y(self, y: float) -> int:
        return self.viewport.y + round(y * self.viewport.height / self.logical_size[1])

    def point(self, point: tuple[float, float]) -> tuple[int, int]:
        return self.x(point[0]), self.y(point[1])

    def rect(self, rect: pygame.Rect) -> pygame.Rect:
        """Прямоугольник холста в пикселях окна: края переводятся отдельно, поэтому соседние
        прямоугольники стыкуются без щелей, как пиксели увеличенного холста."""
        left, top = self.x(rect.left), self.y(rect.top)
        return pygame.Rect(left, top, self.x(rect.right) - left, self.y(rect.bottom) - top)


# Наибольшая длина кадра по одной оси на промежуточном шаге scale_sprite, пикселей.
MAX_STRETCH = 8192
# Цвета-кандидаты для цветового ключа увеличенных заплаток (берётся первый, которого в заплатке нет).
PATCH_KEYS = ((255, 0, 255), (0, 255, 254), (1, 254, 3), (254, 1, 253))


def scale_sprite(image: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    """Кадр размером size в пикселях окна — новая поверхность, исходная не меняется.

    По каждой оси исходник сначала увеличивается ближайшим соседом в целое число раз,
    а затем уменьшается до точного размера усреднением. Так используются все пиксели
    исходного кадра, края пикселей остаются чёткими и все они одного размера (ближайший
    сосед при ×1,5 чередовал бы пиксели шириной 1 и 2, а сглаживание размыло бы кадр).
    При целом масштабе это просто ближайший сосед — без единого нового оттенка.

    Усреднение — только в 2, 4, 8… раз (см. _stretched): у pygame.transform.smoothscale
    такое уменьшение точное, а при другом соотношении цвета чуть темнеют (200 → 198)
    и непрозрачные пиксели становятся полупрозрачными. Если подходящий промежуточный
    размер слишком велик, ось масштабируется ближайшим соседом.

    Прозрачность предумножается на альфу: при усреднении в полупрозрачные края не
    подмешивается чёрный цвет прозрачных пикселей PNG. Поэтому результат выводится
    с BLEND_PREMULTIPLIED.
    """
    width, height = max(1, size[0]), max(1, size[1])
    if not image.get_flags() & pygame.SRCALPHA or image.get_bitsize() != 32:
        converted = pygame.Surface(image.get_size(), pygame.SRCALPHA)
        converted.blit(image, (0, 0))
        image = converted
    result = image.premul_alpha()  # копия: исходный кадр остаётся как есть
    source_w, source_h = result.get_size()
    stretched_w, stretched_h = _stretched(source_w, width), _stretched(source_h, height)
    # Сначала по ширине, потом по высоте: промежуточные кадры остаются небольшими.
    if stretched_w != source_w:
        result = pygame.transform.scale(result, (stretched_w, source_h))
    if stretched_w != width:
        result = pygame.transform.smoothscale(result, (width, source_h))
    if stretched_h != source_h:
        result = pygame.transform.scale(result, (width, stretched_h))
    if stretched_h != height:
        result = pygame.transform.smoothscale(result, (width, height))
    return result


def _stretched(source: int, target: int) -> int:
    """До какой длины увеличить ось ближайшим соседом, чтобы потом точно уменьшить её до target.

    Это наименьшее target·2ⁿ, кратное source: увеличение — в целое число раз, уменьшение —
    в 2ⁿ раз. Если такой длины нет в пределах MAX_STRETCH, возвращается сам target
    (ближайший сосед сразу до нужного размера).
    """
    length = target
    while length <= MAX_STRETCH:
        if length % source == 0:
            return length
        length *= 2
    return target


@dataclass(frozen=True, eq=False)
class SpriteCommand:
    image: pygame.Surface  # исходный кадр (обычно 64×64)
    rect: pygame.Rect  # где кадр стоит на холсте и какого он там размера
    alpha: int = 255
    angle: float = 0.0  # наклон против часовой стрелки вокруг центра rect
    clip: pygame.Rect | None = None  # часть холста, вне которой кадра не видно
    opaque: bool = False  # кадр целиком непрозрачный (фон сцены): выводится быстрым копированием


@dataclass(frozen=True, eq=False)
class TextCommand:
    text: str
    style: TextStyle
    pos: tuple[float, float]  # точка холста, к которой привязан текст
    anchor: str = "topleft"  # какой точкой прямоугольника строки (как у pygame.Rect)
    alpha: int = 255
    clip: pygame.Rect | None = None
    angle: float = 0.0  # поворот строки против часовой стрелки (180 — вверх ногами)


@dataclass(frozen=True, eq=False)
class PatchCommand:
    surface: pygame.Surface  # логическая графика с прозрачным фоном
    rect: pygame.Rect  # её место на холсте


@dataclass(frozen=True, eq=False)
class FillCommand:
    color: config.Color
    rect: pygame.Rect | None  # None — весь холст
    alpha: int = 255


@dataclass(frozen=True, eq=False)
class TearCommand:
    """Холст и команды под ним, выведенные одним изображением, у которого горизонтальные
    полосы сдвинуты вбок (вылезшее за край возвращается с другой стороны)."""

    canvas: pygame.Surface
    commands: tuple[Command, ...]
    bands: tuple[tuple[int, int, int], ...]  # (y, высота, сдвиг) — в логических пикселях


@dataclass(frozen=True, eq=False)
class GroupCommand:
    """Команды, собранные в одну непрозрачную картинку прямоугольника rect и выведенные с
    прозрачностью alpha. Картинка хранится, пока не изменятся сами команды (key)."""

    rect: pygame.Rect
    commands: tuple[Command, ...]
    key: tuple
    alpha: int = 255


Command = SpriteCommand | TextCommand | PatchCommand | FillCommand | TearCommand | GroupCommand


class HiResLayer:
    """Команды высокого разрешения одного кадра и их вывод в окно (см. описание модуля)."""

    def __init__(self, fonts: TextFonts | None = None, *, strict: bool = False) -> None:
        self.fonts = fonts if fonts is not None else TextFonts()
        self.strict = strict
        self.commands: list[Command] = []
        self.covered: list[pygame.Rect] = []  # какие части холста уже заняты командами (с запасом)
        self._scale: float | None = None
        self._metrics: dict[tuple[float, bool], TextMetrics] = {}
        self._sprites: OrderedDict[tuple[pygame.Surface, tuple[int, int]], pygame.Surface] = OrderedDict()
        self._texts: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._patches: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._groups: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._fills: dict[tuple, pygame.Surface] = {}
        self._offscreen: pygame.Surface | None = None

    def clear(self) -> None:
        self.commands.clear()
        self.covered.clear()

    def backdrop_rows(self) -> tuple[int, int] | None:
        """Строки холста (от, до), которые целиком закрыты первой командой — непрозрачным кадром во всю
        ширину холста (подробный фон сцены), или None. Display.present() не увеличивает эти строки холста."""
        first = self.commands[0] if self.commands else None
        if not isinstance(first, SpriteCommand) or not first.opaque or first.angle or first.clip is not None:
            return None
        canvas_w, canvas_h = config.LOGICAL_SIZE
        rect = first.rect
        if rect.left > 0 or rect.right < canvas_w or rect.height <= 0:
            return None
        return max(0, rect.top), min(canvas_h, rect.bottom)

    def covers(self, area: pygame.Rect) -> bool:
        """Лежит ли уже в слое команда, которая может задеть прямоугольник холста area."""
        return area.collidelist(self.covered) >= 0

    def _add(self, command: Command, bounds: pygame.Rect | None) -> None:
        """Добавляет команду; bounds — какую часть холста она может задеть (None — весь холст)."""
        self.commands.append(command)
        self.covered.append(pygame.Rect((-1, -1), config.LOGICAL_SIZE).inflate(2, 2) if bounds is None else bounds)

    # --- Команды (координаты и размеры — логические, как на холсте) ---

    def sprite(
        self,
        image: pygame.Surface,
        rect: pygame.Rect,
        *,
        alpha: int = 255,
        angle: float = 0.0,
        clip: pygame.Rect | None = None,
        opaque: bool = False,
    ) -> None:
        """Кадр image, растянутый на прямоугольник холста rect (размер в окне — по трансформации).

        opaque=True — кадр без прозрачных пикселей (подробный фон сцены, который кладётся под
        персонажей): он увеличивается один раз и выводится обычным копированием, в разы быстрее
        вывода с прозрачностью. Для такого кадра alpha и angle не используются."""
        if alpha <= 0:
            return
        rect = pygame.Rect(rect)
        bounds = rect
        if angle:
            radians = math.radians(angle)
            cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
            bounds = pygame.Rect(0, 0, math.ceil(rect.w * cos + rect.h * sin), math.ceil(rect.w * sin + rect.h * cos))
            bounds.center = rect.center
        if clip is not None:
            bounds = bounds.clip(clip)
        self._add(SpriteCommand(image, rect, min(255, alpha), angle, clip, opaque), bounds.inflate(2, 2))

    def text(
        self,
        text: str,
        style: TextStyle,
        pos: tuple[float, float],
        *,
        anchor: str = "topleft",
        alpha: int = 255,
        clip: pygame.Rect | None = None,
        angle: float = 0.0,
    ) -> None:
        """Строка text, привязанная точкой anchor («topleft», «center», «midleft»…) к точке холста pos.

        angle — поворот против часовой стрелки; anchor тогда относится к прямоугольнику
        уже повёрнутой строки (как у pygame.transform.rotate и get_rect)."""
        if not text or alpha <= 0:
            return
        # Границы — по ширине строки в логических пикселях (самой большой из масштабов раскладки)
        # с запасом на тень и округление: в окне строка может оказаться на пиксель-другой шире.
        metrics = self.text_metrics(style)
        width, height = metrics.width(text) * 1.03, metrics.height
        if angle:
            radians = math.radians(angle)
            cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
            width, height = width * cos + height * sin, width * sin + height * cos
        bounds = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        setattr(bounds, anchor, (round(pos[0]), round(pos[1])))
        bounds = bounds.inflate(4, 4)
        if style.shadow is not None:
            bounds.width += math.ceil(style.shadow_offset) + 1
            bounds.height += math.ceil(style.shadow_offset) + 1
        if clip is not None:
            bounds = bounds.clip(clip)
        self._add(TextCommand(text, style, pos, anchor, min(255, alpha), clip, angle), bounds)

    def text_metrics(self, style: TextStyle) -> TextMetrics:
        """Размеры строк стиля в логических пикселях (шрифтами этого слоя)."""
        key = (style.size, style.bold)
        metrics = self._metrics.get(key)
        if metrics is None:
            metrics = self._metrics[key] = self.fonts.metrics(style)
        return metrics

    def fill(self, color: config.Color, rect: pygame.Rect | None = None, *, alpha: int = 255) -> None:
        if alpha > 0:
            self._add(FillCommand(color, rect, min(255, alpha)), None if rect is None else pygame.Rect(rect))

    def rect(self, color: config.Color, rect: pygame.Rect, width: int = 0, *, alpha: int = 255) -> None:
        """Прямоугольник холста, как pygame.draw.rect: width=0 — залитый, иначе рамка такой
        толщины внутрь. Выводится заливками окна — без масштабирования картинки."""
        rect = pygame.Rect(rect)
        if width <= 0 or 2 * width >= min(rect.width, rect.height):
            self.fill(color, rect, alpha=alpha)
            return
        for side in (
            pygame.Rect(rect.x, rect.y, rect.width, width),
            pygame.Rect(rect.x, rect.bottom - width, rect.width, width),
            pygame.Rect(rect.x, rect.y + width, width, rect.height - 2 * width),
            pygame.Rect(rect.right - width, rect.y + width, width, rect.height - 2 * width),
        ):
            self.fill(color, side, alpha=alpha)

    def torn(
        self, canvas: pygame.Surface, commands: tuple[Command, ...], bands: tuple[tuple[int, int, int], ...]
    ) -> None:
        """Холст canvas с командами commands (записанными в другом HiResLayer), порванный полосами
        bands — (y, высота, сдвиг) в логических пикселях. Закрывает всю область холста."""
        self._add(TearCommand(canvas, tuple(commands), tuple(bands)), None)

    @contextmanager
    def group(self, rect: pygame.Rect, *, alpha: int = 255) -> Iterator[HiResLayer]:
        """Неподвижная панель: команды, добавленные в выданный слой, выводятся одной картинкой
        прямоугольника rect (его они должны закрывать целиком, например заливкой фона).

        Картинка собирается в разрешении окна один раз и хранится, пока команды те же, —
        лист письма с дюжиной строк выводится одним копированием. alpha — прозрачность всей
        панели сразу (лист проявляется целиком, как картинка на холсте)."""
        panel = HiResLayer(self.fonts)
        panel._metrics = self._metrics  # те же размеры строк, без повторных измерений
        yield panel
        if alpha > 0 and panel.commands:
            rect = pygame.Rect(rect)
            key = (tuple(rect), *(_command_key(command) for command in panel.commands))
            self._add(GroupCommand(rect, tuple(panel.commands), key, min(255, alpha)), rect)

    @contextmanager
    def logical(self, canvas: pygame.Surface, area: pygame.Rect | None = None) -> Iterator[pygame.Surface]:
        """Поверхность для логической графики, которая должна лечь поверх уже добавленных команд.

        area — прямоугольник холста, за который рисование не выходит (None — неизвестно).
        Если команды слоя этой области не касаются, это сам холст: он под ними, и порядок
        не нарушится. Иначе — прозрачная заплатка размером с холст, обрезанная по area (или по
        нарисованному, если area не задана); она добавляется командой и выводится в свою очередь.
        """
        size_rect = canvas.get_rect()
        if area is not None:
            area = pygame.Rect(area).clip(size_rect)
        direct = not self.commands or (area is not None and not self.covers(area))
        if direct and not self.strict:
            yield canvas
            return
        patch = pygame.Surface(size_rect.size, pygame.SRCALPHA)
        yield patch
        if self.strict:
            drawn = patch.get_bounding_rect()
            if area is not None and drawn.width and drawn.height and not area.contains(drawn):
                raise AssertionError(f"логическая графика вышла за заявленную область {area}: нарисовано в {drawn}")
            if direct:
                canvas.blit(patch, (0, 0))  # строгий режим рисует туда же, куда и обычный
                return
        crop = area if area is not None else patch.get_bounding_rect()
        if crop.width and crop.height:
            self._add(PatchCommand(patch.subsurface(crop), crop), crop)

    # --- Вывод ---

    def render(self, target: pygame.Surface, transform: ViewTransform) -> None:
        """Выполняет команды по порядку на target (окне) в пределах области transform.viewport."""
        if transform.scale != self._scale:
            self._scale = transform.scale
            self._sprites.clear()
            self._texts.clear()
            self._patches.clear()
            self._groups.clear()
            self._fills.clear()
            self._offscreen = None
        self._render(target, transform, self.commands)

    def _render(
        self, target: pygame.Surface, transform: ViewTransform, commands: list[Command] | tuple[Command, ...]
    ) -> None:
        old_clip = target.get_clip()
        try:
            for command in commands:
                clip = transform.viewport.clip(old_clip)
                if getattr(command, "clip", None) is not None:
                    clip = clip.clip(transform.rect(command.clip))
                target.set_clip(clip)
                if isinstance(command, SpriteCommand):
                    self._draw_sprite(target, transform, command)
                elif isinstance(command, TextCommand):
                    self._draw_text(target, transform, command)
                elif isinstance(command, PatchCommand):
                    rect = transform.rect(command.rect)
                    if rect.width > 0 and rect.height > 0:
                        target.blit(self.scaled_patch(command.surface, rect.size), rect)
                elif isinstance(command, TearCommand):
                    self._draw_torn(target, transform, command)
                elif isinstance(command, GroupCommand):
                    self._draw_group(target, transform, command)
                else:
                    self._draw_fill(target, transform, command)
        finally:
            target.set_clip(old_clip)

    def scaled_sprite(self, image: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        """scale_sprite с кэшем: один кадр одного размера масштабируется один раз."""
        return _remember(self._sprites, (image, size), lambda: scale_sprite(image, size))

    def scaled_opaque(self, image: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        """scale_sprite для непрозрачного кадра: результат без альфа-канала, с кэшем."""

        def build() -> pygame.Surface:
            scaled = scale_sprite(image, size)
            plain = pygame.Surface(scaled.get_size())
            plain.blit(scaled, (0, 0))  # альфа везде 255: цвета предумножения совпадают с обычными
            return plain

        return _remember(self._sprites, (image, size, "opaque"), build)

    def scaled_patch(self, surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        """Заплатка, увеличенная ближайшим соседом, с кэшем по содержимому: окно реплики или полоса
        интерфейса рисуются заново каждый кадр, но меняются редко, а увеличение в полном экране
        стоит около 2 мс. Отпечаток маленькой логической картинки считается в десять раз быстрее."""
        pixels = pygame.image.tobytes(surface, "RGBA")
        digest = hashlib.blake2b(pixels, digest_size=16).digest()
        key = (digest, surface.get_size(), size)
        return _remember(self._patches, key, lambda: _scale_patch(surface, pixels, size))

    def text_image(self, text: str, style: TextStyle, scale: float, angle: float = 0.0) -> pygame.Surface:
        """Строка со сглаживанием шрифтом размера окна (без тени), с кэшем: заново рисуется,
        только если изменились текст, размер, начертание, цвет, масштаб окна или поворот."""

        def render() -> pygame.Surface:
            font = self.fonts.font(style.size, scale, style.bold)
            if style.background is not None:
                # Непрозрачная строка на своём фоне: сглаживание то же, а выводится простым копированием.
                image = font.render(text, True, style.color, style.background)
                if pygame.display.get_surface() is not None:
                    image = image.convert()
            else:
                image = font.render(text, True, style.color)
            # Поворот на 180° — точное отражение пикселей, буквы остаются такими же чёткими.
            return pygame.transform.rotate(image, angle) if angle else image

        key = (text, style.size, style.bold, style.color, style.background, scale, angle)
        return _remember(self._texts, key, render)

    def _draw_sprite(self, target: pygame.Surface, transform: ViewTransform, command: SpriteCommand) -> None:
        rect = transform.rect(command.rect)
        if rect.width <= 0 or rect.height <= 0:
            return
        if command.opaque and not command.angle and command.alpha >= 255:
            target.blit(self.scaled_opaque(command.image, rect.size), rect)
            return
        image = self.scaled_sprite(command.image, rect.size)
        if command.angle:
            # rotozoom заполняет углы прозрачным (0, 0, 0, 0) — для предумноженной альфы это важно.
            image = pygame.transform.rotozoom(image, command.angle, 1.0)
            rect = image.get_rect(center=rect.center)
        if command.alpha < 255:
            image = image.copy()
            a = command.alpha
            image.fill((a, a, a, a), special_flags=pygame.BLEND_RGBA_MULT)  # предумноженная альфа: все каналы
        target.blit(image, rect, special_flags=pygame.BLEND_PREMULTIPLIED)

    def _draw_text(self, target: pygame.Surface, transform: ViewTransform, command: TextCommand) -> None:
        style = command.style
        if style.background is not None and (command.alpha < 255 or style.shadow is not None):
            style = replace(style, background=None)  # полупрозрачной строке фон не подходит
        image = self.text_image(command.text, style, transform.scale, command.angle)
        rect = image.get_rect(**{command.anchor: transform.point(command.pos)})
        layers = [(image, rect)]
        if style.shadow is not None:
            shadow_style = replace(style, color=style.shadow, shadow=None, background=None)
            shadow = self.text_image(command.text, shadow_style, transform.scale, command.angle)
            offset = max(1, round(style.shadow_offset * transform.scale))
            layers.insert(0, (shadow, rect.move(offset, offset)))
        for surface, place in layers:
            if command.alpha < 255:
                surface = surface.copy()
                surface.set_alpha(command.alpha)
            target.blit(surface, place)

    def _draw_group(self, target: pygame.Surface, transform: ViewTransform, command: GroupCommand) -> None:
        rect = transform.rect(command.rect)
        if rect.width <= 0 or rect.height <= 0:
            return

        def build() -> pygame.Surface:
            image = pygame.Surface(rect.size, 0, target)
            # Та же трансформация, только начало координат — в левом верхнем углу панели.
            local = ViewTransform(transform.viewport.move(-rect.x, -rect.y), transform.logical_size)
            self._render(image, local, command.commands)
            return image

        image = _remember(self._groups, (command.key, rect.size), build)
        if command.alpha < 255:
            image.set_alpha(command.alpha)
            target.blit(image, rect)
            image.set_alpha(None)
        else:
            target.blit(image, rect)

    def _draw_torn(self, target: pygame.Surface, transform: ViewTransform, command: TearCommand) -> None:
        """Собирает холст и его команды в отдельном изображении размера области окна и рвёт его полосами."""
        viewport = transform.viewport
        image = self._offscreen
        if image is None or image.get_size() != viewport.size:
            image = self._offscreen = pygame.Surface(viewport.size, 0, command.canvas)
        pygame.transform.scale(command.canvas, viewport.size, image)
        local = ViewTransform(image.get_rect(), transform.logical_size)
        self._render(image, local, command.commands)
        target.blit(image, viewport)
        for y, height, offset in command.bands:
            area = local.rect(pygame.Rect(0, y, transform.logical_size[0], height))
            shift = round(offset * transform.scale)
            for dx in (shift, shift - viewport.width if shift > 0 else shift + viewport.width):
                target.blit(image, (viewport.x + dx, viewport.y + area.y), area)

    def _draw_fill(self, target: pygame.Surface, transform: ViewTransform, command: FillCommand) -> None:
        rect = transform.viewport if command.rect is None else transform.rect(command.rect)
        if command.alpha >= 255:
            target.fill(command.color, rect)
            return
        key = (rect.size, command.color)
        surface = self._fills.get(key)
        if surface is None:
            surface = self._fills[key] = pygame.Surface(rect.size)
            surface.fill(command.color)
        if surface.get_alpha() != command.alpha:  # смена прозрачности заставляет SDL заново готовить вывод
            surface.set_alpha(command.alpha)
        target.blit(surface, rect)


def _command_key(command: Command) -> tuple:
    """Что определяет вид команды внутри группы — для ключа её картинки."""
    if isinstance(command, TextCommand):
        clip = tuple(command.clip) if command.clip is not None else None
        return ("text", command.text, command.style, command.pos, command.anchor, command.alpha, clip, command.angle)
    if isinstance(command, FillCommand):
        return ("fill", command.color, tuple(command.rect) if command.rect is not None else None, command.alpha)
    if isinstance(command, SpriteCommand):
        clip = tuple(command.clip) if command.clip is not None else None
        return ("sprite", command.image, tuple(command.rect), command.alpha, command.angle, clip, command.opaque)
    if isinstance(command, PatchCommand):
        digest = hashlib.blake2b(pygame.image.tobytes(command.surface, "RGBA"), digest_size=16).digest()
        return ("patch", digest, tuple(command.rect))
    raise TypeError(f"в неподвижной панели не может быть {type(command).__name__}")


def _scale_patch(surface: pygame.Surface, pixels: bytes, size: tuple[int, int]) -> pygame.Surface:
    """Увеличивает заплатку ближайшим соседом. Если её пиксели либо прозрачны, либо непрозрачны
    (так рисуют pygame.draw и заливки), результат — поверхность с цветовым ключом и RLE: она
    выводится в несколько раз быстрее смешивания по альфе, а пиксели получаются те же."""
    scaled = pygame.transform.scale(surface, size)
    alphas = set(pixels[3::4])
    if not alphas <= {0, 255} or pygame.display.get_surface() is None:
        return scaled
    colors = {pixels[i : i + 3] for i in range(0, len(pixels), 4) if pixels[i + 3]}
    key = next((color for color in PATCH_KEYS if bytes(color) not in colors), None)
    if key is None:
        return scaled
    keyed = pygame.Surface(size).convert()
    keyed.fill(key)
    keyed.blit(scaled, (0, 0))
    keyed.set_colorkey(key, pygame.RLEACCEL)
    return keyed


def _remember(cache: OrderedDict, key: Hashable, make: Callable[[], pygame.Surface]) -> pygame.Surface:
    """Значение из кэша или make(); при переполнении вытесняется давно не использованное."""
    value = cache.get(key)
    if value is None:
        value = cache[key] = make()
        if len(cache) > CACHE_LIMIT:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    return value


def logical_target(canvas: pygame.Surface, hires: HiResLayer | None, area: pygame.Rect | None = None):
    """Куда рисовать логическую графику, которая должна лечь поверх уже нарисованного.

    Без слоя высокого разрешения — прямо на холст (прежний путь), со слоем — через
    HiResLayer.logical(canvas, area). Используется как контекстный менеджер: with logical_target(...) as s.
    """
    return nullcontext(canvas) if hires is None else hires.logical(canvas, area)
