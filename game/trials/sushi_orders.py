"""Логика испытания суши без Pygame: заказы, что в руках у Алисы, что на тарелке.

Заказы идут строго по порядку, без случайностей. Алиса носит один ингредиент за раз:
взять со станции, положить на тарелку. Неверный или уже положенный ингредиент не
засчитывается и остаётся в руках — его можно вернуть на станцию или поменять на другой,
поэтому застрять невозможно. Заполненный заказ ждёт next_order(): сцена сначала
показывает реакцию повара.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

INGREDIENTS = ("rice", "salmon", "nori", "cucumber", "avocado")
INGREDIENT_NAMES = {"rice": "Рис", "salmon": "Лосось", "nori": "Нори", "cucumber": "Огурец", "avocado": "Авокадо"}


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    ingredients: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.ingredients:
            raise ValueError(f"в рецепте «{self.name}» нет ингредиентов")
        unknown = [item for item in self.ingredients if item not in INGREDIENTS]
        if unknown:
            raise ValueError(f"в рецепте «{self.name}» неизвестные ингредиенты: {', '.join(unknown)}")
        if len(set(self.ingredients)) != len(self.ingredients):
            raise ValueError(f"в рецепте «{self.name}» ингредиент повторяется")


RECIPES = (
    Recipe("nigiri_salmon", "Нигири с лососем", ("rice", "salmon")),
    Recipe("maki_cucumber", "Маки с огурцом", ("rice", "nori", "cucumber")),
    Recipe("roll_salmon_avocado", "Ролл с лососем и авокадо", ("rice", "nori", "salmon", "avocado")),
)


class TakeResult(Enum):
    TAKEN = "taken"  # руки были пусты — ингредиент взят
    RETURNED = "returned"  # тот же ингредиент вернули на его станцию
    SWAPPED = "swapped"  # прежний вернулся на место, взят новый
    LOCKED = "locked"  # сейчас нельзя: заказ собран и ждёт повара или все заказы готовы


class PlateResult(Enum):
    ADDED = "added"
    ORDER_COMPLETE = "order_complete"  # добавлен последний недостающий ингредиент
    EMPTY_HANDS = "empty_hands"
    WRONG = "wrong"  # ингредиента нет в рецепте — остаётся в руках
    DUPLICATE = "duplicate"  # уже лежит на тарелке — остаётся в руках
    LOCKED = "locked"


class SushiOrders:
    """Текущий заказ, тарелка и руки Алисы."""

    def __init__(self, recipes: Iterable[Recipe] = RECIPES) -> None:
        self.recipes = tuple(recipes)
        if not self.recipes:
            raise ValueError("нужен хотя бы один заказ")
        self.index = 0  # номер текущего заказа; len(recipes) — все готовы
        self.held: str | None = None
        self._plate: list[str] = []

    @property
    def current(self) -> Recipe | None:
        return self.recipes[self.index] if self.index < len(self.recipes) else None

    @property
    def plate(self) -> tuple[str, ...]:
        return tuple(self._plate)

    @property
    def missing(self) -> tuple[str, ...]:
        """Чего ещё не хватает на тарелке, в порядке рецепта."""
        recipe = self.current
        return tuple(item for item in recipe.ingredients if item not in self._plate) if recipe else ()

    @property
    def order_complete(self) -> bool:
        return self.current is not None and not self.missing

    @property
    def all_done(self) -> bool:
        return self.index >= len(self.recipes)

    @property
    def completed_orders(self) -> int:
        return self.index

    def take(self, ingredient: str) -> TakeResult:
        """Взаимодействие со станцией ингредиента."""
        if ingredient not in INGREDIENTS:
            raise ValueError(f"неизвестный ингредиент {ingredient!r}")
        if self.current is None or self.order_complete:
            return TakeResult.LOCKED
        if self.held == ingredient:
            self.held = None
            return TakeResult.RETURNED
        result = TakeResult.TAKEN if self.held is None else TakeResult.SWAPPED
        self.held = ingredient
        return result

    def put_back(self) -> str | None:
        """Возвращает ингредиент из рук на его станцию. Возвращает, что было в руках."""
        held, self.held = self.held, None
        return held

    def place(self) -> PlateResult:
        """Взаимодействие с тарелкой: положить то, что в руках."""
        recipe = self.current
        if recipe is None or self.order_complete:
            return PlateResult.LOCKED
        if self.held is None:
            return PlateResult.EMPTY_HANDS
        if self.held not in recipe.ingredients:
            return PlateResult.WRONG
        if self.held in self._plate:
            return PlateResult.DUPLICATE
        self._plate.append(self.held)
        self.held = None
        return PlateResult.ORDER_COMPLETE if self.order_complete else PlateResult.ADDED

    def next_order(self) -> bool:
        """Переходит к следующему заказу — только если текущий собран. Тарелка очищается."""
        if not self.order_complete:
            return False
        self.index += 1
        self._plate.clear()
        return True
