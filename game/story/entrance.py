"""Вход в Страну чудес: Алиса сама находит место норы, сказка ломается, и нора появляется.

Здесь только модель эпизода — стадии, время и описание эффектов, без Pygame. Сцена вступления
(game/story/intro_scene.py) ведёт Алису как Character, передаёт сюда её положение и dt,
а потом рисует то, что описывает effects().

Стадии идут строго по порядку, каждая — ровно один раз:
  FREE_WALK      — Алиса ходит, куда хочет; у места будущей норы — лишь редкие искорки;
  GLITCH_WARNING — Алиса подошла к месту норы: мерцает земля, сдвигаются мелочи, первые искры;
  WORLD_BREAKING — полосы страницы съезжают, вспышки, вихрь искр;
  HOLE_OPENING   — магический круг, волны, земля сворачивается внутрь, открывается глубина;
  HOLE_READY     — нора на месте, эффекты затихают, Алиса снова ходит и сама решает, когда войти;
  ENTERING_HOLE  — игрок нажал E у норы: дальше ведёт сценарий вступления.
С GLITCH_WARNING до HOLE_READY управление у постановки, потом обязательно возвращается.

Время копится шагами не длиннее MAX_STEP, остаток переходит в следующую стадию: итог не зависит
от частоты кадров, а большой dt не проскакивает ни одной стадии. Эффекты — функции стадии
и времени (без случайных чисел): каждый кадр предсказуем, и его можно проверить тестом.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class Stage(str, Enum):
    FREE_WALK = "free_walk"
    GLITCH_WARNING = "glitch_warning"
    WORLD_BREAKING = "world_breaking"
    HOLE_OPENING = "hole_opening"
    HOLE_READY = "hole_ready"
    ENTERING_HOLE = "entering_hole"


ORDER = tuple(Stage)
# Сколько длятся стадии постановки, секунд. Свободная ходьба и готовая нора длятся,
# сколько захочет игрок.
DURATIONS = {Stage.GLITCH_WARNING: 1.0, Stage.WORLD_BREAKING: 1.4, Stage.HOLE_OPENING: 2.8}
SETTLE_SECONDS = 1.2  # после появления норы последние искры и свечение затихают за это время
MAX_STEP = 0.05

# Место действия, логические пиксели по горизонтали (Алиса ходит по одной линии земли).
HOLE_X = 268  # где появится нора: у правого края страницы
WALK_MIN_X = 20  # левее Алиса не уходит: там рамка страницы
WALK_MAX_X = 242  # правее — край норы (а пока её нет, Алиса раньше упрётся в место сбоя)
TRIGGER_DISTANCE = 44  # подошла к месту норы ближе этого — сказка начинает ломаться
ENTER_DISTANCE = 30  # стоит ближе этого к готовой норе — E заглядывает внутрь

# Сколько искр в каждом эффекте.
WARNING_SPARKS = 6
SWIRL_SPARKS = 18
SPIRAL_SPARKS = 20
SETTLE_SPARKS = 6


@dataclass(frozen=True)
class Spark:
    """Магическая искра: смещение от центра норы на линии земли, размер 1–3, цвет (номер в палитре
    сцены) и непрозрачность 0..1."""

    dx: float
    dy: float
    size: int
    color: int
    alpha: float


@dataclass(frozen=True)
class Effects:
    """Что рисовать сейчас. Все силы — от 0 до 1; 0 — эффекта нет."""

    hint: float = 0.0  # едва заметные намёки у места норы (пока Алиса свободно ходит)
    flicker: float = 0.0  # мерцание земли
    shift: int = 0  # на сколько пикселей сдвинуты отдельные мелочи страницы (дерево, облако…)
    tear: int = 0  # насколько съезжают горизонтальные полосы страницы
    slot: int = 0  # номер узора сдвигов: меняется рывками, а не каждый кадр
    flash: float = 0.0  # вспышка на весь экран (короткая)
    scanlines: int = 0  # сколько цветных полос-искажений
    glow: float = 0.0  # свечение земли у места норы
    ring: float = 0.0  # магический круг на земле
    spin: float = 0.0  # поворот круга, радианы
    waves: tuple[float, ...] = ()  # расходящиеся кольца: доля пути каждого, 0..1
    fold: float = 0.0  # земля сворачивается внутрь круга
    depth: float = 0.0  # тёмная глубина норы раскрыта на столько
    rim: float = 0.0  # окантовка: земля, корни, трава
    sparks: tuple[Spark, ...] = field(default_factory=tuple)

    @property
    def is_calm(self) -> bool:
        """Временных эффектов нет: осталась только сама нора (или ничего)."""
        return self == Effects(depth=self.depth, rim=self.rim)


def _ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _noise(index: int, salt: int) -> float:
    """Детерминированное «случайное» число 0..1: у каждой искры свои, но всегда одни и те же."""
    value = math.sin(index * 12.9898 + salt * 78.233) * 43758.5453
    return value - math.floor(value)


def _pulse(t: float, start: float, length: float) -> float:
    """1 внутри отрезка [start, start + length), иначе 0."""
    return 1.0 if start <= t < start + length else 0.0


class Entrance:
    """Модель эпизода: стадия, время в ней и описание эффектов. Без Pygame.

    update(dt, x) — x — где сейчас Алиса; enter(x) — нажата E (или Enter).
    stage_log — стадии в порядке начала, каждая по одному разу.
    """

    def __init__(self) -> None:
        self.stage = Stage.FREE_WALK
        self.stage_time = 0.0
        self.time = 0.0
        self.stage_log: list[Stage] = [Stage.FREE_WALK]

    # --- Состояние ---

    @property
    def can_walk(self) -> bool:
        """Управление у игрока: до сбоя и когда нора уже готова."""
        return self.stage in (Stage.FREE_WALK, Stage.HOLE_READY)

    @property
    def hole_exists(self) -> bool:
        """Нора готова и с ней можно взаимодействовать."""
        return self.stage in (Stage.HOLE_READY, Stage.ENTERING_HOLE)

    @staticmethod
    def clamp(x: float) -> float:
        """Положение Алисы в пределах сцены: от рамки страницы до края норы."""
        return min(WALK_MAX_X, max(WALK_MIN_X, x))

    @staticmethod
    def in_trigger_zone(x: float) -> bool:
        return abs(x - HOLE_X) <= TRIGGER_DISTANCE

    def can_enter(self, x: float) -> bool:
        """E сейчас сработает: нора готова, и Алиса стоит рядом с ней."""
        return self.stage is Stage.HOLE_READY and abs(x - HOLE_X) <= ENTER_DISTANCE

    # --- Ход эпизода ---

    def update(self, dt: float, x: float) -> None:
        """Продвигает эпизод на dt секунд; x — где Алиса (её задаёт управление игрока)."""
        if not 0 <= dt < math.inf:
            raise ValueError(f"dt должен быть неотрицательным конечным числом, а не {dt!r}")
        remaining = dt
        while remaining > 1e-12:
            if self.stage is Stage.FREE_WALK and self.in_trigger_zone(x):
                self._go(Stage.GLITCH_WARNING)  # время этого шага уже идёт на сбой
                continue
            step = min(remaining, MAX_STEP)
            remaining -= step
            duration = DURATIONS.get(self.stage)
            if duration is None:  # свободная ходьба, готовая нора и вход: ждут игрока или сценарий
                self.time += step
                self.stage_time += step
                continue
            # Стадия постановки: остаток шага переходит в следующую, ничего не пропуская.
            used = min(step, duration - self.stage_time)
            self.time += used
            self.stage_time += used
            if self.stage_time >= duration - 1e-9:
                self._go(ORDER[ORDER.index(self.stage) + 1])
                remaining += step - used

    def enter(self, x: float) -> bool:
        """E у готовой норы: True — Алиса заглядывает внутрь (ровно один раз), иначе ничего."""
        if not self.can_enter(x):
            return False
        self._go(Stage.ENTERING_HOLE)
        return True

    def _go(self, stage: Stage) -> None:
        self.stage = stage
        self.stage_time = 0.0
        self.stage_log.append(stage)

    # --- Эффекты ---

    def effects(self, x: float | None = None) -> Effects:
        """Что рисовать сейчас; x — где Алиса (от него зависят только намёки до сбоя)."""
        t = self.stage_time
        stage = self.stage
        if stage is Stage.FREE_WALK:
            distance = abs(x - HOLE_X) if x is not None else math.inf
            hint = max(0.0, min(1.0, 1 - (distance - TRIGGER_DISTANCE) / 140))
            return Effects(hint=hint, sparks=self._hint_sparks(hint))
        if stage is Stage.GLITCH_WARNING:
            flicker = max(_pulse(t, 0.05, 0.12), 0.7 * _pulse(t, 0.42, 0.08), 0.5 * _pulse(t, 0.7, 0.06))
            slot = int(t / 0.1)
            shift = (1 if slot % 2 else -1) if slot in (2, 3, 6, 8) else 0
            scanlines = 2 if 0.45 <= t < 0.53 else 0
            count = min(WARNING_SPARKS, int(t / 0.12))
            sparks = tuple(self._rising_spark(i, t) for i in range(count))
            return Effects(flicker=flicker, shift=shift, slot=slot, scanlines=scanlines, glow=0.3 * t, sparks=sparks)
        if stage is Stage.WORLD_BREAKING:
            duration = DURATIONS[stage]
            tear = 1 + round(3 * t / duration)
            flash = max(0.45 * _pulse(t, 0.25, 0.12), 0.35 * _pulse(t, 0.85, 0.1))
            scanlines = 3 if any(_pulse(t, s, 0.12) for s in (0.1, 0.6, 1.1)) else 0
            ring = 0.4 * _ease((t - 1.1) / 0.3)
            sparks = tuple(self._swirl_spark(i, t) for i in range(SWIRL_SPARKS))
            return Effects(
                flicker=0.4 * _pulse(t % 0.5, 0.0, 0.06), tear=tear, slot=int(t / 0.08), flash=flash,
                scanlines=scanlines, glow=0.3 + 0.4 * t / duration, ring=ring, spin=t * 2.4, sparks=sparks,
            )
        if stage is Stage.HOLE_OPENING:
            q = t / DURATIONS[stage]
            ring = (0.4 + 0.6 * _ease(q / 0.15)) * (1 - _ease((q - 0.85) / 0.15))  # с той силы, что был
            waves = tuple(w for w in ((q - start) / 0.35 for start in (0.12, 0.27, 0.42)) if 0 < w < 1)
            depth = _ease((q - 0.45) / 0.4)
            glow = 0.7 + 0.3 * _ease(q / 0.5) if q < 0.5 else 1.0 - 0.4 * _ease((q - 0.5) / 0.5)
            sparks = tuple(s for s in (self._spiral_spark(i, q) for i in range(SPIRAL_SPARKS)) if s is not None)
            return Effects(
                tear=round(3 * (1 - q / 0.2)) if q < 0.2 else 0, slot=int(t / 0.08),
                flash=0.35 * _pulse(q, 0.45, 0.05), glow=glow, ring=ring, spin=1.4 * 2.4 + t * 2.4,
                waves=waves, fold=_ease((q - 0.25) / 0.45), depth=depth, rim=_ease((q - 0.65) / 0.3), sparks=sparks,
            )
        if stage is Stage.HOLE_READY and t < SETTLE_SECONDS:
            fade = 1 - t / SETTLE_SECONDS
            sparks = tuple(s for s in (self._sinking_spark(i, t) for i in range(SETTLE_SPARKS)) if s is not None)
            return Effects(glow=0.6 * fade, depth=1.0, rim=1.0, sparks=sparks)
        return Effects(depth=1.0, rim=1.0)  # нора стоит спокойно и больше не мерцает

    def _hint_sparks(self, hint: float) -> tuple[Spark, ...]:
        """Редкая искорка у места норы: раз в 1,6 с на долю секунды. Ближе к месту — ярче."""
        period = 1.6
        index = int(self.time / period)
        phase = self.time - index * period
        if phase >= 0.35:
            return ()
        brightness = math.sin(phase / 0.35 * math.pi) * (0.35 + 0.65 * hint)
        dx = (_noise(index, 1) - 0.5) * 30
        dy = -2 - _noise(index, 2) * 10
        return (Spark(dx, dy, 2 if hint > 0.5 else 1, index % 4, brightness),)

    @staticmethod
    def _rising_spark(index: int, t: float) -> Spark:
        """Первые искры: поднимаются от земли у места норы и гаснут."""
        born = index * 0.12
        age = (t - born) % 0.7
        dx = (_noise(index, 3) - 0.5) * 36
        return Spark(dx + math.sin(age * 9 + index) * 2, -age * 26, 1 + index % 2, index % 4, 1 - age / 0.7)

    @staticmethod
    def _swirl_spark(index: int, t: float) -> Spark:
        """Вихрь искр вокруг места норы: кружатся и понемногу стягиваются к центру."""
        angle = _noise(index, 4) * math.tau + t * (3 + _noise(index, 5) * 2)
        radius = (18 + _noise(index, 6) * 20) * (1 - 0.25 * t / DURATIONS[Stage.WORLD_BREAKING])
        height = 4 + _noise(index, 7) * 30
        dy = math.sin(angle) * radius / 3 - height * (0.5 + 0.5 * math.sin(t * 4 + index))
        alpha = 0.6 + 0.4 * math.sin(t * 10 + index * 1.7)
        return Spark(math.cos(angle) * radius, dy, 1 + index % 3, index % 4, alpha)

    @staticmethod
    def _spiral_spark(index: int, q: float) -> Spark | None:
        """Искры закручиваются по спирали и исчезают в центре норы."""
        start = _noise(index, 8) * 0.35
        p = (q - start) / (1 - start)
        if p <= 0:
            return None
        pull = _ease(p)
        radius = (30 + _noise(index, 9) * 22) * (1 - pull)
        if radius < 2:
            return None  # искра уже внутри
        angle = _noise(index, 10) * math.tau + p * 7
        height = (6 + _noise(index, 11) * 24) * (1 - pull)
        alpha = min(1.0, p * 4) * (1 - pull * 0.5)
        return Spark(math.cos(angle) * radius, math.sin(angle) * radius / 3 - height, 1 + index % 3, index % 4, alpha)

    @staticmethod
    def _sinking_spark(index: int, t: float) -> Spark | None:
        """После появления норы последние искры медленно опускаются в неё и гаснут."""
        p = t / SETTLE_SECONDS - index * 0.08
        if p <= 0 or p >= 1:
            return None
        dx = (_noise(index, 12) - 0.5) * 20 * (1 - p)
        return Spark(dx, -18 * (1 - p), 1 + index % 2, index % 4, 1 - p)
