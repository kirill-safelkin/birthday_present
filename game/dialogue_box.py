"""Временное оформление диалога: окно внизу экрана с именем, текстом и вариантами ответа."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pygame

import config
from game.dialogue import DialogueController, DialogueError, DialogueNode, DialogueScript
from game.fonts import load_font, render_text

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

_WORD = re.compile(r"\S+")


def wrap_spans(text: str, font: pygame.font.Font, max_width: int) -> list[tuple[int, int]]:
    """Разбивает текст на строки не шире max_width пикселей.

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


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
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


class DialogueBox:
    """Рисует текущее состояние DialogueController на логическом холсте 320×180."""

    def __init__(self) -> None:
        self._font = load_font(FONT_SIZE)
        self.line_height = self._font.get_linesize()
        self._layouts: dict[DialogueNode, DialogueLayout] = {}

    def check_fits(self, script: DialogueScript) -> None:
        """Проверяет, что каждая реплика сценария помещается на экран, иначе DialogueError."""
        for node in script.nodes.values():
            self.layout(node)

    def layout(self, node: DialogueNode) -> DialogueLayout:
        layout = self._layouts.get(node)
        if layout is None:
            layout = self._layouts[node] = self._build_layout(node)
        return layout

    def draw(self, surface: pygame.Surface, dialogue: DialogueController) -> None:
        node = dialogue.node
        if node is None:
            return
        layout = self.layout(node)
        box = layout.box
        pygame.draw.rect(surface, config.DIALOGUE_BOX_COLOR, box)
        pygame.draw.rect(surface, config.DIALOGUE_BORDER_COLOR, box, 1)

        if layout.name_tab is not None:
            tab = layout.name_tab
            pygame.draw.rect(surface, config.DIALOGUE_BOX_COLOR, tab)
            pygame.draw.rect(surface, config.DIALOGUE_BORDER_COLOR, tab, 1)
            # Убираем линию между табличкой и окном, чтобы они выглядели единым целым.
            surface.fill(config.DIALOGUE_BOX_COLOR, (tab.x + 1, box.y, tab.width - 2, 1))
            name = render_text(self._font, node.speaker, config.DIALOGUE_NAME_COLOR)
            surface.blit(name, (tab.x + NAME_PADDING_X, tab.y + NAME_PADDING_Y))

        # Строки размечены заранее, печать только открывает их символ за символом.
        visible = dialogue.visible_chars
        for row, (start, end) in enumerate(layout.text_spans):
            if visible <= start:
                break
            line = render_text(self._font, node.text[start : min(end, visible)], config.DIALOGUE_TEXT_COLOR)
            surface.blit(line, (box.x + PADDING_X, box.y + PADDING_Y + row * self.line_height))

        if dialogue.is_typing:
            return
        if dialogue.choices:
            self._draw_choices(surface, layout, dialogue.selected_index)
        else:
            # Стрелка у нижней рамки справа, ниже строк текста: текст дописан, Enter продолжит диалог.
            _draw_arrow_down(surface, config.DIALOGUE_TEXT_COLOR, box.right - PADDING_X - 5, box.bottom - 4)

    def _draw_choices(self, surface: pygame.Surface, layout: DialogueLayout, selected_index: int) -> None:
        x = layout.box.x + PADDING_X
        y = layout.choices_top
        for index, lines in enumerate(layout.choice_lines):
            height = len(lines) * self.line_height
            selected = index == selected_index
            if selected:
                surface.fill(config.DIALOGUE_SELECTED_BG_COLOR, (layout.box.x + 3, y, layout.box.width - 6, height))
                _draw_arrow_right(surface, config.DIALOGUE_SELECTED_COLOR, x + 1, y + 4)
            color = config.DIALOGUE_SELECTED_COLOR if selected else config.DIALOGUE_CHOICE_COLOR
            for row, line in enumerate(lines):
                surface.blit(render_text(self._font, line, color), (x + CHOICE_INDENT, y + row * self.line_height))
            y += height

    def _build_layout(self, node: DialogueNode) -> DialogueLayout:
        line_height = self.line_height
        inner_width = SCREEN_WIDTH - 2 * MARGIN - 2 * PADDING_X
        text_spans = wrap_spans(node.text, self._font, inner_width)
        choice_lines = [wrap_text(choice.text, self._font, inner_width - CHOICE_INDENT) for choice in node.choices or ()]

        # Высота окна рассчитывается сразу с вариантами ответа, чтобы окно не росло,
        # когда они появятся после печати текста.
        content_height = len(text_spans) * line_height
        if choice_lines:
            content_height += CHOICES_GAP + sum(len(lines) for lines in choice_lines) * line_height
        box_height = max(MIN_ROWS * line_height, content_height) + 2 * PADDING_Y
        box = pygame.Rect(MARGIN, SCREEN_HEIGHT - MARGIN - box_height, SCREEN_WIDTH - 2 * MARGIN, box_height)

        name_tab = None
        if node.speaker:
            name_width = self._font.size(node.speaker)[0] + 2 * NAME_PADDING_X
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
        return DialogueLayout(box, name_tab, text_spans, choice_lines, choices_top)


def _draw_arrow_right(surface: pygame.Surface, color: config.Color, x: int, y: int) -> None:
    """Стрелка выбора 3×5 пикселей. Рисуется линиями, чтобы края оставались ровными."""
    for step in range(3):
        pygame.draw.line(surface, color, (x + step, y + step), (x + step, y + 4 - step))


def _draw_arrow_down(surface: pygame.Surface, color: config.Color, x: int, y: int) -> None:
    """Стрелка «продолжить» 5×3 пикселя."""
    for step in range(3):
        pygame.draw.line(surface, color, (x + step, y + step), (x + 4 - step, y + step))
