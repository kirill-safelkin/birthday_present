"""Ввод: логические действия вместо конкретных клавиш и проверка клавиш с учётом раскладки.

Игровая логика спрашивает не «нажата ли W», а «нажато ли действие move_up». Какие
клавиши ему соответствуют, описано в DEFAULT_BINDINGS. Буквенные клавиши сверяются
и по физическому положению (скан-коду), поэтому работают в немецкой и русской раскладках.

ActionInput — общее состояние ввода: какие клавиши удерживаются сейчас. Он же
отличает новое нажатие от системного автоповтора зажатой клавиши.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

import pygame


class Action(str, Enum):
    """Логическое действие игрока."""

    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    CONFIRM = "confirm"  # подтвердить: продолжить реплику, выбрать вариант
    INTERACT = "interact"  # действие с объектом или персонажем рядом
    CANCEL = "cancel"  # назад, закрыть вложенный экран


MOVE_ACTIONS = frozenset({Action.MOVE_UP, Action.MOVE_DOWN, Action.MOVE_LEFT, Action.MOVE_RIGHT})


@dataclass(frozen=True)
class KeyBinding:
    """Клавиша, вызывающая действие. scancode задаётся для букв: их код зависит от раскладки."""

    action: Action
    key: int
    scancode: int | None = None


# Одна клавиша может вызывать несколько действий (Enter — и подтверждение, и взаимодействие):
# сцена сама решает, какое из них ей нужно.
DEFAULT_BINDINGS: tuple[KeyBinding, ...] = (
    KeyBinding(Action.MOVE_UP, pygame.K_UP, pygame.KSCAN_UP),
    KeyBinding(Action.MOVE_UP, pygame.K_w, pygame.KSCAN_W),
    KeyBinding(Action.MOVE_DOWN, pygame.K_DOWN, pygame.KSCAN_DOWN),
    KeyBinding(Action.MOVE_DOWN, pygame.K_s, pygame.KSCAN_S),
    KeyBinding(Action.MOVE_LEFT, pygame.K_LEFT, pygame.KSCAN_LEFT),
    KeyBinding(Action.MOVE_LEFT, pygame.K_a, pygame.KSCAN_A),
    KeyBinding(Action.MOVE_RIGHT, pygame.K_RIGHT, pygame.KSCAN_RIGHT),
    KeyBinding(Action.MOVE_RIGHT, pygame.K_d, pygame.KSCAN_D),
    KeyBinding(Action.CONFIRM, pygame.K_RETURN),
    KeyBinding(Action.CONFIRM, pygame.K_KP_ENTER),
    KeyBinding(Action.CONFIRM, pygame.K_SPACE),
    KeyBinding(Action.INTERACT, pygame.K_e, pygame.KSCAN_E),
    KeyBinding(Action.INTERACT, pygame.K_RETURN),
    KeyBinding(Action.INTERACT, pygame.K_KP_ENTER),
    KeyBinding(Action.CANCEL, pygame.K_BACKSPACE),
)


def matches_key(event: pygame.event.Event, key: int, scancode: int | None) -> bool:
    """True, если событие клавиатуры относится к клавише key.

    Сравниваем и код клавиши, и её физическое положение (скан-код): при нелатинской
    раскладке код буквенной клавиши другой (у D в русской раскладке это «в»),
    а скан-код тот же. scancode=None — сравнивать только код.
    """
    if event.key == key:
        return True
    return scancode is not None and getattr(event, "scancode", None) == scancode


def actions_for(event: pygame.event.Event, bindings: Iterable[KeyBinding] = DEFAULT_BINDINGS) -> frozenset[Action]:
    """Действия, к которым относится нажатие или отпускание клавиши. Для других событий — пусто."""
    if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
        return frozenset()
    return frozenset(binding.action for binding in bindings if matches_key(event, binding.key, binding.scancode))


def _key_id(event: pygame.event.Event) -> object:
    # Физическая клавиша: скан-код не меняется при смене раскладки между нажатием и отпусканием.
    scancode = getattr(event, "scancode", 0)
    return ("scancode", scancode) if scancode else ("key", event.key)


class ActionInput:
    """Какие клавиши и действия удерживаются сейчас.

    handle_event() нужно передавать все события клавиатуры. Повторный KEYDOWN уже
    зажатой клавиши — это системный автоповтор: handle_event() возвращает False, и
    такое событие не должно считаться новым нажатием (например, повторным Enter).
    """

    def __init__(self, bindings: Iterable[KeyBinding] = DEFAULT_BINDINGS) -> None:
        self.bindings = tuple(bindings)
        # Зажатые клавиши в порядке нажатия → их действия.
        self._held: dict[object, frozenset[Action]] = {}

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обновляет состояние. False — событие является автоповтором зажатой клавиши."""
        if event.type == pygame.KEYDOWN:
            key = _key_id(event)
            if key in self._held:
                return False
            self._held[key] = self.actions_for(event)
        elif event.type == pygame.KEYUP:
            self._held.pop(_key_id(event), None)
        elif event.type == pygame.WINDOWFOCUSLOST:
            # Отпускание клавиш в неактивном окне может не дойти до игры: считаем их отпущенными.
            self.release_all()
        return True

    def actions_for(self, event: pygame.event.Event) -> frozenset[Action]:
        return actions_for(event, self.bindings)

    def pressed(self, event: pygame.event.Event) -> frozenset[Action]:
        """Действия, нажатые этим событием (только KEYDOWN)."""
        return self.actions_for(event) if event.type == pygame.KEYDOWN else frozenset()

    def is_held(self, action: Action) -> bool:
        return any(action in actions for actions in self._held.values())

    def held_actions(self) -> list[Action]:
        """Удерживаемые действия от давно нажатого к последнему нажатому, без повторов."""
        latest: dict[Action, int] = {}
        for position, actions in enumerate(self._held.values()):
            for action in actions:
                latest[action] = position
        return sorted(latest, key=latest.__getitem__)

    def release_all(self) -> None:
        self._held.clear()
