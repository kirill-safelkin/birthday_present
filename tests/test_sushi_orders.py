"""Проверки логики заказов суши — без Pygame и без окна."""

import unittest

from game.trials.sushi_orders import (
    INGREDIENT_NAMES,
    INGREDIENTS,
    RECIPES,
    PlateResult,
    Recipe,
    SushiOrders,
    TakeResult,
)


def deliver(orders: SushiOrders, ingredient: str) -> PlateResult:
    """Взять ингредиент со станции и положить на тарелку."""
    orders.take(ingredient)
    return orders.place()


class RecipesTest(unittest.TestCase):
    def test_three_fixed_recipes_in_order(self) -> None:
        self.assertEqual(
            [(recipe.name, recipe.ingredients) for recipe in RECIPES],
            [
                ("Нигири с лососем", ("rice", "salmon")),
                ("Маки с огурцом", ("rice", "nori", "cucumber")),
                ("Ролл с лососем и авокадо", ("rice", "nori", "salmon", "avocado")),
            ],
        )

    def test_five_ingredients_with_russian_names(self) -> None:
        self.assertEqual(INGREDIENTS, ("rice", "salmon", "nori", "cucumber", "avocado"))
        self.assertEqual(set(INGREDIENT_NAMES), set(INGREDIENTS))
        used = {item for recipe in RECIPES for item in recipe.ingredients}
        self.assertEqual(used, set(INGREDIENTS))  # каждая станция нужна хотя бы в одном заказе

    def test_invalid_recipes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Recipe("x", "Пусто", ())
        with self.assertRaises(ValueError):
            Recipe("x", "Пицца", ("rice", "cheese"))
        with self.assertRaises(ValueError):
            Recipe("x", "Двойной рис", ("rice", "rice"))
        with self.assertRaises(ValueError):
            SushiOrders([])


class OrdersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.orders = SushiOrders()

    def test_each_recipe_accepts_all_its_ingredients(self) -> None:
        for number, recipe in enumerate(RECIPES):
            with self.subTest(recipe=recipe.name):
                self.assertIs(self.orders.current, recipe)
                self.assertEqual(self.orders.missing, recipe.ingredients)
                results = [deliver(self.orders, item) for item in recipe.ingredients]
                self.assertEqual(results[:-1], [PlateResult.ADDED] * (len(results) - 1))
                self.assertIs(results[-1], PlateResult.ORDER_COMPLETE)
                self.assertTrue(self.orders.order_complete)
                self.assertEqual(sorted(self.orders.plate), sorted(recipe.ingredients))
                self.assertTrue(self.orders.next_order())
                self.assertEqual(self.orders.completed_orders, number + 1)
                self.assertEqual(self.orders.plate, ())  # новая тарелка
        self.assertTrue(self.orders.all_done)
        self.assertIsNone(self.orders.current)

    def test_ingredients_can_be_placed_in_any_order(self) -> None:
        for item in ("salmon", "rice"):
            deliver(self.orders, item)
        self.assertTrue(self.orders.order_complete)

    def test_extra_ingredient_is_not_counted_and_stays_in_hands(self) -> None:
        self.orders.take("cucumber")  # в нигири огурца нет
        self.assertIs(self.orders.place(), PlateResult.WRONG)
        self.assertEqual(self.orders.plate, ())
        self.assertEqual(self.orders.held, "cucumber")
        self.assertEqual(self.orders.missing, ("rice", "salmon"))

    def test_same_ingredient_cannot_be_counted_twice(self) -> None:
        deliver(self.orders, "rice")
        self.orders.take("rice")
        self.assertIs(self.orders.place(), PlateResult.DUPLICATE)
        self.assertEqual(self.orders.plate, ("rice",))
        self.assertEqual(self.orders.held, "rice")
        self.assertFalse(self.orders.order_complete)

    def test_wrong_item_never_leaves_player_stuck(self) -> None:
        self.orders.take("avocado")
        self.orders.place()  # не подошло
        self.assertIs(self.orders.take("avocado"), TakeResult.RETURNED)  # вернуть на свою станцию
        self.assertIsNone(self.orders.held)
        self.orders.take("nori")
        self.assertIs(self.orders.take("rice"), TakeResult.SWAPPED)  # или сразу поменять на нужный
        self.assertEqual(self.orders.held, "rice")
        self.assertIs(self.orders.place(), PlateResult.ADDED)
        self.orders.take("cucumber")
        self.assertEqual(self.orders.put_back(), "cucumber")
        self.assertIsNone(self.orders.held)

    def test_only_one_item_in_hands(self) -> None:
        self.assertIs(self.orders.take("rice"), TakeResult.TAKEN)
        self.assertIs(self.orders.take("salmon"), TakeResult.SWAPPED)
        self.assertEqual(self.orders.held, "salmon")

    def test_empty_hands_at_the_plate(self) -> None:
        self.assertIs(self.orders.place(), PlateResult.EMPTY_HANDS)
        self.assertEqual(self.orders.plate, ())

    def test_next_order_does_not_open_early(self) -> None:
        self.assertFalse(self.orders.next_order())
        deliver(self.orders, "rice")
        self.assertFalse(self.orders.next_order())
        self.assertIs(self.orders.current, RECIPES[0])

    def test_complete_order_waits_for_the_chef(self) -> None:
        deliver(self.orders, "rice")
        deliver(self.orders, "salmon")
        # Пока повар не отреагировал (next_order), ни взять, ни положить нельзя.
        self.assertIs(self.orders.take("nori"), TakeResult.LOCKED)
        self.assertIsNone(self.orders.held)
        self.assertIs(self.orders.place(), PlateResult.LOCKED)
        self.assertTrue(self.orders.next_order())
        self.assertIs(self.orders.take("nori"), TakeResult.TAKEN)

    def test_after_all_orders_nothing_can_be_taken(self) -> None:
        for recipe in RECIPES:
            for item in recipe.ingredients:
                deliver(self.orders, item)
            self.orders.next_order()
        self.assertIs(self.orders.take("rice"), TakeResult.LOCKED)
        self.assertIs(self.orders.place(), PlateResult.LOCKED)
        self.assertFalse(self.orders.next_order())

    def test_unknown_ingredient_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            self.orders.take("cheese")

    def test_same_actions_give_same_result(self) -> None:
        script = ["rice", "cucumber", "salmon", "salmon", "rice"]
        runs = []
        for _ in range(2):
            orders = SushiOrders()
            runs.append([(orders.take(item), orders.place()) for item in script])
        self.assertEqual(runs[0], runs[1])  # ни капли случайности


if __name__ == "__main__":
    unittest.main()
