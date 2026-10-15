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

    Показанные реплики запоминаются в истории разговора: ← возвращает к предыдущей, →
    (как и пробел, E, Enter) — снова к следующей. Пока игрок листает историю (is_reviewing),
    node — старая реплика, она видна целиком, а на вопросе выделен ответ, который тогда выбрали;
    ответить заново или пропустить что-то нельзя. Текущая реплика ждёт на своём месте: её
    печать и выделение не теряются, а answers и всё, что уже случилось, не меняются.
    Дальше текущей реплики история не заходит — там диалог идёт по обычным правилам.
    История у каждого контроллера своя: новый разговор начинается с пустой.
    """

    def __init__(self, script: DialogueScript, chars_per_second: float = config.DIALOGUE_CHARS_PER_SECOND) -> None:
        if chars_per_second <= 0:
            raise ValueError("скорость печати должна быть больше нуля")
        self.script = script
        self.chars_per_second = chars_per_second
        # Выбранные ответы: идентификатор реплики с вопросом → вариант. Если к вопросу
        # вернулись и ответили снова, хранится последний ответ.
        self.answers: dict[str, DialogueChoice] = {}
        # Показанные реплики по порядку; последняя — текущая. Реплика может встретиться
        # дважды (вопрос задали снова), поэтому ответ хранится у шага истории, а не у реплики.
        self._history: list[DialogueNode] = []
        self._picked: list[int | None] = []  # какой ответ выбран на каждом шаге (None — не вопрос)
        self._cursor = 0  # какой шаг истории на экране
        self._finished = False
        self._selected = 0  # выделение на текущей реплике
        self._typed = 0.0  # сколько символов напечатано; дробное, чтобы копить маленькие dt
        self._go_to(script.start_id)

    @property
    def node(self) -> DialogueNode | None:
        """Реплика на экране: текущая или, пока листают историю, одна из прежних. None — диалог окончен."""
        return None if self._finished else self._history[self._cursor]

    @property
    def is_finished(self) -> bool:
        return self._finished

    @property
    def is_reviewing(self) -> bool:
        """На экране не текущая реплика, а одна из уже пройденных."""
        return not self._finished and self._cursor < len(self._history) - 1

    @property
    def can_go_back(self) -> bool:
        return not self._finished and self._cursor > 0

    @property
    def selected_index(self) -> int:
        """Выделенный вариант; в истории — тот, что был выбран на этом вопросе."""
        if self.is_reviewing:
            return self._picked[self._cursor] or 0
        return self._selected

    @property
    def visible_chars(self) -> int:
        """Сколько символов реплики на экране уже видно."""
        node = self.node
        if node is None:
            return 0
        if self.is_reviewing:
            return len(node.text)  # прежняя реплика уже была прочитана — она видна вся
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
        """Варианты ответа на экране. Появляются только после печати текста."""
        if self.node is None or self.is_typing:
            return ()
        return self.node.choices or ()

    def update(self, dt: float) -> None:
        """Продвигает печать текущей реплики на dt секунд. Пока листают историю, печать ждёт."""
        if self.is_reviewing:
            return
        if self.node is not None and self.is_typing:
            self._typed = min(len(self.node.text), self._typed + dt * self.chars_per_second)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Обрабатывает нажатие клавиши. Возвращает True, если оно относится к диалогу.

        Действие confirm (Enter, пробел) дописывает текст и продолжает диалог, page_forward (→)
        делает то же, что пробел, а page_back (←) возвращает к предыдущей показанной реплике.
        move_up и move_down (стрелки, W/S) двигают выделение. Вариант ответа выбирает только
        клавиша, у которой есть и действие interact, — Enter (E сцены передают в confirm() сами).
        Пробел и → на вопросе ничего не делают: быстрое пролистывание не выберет ответ вслепую
        и не проскочит ветку. Реагируем только на KEYDOWN: одно физическое нажатие — один шаг
        диалога (автоповтор отсекает ActionInput).
        """
        if event.type != pygame.KEYDOWN or self.is_finished:
            return False
        actions = actions_for(event)
        if Action.PAGE_BACK in actions:
            self.back()
        elif Action.CONFIRM in actions or Action.PAGE_FORWARD in actions:
            if self.is_reviewing or not self.choices or Action.INTERACT in actions:
                self.confirm()
        elif Action.MOVE_UP in actions:
            self.move_selection(-1)
        elif Action.MOVE_DOWN in actions:
            self.move_selection(1)
        else:
            return False
        return True

    def confirm(self) -> None:
        """Дописать текст, а если он уже виден — выбрать выделенный ответ или перейти дальше.
        В истории — шаг к следующей уже показанной реплике.

        Это шаг E или Enter; пробел и → сюда на вопросе не попадают (см. handle_event)."""
        node = self.node
        if node is None:
            return
        if self.is_reviewing:
            self._cursor += 1  # уже показанная реплика: без новых ответов и переходов
        elif self.is_typing:
            self._typed = len(node.text)
        elif node.choices:
            choice = node.choices[self._selected]
            self.answers[node.id] = choice
            self._picked[-1] = self._selected
            self._go_to(choice.next_id)
        else:
            self._go_to(node.next_id)

    def back(self) -> bool:
        """← : к предыдущей показанной реплике. Раньше первой реплики разговора не уходит.
        True, если реплика на экране сменилась."""
        if not self.can_go_back:
            return False
        self._cursor -= 1
        return True

    def move_selection(self, step: int) -> None:
        """Стрелки: сдвигает выделение по кругу. Пока текст печатается, вариантов не видно,
        а в истории ответ уже выбран — его не меняют."""
        choices = self.choices
        if choices and not self.is_reviewing:
            self._selected = (self._selected + step) % len(choices)

    def _go_to(self, node_id: str | None) -> None:
        # Ссылки проверены при загрузке сценария, поэтому реплика с таким id существует.
        # Новая реплика начинает печататься с нуля, так что одно нажатие не пропустит её текст.
        self._selected = 0
        self._typed = 0.0
        if node_id is None:
            self._finished = True
            return
        self._history.append(self.script.nodes[node_id])
        self._picked.append(None)
        self._cursor = len(self._history) - 1
