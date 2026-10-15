"""Шрифты с поддержкой кириллицы.

Два вида текста:
- пиксельный — load_font() и render_text(): моноширинный шрифт в пикселях холста 320×180,
  без сглаживания; увеличивается вместе с холстом (сцены, ещё не переведённые на слой
  высокого разрешения);
- высокого разрешения — TextStyle и TextFonts: разборчивый шрифт без засечек, который
  рисуется со сглаживанием прямо в разрешении окна (game/graphics/hires.py). Размеры
  в нём тоже задаются в логических пикселях холста, а в пиксели окна переводятся при выводе.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config

# Встроенный шрифт Pygame (freesansbold.ttf) Pygame сам уменьшает до 0,6875 запрошенного
# размера. Делим на этот множитель, чтобы запасной шрифт был того же роста, что и системные.
DEFAULT_FONT_SCALE = 0.6875

# Масштабы окна, при которых измеряется ширина текста высокого разрешения. Хинтинг округляет
# ширину каждой буквы до пикселей окна, поэтому одна и та же строка при ×3 бывает на несколько
# логических пикселей шире, чем при ×6. Перенос строк считается по самой широкой из них:
# раскладка одна для любого окна, а строки помещаются в свои рамки при каждом из этих масштабов
# (×3 — окно 960×540, ×6 — полный экран 1920×1080/1200, остальные — окно другого размера).
LAYOUT_SCALES = (2, 3, 4, 5, 6)


def find_font_path() -> str | None:
    """Возвращает путь к первому установленному шрифту из config.FONT_CANDIDATES.

    None означает встроенный шрифт Pygame (freesansbold.ttf): кириллица в нём
    есть, но он не моноширинный.
    """
    for name in config.FONT_CANDIDATES:
        path = pygame.font.match_font(name)
        if path:
            return path
    return None


def load_font(size: int) -> pygame.font.Font:
    """Загружает шрифт нужного размера в пикселях логического разрешения."""
    return pygame.font.Font(find_font_path(), size)


def render_text(font: pygame.font.Font, text: str, color: config.Color) -> pygame.Surface:
    """Рисует строку без сглаживания: у пиксельного текста не должно быть полупрозрачных краёв."""
    return font.render(text, False, color)


def find_text_font_path(bold: bool = False) -> str | None:
    """Путь к первому установленному шрифту без засечек из config.TEXT_FONT_CANDIDATES.

    bold=True ищет полужирное начертание того же шрифта; если его нет, возвращается
    обычное (TextFonts тогда сделает его жирным сам). None — встроенный шрифт Pygame
    (freesansbold.ttf, в нём тоже есть кириллица).
    """
    for name in config.TEXT_FONT_CANDIDATES:
        path = pygame.font.match_font(name, bold=bold) or pygame.font.match_font(name)
        if path:
            return path
    return None


@dataclass(frozen=True)
class TextStyle:
    """Как выглядит текст высокого разрешения.

    size — высота шрифта в логических пикселях холста (как у load_font); в окне ×3
    это втрое больше пикселей. shadow — цвет тени, сдвинутой на shadow_offset
    логических пикселей вправо и вниз (None — без тени). background — цвет однотонного
    фона, на котором всегда стоит строка (бумага письма, полоса интерфейса, окно реплики):
    тогда она рисуется сразу на этом фоне, непрозрачной, и выводится в разы быстрее
    сглаженной прозрачной; буквы выглядят так же. Пока надпись полупрозрачна или у неё
    есть тень, фон не используется.
    """

    size: float
    color: config.Color
    bold: bool = False
    shadow: config.Color | None = None
    shadow_offset: float = 0.5
    background: config.Color | None = None

    def __post_init__(self) -> None:
        if not 0 < self.size < math.inf:
            raise ValueError(f"размер шрифта должен быть положительным числом, а не {self.size!r}")


_AUTO = object()


class TextFonts:
    """Шрифты текста высокого разрешения: Font на каждый размер в пикселях окна и начертание.

    Шрифты создаются по требованию и живут в этом объекте, как load_font() в сценах:
    после pygame.quit() старые Font использовать нельзя, а новый объект создаст новые.
    regular и bold — пути к файлам шрифтов (None — встроенный шрифт Pygame); по умолчанию
    они ищутся среди установленных (find_text_font_path).
    """

    def __init__(self, regular: str | None | object = _AUTO, bold: str | None | object = _AUTO) -> None:
        self.regular_path = find_text_font_path() if regular is _AUTO else regular
        if bold is _AUTO:
            bold = find_text_font_path(bold=True) if regular is _AUTO else regular
        self.bold_path = bold
        self._fonts: dict[tuple[int, bool], pygame.font.Font] = {}

    def font(self, size: float, scale: float, bold: bool = False) -> pygame.font.Font:
        """Шрифт для текста размера size (логические пиксели) в окне с масштабом scale."""
        pixels = max(1, round(size * scale))
        key = (pixels, bold)
        font = self._fonts.get(key)
        if font is None:
            path = self.bold_path if bold else self.regular_path
            requested = pixels if path is not None else max(1, round(pixels / DEFAULT_FONT_SCALE))
            font = pygame.font.Font(path, requested)
            # Отдельного жирного файла нет — Pygame утолщает буквы обычного начертания.
            font.set_bold(bold and path == self.regular_path)
            self._fonts[key] = font
        return font

    def metrics(self, style: TextStyle) -> TextMetrics:
        return TextMetrics(self, style)


class TextMetrics:
    """Размеры текста одного стиля в логических пикселях — для раскладки (переносы, рамки).

    size(text) — как у pygame.font.Font, поэтому подходит для wrap_spans(); ширина берётся
    самая большая из LAYOUT_SCALES, высота — тоже (см. LAYOUT_SCALES).
    """

    def __init__(self, fonts: TextFonts, style: TextStyle) -> None:
        self.style = style
        self._fonts = [(fonts.font(style.size, scale, style.bold), scale) for scale in LAYOUT_SCALES]
        self.height = max(font.get_height() / scale for font, scale in self._fonts)
        self._widths: dict[str, float] = {}  # надписи интерфейса измеряются каждый кадр — запоминаем

    def width(self, text: str) -> float:
        width = self._widths.get(text)
        if width is None:
            if len(self._widths) >= 1024:
                self._widths.clear()
            width = self._widths[text] = max(font.size(text)[0] / scale for font, scale in self._fonts) if text else 0.0
        return width

    def size(self, text: str) -> tuple[float, float]:
        return self.width(text), self.height

    def missing_glyphs(self, text: str) -> set[str]:
        """Буквы text, которых нет в шрифте (Pygame показал бы вместо них пустые квадраты)."""
        font = self._fonts[0][0]
        return {char for char, metric in zip(text, font.metrics(text)) if metric is None and not char.isspace()}
