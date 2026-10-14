"""Временное оформление диалога: окно внизу экрана с именем, текстом и вариантами ответа.

Два способа вывода. На холсте (прежний путь, для сцен без слоя высокого разрешения) всё
рисуется пиксельным шрифтом холста. Со слоем высокого разрешения (game/graphics/hires.py)
рамка окна остаётся пиксельной и рисуется той же графикой, а имя, реплика и варианты —
шрифтом без засечек в разрешении окна. Для каждого способа своя раскладка (переносы строк
считаются своим шрифтом), но размеры окна и строк — в тех же логических пикселях.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import pygame

import config
from game.dialogue.model import DialogueController, DialogueError, DialogueNode, DialogueScript
from game.graphics.fonts import TextFonts, TextMetrics, TextStyle, load_font, render_text
from game.graphics.hires import HiResLayer

SCREEN_WIDTH, SCREEN_HEIGHT = config.LOGICAL_SIZE
FONT_SIZE = 10
MARGIN = 6  # от края экрана до окна
PADDING_X = 8  # внутренние отступы окна
PADDING_Y = 6
MIN_ROWS = 3  # минимальная высота в строках, чтобы окно не «прыгало» между короткими репликами
CHOICES_GAP = 4  # между текстом реплики и вариантами ответа
CHOICE_INDENT = 10  # место слева от вариантов под стрелку выбора
NAME_PADDING_X = 6
NAME_PADDING_Y = 2

# Текст высокого разрешения: размер — в логических пикселях, как у FONT_SIZE.
TEXT_SIZE = 9
TEXT_STYLE = TextStyle(TEXT_SIZE, config.DIALOGUE_TEXT_COLOR)
NAME_STYLE = TextStyle(TEXT_SIZE, config.DIALOGUE_NAME_COLOR, bold=True)
CHOICE_STYLE = TextStyle(TEXT_SIZE, config.DIALOGUE_CHOICE_COLOR)
SELECTED_STYLE = TextStyle(TEXT_SIZE, config.DIALOGUE_SELECTED_COLOR)

_WORD = re.compile(r"\S+")


def wrap_spans(text: str, font: pygame.font.Font | TextMetrics, max_width: int) -> list[tuple[int, int]]:
    """Разбивает текст на строки не шире max_width пикселей.

    font — пиксельный шрифт холста или TextMetrics текста высокого разрешения (ширина
    в логических пикселях): нужен только его метод size().

    Возвращает границы строк (начало, конец) в исходном тексте. Так печатающийся
    текст сразу появляется на своей строке, и слова не перескакивают при переносе.
    Переносы делаются по пробелам. Слово, которое не помещается в строку целиком,
    режется по буквам. Символ \\n начинает новую строку.
    """
    spans: list[tuple[int, int]] = []
    paragraph_start = 0
    for paragraph in text.split("\n"):
        line: tuple[int, int] | None = None
        for match in _WORD.finditer(paragraph):
            start, end = paragraph_start + match.start(), paragraph_start + match.end()
            if line is not None and font.size(text[line[0] : end])[0] <= max_width:
                line = (line[0], end)
                continue
            if line is not None:
                spans.append(line)
            while font.size(text[start:end])[0] > max_width:
                cut = start + 1  # хотя бы одна буква, даже если строка совсем узкая
                while cut < end and font.size(text[start : cut + 1])[0] <= max_width:
                    cut += 1
                spans.append((start, cut))
                start = cut
            line = (start, end)
        spans.append(line if line is not None else (paragraph_start, paragraph_start))
        paragraph_start += len(paragraph) + 1
    return spans


def wrap_text(text: str, font: pygame.font.Font | TextMetrics, max_width: int) -> list[str]:
    """То же, что wrap_spans, но возвращает сами строки."""
    return [text[start:end] for start, end in wrap_spans(text, font, max_width)]


@dataclass(frozen=True)
class DialogueLayout:
    """Расположение одной реплики на экране. Считается один раз на реплику."""

    box: pygame.Rect
    name_tab: pygame.Rect | None
    text_spans: list[tuple[int, int]]
    choice_lines: list[list[str]]
    choices_top: int
    line_height: int


class DialogueBox:
    """Рисует текущее состояние DialogueController на логическом холсте 320×180
    или, со слоем высокого разрешения, — текст в разрешении окна (см. описание модуля)."""

    def __init__(self, fonts: TextFonts | None = None) -> None:
        self._font = load_font(FONT_SIZE)
        self.line_height = self._font.get_linesize()
        fonts = fonts if fonts is not None else TextFonts()
        self._text_metrics = fonts.metrics(TEXT_STYLE)
        self._name_metrics = fonts.metrics(NAME_STYLE)
        # Строки высокого разрешения не теснее пиксельных: окно того же размера, текст — того же ритма.
        self.hires_line_height = max(self.line_height, math.ceil(self._text_metrics.height))
        self._layouts: dict[tuple[DialogueNode, bool], DialogueLayout] = {}

    def check_fits(self, script: DialogueScript) -> None:
        """Проверяет, что каждая реплика сценария помещается на экран при обоих способах вывода,
        иначе DialogueError."""
        for node in script.nodes.values():
            self.layout(node)
            self.layout(node, hires=True)

    def layout(self, node: DialogueNode, hires: bool = False) -> DialogueLayout:
        """Раскладка реплики для холста или (hires=True) для текста высокого разрешения."""
        key = (node, hires)
        layout = self._layouts.get(key)
        if layout is None:
            layout = self._layouts[key] = self._build_layout(node, hires)
        return layout

    def draw(self, surface: pygame.Surface, dialogue: DialogueController, hires: HiResLayer | None = None) -> None:
        node = dialogue.node
        if node is None:
            return
        if hires is not None:
            self._draw_hires(surface, dialogue, node, hires)
            return
        layout = self.layout(node)
        box = layout.box
        self._draw_frame(surface, layout, dialogue)

        if layout.name_tab is not None:
            tab = layout.name_tab
            name = render_text(self._font, node.speaker, config.DIALOGUE_NAME_COLOR)
            surface.blit(name, (tab.x + NAME_PADDING_X, tab.y + NAME_PADDING_Y))

        # Строки размечены заранее, печать только открывает их символ за символом.
        visible = dialogue.visible_chars
        for row, (start, end) in enumerate(layout.text_spans):
            if visible <= start:
                break
            line = render_text(self._font, node.text[start : min(end, visible)], config.DIALOGUE_TEXT_COLOR)
            surface.blit(line, (box.x + PADDING_X, box.y + PADDING_Y + row * self.line_height))

        if not dialogue.is_typing and dialogue.choices:
            x, y = box.x + PADDING_X + CHOICE_INDENT, layout.choices_top
            for index, lines in enumerate(layout.choice_lines):
                selected = index == dialogue.selected_index
                color = config.DIALOGUE_SELECTED_COLOR if selected else config.DIALOGUE_CHOICE_COLOR
                for row, line in enumerate(lines):
                    surface.blit(render_text(self._font, line, color), (x, y + row * self.line_height))
                y += len(lines) * self.line_height

    def _draw_hires(self, surface: pygame.Surface, dialogue: DialogueController, node: DialogueNode,
                    hires: HiResLayer) -> None:
        """Рамка — пиксельная (поверх уже нарисованных персонажей), текст — в разрешении окна.

        Каждая строка выравнивается по середине своей строки раскладки: так шрифт любой
        высоты стоит в окне так же, как пиксельный."""
        layout = self.layout(node, hires=True)
        box, line_height = layout.box, layout.line_height
        area = box.union(layout.name_tab) if layout.name_tab is not None else box
        with hires.logical(surface, area) as panel:
            self._draw_frame(panel, layout, dialogue)

        if layout.name_tab is not None:
            tab = layout.name_tab
            hires.text(node.speaker, NAME_STYLE, (tab.x + NAME_PADDING_X, tab.y + NAME_PADDING_Y + line_height / 2),
                       anchor="midleft")

        visible = dialogue.visible_chars
        for row, (start, end) in enumerate(layout.text_spans):
            if visible <= start:
                break
            middle = box.y + PADDING_Y + row * line_height + line_height / 2
            hires.text(node.text[start : min(end, visible)], TEXT_STYLE, (box.x + PADDING_X, middle), anchor="midleft")

        if not dialogue.is_typing and dialogue.choices:
            y = layout.choices_top
            for index, lines in enumerate(layout.choice_lines):
                style = SELECTED_STYLE if index == dialogue.selected_index else CHOICE_STYLE
                for row, line in enumerate(lines):
                    middle = y + row * line_height + line_height / 2
                    hires.text(line, style, (box.x + PADDING_X + CHOICE_INDENT, middle), anchor="midleft")
                y += len(lines) * line_height

    def _draw_frame(self, surface: pygame.Surface, layout: DialogueLayout, dialogue: DialogueController) -> None:
        """Всё, кроме текста: окно, табличка с именем, подсветка выбранного ответа и стрелки."""
        box = layout.box
        pygame.draw.rect(surface, config.DIALOGUE_BOX_COLOR, box)
        pygame.draw.rect(surface, config.DIALOGUE_BORDER_COLOR, box, 1)

        if layout.name_tab is not None:
            tab = layout.name_tab
            pygame.draw.rect(surface, config.DIALOGUE_BOX_COLOR, tab)
            pygame.draw.rect(surface, config.DIALOGUE_BORDER_COLOR, tab, 1)
            # Убираем линию между табличкой и окном, чтобы они выглядели единым целым.
            surface.fill(config.DIALOGUE_BOX_COLOR, (tab.x + 1, box.y, tab.width - 2, 1))

        if dialogue.is_typing:
            return
        if dialogue.choices:
            self._draw_choice_marks(surface, layout, dialogue.selected_index)
        else:
            # Стрелка у нижней рамки справа, ниже строк текста: текст дописан, Enter продолжит диалог.
            _draw_arrow_down(surface, config.DIALOGUE_TEXT_COLOR, box.right - PADDING_X - 5, box.bottom - 4)

    def _draw_choice_marks(self, surface: pygame.Surface, layout: DialogueLayout, selected_index: int) -> None:
        """Подсветка и стрелка у выбранного варианта ответа."""
        x = layout.box.x + PADDING_X
        y = layout.choices_top
        for index, lines in enumerate(layout.choice_lines):
            height = len(lines) * layout.line_height
            if index == selected_index:
                surface.fill(config.DIALOGUE_SELECTED_BG_COLOR, (layout.box.x + 3, y, layout.box.width - 6, height))
                _draw_arrow_right(surface, config.DIALOGUE_SELECTED_COLOR, x + 1, y + layout.line_height // 2 - 2)
            y += height

    def _build_layout(self, node: DialogueNode, hires: bool) -> DialogueLayout:
        font = self._text_metrics if hires else self._font
        line_height = self.hires_line_height if hires else self.line_height
        inner_width = SCREEN_WIDTH - 2 * MARGIN - 2 * PADDING_X
        text_spans = wrap_spans(node.text, font, inner_width)
        choice_lines = [wrap_text(choice.text, font, inner_width - CHOICE_INDENT) for choice in node.choices or ()]

        # Высота окна рассчитывается сразу с вариантами ответа, чтобы окно не росло,
        # когда они появятся после печати текста.
        content_height = len(text_spans) * line_height
        if choice_lines:
            content_height += CHOICES_GAP + sum(len(lines) for lines in choice_lines) * line_height
        box_height = max(MIN_ROWS * line_height, content_height) + 2 * PADDING_Y
        box = pygame.Rect(MARGIN, SCREEN_HEIGHT - MARGIN - box_height, SCREEN_WIDTH - 2 * MARGIN, box_height)

        name_tab = None
        if node.speaker:
            name_width = math.ceil((self._name_metrics if hires else self._font).size(node.speaker)[0])
            name_width += 2 * NAME_PADDING_X
            # Табличка с именем стоит на верхней рамке окна.
            name_tab = pygame.Rect(box.x + PADDING_X, 0, name_width, line_height + 2 * NAME_PADDING_Y)
            name_tab.bottom = box.y + 1
            if name_tab.right > box.right - PADDING_X:
                raise DialogueError(f"имя «{node.speaker}» в реплике «{node.id}» не помещается в окно диалога")

        top = name_tab.top if name_tab is not None else box.top
        if top < MARGIN:
            raise DialogueError(
                f"реплика «{node.id}» не помещается на экран: сократите текст или разбейте его на несколько реплик"
            )
        choices_top = box.y + PADDING_Y + len(text_spans) * line_height + CHOICES_GAP
        return DialogueLayout(box, name_tab, text_spans, choice_lines, choices_top, line_height)


def _draw_arrow_right(surface: pygame.Surface, color: config.Color, x: int, y: int) -> None:
    """Стрелка выбора 3×5 пикселей. Рисуется линиями, чтобы края оставались ровными."""
    for step in range(3):
        pygame.draw.line(surface, color, (x + step, y + step), (x + step, y + 4 - step))


def _draw_arrow_down(surface: pygame.Surface, color: config.Color, x: int, y: int) -> None:
    """Стрелка «продолжить» 5×3 пикселя."""
    for step in range(3):
        pygame.draw.line(surface, color, (x + step, y + step), (x + 4 - step, y + step))
