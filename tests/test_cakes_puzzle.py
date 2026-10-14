"""Проверки логики рецепта испытания тортов — без Pygame и без окна."""

import itertools
import subprocess
import sys
import unittest
from pathlib import Path

from game.trials.cakes_puzzle import (
    CORRECT_ORDER,
    START_ORDER,
    STEP_NAMES,
    STEP_SHORT_NAMES,
    STEPS,
    CakeRecipe,
    CheckResult,
    PickResult,
)

ROOT = Path(__file__).resolve().parent.parent


def solve(recipe: CakeRecipe) -> None:
    """Расставляет этапы по порядку из любого состояния — только обычными действиями."""
    if recipe.picked is not None:
        recipe.pick(recipe.picked)
    for index, step in enumerate(CORRECT_ORDER):
        if recipe.order[index] != step:
            recipe.pick(recipe.order.index(step))
            recipe.pick(index)


class DataTest(unittest.TestCase):
    def test_five_steps_in_the_correct_order(self) -> None:
        self.assertEqual([STEP_NAMES[step] for step in CORRECT_ORDER], [
            "Подготовить ингредиенты",
            "Замесить тесто",
            "Испечь коржи",
            "Остудить коржи",
            "Добавить крем и украсить торт",
        ])
        self.assertEqual(set(STEP_SHORT_NAMES), set(STEPS))
        for step in STEPS:
            self.assertLess(len(STEP_SHORT_NAMES[step]), len(STEP_NAMES[step]))  # короткие — правда короче

    def test_start_order_is_reversed_and_wrong(self) -> None:
        recipe = CakeRecipe()
        self.assertEqual(recipe.order, START_ORDER)
        self.assertEqual(recipe.order, tuple(reversed(CORRECT_ORDER)))
        self.assertNotEqual(recipe.order, CORRECT_ORDER)
        self.assertEqual(recipe.first_mistake(), 0)
        self.assertTrue(recipe.is_complete)
        self.assertFalse(recipe.solved)

    def test_invalid_recipes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CakeRecipe(["ingredients", "pizza"])
        with self.assertRaises(ValueError):
            CakeRecipe([])


class CheckTest(unittest.TestCase):
    def test_only_the_correct_order_is_accepted(self) -> None:
        accepted = []
        for order in itertools.permutations(STEPS):
            recipe = CakeRecipe(order)
            if recipe.check() is CheckResult.SOLVED:
                accepted.append(order)
            else:
                self.assertFalse(recipe.solved, order)
        self.assertEqual(accepted, [CORRECT_ORDER])  # обратный и все остальные порядки — нет

    def test_reversed_order_is_wrong_and_can_be_retried(self) -> None:
        recipe = CakeRecipe()
        self.assertIs(recipe.check(), CheckResult.WRONG)
        self.assertEqual(recipe.failed_checks, 1)
        self.assertEqual(recipe.order, START_ORDER)  # порядок не перемешан и не сброшен
        recipe.swap(0, 4)
        self.assertEqual(recipe.first_mistake(), 1)
        self.assertIs(recipe.check(), CheckResult.WRONG)
        self.assertEqual(recipe.failed_checks, 2)
        recipe.swap(1, 3)
        self.assertIs(recipe.check(), CheckResult.SOLVED)
        self.assertTrue(recipe.solved)

    def test_no_success_without_all_five_steps(self) -> None:
        for order in (CORRECT_ORDER[:4], CORRECT_ORDER[1:], ("ingredients", "dough", "bake", "cool", "cool"),
                      (*CORRECT_ORDER, "decorate")):
            with self.subTest(order=order):
                recipe = CakeRecipe(order)
                self.assertFalse(recipe.is_complete)
                self.assertIs(recipe.check(), CheckResult.INCOMPLETE)
                self.assertFalse(recipe.solved)
                self.assertIsNotNone(recipe.first_mistake())

    def test_solved_recipe_does_not_fire_success_again(self) -> None:
        recipe = CakeRecipe(CORRECT_ORDER)
        self.assertIs(recipe.check(), CheckResult.SOLVED)
        for _ in range(3):
            self.assertIs(recipe.check(), CheckResult.ALREADY_SOLVED)
        for index in range(len(STEPS)):
            self.assertIs(recipe.pick(index), PickResult.LOCKED)
        self.assertIsNone(recipe.picked)
        self.assertEqual(recipe.order, CORRECT_ORDER)
        self.assertEqual(recipe.failed_checks, 0)


class PickTest(unittest.TestCase):
    def setUp(self) -> None:
        self.recipe = CakeRecipe()  # крем, остудить, испечь, тесто, ингредиенты

    def test_swap_exchanges_two_steps(self) -> None:
        self.recipe.swap(1, 3)
        self.assertEqual(self.recipe.order, ("decorate", "dough", "bake", "cool", "ingredients"))
        self.recipe.swap(3, 1)
        self.assertEqual(self.recipe.order, START_ORDER)
        self.recipe.swap(2, 2)
        self.assertEqual(self.recipe.order, START_ORDER)
        with self.assertRaises(ValueError):
            self.recipe.swap(0, 5)

    def test_pick_then_choose_another_place(self) -> None:
        self.assertIs(self.recipe.pick(4), PickResult.PICKED)
        self.assertEqual(self.recipe.picked, 4)
        self.assertEqual(self.recipe.order, START_ORDER)  # взять — ещё не переставить
        self.assertIs(self.recipe.pick(0), PickResult.SWAPPED)
        self.assertIsNone(self.recipe.picked)
        self.assertEqual(self.recipe.order, ("ingredients", "cool", "bake", "dough", "decorate"))

    def test_picking_the_same_step_puts_it_back(self) -> None:
        self.recipe.pick(2)
        self.assertIs(self.recipe.pick(2), PickResult.DROPPED)
        self.assertIsNone(self.recipe.picked)
        self.assertEqual(self.recipe.order, START_ORDER)

    def test_check_puts_the_picked_step_back(self) -> None:
        self.recipe.pick(1)
        self.assertIs(self.recipe.check(), CheckResult.WRONG)
        self.assertIsNone(self.recipe.picked)
        self.assertEqual(self.recipe.order, START_ORDER)

    def test_unknown_position_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            self.recipe.pick(5)
        with self.assertRaises(ValueError):
            self.recipe.pick(-1)

    def test_game_cannot_be_blocked(self) -> None:
        # Любая последовательность выборов и проверок оставляет путь к решению и не теряет этапы.
        actions = [0, 2, 4, "check"]
        for length in range(5):
            for sequence in itertools.product(actions, repeat=length):
                recipe = CakeRecipe()
                for action in sequence:
                    recipe.check() if action == "check" else recipe.pick(action)
                self.assertEqual(sorted(recipe.order), sorted(STEPS), sequence)
                solve(recipe)
                self.assertIn(recipe.check(), (CheckResult.SOLVED, CheckResult.ALREADY_SOLVED), sequence)

    def test_same_actions_give_same_result(self) -> None:
        runs = []
        for _ in range(2):
            recipe = CakeRecipe()
            log = [recipe.pick(index) for index in (0, 4, 1, 1, 3)] + [recipe.check()]
            runs.append((log, recipe.order))
        self.assertEqual(runs[0], runs[1])  # ни капли случайности

    def test_logic_does_not_need_pygame(self) -> None:
        # Отдельный процесс: в этом Pygame уже мог загрузить другой модуль тестов.
        code = "import sys, game.trials.cakes_puzzle; print('pygame' in sys.modules)"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
