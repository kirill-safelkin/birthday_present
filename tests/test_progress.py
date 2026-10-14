"""Проверки прогресса трёх испытаний."""

import unittest

from game.world.progress import TRIAL_NAMES, TRIALS, GameProgress


class GameProgressTest(unittest.TestCase):
    def setUp(self) -> None:
        self.progress = GameProgress()

    def test_starts_empty(self) -> None:
        self.assertEqual(self.progress.completed, ())
        self.assertEqual((self.progress.fragments, self.progress.total), (0, 3))
        self.assertFalse(self.progress.has_all_fragments)

    def test_three_known_trials(self) -> None:
        self.assertEqual(TRIALS, ("sushi", "forms", "cakes"))
        self.assertEqual(TRIAL_NAMES, {"sushi": "Суши", "forms": "Формуляры", "cakes": "Торты"})

    def test_repeated_completion_does_not_duplicate(self) -> None:
        self.assertTrue(self.progress.complete("sushi"))
        self.assertFalse(self.progress.complete("sushi"))
        self.assertEqual(self.progress.completed, ("sushi",))
        self.assertEqual(self.progress.fragments, 1)
        self.assertTrue(self.progress.is_completed("sushi"))
        self.assertFalse(self.progress.is_completed("cakes"))

    def test_unknown_trial_is_rejected_without_changing_state(self) -> None:
        for bad in ("pizza", "", "Sushi", None):
            with self.subTest(trial=bad), self.assertRaises(ValueError):
                self.progress.complete(bad)
        self.assertEqual(self.progress.completed, ())

    def test_final_opens_only_after_all_three(self) -> None:
        for trial in ("cakes", "sushi"):
            self.progress.complete(trial)
            self.assertFalse(self.progress.has_all_fragments)
        self.progress.complete("cakes")  # повтор не считается третьим фрагментом
        self.assertFalse(self.progress.has_all_fragments)
        self.progress.complete("forms")
        self.assertTrue(self.progress.has_all_fragments)
        self.assertEqual(self.progress.completed, ("cakes", "sushi", "forms"))

    def test_completed_cannot_be_changed_from_outside(self) -> None:
        completed = self.progress.completed
        self.assertIsInstance(completed, tuple)


if __name__ == "__main__":
    unittest.main()
