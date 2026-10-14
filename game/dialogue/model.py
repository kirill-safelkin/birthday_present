"""Диалоги: сценарий и логика его прохождения, без отрисовки.

Сценарий (DialogueScript) — набор реплик (DialogueNode), связанных идентификаторами.
Реплика ведёт к следующей (next_id), предлагает варианты ответа (choices) или,
если нет ни того ни другого, завершает диалог. DialogueController проводит игрока
по сценарию: печатает текст, переключает реплики и запоминает выбранные ответы.
Отрисовка находится в game/dialogue/box.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pygame

import config
from game.core.input import Action, actions_for


class DialogueError(ValueError):
    """Ошибка в сценарии диалога. Обнаруживается при загрузке сценария, а не во время игры."""


@dataclass(frozen=True)
class DialogueChoice:
    """Вариант ответа: текст на экране и идентификатор реплики, к которой он ведёт."""

    text: str
    next_id: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise DialogueError(f"пустой текст у варианта ответа, ведущего к «{self.next_id}»")
        if not self.next_id.strip():
            raise DialogueError(f"у варианта ответа «{self.text}» не указана следующая реплика")


@dataclass(frozen=True)
class DialogueNode:
    """Одна реплика.

    next_id — следующая реплика, choices — варианты ответа вместо неё. Если нет
    ни того ни другого, реплика последняя: после неё диалог завершается.
    Пустое имя говорящего означает слова рассказчика (без таблички с именем).
    """

    id: str
    speaker: str
    text: str
    next_id: str | None = None
    choices: Sequence[DialogueChoice] | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise DialogueError("пустой идентификатор реплики")
        if not self.text.strip():
            raise DialogueError(f"пустой текст реплики «{self.id}»")
        if self.choices is not None:
            # Кортеж вместо списка: реплика неизменяема, и её можно использовать как ключ словаря.
            object.__setattr__(self, "choices", tuple(self.choices))
            if not self.choices:
                raise DialogueError(f"у реплики «{self.id}» пустой список вариантов ответа")
            if self.next_id is not None:
                raise DialogueError(f"у реплики «{self.id}» указаны и next_id, и варианты ответа")

    @property
    def targets(self) -> tuple[str, ...]:
        """Идентификаторы реплик, к которым можно перейти отсюда."""
        if self.choices:
            return tuple(choice.next_id for choice in self.choices)
        return (self.next_id,) if self.next_id is not None else ()


class DialogueScript:
    """Реплики одного диалога и начальная реплика. Сценарий проверяется при создании."""

    def __init__(self, start_id: str, nodes: Iterable[DialogueNode]) -> None:
        self.start_id = start_id
        self.nodes: dict[str, DialogueNode] = {}
        for node in nodes:
            if node.id in self.nodes:
                raise DialogueError(f"идентификатор реплики «{node.id}» повторяется")
            self.nodes[node.id] = node
        self._validate()

    def _validate(self) -> None:
        if not self.nodes:
            raise DialogueError("в сценарии нет ни одной реплики")
        if self.start_id not in self.nodes:
            raise DialogueError(f"начальная реплика «{self.start_id}» не найдена")
        for node in self.nodes.values():
            for target in node.targets:
                if target not in self.nodes:
                    raise DialogueError(f"реплика «{node.id}» ссылается на несуществующую реплику «{target}»")

        # Из каждой реплики должен быть путь к концу диалога, иначе игрок застрянет в цикле.
        can_finish = {node.id for node in self.nodes.values() if not node.targets}
        changed = True
        while changed:
            changed = False
            for node in self.nodes.values():
                if node.id not in can_finish and any(target in can_finish for target in node.targets):
                    can_finish.add(node.id)
                    changed = True
        stuck = [node_id for node_id in self.nodes if node_id not in can_finish]
        if stuck:
            names = ", ".join(f"«{node_id}»" for node_id in stuck)
            raise DialogueError(f"из реплик {names} нельзя дойти до конца диалога")


class DialogueController:
    """Проводит игрока по сценарию: печать текста, переходы и выбор ответа.

    Контроллер не рисует и не управляет приложением: вызывающий код передаёт
    сюда события и dt, а затем читает состояние — node, visible_text, choices,
    selected_index, is_finished и answers.
    """

    def __init__(self, script: DialogueScript, chars_per_second: float = config.DIALOGUE_CHARS_PER_SECOND) -> None:
        if chars_per_second <= 0:
            raise ValueError("скорость печати должна быть больше нуля")
        self.script = script
        self.chars_per_second = chars_per_second
        # Выбранные ответы: идентификатор реплики с вопросом → вариант. Если к вопросу
        # вернулись и ответили снова, хранится последний ответ.
        self.answers: dict[str, DialogueChoice] = {}
        self.node: DialogueNode | None = None
        self.selected_index = 0
        self._typed = 0.0  # сколько символов напечатано; дробное, чтобы копить маленькие dt
        self._go_to(script.start_id)

    @property
    def is_finished(self) -> bool:
        return self.node is None

    @property
    def visible_chars(self) -> int:
        """Сколько символов текущей реплики уже видно."""
        # Допуск на погрешность float: сумма многих маленьких dt бывает чуть меньше точной.
        return int(self._typed + 1e-6)

    @property
    def visible_text(self) -> str:
        return self.node.text[: self.visible_chars] if self.node is not None else ""

    @property
    def is_typing(self) -> bool:
        return self.node is not None and self.visible_chars < len(self.node.text)

    @property
    def choices(self) -> Sequence[DialogueChoice]:
        """Варианты ответа, доступные сейчас. Появляются только после печати текста."""
        if self.node is None or self.is_typing:
            return ()
        return self.node.choices or ()

    def update(self, dt: float) -> None:
        """Продвигает печать текста на dt секунд."""
        if self.node is not None and self.is_typing:
            self._typed = min(len(self.node.text), self._typed + dt * self.chars_per_second)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обрабатывает нажатие клавиши. Возвращает True, если оно относится к диалогу.

        Действие confirm (Enter, пробел) дописывает текст, продолжает или выбирает ответ;
        move_up и move_down (стрелки, W/S) двигают выделение. Реагируем только на KEYDOWN:
        одно физическое нажатие — один шаг диалога (автоповтор отсекает ActionInput).
        """
        if event.type != pygame.KEYDOWN or self.is_finished:
            return False
        actions = actions_for(event)
        if Action.CONFIRM in actions:
            self.confirm()
        elif Action.MOVE_UP in actions:
            self.move_selection(-1)
        elif Action.MOVE_DOWN in actions:
            self.move_selection(1)
        else:
            return False
        return True

    def confirm(self) -> None:
        """Enter или пробел: дописать текст, а если он уже виден — выбрать ответ или перейти дальше."""
        node = self.node
        if node is None:
            return
        if self.is_typing:
            self._typed = len(node.text)
        elif node.choices:
            choice = node.choices[self.selected_index]
            self.answers[node.id] = choice
            self._go_to(choice.next_id)
        else:
            self._go_to(node.next_id)

    def move_selection(self, step: int) -> None:
        """Стрелки: сдвигает выделение по кругу. Пока текст печатается, вариантов не видно."""
        choices = self.choices
        if choices:
            self.selected_index = (self.selected_index + step) % len(choices)

    def _go_to(self, node_id: str | None) -> None:
        # Ссылки проверены при загрузке сценария, поэтому реплика с таким id существует.
        # Новая реплика начинает печататься с нуля, так что одно нажатие не пропустит её текст.
        self.node = self.script.nodes[node_id] if node_id is not None else None
        self.selected_index = 0
        self._typed = 0.0
