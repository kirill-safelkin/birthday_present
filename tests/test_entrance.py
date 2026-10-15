"""Проверки модели входа в Страну чудес (game/story/entrance.py): стадии, триггер, эффекты, вход в нору.

Модель не зависит от Pygame, поэтому проверяется без окна и без сцены."""

import os

# Модуль не рисует, но правило общее для всех тестов: SDL — в память, до любого импорта Pygame.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

from game.story.entrance import (  # noqa: E402
    DURATIONS,
    ENTER_DISTANCE,
    HOLE_X,
    ORDER,
    SETTLE_SECONDS,
    TRIGGER_DISTANCE,
    WALK_MAX_X,
    WALK_MIN_X,
    Effects,
    Entrance,
    Stage,
)

FAR = HOLE_X - TRIGGER_DISTANCE - 60  # Алиса далеко от места норы
TRIGGER = HOLE_X - TRIGGER_DISTANCE  # ближайшая к Алисе граница области срабатывания
NEAR = HOLE_X - ENTER_DISTANCE + 2  # у самой норы
SHOW = sum(DURATIONS.values())  # сколько длится постановка от сбоя до готовой норы


def run(entrance: Entrance, seconds: float, x: float, dt: float = 1 / 60) -> None:
    elapsed = 0.0
    while elapsed < seconds - 1e-9:
        chunk = min(dt, seconds - elapsed)
        entrance.update(chunk, x)
        elapsed += chunk


def ready_entrance() -> Entrance:
    entrance = Entrance()
    entrance.update(SHOW + 0.01, TRIGGER)
    assert entrance.stage is Stage.HOLE_READY
    return entrance


class FreeWalkTest(unittest.TestCase):
    def test_starts_with_free_walk_and_no_hole(self) -> None:
        entrance = Entrance()
        self.assertIs(entrance.stage, Stage.FREE_WALK)
        self.assertTrue(entrance.can_walk)
        self.assertFalse(entrance.hole_exists)
        fx = entrance.effects(FAR)
        self.assertEqual((fx.depth, fx.rim, fx.ring, fx.fold, fx.waves), (0.0, 0.0, 0.0, 0.0, ()))

    def test_nothing_happens_while_alice_is_far(self) -> None:
        entrance = Entrance()
        run(entrance, 120.0, FAR)
        self.assertIs(entrance.stage, Stage.FREE_WALK)
        self.assertEqual(entrance.stage_log, [Stage.FREE_WALK])

    def test_walking_back_and_forth_outside_the_area_keeps_control(self) -> None:
        entrance = Entrance()
        for x in (FAR, TRIGGER - 1, WALK_MIN_X, TRIGGER - 0.5, FAR, TRIGGER - 3):
            run(entrance, 0.7, x)
            self.assertIs(entrance.stage, Stage.FREE_WALK)
            self.assertTrue(entrance.can_walk)

    def test_hints_get_stronger_closer_to_the_place_but_never_show_a_hole(self) -> None:
        entrance = Entrance()
        hints = [entrance.effects(x).hint for x in (WALK_MIN_X, FAR, TRIGGER - 20, TRIGGER - 1)]
        self.assertEqual(hints, sorted(hints))
        self.assertGreater(hints[-1], hints[0])
        sparks = 0
        for _ in range(400):  # редкие искорки, а не постоянное свечение
            entrance.update(0.01, FAR)
            fx = entrance.effects(FAR)
            sparks += bool(fx.sparks)
            self.assertEqual((fx.depth, fx.rim, fx.ring, fx.flash), (0.0, 0.0, 0.0, 0.0))
        self.assertGreater(sparks, 0)
        self.assertLess(sparks, 200)

    def test_alice_stays_inside_the_scene(self) -> None:
        self.assertEqual(Entrance.clamp(-500), WALK_MIN_X)
        self.assertEqual(Entrance.clamp(10_000), WALK_MAX_X)
        self.assertEqual(Entrance.clamp(150.5), 150.5)
        self.assertLess(WALK_MAX_X, HOLE_X)  # к центру норы не подойти: дальше её край
        self.assertLessEqual(HOLE_X - WALK_MAX_X, ENTER_DISTANCE)  # но с края в неё можно заглянуть


