"""Тестовая галерея спрайтов: просмотр кадров и групп анимации импортированных персонажей.

Открывается клавишей P с экрана проверки. Это инструмент проверки ресурсов, а не часть игры:
персонажи здесь не подключаются к сценам.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

import config
from game.core.input import matches_key
from game.dialogue.box import wrap_text
from game.graphics.animation import AnimationPlayer
from game.graphics.fonts import load_font, render_text
from game.graphics.sprite_manifest import (
    CHARACTERS_DIR,
    CharacterSprites,
    ManifestError,
    SpriteFrame,
    SpriteGroup,
    character_dirs,
    load_character_sprites,
)

SCREEN_WIDTH, SCREEN_HEIGHT = config.LOGICAL_SIZE
# Сначала главные герои, остальные папки — по алфавиту после них.
CHARACTER_ORDER = ("alice", "chuchmek", "leo", "white_rabbit", "cat_chef", "goose_inspector", "hamster_official")
# Размер, до которого увеличивается или уменьшается кадр на холсте 320×180, в логических пикселях.
DISPLAY_SIZES = (24, 32, 40, 48, 64)
SIZE_KEYS = (
    (pygame.K_1, pygame.K_KP1, pygame.KSCAN_1),
    (pygame.K_2, pygame.K_KP2, pygame.KSCAN_2),
    (pygame.K_3, pygame.K_KP3, pygame.KSCAN_3),
    (pygame.K_4, pygame.K_KP4, pygame.KSCAN_4),
    (pygame.K_5, pygame.K_KP5, pygame.KSCAN_5),
)
BACK_KEY = pygame.K_BACKSPACE
# Зажатая ↑/↓ листает кадры сама: сначала пауза, потом шаг за шагом.
REPEAT_DELAY = 0.35
REPEAT_INTERVAL = 0.07

PANEL_RECT = pygame.Rect(8, 30, 76, 76)
PANEL_TILE = 4
PANEL_COLORS: tuple[config.Color, config.Color] = ((40, 44, 64), (48, 53, 76))
CELL_OUTLINE_COLOR: config.Color = (90, 98, 132)
DRAFT_COLOR: config.Color = (236, 146, 86)
ERROR_COLOR: config.Color = (232, 112, 112)
INFO_LEFT = 92
INFO_TOP = 30
INFO_WIDTH = SCREEN_WIDTH - INFO_LEFT - 6
MAX_DESCRIPTION_LINES = 2
MAX_REASON_LINES = 3
HINTS = (
    "←/→ персонаж  ↑/↓ кадр  Tab группа  Пробел пуск/стоп",
    "1–5 размер 24–64  Backspace назад  ESC выход",
)
HINTS_TOP = 156


@dataclass(eq=False)
class GalleryEntry:
    """Персонаж в галерее: загруженные спрайты или понятное сообщение об ошибке."""

    id: str
    sprites: CharacterSprites | None
    error: str = ""


def load_entries(root: str | Path = CHARACTERS_DIR) -> list[GalleryEntry]:
    """Загружает всех персонажей из root. Сломанный персонаж не мешает остальным."""
    order = {char_id: position for position, char_id in enumerate(CHARACTER_ORDER)}
    directories = sorted(character_dirs(root), key=lambda path: (order.get(path.name, len(order)), path.name))
    entries = []
    for directory in directories:
        try:
            entries.append(GalleryEntry(directory.name, load_character_sprites(directory)))
        except (ManifestError, FileNotFoundError, pygame.error) as exc:
            entries.append(GalleryEntry(directory.name, None, str(exc)))
    return entries


class SpriteGallery:
    """Один персонаж за раз: кадр в увеличении, его описание и группы анимации."""

    def __init__(self, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.characters_dir = Path(characters_dir)
        self.entries = load_entries(characters_dir)
        self.character_index = 0
        self.frame_index = 0  # позиция в списке кадров манифеста
        self.group_index = 0
        self.display_size = DISPLAY_SIZES[-1]
        self.player: AnimationPlayer | None = None  # не None, пока группа проигрывается
        self.is_finished = False  # пора вернуться на экран проверки
        self._repeat_step = 0
        self._repeat_timer = 0.0

        self._title_font = load_font(10)
        self._font = load_font(9)
        self._line_height = self._font.get_linesize()
        # Надписи и подложка рисуются один раз и потом только копируются: экран обновляется
        # 60 раз в секунду, а текст меняется редко.
        self._text_cache: dict[tuple[int, str, config.Color], pygame.Surface] = {}
        self._panel = _render_panel()
        self.labels: list[tuple[pygame.Surface, pygame.Rect]] = []
        for row, text in enumerate(HINTS):
            hint = self._text(self._font, text, config.HINT_COLOR)
            self.labels.append((hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, HINTS_TOP + row * self._line_height))))

    # --- Текущее состояние ---

    @property
    def entry(self) -> GalleryEntry | None:
        return self.entries[self.character_index] if self.entries else None

    @property
    def sprites(self) -> CharacterSprites | None:
        return self.entry.sprites if self.entry is not None else None

    @property
    def group(self) -> SpriteGroup | None:
        sprites = self.sprites
        if sprites is None or not sprites.groups:
            return None
        return list(sprites.groups.values())[self.group_index]

    @property
    def is_playing(self) -> bool:
        return self.player is not None

    @property
    def current_frame(self) -> SpriteFrame | None:
        """Кадр на экране: при проигрывании — текущий кадр группы, иначе выбранный."""
        sprites = self.sprites
        if sprites is None:
            return None
        if self.player is not None and self.group is not None:
            return sprites.frame(self.group.frame_ids[self.player.frame_index])
        return sprites.frames[self.frame_index]

    # --- Управление ---

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.WINDOWFOCUSLOST:
            self._repeat_step = 0
        elif event.type == pygame.KEYUP and event.key in (pygame.K_UP, pygame.K_DOWN):
            self._repeat_step = 0
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event)

    def _handle_key(self, event: pygame.event.Event) -> None:
        if event.key == BACK_KEY:
            self.is_finished = True
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.select_character(self.character_index + (1 if event.key == pygame.K_RIGHT else -1))
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            step = 1 if event.key == pygame.K_DOWN else -1
            self.step_frame(step)
            self._repeat_step = step
            self._repeat_timer = REPEAT_DELAY
        elif event.key == pygame.K_TAB:
            self.select_group(self.group_index + (-1 if event.mod & pygame.KMOD_SHIFT else 1))
        elif event.key == pygame.K_SPACE:
            self.toggle_playback()
        else:
            for size, keys in zip(DISPLAY_SIZES, SIZE_KEYS):
                key, keypad_key, scancode = keys
                if event.key == keypad_key or matches_key(event, key, scancode):
                    self.display_size = size

    def select_character(self, index: int) -> None:
        if not self.entries:
            return
        self.character_index = index % len(self.entries)
        self.frame_index = 0
        self.group_index = 0
        self.player = None

    def step_frame(self, step: int) -> None:
        """Предыдущий или следующий кадр по кругу. Проигрывание останавливается на показанном кадре.

        Если кадр не входит в выбранную группу, выбирается первая группа с этим кадром.
        """
        sprites = self.sprites
        if sprites is None:
            return
        shown = self.current_frame
        self.player = None
        position = sprites.frames.index(shown) if shown is not None else self.frame_index
        self.frame_index = (position + step) % len(sprites.frames)
        frame_id = sprites.frames[self.frame_index].id
        group = self.group
        if group is not None and frame_id not in group.frame_ids:
            for index, candidate in enumerate(sprites.groups.values()):
                if frame_id in candidate.frame_ids:
                    self.group_index = index
                    break

    def select_group(self, index: int) -> None:
        """Выбирает группу и показывает её первый кадр; если шло проигрывание, играет новую группу."""
        sprites = self.sprites
        if sprites is None or not sprites.groups:
            return
        self.group_index = index % len(sprites.groups)
        group = self.group
        self.frame_index = sprites.frames.index(sprites.frame(group.frame_ids[0]))
        if self.player is not None:
            self.player = AnimationPlayer(sprites.animation(group.name, loop=True))

    def toggle_playback(self) -> None:
        """Пуск и остановка группы. Для просмотра любая группа играет по кругу."""
        sprites = self.sprites
        group = self.group
        if sprites is None or group is None:
            return
        if self.player is None:
            self.player = AnimationPlayer(sprites.animation(group.name, loop=True))
        else:
            self.frame_index = sprites.frames.index(self.current_frame)
            self.player = None

    def update(self, dt: float) -> None:
        if self.player is not None:
            self.player.update(dt)
        if self._repeat_step:
            self._repeat_timer -= dt
            while self._repeat_timer <= 0:
                self.step_frame(self._repeat_step)
                self._repeat_timer += REPEAT_INTERVAL

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND_COLOR)
        entry = self.entry
        if entry is None:
            self._draw_message(surface, "Галерея пуста", f"Персонажи не найдены в {self.characters_dir}")
        elif entry.sprites is None:
            self._draw_message(surface, f"{entry.id}: ошибка", entry.error)
        else:
            self._draw_character(surface, entry.sprites)
        for image, rect in self.labels:
            surface.blit(image, rect)

    def scaled_frame(self) -> pygame.Surface | None:
        """Текущий кадр, приведённый к display_size методом ближайшего соседа (исходник не меняется)."""
        frame = self.current_frame
        if frame is None:
            return None
        width, height = frame.image.get_size()
        size = (width * self.display_size // max(width, height), height * self.display_size // max(width, height))
        # transform.scale берёт ближайший пиксель без сглаживания и создаёт новую поверхность.
        return pygame.transform.scale(frame.image, size)

    def info_lines(self) -> list[str]:
        return [text for text, _ in self._info()]

    def _info(self) -> list[tuple[str, config.Color]]:
        sprites = self.sprites
        frame = self.current_frame
        if sprites is None or frame is None:
            return []
        lines: list[tuple[str, config.Color]] = [
            (f"Кадр {sprites.frames.index(frame) + 1}/{len(sprites.frames)} · ячейка {frame.index}", config.TEXT_COLOR),
            (frame.id, config.TITLE_COLOR),
        ]
        description = wrap_text(frame.description, self._font, INFO_WIDTH)
        lines += [(line, config.TEXT_COLOR) for line in _limit(description, MAX_DESCRIPTION_LINES)]
        group = self.group
        if group is None:
            lines.append(("Групп анимации нет — только позы", config.HINT_COLOR))
            return lines
        lines.append((f"Группа {self.group_index + 1}/{len(sprites.groups)}: {group.name}", config.TEXT_COLOR))
        if frame.id not in group.frame_ids:
            in_any = any(frame.id in other.frame_ids for other in sprites.groups.values())
            note = "Кадр не входит в эту группу" if in_any else "Кадр не входит ни в одну группу"
            lines.append((note, config.HINT_COLOR))
        mode = "цикл" if group.loop else "один раз"
        lines.append((f"{group.fps:g} кадр/с · в игре: {mode} · кадров {len(group.frame_ids)}", config.HINT_COLOR))
        if group.draft:
            reason = wrap_text(f"ЧЕРНОВИК: {group.draft_reason}", self._font, INFO_WIDTH)
            lines += [(line, DRAFT_COLOR) for line in _limit(reason, MAX_REASON_LINES)]
        if self.player is not None:
            position = f"{self.player.frame_index + 1}/{len(group.frame_ids)}"
            lines.append((f"▶ Проигрывается, кадр группы {position}", DRAFT_COLOR if group.draft else config.FPS_COLOR))
        else:
            lines.append(("■ Остановлено", config.HINT_COLOR))
        return lines

    def _text(self, font: pygame.font.Font, text: str, color: config.Color) -> pygame.Surface:
        key = (id(font), text, color)
        image = self._text_cache.get(key)
        if image is None:
            image = self._text_cache[key] = render_text(font, text, color)
        return image

    def _draw_character(self, surface: pygame.Surface, sprites: CharacterSprites) -> None:
        title = self._text(self._title_font, f"◀ {sprites.display_name} ▶", config.TITLE_COLOR)
        surface.blit(title, (6, 3))
        size = self.display_size
        counter_text = f"{self.character_index + 1}/{len(self.entries)} · размер {size}×{size}"
        counter = self._text(self._font, counter_text, config.TEXT_COLOR)
        surface.blit(counter, counter.get_rect(topright=(SCREEN_WIDTH - 6, 4)))
        details = f"{sprites.id} · сетка {sprites.columns}×{sprites.rows} · кадров {len(sprites.frames)}"
        surface.blit(self._text(self._font, f"{details} · групп {len(sprites.groups)}", config.HINT_COLOR), (6, 16))

        surface.blit(self._panel, PANEL_RECT)
        image = self.scaled_frame()
        if image is not None:
            rect = image.get_rect(midbottom=(PANEL_RECT.centerx, PANEL_RECT.bottom - 6))
            pygame.draw.rect(surface, CELL_OUTLINE_COLOR, rect.inflate(2, 2), 1)
            surface.blit(image, rect)
        group = self.group
        if self.player is not None and group is not None and group.draft:
            # Черновую последовательность видно сразу: рамка панели — цветом черновика.
            pygame.draw.rect(surface, DRAFT_COLOR, PANEL_RECT, 1)

        for row, (text, color) in enumerate(self._info()):
            surface.blit(self._text(self._font, text, color), (INFO_LEFT, INFO_TOP + row * self._line_height))

    def _draw_message(self, surface: pygame.Surface, title: str, message: str) -> None:
        surface.blit(self._text(self._title_font, title, ERROR_COLOR), (6, 3))
        if self.entries:
            counter = self._text(self._font, f"{self.character_index + 1}/{len(self.entries)}", config.TEXT_COLOR)
            surface.blit(counter, counter.get_rect(topright=(SCREEN_WIDTH - 6, 4)))
        lines = wrap_text(message, self._font, SCREEN_WIDTH - 12)
        for row, line in enumerate(_limit(lines, 10)):
            surface.blit(self._text(self._font, line, config.TEXT_COLOR), (6, INFO_TOP + row * self._line_height))


def _limit(lines: list[str], count: int) -> list[str]:
    """Не больше count строк; если текст не поместился, последняя строка заканчивается «…»."""
    if len(lines) <= count:
        return lines
    return lines[: count - 1] + [lines[count - 1].rstrip(" ,.;:—") + "…"]


def _render_panel() -> pygame.Surface:
    """Клетчатая подложка под кадром: на ней видны прозрачные и полупрозрачные пиксели."""
    panel = pygame.Surface(PANEL_RECT.size)
    for y in range(0, PANEL_RECT.height, PANEL_TILE):
        for x in range(0, PANEL_RECT.width, PANEL_TILE):
            panel.fill(PANEL_COLORS[(x // PANEL_TILE + y // PANEL_TILE) % 2], (x, y, PANEL_TILE, PANEL_TILE))
    return panel
