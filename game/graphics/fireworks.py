"""Пиксельный фейерверк: ракеты, звёздчатые и круглые разрывы, искры, вспышки света, конфетти.

Только логика и рисование на холсте 320×180, без привязки к сцене и без ресурсов. Всё идёт
по dt: время делится на шаги не длиннее STEP, поэтому картинка не зависит от частоты кадров,
а после подвисания окна (большой dt) частицы не «телепортируются». Ничего не блокирует цикл:
ни задержек, ни потоков.

Фейерверк — короткими залпами: в залпе два-четыре разрыва друг за другом, потом пауза, потом
следующий залп (SALVOS идут по кругу). Он не сыплется непрерывным хаотичным потоком.
Количество частиц ограничено (MAX_SPARKS, MAX_CONFETTI, MAX_FLASHES, MAX_ROCKETS): если лимит
исчерпан, разрыв просто получает меньше искр, а старые уходят сами — список не растёт бесконечно.

Случайность — random.Random с зерном: один и тот же ход времени даёт одну и ту же картинку.
Рисуется всё в логических пикселях: искра — квадратик 1–2 пикселя, как остальная графика сцены.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

import config
from game.graphics.pixel_art import glow_sprite, mix

STEP = 1 / 60  # самый длинный шаг моделирования, секунд
MAX_SPARKS = 340
MAX_CONFETTI = 36
MAX_FLASHES = 4
MAX_ROCKETS = 4

SKY_DIM: config.Color = (34, 24, 64)  # к этому цвету гаснут искры: ночное небо за ними
WHITE_HOT: config.Color = (255, 248, 224)

PALETTES: dict[str, tuple[config.Color, config.Color]] = {
    # основной цвет и второй — для двухцветных разрывов
    "gold": ((255, 208, 92), (255, 150, 60)),
    "rose": ((255, 120, 178), (255, 190, 214)),
    "azure": ((104, 192, 255), (176, 228, 255)),
    "violet": ((184, 128, 255), (232, 176, 255)),
    "red": ((255, 88, 96), (255, 170, 120)),
    "mint": ((120, 236, 180), (190, 255, 220)),
}
CONFETTI_COLORS: tuple[config.Color, ...] = (
    (255, 120, 170), (255, 214, 96), (120, 200, 255), (190, 140, 255), (130, 230, 170), (255, 150, 90),
)

# Разрыв: вид, высота центра над землёй (логический y), палитра. Ракеты стартуют из-за холмов.
LAUNCH_Y = 96
PEONY, STAR, RING, WILLOW = "peony", "star", "ring", "willow"


@dataclass(frozen=True)
class Launch:
    """Один разрыв залпа: через сколько секунд после начала залпа, где и каким цветом."""

    delay: float
    x: float
    y: float
    palette: str
    kind: str = PEONY
    second: str | None = None  # вторая палитра: двухцветный разрыв


# Залпы идут по кругу. Разрывы в верхней части экрана и по краям: центр над столом занимают
# фрагменты, а под ленточкой с названием страницы разрывы никогда не стоят дольше мгновения.
SALVOS: tuple[tuple[Launch, ...], ...] = (
    (
        Launch(0.0, 64, 44, "rose", STAR, "gold"),
        Launch(0.5, 258, 42, "azure", PEONY, "violet"),
        Launch(1.0, 104, 34, "gold", RING),
    ),
    (
        Launch(0.0, 256, 38, "violet", STAR, "rose"),
        Launch(0.45, 62, 40, "mint", PEONY, "azure"),
        Launch(0.9, 216, 34, "rose", RING, "gold"),
        Launch(1.3, 104, 44, "gold", WILLOW),
    ),
    (
        Launch(0.0, 60, 46, "red", PEONY, "gold"),
        Launch(0.4, 264, 46, "gold", STAR, "rose"),
        Launch(0.8, 218, 36, "azure", RING, "violet"),
    ),
)
SALVO_GAP = 1.2  # тишина между залпами, секунд


@dataclass(eq=False)
class Rocket:
    x: float
    y0: float
    y1: float
    age: float
    rise: float  # сколько секунд поднимается
    launch: Launch


@dataclass(eq=False)
class Spark:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    age: float
    color: config.Color
    drag: float
    gravity: float
    big: bool  # первые мгновения искра в два пикселя
    seed: int  # для мерцания в конце жизни


@dataclass(eq=False)
class Flash:
    x: float
    y: float
    age: float
    color: config.Color


@dataclass(eq=False)
class Confetto:
    x: float
    y: float
    vx: float
    fall: float  # скорость падения, пикселей в секунду
    phase: float
    life: float
    age: float
    color: config.Color


class FireworkShow:
    """Праздничный фейерверк. start() запускает залпы, stop() прекращает новые; искры, уже
    летящие в небе, догорают сами (clear() убирает всё сразу)."""

    FLASH_SECONDS = 0.28
    FLASH_RADIUS = 40
    FLASH_PEAK = 105  # самая яркая вспышка света не затмевает экран: не больше половины непрозрачности и только в центре

    def __init__(self, seed: int = 7, bounds: tuple[int, int] = config.LOGICAL_SIZE) -> None:
        self.rng = random.Random(seed)
        self.bounds = bounds
        self.running = False
        self.clock = 0.0  # время с начала залпа
        self.salvo_index = 0
        self._pending: list[Launch] = []  # разрывы текущего залпа, которых ещё не было
        self._gap = 0.0  # сколько осталось ждать до следующего залпа
        self.bursts_fired = 0
        self.rockets: list[Rocket] = []
        self.sparks: list[Spark] = []
        self.flashes: list[Flash] = []
        self.confetti: list[Confetto] = []
        self._glows: dict[config.Color, pygame.Surface] = {}

    # --- Управление ---

    @property
    def particle_count(self) -> int:
        return len(self.sparks) + len(self.confetti) + len(self.rockets) + len(self.flashes)

    @property
    def idle(self) -> bool:
        """Нет ни частиц, ни ракет, ни новых залпов: рисовать нечего."""
        return not self.running and not self.particle_count

    def start(self) -> None:
        """Запускает залпы. Повторный вызов ничего не меняет: фейерверк один."""
        if self.running:
            return
        self.running = True
        self._begin_salvo()

    def stop(self) -> None:
        """Новых разрывов больше не будет; ракеты и искры в небе догорают."""
        self.running = False
        self._pending.clear()

    def clear(self) -> None:
        self.stop()
        self.rockets.clear()
        self.sparks.clear()
        self.flashes.clear()
        self.confetti.clear()

    def _begin_salvo(self) -> None:
        salvo = SALVOS[self.salvo_index % len(SALVOS)]
        self.salvo_index += 1
        self.clock = 0.0
        self._pending = list(salvo)

    # --- Время ---

    def update(self, dt: float) -> None:
        if dt <= 0:
            return
        dt = min(dt, config.MAX_FRAME_TIME * 3)
        steps = max(1, math.ceil(dt / STEP))
        for _ in range(steps):
            self._step(dt / steps)

    def _step(self, dt: float) -> None:
        if self.running:
            self.clock += dt
            while self._pending and self._pending[0].delay <= self.clock:
                self._launch(self._pending.pop(0))
            if not self._pending:
                self._gap += dt
                if self._gap >= SALVO_GAP and not self.rockets and not self.flashes:
                    self._gap = 0.0
                    self._begin_salvo()
        self._step_rockets(dt)
        self._step_sparks(dt)
        self.flashes = [flash for flash in self.flashes if self._age(flash, dt) < self.FLASH_SECONDS]
        self._step_confetti(dt)

    @staticmethod
    def _age(item, dt: float) -> float:
        item.age += dt
        return item.age

    def _launch(self, launch: Launch) -> None:
        if len(self.rockets) >= MAX_ROCKETS:
            return
        rise = 0.5 + (LAUNCH_Y - launch.y) / 260
        self.rockets.append(Rocket(launch.x, LAUNCH_Y, launch.y, 0.0, rise, launch))

    def _step_rockets(self, dt: float) -> None:
        alive = []
        for rocket in self.rockets:
            rocket.age += dt
            if rocket.age >= rocket.rise:
                self._burst(rocket.launch)
            else:
                alive.append(rocket)
        self.rockets = alive

    def _step_sparks(self, dt: float) -> None:
        alive = []
        for spark in self.sparks:
            spark.age += dt
            if spark.age >= spark.life:
                continue
            spark.vy += spark.gravity * dt
            k = math.exp(-spark.drag * dt)
            spark.vx *= k
            spark.vy *= k
            spark.x += spark.vx * dt
            spark.y += spark.vy * dt
            alive.append(spark)
        self.sparks = alive

    def _step_confetti(self, dt: float) -> None:
        alive = []
        height = self.bounds[1]
        for piece in self.confetti:
            piece.age += dt
            piece.x += piece.vx * dt + math.sin(piece.age * 3.1 + piece.phase) * 6 * dt
            piece.y += piece.fall * dt
            if piece.age < piece.life and piece.y < height - 4:
                alive.append(piece)
        self.confetti = alive

    # --- Разрыв ---

    def _burst(self, launch: Launch) -> None:
        """Разрыв ракеты: искры по виду разрыва, вспышка света и горсть конфетти."""
        self.bursts_fired += 1
        main = PALETTES[launch.palette][0]
        other = PALETTES[launch.second or launch.palette][0 if launch.second else 1]
        if len(self.flashes) < MAX_FLASHES:
            self.flashes.append(Flash(launch.x, launch.y, 0.0, main))
        room = MAX_SPARKS - len(self.sparks)
        for index, (angle, speed, tint) in enumerate(self._pattern(launch.kind)):
            if index >= room:
                break
            color = other if tint else main
            wiggle = self.rng.uniform(0.92, 1.08)
            life = self.rng.uniform(1.6, 2.1) if launch.kind != WILLOW else self.rng.uniform(2.3, 2.9)
            self.sparks.append(Spark(
                launch.x, launch.y,
                math.cos(angle) * speed * wiggle, math.sin(angle) * speed * wiggle,
                life, 0.0, color,
                drag=2.3 if launch.kind != WILLOW else 1.7,
                gravity=22.0 if launch.kind != WILLOW else 34.0,
                big=True, seed=self.rng.randrange(1000),
            ))
        for _ in range(min(5, MAX_CONFETTI - len(self.confetti))):
            self.confetti.append(Confetto(
                launch.x + self.rng.uniform(-14, 14), launch.y + self.rng.uniform(-6, 8),
                self.rng.uniform(-6, 6), self.rng.uniform(13, 22), self.rng.uniform(0, math.tau),
                self.rng.uniform(4.0, 6.5), 0.0, self.rng.choice(CONFETTI_COLORS),
            ))

    def _pattern(self, kind: str) -> list[tuple[float, float, bool]]:
        """Направления, скорости и «второй цвет» искр разрыва: (угол, скорость, второй ли цвет)."""
        speed = 94.0
        pattern: list[tuple[float, float, bool]] = []
        if kind == STAR:
            # Пять лучей: на каждом несколько искр с разной скоростью — получается звезда.
            for tip in range(5):
                angle = -math.pi / 2 + tip * math.tau / 5
                for fraction in (0.25, 0.4, 0.55, 0.7, 0.85, 1.0):
                    pattern.append((angle, speed * fraction, fraction < 0.5))
                    pattern.append((angle + 0.07, speed * fraction * 0.96, fraction < 0.5))
                valley = angle + math.pi / 5
                for fraction in (0.28, 0.4, 0.5):
                    pattern.append((valley, speed * fraction, True))
        elif kind == RING:
            for index in range(44):
                pattern.append((index * math.tau / 44, speed * 0.95, index % 2 == 0))
            for index in range(22):  # второе, меньшее кольцо внутри
                pattern.append((index * math.tau / 22 + 0.07, speed * 0.55, True))
        elif kind == WILLOW:
            for index in range(40):
                pattern.append((index * math.tau / 40 + self.rng.uniform(-0.05, 0.05),
                                speed * self.rng.uniform(0.55, 0.9), index % 3 == 0))
        else:
            for index in range(120):  # шар: скорости от малых к большим, поэтому разрыв не пустое кольцо
                pattern.append((index * math.tau / 120 + self.rng.uniform(-0.04, 0.04),
                                speed * self.rng.uniform(0.3, 1.0), index % 4 == 0))
        return pattern

    # --- Рисование ---

    def draw(self, surface: pygame.Surface) -> None:
        """Рисует всё на холсте: мягкие вспышки, ракеты, искры, конфетти. Ничего не закрывает целиком."""
        for flash in self.flashes:
            self._draw_flash(surface, flash)
        for rocket in self.rockets:
            self._draw_rocket(surface, rocket)
        for spark in self.sparks:
            self._draw_spark(surface, spark)
        for piece in self.confetti:
            self._draw_confetto(surface, piece)

    def _glow(self, color: config.Color) -> pygame.Surface:
        glow = self._glows.get(color)
        if glow is None:
            glow = self._glows[color] = glow_sprite(self.FLASH_RADIUS, color, 255)
        return glow

    def _draw_flash(self, surface: pygame.Surface, flash: Flash) -> None:
        fade = 1 - flash.age / self.FLASH_SECONDS
        glow = self._glow(flash.color)
        glow.set_alpha(round(self.FLASH_PEAK * fade * fade))  # не белит экран: пик — меньше трети
        surface.blit(glow, glow.get_rect(center=(round(flash.x), round(flash.y))))

    @staticmethod
    def rocket_position(rocket: Rocket, back: float = 0.0) -> tuple[float, float]:
        """Где ракета (или точка её хвоста, отставшая на долю подъёма back): взлёт быстрый, к концу медленнее."""
        progress = max(0.0, min(1.0, rocket.age / rocket.rise - back))
        eased = 1 - (1 - progress) ** 2
        x = rocket.x + math.sin(progress * 9 + rocket.launch.x) * (1 - progress) * 1.2
        return x, rocket.y0 + (rocket.y1 - rocket.y0) * eased

    def _draw_rocket(self, surface: pygame.Surface, rocket: Rocket) -> None:
        for tail in range(7, -1, -1):  # хвост из угасающих точек за головой
            x, y = self.rocket_position(rocket, tail * 0.028)
            color = WHITE_HOT if tail == 0 else mix((255, 196, 96), SKY_DIM, tail / 8)
            surface.set_at((round(x), round(y)), color)

    @staticmethod
    def spark_color(spark: Spark) -> config.Color:
        """Искра белеет в первый миг, держит свой цвет примерно до середины жизни и гаснет к ночному небу."""
        t = spark.age / spark.life
        if t < 0.1:
            return mix(WHITE_HOT, spark.color, t / 0.1)
        if t < 0.5:
            return spark.color
        return mix(spark.color, SKY_DIM, ((t - 0.5) / 0.5) ** 1.3)

    def _draw_spark(self, surface: pygame.Surface, spark: Spark) -> None:
        t = spark.age / spark.life
        if t > 0.75 and (int(spark.age * 30) + spark.seed) % 3 == 0:
            return  # перед угасанием искра мерцает
        x, y = round(spark.x), round(spark.y)
        if not (0 <= x < self.bounds[0] and 0 <= y < self.bounds[1]):
            return
        color = self.spark_color(spark)
        speed = math.hypot(spark.vx, spark.vy)
        if speed > 12 and t < 0.75:  # след за быстрой искрой: две угасающие точки
            for length, dim in ((0.045, 0.15), (0.09, 0.4), (0.135, 0.65)):
                tail = (round(spark.x - spark.vx * length), round(spark.y - spark.vy * length))
                if 0 <= tail[0] < self.bounds[0] and 0 <= tail[1] < self.bounds[1]:
                    surface.set_at(tail, mix(color, SKY_DIM, dim))
        if t < 0.8:
            surface.fill(color, (x, y, 2, 2))
            if t < 0.45:  # раскалённая «голова» искры
                surface.set_at((x, y), mix(color, WHITE_HOT, 0.55))
        else:
            surface.set_at((x, y), color)

    def _draw_confetto(self, surface: pygame.Surface, piece: Confetto) -> None:
        x, y = round(piece.x), round(piece.y)
        if not (0 <= x < self.bounds[0] - 1 and 0 <= y < self.bounds[1] - 1):
            return
        color = mix(piece.color, SKY_DIM, max(0.0, (piece.age / piece.life - 0.7) * 2))
        flat = int(piece.age * 5 + piece.phase) % 2 == 0  # переворачивается в полёте
        surface.fill(color, (x, y, 2, 1) if flat else (x, y, 1, 2))