class TriggerTest(unittest.TestCase):
    def test_entering_the_area_starts_the_show_and_takes_control(self) -> None:
        entrance = Entrance()
        entrance.update(1 / 60, TRIGGER)
        self.assertIs(entrance.stage, Stage.GLITCH_WARNING)
        self.assertFalse(entrance.can_walk)
        self.assertFalse(entrance.hole_exists)

    def test_any_point_of_the_area_works_not_just_one_coordinate(self) -> None:
        for x in (TRIGGER, TRIGGER + 0.3, TRIGGER + 7, HOLE_X - 10, WALK_MAX_X):
            with self.subTest(x=x):
                entrance = Entrance()
                entrance.update(1 / 60, x)
                self.assertIs(entrance.stage, Stage.GLITCH_WARNING)
        entrance = Entrance()
        entrance.update(1 / 60, TRIGGER - 0.01)
        self.assertIs(entrance.stage, Stage.FREE_WALK)

    def test_show_starts_once_and_goes_through_every_stage_in_order(self) -> None:
        entrance = Entrance()
        stages = []
        for _ in range(2000):
            entrance.update(1 / 60, TRIGGER)  # Алиса всё время стоит в области срабатывания
            if not stages or stages[-1] is not entrance.stage:
                stages.append(entrance.stage)
        self.assertEqual(stages, list(ORDER[1:5]))
        self.assertEqual(entrance.stage_log, list(ORDER[:5]))  # каждая стадия — один раз
        self.assertTrue(entrance.can_walk)  # готовая нора: управление вернулось

    def test_big_dt_does_not_skip_a_stage(self) -> None:
        for dt in (0.3, 1.0, 2.5, SHOW + 5, 1000.0):
            with self.subTest(dt=dt):
                entrance = Entrance()
                entrance.update(dt, TRIGGER)
                self.assertEqual(entrance.stage_log[: len(entrance.stage_log)], list(ORDER[: len(entrance.stage_log)]))
                if dt >= SHOW:
                    self.assertIs(entrance.stage, Stage.HOLE_READY)
                    self.assertAlmostEqual(entrance.stage_time, dt - SHOW, places=6)

    def test_timeline_does_not_depend_on_frame_rate(self) -> None:
        moments = (0.5, 1.7, 3.0, 4.9, SHOW + 0.4)
        reference = None
        for dt in (1 / 144, 1 / 60, 1 / 30, 0.1, 0.7):
            entrance = Entrance()
            entrance.update(1e-3, TRIGGER)  # сбой начался
            elapsed, samples = 0.0, []
            for moment in moments:
                run(entrance, moment - elapsed, TRIGGER, dt)
                elapsed = moment
                samples.append((entrance.stage, round(entrance.stage_time, 6)))
            if reference is None:
                reference = samples
            self.assertEqual(samples, reference, dt)

    def test_rejects_bad_dt(self) -> None:
        entrance = Entrance()
        for dt in (-0.1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                entrance.update(dt, FAR)


class HoleTest(unittest.TestCase):
    def test_hole_grows_gradually_and_is_usable_only_when_ready(self) -> None:
        entrance = Entrance()
        entrance.update(1e-3, TRIGGER)
        depths, seen_waves, seen_fold, seen_ring, seen_sparks = [], False, False, False, False
        while entrance.stage is not Stage.HOLE_READY:
            fx = entrance.effects()
            depths.append((entrance.stage, fx.depth))
            seen_waves |= bool(fx.waves)
            seen_fold |= fx.fold > 0
            seen_ring |= fx.ring > 0
            seen_sparks |= bool(fx.sparks)
            self.assertFalse(entrance.hole_exists)
            self.assertFalse(entrance.can_enter(NEAR))
            entrance.update(1 / 60, TRIGGER)
        values = [depth for _, depth in depths]
        self.assertEqual(values, sorted(values))  # глубина только растёт
        self.assertTrue(all(depth == 0 for stage, depth in depths if stage is not Stage.HOLE_OPENING))
        self.assertTrue(any(0 < depth < 1 for depth in values))  # раскрывается постепенно, а не включается
        self.assertTrue(seen_waves and seen_fold and seen_ring and seen_sparks)
        self.assertTrue(entrance.hole_exists)
        self.assertEqual(entrance.effects().depth, 1.0)

    def test_effects_settle_and_the_hole_stops_flickering(self) -> None:
        entrance = ready_entrance()
        self.assertFalse(entrance.effects().is_calm)  # последние искры и свечение ещё есть
        run(entrance, SETTLE_SECONDS + 0.05, NEAR)
        calm = entrance.effects()
        self.assertTrue(calm.is_calm)
        self.assertEqual(calm, Effects(depth=1.0, rim=1.0))
        for _ in range(50):  # дальше нора стоит неподвижно
            entrance.update(0.13, NEAR)
            self.assertEqual(entrance.effects(), calm)

    def test_effects_do_not_jump_between_stages(self) -> None:
        # Был дефект: круг в конце WORLD_BREAKING уже светился, а HOLE_OPENING начинал его с нуля — он мигал.
        entrance = Entrance()
        entrance.update(1e-3, TRIGGER)
        previous = None
        while entrance.stage is not Stage.HOLE_READY:
            fx = entrance.effects()
            if previous is not None:
                self.assertLess(abs(fx.ring - previous.ring), 0.1, entrance.stage)
                self.assertLess(abs(fx.glow - previous.glow), 0.1, entrance.stage)
                self.assertLess(abs(fx.spin - previous.spin), 0.2, entrance.stage)
            previous = fx
            entrance.update(1 / 60, TRIGGER)
        self.assertLess(abs(entrance.effects().glow - previous.glow), 0.1)  # и в готовую нору — плавно

    def test_flashes_are_short(self) -> None:
        entrance = Entrance()
        entrance.update(1e-3, TRIGGER)
        bright = 0.0
        while entrance.stage is not Stage.HOLE_READY:
            if entrance.effects().flash > 0:
                bright += 1 / 120
            self.assertLessEqual(entrance.effects().flash, 0.5)
            entrance.update(1 / 120, TRIGGER)
        self.assertGreater(bright, 0)
        self.assertLess(bright, 0.5)  # вспышки не закрывают персонажей надолго


class EnterTest(unittest.TestCase):
    def test_e_far_from_the_hole_does_nothing(self) -> None:
        entrance = ready_entrance()
        for x in (WALK_MIN_X, FAR, TRIGGER, HOLE_X - ENTER_DISTANCE - 0.5):
            self.assertFalse(entrance.enter(x))
            self.assertIs(entrance.stage, Stage.HOLE_READY)

    def test_e_near_the_hole_enters_exactly_once(self) -> None:
        entrance = ready_entrance()
        self.assertTrue(entrance.can_enter(NEAR))
        self.assertTrue(entrance.enter(NEAR))
        self.assertIs(entrance.stage, Stage.ENTERING_HOLE)
        self.assertFalse(entrance.can_walk)  # дальше ведёт сценарий
        for _ in range(5):
            self.assertFalse(entrance.enter(NEAR))
        self.assertEqual(entrance.stage_log.count(Stage.ENTERING_HOLE), 1)
        self.assertEqual(entrance.stage_log, list(ORDER))

    def test_e_before_the_hole_exists_does_nothing(self) -> None:
        entrance = Entrance()
        self.assertFalse(entrance.enter(NEAR))
        entrance.update(1e-3, TRIGGER)
        while entrance.stage is not Stage.HOLE_READY:
            self.assertFalse(entrance.enter(NEAR))
            entrance.update(0.1, TRIGGER)

    def test_walking_away_and_back_keeps_the_hole_usable(self) -> None:
        entrance = ready_entrance()
        for x in (FAR, WALK_MIN_X, TRIGGER):
            run(entrance, 3.0, x)
            self.assertIs(entrance.stage, Stage.HOLE_READY)  # нора не исчезает и не перезапускается
            self.assertFalse(entrance.can_enter(x))
        self.assertTrue(entrance.can_enter(WALK_MAX_X))
        self.assertTrue(entrance.enter(WALK_MAX_X))


if __name__ == "__main__":
    unittest.main()
