"""Проверки Лео на площади: только неходячие позы, смена по времени (не по кадрам), спокойные переходы."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import random  # noqa: E402
import unittest  # noqa: E402

from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.world.leo import AWAKE, LAUGH, MOODS, POSE_BY_FRAME, POSES, SLEEP, START_POSE, LeoIdle, LeoPose  # noqa: E402


def timeline(seed: int, dt: float, seconds: float) -> list[tuple[float, str]]:
    """Смены поз: (момент смены, новая поза) за seconds секунд кадрами по dt."""
    leo = LeoIdle(random.Random(seed))
    changes, time = [], 0.0
    for _ in range(round(seconds / dt)):
        before = leo.changes
        leo.update(dt)
        time += dt
        if leo.changes != before:
            changes.append((time, leo.frame))
    return changes


class PosesTest(unittest.TestCase):
    def test_only_sitting_and_lying_poses_from_the_manifest(self) -> None:
        manifest = load_character_sprites(CHARACTERS_DIR / "leo")
        frames = {frame.id for frame in manifest.frames}
        self.assertEqual(manifest.groups, {})  # у Лео нет циклов ходьбы — только отдельные позы
        for pose in POSES:
            self.assertIn(pose.frame, frames)
        used = {pose.frame for pose in POSES}
        # Ни ползания (почти ходьба), ни слёз и сердитого лица — Лео на празднике.
        self.assertFalse(used & {"crawl_try", "cry", "wipe_tears", "frown"})
        self.assertFalse(any("walk" in frame or "crawl" in frame for frame in used))
        self.assertEqual(len(used), len(POSES))

    def test_every_mood_has_poses_and_sensible_durations(self) -> None:
        self.assertEqual({pose.mood for pose in POSES}, set(MOODS))
        self.assertEqual({pose.frame for pose in POSES if pose.mood == SLEEP},
                         {"sleep_blanket", "sleep_teddy", "nap_pillow"})
        self.assertIn("laugh", {pose.frame for pose in POSES if pose.mood == LAUGH})
        self.assertIn("sit_idle", {pose.frame for pose in POSES if pose.mood == AWAKE})
        for pose in POSES:
            low, high = pose.seconds
            self.assertGreaterEqual(low, 2.0, pose.frame)  # спокойно, а не мельтешение
            self.assertLessEqual(high, 15.0, pose.frame)
        self.assertEqual(POSE_BY_FRAME[START_POSE].mood, SLEEP)  # поначалу Лео спит

    def test_bad_poses_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LeoPose("sit_idle", "dance", (1.0, 2.0))
        with self.assertRaises(ValueError):
            LeoPose("sit_idle", AWAKE, (3.0, 2.0))
        with self.assertRaises(ValueError):
            LeoIdle(start="crawl_try")


class TimingTest(unittest.TestCase):
    def test_pose_holds_until_its_time_is_up(self) -> None:
        leo = LeoIdle(random.Random(1))
        low, _ = leo.pose.seconds
        for _ in range(round((low - 0.1) * 60)):
            leo.update(1 / 60)
        self.assertEqual((leo.frame, leo.changes), (START_POSE, 0))  # не каждый кадр
        leo.update(leo.time_left + 0.001)
        self.assertEqual(leo.changes, 1)
        self.assertNotEqual(leo.frame, START_POSE)

    def test_each_pose_lasts_within_its_range(self) -> None:
        leo = LeoIdle(random.Random(5))
        dt, time, started, pose = 1 / 120, 0.0, 0.0, leo.pose
        for _ in range(round(900 / dt)):
            leo.update(dt)
            time += dt
            if leo.pose is not pose:
                low, high = pose.seconds
                self.assertGreaterEqual(time - started, low - dt, pose.frame)
                self.assertLessEqual(time - started, high + dt, pose.frame)
                started, pose = time, leo.pose

    def test_switches_do_not_depend_on_frame_rate(self) -> None:
        for seed in (2, 11):
            with self.subTest(seed=seed):
                slow, fast = timeline(seed, 1 / 30, 300), timeline(seed, 1 / 144, 300)
                self.assertGreater(len(slow), 20)
                self.assertEqual([frame for _, frame in slow], [frame for _, frame in fast])
                for (t_slow, _), (t_fast, _) in zip(slow, fast):
                    self.assertAlmostEqual(t_slow, t_fast, delta=1 / 30 + 1e-6)

    def test_long_frame_does_not_lose_time(self) -> None:
        steady = LeoIdle(random.Random(9))
        for _ in range(100 * 60):
            steady.update(1 / 60)
        jumpy = LeoIdle(random.Random(9))
        jumpy.update(100.0)  # окно было свёрнуто: несколько смен за один кадр, без ошибок
        self.assertEqual((jumpy.frame, jumpy.changes), (steady.frame, steady.changes))
        self.assertAlmostEqual(jumpy.time_left, steady.time_left, places=6)
        self.assertGreater(jumpy.time_left, 0)

    def test_dt_must_be_valid(self) -> None:
        leo = LeoIdle(random.Random(0))
        for dt in (-0.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                leo.update(dt)
        leo.update(0)
        self.assertEqual(leo.changes, 0)


class TransitionsTest(unittest.TestCase):
    def test_calm_transitions_between_moods(self) -> None:
        seen_moods, pairs = set(), set()
        for seed in range(5):
            leo = LeoIdle(random.Random(seed))
            previous = leo.pose
            for _ in range(200):
                leo.update(leo.time_left + 1e-6)
                current = leo.pose
                self.assertIsNot(current, previous)  # всегда новая поза, а не та же подряд
                pairs.add((previous.mood, current.mood))
                seen_moods.add(current.mood)
                previous = current
        self.assertEqual(seen_moods, set(MOODS))
        self.assertNotIn((SLEEP, LAUGH), pairs)  # спящий сначала просыпается
        self.assertNotIn((SLEEP, SLEEP), pairs)
        self.assertNotIn((LAUGH, SLEEP), pairs)  # и не засыпает посреди смеха
        self.assertIn((AWAKE, SLEEP), pairs)
        self.assertIn((AWAKE, LAUGH), pairs)

    def test_same_seed_same_story(self) -> None:
        self.assertEqual(timeline(4, 1 / 60, 120), timeline(4, 1 / 60, 120))


if __name__ == "__main__":
    unittest.main()
