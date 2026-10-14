"""Логика первой части испытания тортов без Pygame: рецепт с перепутанными этапами.

Чучмек выполнил рецепт задом наперёд, поэтому этапы стоят в обратном порядке.
Игрок берёт этап (pick) и выбирает другую позицию — этапы меняются местами; повторный
выбор того же этапа просто кладёт его обратно. Проверка (check) засчитывает только
порядок «ингредиенты → тесто → выпечка → остудить → крем»; неверный порядок не
засчитывается и ничего не портит, а решённый рецепт не «решается» повторно.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

# Этапы в правильном порядке.
STEPS = ("ingredients", "dough", "bake", "cool", "decorate")
CORRECT_ORDER = STEPS
START_ORDER = tuple(reversed(STEPS))  # как сделал Чучмек
STEP_NAMES = {
    "ingredients": "Подготовить ингредиенты",
    "dough": "Замесить тесто",
    "bake": "Испечь коржи",
    "cool": "Остудить коржи",
    "decorate": "Добавить крем и украсить торт",
}
# Короткие подписи — там, где полное название не помещается.
STEP_SHORT_NAMES = {
    "ingredients": "Ингредиенты",
    "dough": "Тесто",
    "bake": "Выпечка",
    "cool": "Остудить",
    "decorate": "Крем",
}


class PickResult(Enum):
    PICKED = "picked"  # этап взят — теперь выбрать, с каким поменять
    DROPPED = "dropped"  # тот же этап выбран снова — положен обратно
    SWAPPED = "swapped"  # этапы поменялись местами
    LOCKED = "locked"  # рецепт уже решён


class CheckResult(Enum):
    SOLVED = "solved"  # порядок верный — рецепт исправлен
    WRONG = "wrong"  # не засчитано, можно переставлять дальше
    INCOMPLETE = "incomplete"  # в рецепте не ровно пять разных этапов
    ALREADY_SOLVED = "already_solved"  # повторная проверка ничего не запускает


class CakeRecipe:
    """Текущий порядок этапов и выбранный (взятый) этап."""

    def __init__(self, order: Iterable[str] = START_ORDER) -> None:
        self._order = list(order)
        unknown = [step for step in self._order if step not in STEPS]
        if unknown:
            raise ValueError(f"неизвестные этапы рецепта: {', '.join(unknown)}")
        if not self._order:
            raise ValueError("в рецепте нет ни одного этапа")
        self.picked: int | None = None  # позиция взятого этапа
        self.solved = False
        self.failed_checks = 0

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(self._order)

    @property
    def is_complete(self) -> bool:
        """В рецепте ровно пять разных этапов — без пропусков и повторов."""
        return sorted(self._order) == sorted(STEPS)

    def first_mistake(self) -> int | None:
        """Первая позиция, где стоит не тот этап. None — порядок верный."""
        for index, step in enumerate(CORRECT_ORDER):
            if index >= len(self._order) or self._order[index] != step:
                return index
        return None if len(self._order) == len(CORRECT_ORDER) else len(CORRECT_ORDER)

    def swap(self, first: int, second: int) -> None:
        """Меняет местами этапы на двух позициях."""
        for index in (first, second):
            if not 0 <= index < len(self._order):
                raise ValueError(f"в рецепте нет позиции {index}")
        self._order[first], self._order[second] = self._order[second], self._order[first]

    def pick(self, index: int) -> PickResult:
        """Выбор этапа: взять, положить обратно или поменять со взятым."""
        if not 0 <= index < len(self._order):
            raise ValueError(f"в рецепте нет позиции {index}")
        if self.solved:
            return PickResult.LOCKED
        if self.picked is None:
            self.picked = index
            return PickResult.PICKED
        if self.picked == index:
            self.picked = None
            return PickResult.DROPPED
        self.swap(self.picked, index)
        self.picked = None
        return PickResult.SWAPPED

    def check(self) -> CheckResult:
        """Проверить рецепт. Взятый этап при этом просто кладётся обратно."""
        if self.solved:
            return CheckResult.ALREADY_SOLVED
        self.picked = None
        if not self.is_complete:
            return CheckResult.INCOMPLETE
        if self.first_mistake() is None:
            self.solved = True
            return CheckResult.SOLVED
        self.failed_checks += 1
        return CheckResult.WRONG
