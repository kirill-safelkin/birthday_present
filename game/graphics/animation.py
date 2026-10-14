"""Анимация спрайтов: кадры, их проигрывание, наборы анимаций персонажей и листы спрайтов.

Animation — неизменяемые данные: кадры, скорость и режим (циклическая или одноразовая).
Одну анимацию могут одновременно использовать несколько персонажей. AnimationPlayer
хранит, какой кадр показывать сейчас. AnimationSet — анимации одного персонажа
по состояниям и направлениям с резервными вариантами для отсутствующих.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pygame

import config

# Основные состояния персонажа. Набор не закрытый: персонаж может иметь и свои
# состояния (например, бег и прятки у клубники), а AnimationSet подберёт им замену.
IDLE = "idle"  # стоит
WALK = "walk"  # идёт
TALK = "talk"  # разговаривает
REACT = "react"  # реагирует на событие

# Допуск на погрешность float: сумма многих маленьких dt бывает чуть меньше точной.
_EPSILON = 1e-9


class AnimationError(ValueError):
    """Ошибка в данных анимации. Обнаруживается при создании анимации, а не во время игры."""


class SpriteSheetError(AnimationError):
    """Изображение не удалось загрузить или разрезать на кадры."""


class Direction(Enum):
    """Направление взгляда. Значение — единичный вектор на экране (ось y направлена вниз)."""

    DOWN = (0, 1)
    UP = (0, -1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


@dataclass(frozen=True, eq=False)
class Animation:
    """Последовательность кадров, скорость в кадрах в секунду и режим проигрывания.

    loop=True — анимация повторяется по кругу (ходьба, ожидание). loop=False —
    проигрывается один раз и останавливается на последнем кадре (реакция).
    sources — исходные кадры высокого разрешения, по одному на каждый кадр frames
    (например, 64×64 для кадров, уменьшенных до 32×32 для холста). Их рисует слой
    высокого разрешения (game/graphics/hires.py); None — исходники и есть frames.
    """

    frames: Sequence[pygame.Surface]
    fps: float
    loop: bool = True
    sources: Sequence[pygame.Surface] | None = None

    def __post_init__(self) -> None:
        # Кортеж вместо списка: анимация неизменяема, её можно безопасно делить между персонажами.
        object.__setattr__(self, "frames", tuple(self.frames))
        if not self.frames:
            raise AnimationError("в анимации нет ни одного кадра")
        for index, frame in enumerate(self.frames):
            if not isinstance(frame, pygame.Surface):
                raise AnimationError(f"кадр {index} — не pygame.Surface, а {type(frame).__name__}")
        if self.sources is not None:
            object.__setattr__(self, "sources", tuple(self.sources))
            if len(self.sources) != len(self.frames):
                raise AnimationError(
                    f"исходных кадров {len(self.sources)}, а кадров анимации {len(self.frames)}: нужно поровну"
                )
            for index, source in enumerate(self.sources):
                if not isinstance(source, pygame.Surface):
                    raise AnimationError(f"исходный кадр {index} — не pygame.Surface, а {type(source).__name__}")
        if isinstance(self.fps, bool) or not isinstance(self.fps, (int, float)) or not 0 < self.fps < math.inf:
            raise AnimationError(
                f"скорость анимации должна быть положительным числом кадров в секунду, а не {self.fps!r}"
            )

    @property
    def frame_duration(self) -> float:
        """Сколько секунд показывается один кадр."""
        return 1 / self.fps

    @property
    def duration(self) -> float:
        """Длительность одного прохода анимации в секундах."""
        return len(self.frames) / self.fps

    def source(self, index: int) -> pygame.Surface:
        """Исходный кадр высокого разрешения для кадра index (или сам кадр, если исходников нет)."""
        return self.sources[index] if self.sources is not None else self.frames[index]

    def flipped(self) -> Animation:
        """Та же анимация, отражённая по горизонтали: например, ходьба влево из ходьбы вправо."""
        def flip(frames: Sequence[pygame.Surface]) -> list[pygame.Surface]:
            return [pygame.transform.flip(frame, True, False) for frame in frames]

        sources = flip(self.sources) if self.sources is not None else None
        return Animation(flip(self.frames), self.fps, self.loop, sources)


class AnimationPlayer:
    """Проигрывает анимацию: отсчитывает время и выбирает текущий кадр.

    Кадр выбирается по прошедшему времени, а не по числу вызовов update(), поэтому
    скорость анимации не зависит от частоты кадров игры. Если за один вызов прошло
    время нескольких кадров, лишние кадры пропускаются, а остаток времени сохраняется.
    """

    def __init__(self, animation: Animation) -> None:
        self.animation = animation
        self.frame_index = 0
        self.is_finished = False  # одноразовая анимация дошла до конца
        self._progress = 0.0  # сколько кадров прошло с начала текущего; дробное, чтобы копить маленькие dt

    @property
    def frame(self) -> pygame.Surface:
        """Кадр, который нужно нарисовать сейчас."""
        return self.animation.frames[self.frame_index]

    @property
    def source(self) -> pygame.Surface:
        """Исходный кадр высокого разрешения для текущего кадра (см. Animation.sources)."""
        return self.animation.source(self.frame_index)

    def play(self, animation: Animation, restart: bool = False) -> None:
        """Переключает на другую анимацию и начинает её с первого кадра.

        Если эта анимация уже играет, она продолжается: персонаж, который каждый кадр
        подтверждает, что идёт, не должен застывать на первом кадре ходьбы.
        restart=True начинает её заново (например, повторная реакция).
        """
        if animation is self.animation and not restart:
            return
        self.animation = animation
        self.reset()

    def reset(self) -> None:
        """Возвращает анимацию к первому кадру и обнуляет накопленное время."""
        self.frame_index = 0
        self.is_finished = False
        self._progress = 0.0

    def update(self, dt: float) -> None:
        """Продвигает анимацию на dt секунд."""
        if not 0 <= dt < math.inf:
            raise ValueError(f"dt должен быть неотрицательным конечным числом, а не {dt!r}")
        if self.is_finished:
            return
        animation = self.animation
        self._progress += dt * animation.fps
        steps = int(self._progress + _EPSILON)
        if steps == 0:
            return
        self._progress = max(0.0, self._progress - steps)
        count = len(animation.frames)
        if animation.loop:
            self.frame_index = (self.frame_index + steps) % count
        elif self.frame_index + steps < count:
            self.frame_index += steps
        else:
            # Время последнего кадра истекло: одноразовая анимация остаётся на нём.
            self.frame_index = count - 1
            self.is_finished = True
            self._progress = 0.0


class AnimationSet:
    """Анимации одного персонажа по состояниям и направлениям.

    Анимация добавляется для конкретного направления или без него (direction=None) —
    тогда она подходит для любого направления. Если нужной анимации нет, get()
    подбирает замену и никогда не выбрасывает исключение:
      1. то же состояние для нужного направления, затем без направления;
      2. резервное состояние из fallbacks (по умолчанию для любого состояния — idle)
         и так далее по цепочке;
      3. анимация default.
    """

    def __init__(self, default: Animation, fallbacks: Mapping[str, str] | None = None) -> None:
        if not isinstance(default, Animation):
            raise AnimationError("анимация по умолчанию должна быть объектом Animation")
        self.default = default
        # Например, {"run": WALK, "hide": IDLE}: бег без своих кадров показывается как ходьба.
        self.fallbacks: dict[str, str] = dict(fallbacks or {})
        self._animations: dict[tuple[str, Direction | None], Animation] = {}

    def add(self, state: str, animation: Animation, direction: Direction | None = None) -> None:
        """Добавляет (или заменяет) анимацию состояния для направления или для всех направлений."""
        if not isinstance(state, str) or not state.strip():
            raise AnimationError("у анимации должно быть непустое имя состояния")
        if not isinstance(animation, Animation):
            raise AnimationError(f"анимация состояния «{state}» должна быть объектом Animation")
        if direction is not None and not isinstance(direction, Direction):
            raise AnimationError(f"направление анимации «{state}» должно быть Direction или None")
        self._animations[state, direction] = animation

    def has(self, state: str, direction: Direction | None = None) -> bool:
        """Есть ли собственная анимация именно для этого состояния и направления (без замен)."""
        return (state, direction) in self._animations

    @property
    def states(self) -> set[str]:
        """Состояния, для которых есть собственные анимации."""
        return {state for state, _ in self._animations}

    def get(self, state: str, direction: Direction) -> Animation:
        """Самая подходящая анимация для состояния и направления."""
        visited: set[str] = set()
        current: str | None = state
        # visited защищает от зацикленных замен вроде {"a": "b", "b": "a"}.
        while current is not None and current not in visited:
            visited.add(current)
            for key in ((current, direction), (current, None)):
                animation = self._animations.get(key)
                if animation is not None:
                    return animation
            current = self.fallbacks.get(current, IDLE if current != IDLE else None)
        return self.default


def resolve_path(path: str | Path, base_dir: str | Path = config.PROJECT_DIR) -> Path:
    """Относительный путь считается от base_dir (по умолчанию — папки проекта), а не от текущего каталога."""
    path = Path(path)
    return path if path.is_absolute() else Path(base_dir) / path


def load_image(path: str | Path, base_dir: str | Path = config.PROJECT_DIR) -> pygame.Surface:
    """Загружает изображение с сохранением прозрачности PNG.

    Отсутствующий файл — FileNotFoundError, повреждённый или неподдерживаемый — SpriteSheetError.
    """
    full_path = resolve_path(path, base_dir)
    if not full_path.is_file():
        raise FileNotFoundError(f"файл изображения не найден: {full_path}")
    try:
        image = pygame.image.load(str(full_path))
    except pygame.error as exc:
        raise SpriteSheetError(f"не удалось загрузить изображение {full_path}: {exc}") from exc
    # convert_alpha() ускоряет вывод на экран, но работает только после создания окна.
    # До этого (например, в тестах) изображение остаётся в исходном формате, прозрачность сохраняется и так.
    if pygame.display.get_surface() is not None:
        image = image.convert_alpha()
    return image


def slice_sheet(
    sheet: pygame.Surface,
    frame_size: config.Size,
    *,
    columns: int | None = None,
    rows: int | None = None,
) -> list[tuple[pygame.Surface, ...]]:
    """Режет лист спрайтов на одинаковые кадры и возвращает строки сетки.

    Каждая строка — кадры слева направо; обычно одна строка листа — одна анимация
    (например, ходьба в одном направлении). Размер кадра задаётся явно и не угадывается:
    лист должен делиться на кадры без остатка. columns и rows, если заданы, сверяются
    с размером листа — так в анимацию не попадёт картинка другого формата, например
    концепт-лист с подписями, палитрой и несколькими персонажами.
    """
    if not isinstance(sheet, pygame.Surface):
        raise SpriteSheetError("лист спрайтов должен быть pygame.Surface")
    if len(frame_size) != 2 or not all(isinstance(side, int) and side > 0 for side in frame_size):
        raise SpriteSheetError(f"размер кадра должен состоять из двух положительных целых чисел, а не {frame_size!r}")
    for name, value in (("columns", columns), ("rows", rows)):
        if value is not None and (not isinstance(value, int) or value <= 0):
            raise SpriteSheetError(f"{name} должно быть положительным целым числом, а не {value!r}")

    frame_w, frame_h = frame_size
    sheet_w, sheet_h = sheet.get_size()
    if sheet_w % frame_w or sheet_h % frame_h:
        raise SpriteSheetError(
            f"лист {sheet_w}×{sheet_h} не делится на кадры {frame_w}×{frame_h} без остатка"
        )
    actual_columns, actual_rows = sheet_w // frame_w, sheet_h // frame_h
    if (columns is not None and columns != actual_columns) or (rows is not None and rows != actual_rows):
        raise SpriteSheetError(
            f"в листе {sheet_w}×{sheet_h} помещается сетка {actual_columns}×{actual_rows} кадров "
            f"{frame_w}×{frame_h}, а ожидалась {columns or actual_columns}×{rows or actual_rows}"
        )

    # copy(): кадры не зависят от листа, и его можно освободить или изменить.
    return [
        tuple(
            sheet.subsurface((column * frame_w, row * frame_h, frame_w, frame_h)).copy()
            for column in range(actual_columns)
        )
        for row in range(actual_rows)
    ]


def load_sprite_sheet(
    path: str | Path,
    frame_size: config.Size,
    *,
    columns: int | None = None,
    rows: int | None = None,
    base_dir: str | Path = config.PROJECT_DIR,
) -> list[tuple[pygame.Surface, ...]]:
    """Загружает лист спрайтов и режет его на кадры (см. load_image и slice_sheet)."""
    return slice_sheet(load_image(path, base_dir), frame_size, columns=columns, rows=rows)
