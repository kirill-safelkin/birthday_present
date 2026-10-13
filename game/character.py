"""Игровой персонаж: позиция, движение, направление взгляда и анимация.

Класс общий для всех героев: Алиса, Лео, Чучмек, клубника и остальные отличаются
только набором анимаций (AnimationSet) и скоростью. Персонаж не знает о локациях
и столкновениях — это будет задачей сцены.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config
from game.animation import IDLE, REACT, TALK, WALK, AnimationPlayer, AnimationSet, Direction
from game.keys import matches_key
from game.placeholder_sprite import placeholder_animations


@dataclass(frozen=True)
class MoveKey:
    """Клавиша движения: код клавиши, скан-код (физическое положение) и направление."""

    key: int
    scancode: int
    direction: Direction


# Стрелки и WASD. Буквы проверяются и по скан-коду, поэтому работают и в русской раскладке.
MOVE_KEYS = (
    MoveKey(pygame.K_UP, pygame.KSCAN_UP, Direction.UP),
    MoveKey(pygame.K_DOWN, pygame.KSCAN_DOWN, Direction.DOWN),
    MoveKey(pygame.K_LEFT, pygame.KSCAN_LEFT, Direction.LEFT),
    MoveKey(pygame.K_RIGHT, pygame.KSCAN_RIGHT, Direction.RIGHT),
    MoveKey(pygame.K_w, pygame.KSCAN_W, Direction.UP),
    MoveKey(pygame.K_s, pygame.KSCAN_S, Direction.DOWN),
    MoveKey(pygame.K_a, pygame.KSCAN_A, Direction.LEFT),
    MoveKey(pygame.K_d, pygame.KSCAN_D, Direction.RIGHT),
)


def find_move_key(event: pygame.event.Event) -> MoveKey | None:
    """Клавиша движения, к которой относится событие клавиатуры, или None."""
    for move_key in MOVE_KEYS:
        if matches_key(event, move_key.key, move_key.scancode):
            return move_key
    return None


class Character:
    """Персонаж на логическом холсте.

    (x, y) — точка под ногами, середина нижнего края кадра: так персонажей разного
    роста удобно ставить на пол, а позже и сортировать по глубине.
    state — состояние анимации: idle, walk, talk, react или собственное состояние
    персонажа (например, «hide» у клубники). Анимацию для него подбирает AnimationSet,
    в том числе резервную, если своей нет.
    """

    def __init__(
        self,
        name: str,
        animations: AnimationSet | None = None,
        position: tuple[float, float] = (0.0, 0.0),
        speed: float = config.CHARACTER_WALK_SPEED,
        direction: Direction = Direction.DOWN,
    ) -> None:
        self.name = name
        # Без своих кадров персонаж выглядит как временный манекен, а запуск игры не ломается.
        self.animations = animations if animations is not None else placeholder_animations()
        self.x = self.y = 0.0
        self.set_position(*position)
        self.speed = 0.0
        self.set_speed(speed)
        self.direction = direction
        self.state = IDLE
        self.player = AnimationPlayer(self.animations.get(IDLE, direction))
        self._heading = pygame.Vector2()  # единичный вектор направления движения; нулевой, когда стоит
        self._held_keys: list[MoveKey] = []  # зажатые клавиши движения в порядке нажатия
        self._resume_after_animation = False  # вернуться к ходьбе или idle, когда реакция доиграет

    @property
    def velocity(self) -> pygame.Vector2:
        """Текущая скорость в логических пикселях в секунду."""
        return self._heading * self.speed

    @property
    def is_moving(self) -> bool:
        return self._heading.length_squared() > 0

    @property
    def pixel_position(self) -> tuple[int, int]:
        """Позиция, округлённая до пикселя холста.

        floor(x + 0.5), а не round(): round() округляет половины к чётному,
        и при движении персонаж шагал бы по пикселям неравномерно.
        """
        return math.floor(self.x + 0.5), math.floor(self.y + 0.5)

    @property
    def rect(self) -> pygame.Rect:
        """Прямоугольник текущего кадра на холсте."""
        return self.player.frame.get_rect(midbottom=self.pixel_position)

    def set_position(self, x: float, y: float) -> None:
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f"координаты персонажа должны быть конечными числами, а не ({x!r}, {y!r})")
        self.x, self.y = float(x), float(y)

    def set_speed(self, speed: float) -> None:
        """Скорость ходьбы в логических пикселях в секунду. Идущий персонаж сразу идёт с новой скоростью."""
        if not 0 <= speed < math.inf:
            raise ValueError(f"скорость персонажа должна быть неотрицательным конечным числом, а не {speed!r}")
        self.speed = float(speed)

    def face(self, direction: Direction) -> None:
        """Поворачивается, не меняя состояния."""
        self.direction = direction
        self.player.play(self.animations.get(self.state, direction))

    def move(self, dx: float, dy: float, facing: Direction | None = None) -> None:
        """Идёт в направлении вектора (dx, dy) со скоростью speed; (0, 0) — остановка.

        Вектор нормализуется: по диагонали персонаж идёт так же быстро, как по прямой.
        facing — куда смотреть; по умолчанию направление выбирается по движению.
        """
        if not (math.isfinite(dx) and math.isfinite(dy)):
            raise ValueError(f"направление движения должно состоять из конечных чисел, а не ({dx!r}, {dy!r})")
        heading = pygame.Vector2(dx, dy)
        if heading.length_squared() == 0:
            self.stop()
            return
        self._heading = heading.normalize()
        self.direction = facing if facing is not None else _facing(heading, self.direction)
        self.set_state(WALK)

    def stop(self) -> None:
        """Останавливается и переходит в idle. Направление взгляда сохраняется."""
        self._heading = pygame.Vector2()
        self.set_state(IDLE)

    def set_state(self, state: str, restart: bool = False) -> None:
        """Переключает состояние анимации, не трогая движение.

        Анимация того же состояния и направления продолжается, а не начинается
        заново; restart=True начинает её с первого кадра.
        """
        if not isinstance(state, str) or not state.strip():
            raise ValueError("состояние персонажа должно быть непустой строкой")
        self.state = state
        self._resume_after_animation = False
        self.player.play(self.animations.get(state, self.direction), restart)

    def talk(self) -> None:
        """Останавливается и говорит, пока не пойдёт или не будет остановлен."""
        self._heading = pygame.Vector2()
        self.set_state(TALK)

    def react(self, state: str = REACT) -> None:
        """Останавливается и проигрывает реакцию один раз.

        Потом персонаж возвращается в idle или снова идёт, если клавиши движения
        всё ещё зажаты. Если одноразовой анимации для реакции нет и замена
        циклическая, ждать её конца бессмысленно: персонаж возвращается сразу.
        """
        self._heading = pygame.Vector2()
        self.set_state(state, restart=True)
        if self.player.animation.loop:
            self._follow_controls(always_stop=True)
        else:
            self._resume_after_animation = True

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Клавиши движения: стрелки и WASD. Возвращает True, если событие относится к движению."""
        if event.type == pygame.WINDOWFOCUSLOST:
            # Отпускание клавиш в неактивном окне может не дойти до игры: считаем их отпущенными.
            self._held_keys.clear()
            self._follow_controls()
            return False
        if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return False
        move_key = find_move_key(event)
        if move_key is None:
            return False
        if move_key in self._held_keys:
            self._held_keys.remove(move_key)
        if event.type == pygame.KEYDOWN:
            self._held_keys.append(move_key)
        # Нажатие прерывает разговор или реакцию, а отпускание клавиши — нет:
        # после реакции персонаж сам продолжит идти по зажатым клавишам.
        if event.type == pygame.KEYDOWN or self.state in (IDLE, WALK):
            self._follow_controls()
        return True

    def update(self, dt: float) -> None:
        """Сдвигает персонажа и его анимацию на dt секунд."""
        if not 0 <= dt < math.inf:
            raise ValueError(f"dt должен быть неотрицательным конечным числом, а не {dt!r}")
        self.x += self._heading.x * self.speed * dt
        self.y += self._heading.y * self.speed * dt
        self.player.update(dt)
        if self._resume_after_animation and self.player.is_finished:
            self._follow_controls(always_stop=True)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.player.frame, self.rect)

    def _follow_controls(self, always_stop: bool = False) -> None:
        """Идёт туда, куда ведут зажатые клавиши. Если они никуда не ведут — останавливается,
        когда шёл (или всегда при always_stop)."""
        heading, facing = self._controls_heading()
        if heading.length_squared() > 0:
            self.move(heading.x, heading.y, facing)
        elif always_stop or self.is_moving:
            self.stop()

    def _controls_heading(self) -> tuple[pygame.Vector2, Direction | None]:
        """Куда ведут зажатые клавиши и куда при этом смотреть.

        Противоположные клавиши гасят друг друга. Смотрит персонаж туда, куда указывает
        последняя нажатая клавиша из участвующих в движении: если при ходьбе вниз
        нажать →, он повернётся вправо, а когда → отпустят — снова вниз.
        """
        heading = pygame.Vector2()
        for move_key in self._held_keys:
            heading += move_key.direction.value
        for move_key in reversed(self._held_keys):
            dx, dy = move_key.direction.value
            if dx * heading.x > 0 or dy * heading.y > 0:
                return heading, move_key.direction
        return heading, None


def _facing(heading: pygame.Vector2, current: Direction) -> Direction:
    """Направление взгляда при движении по вектору heading.

    Персонаж не отворачивается, если уже смотрит вдоль одной из осей движения,
    иначе при ходьбе по диагонали он бы дёргался. Если не смотрит — поворачивается
    по преобладающей оси, а при равенстве — по горизонтали.
    """
    horizontal = Direction.RIGHT if heading.x > 0 else Direction.LEFT
    vertical = Direction.DOWN if heading.y > 0 else Direction.UP
    if (heading.x and current is horizontal) or (heading.y and current is vertical):
        return current
    return horizontal if abs(heading.x) >= abs(heading.y) else vertical
