"""Проверки фейерверка: залпы, пределы числа частиц, независимость от частоты кадров, угасание."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.graphics import fireworks  # noqa: E402
from game.graphics.fireworks import (  # noqa: E402
    MAX_CONFETTI,
    MAX_FLASHES,
    MAX_ROCKETS,
    MAX_SPARKS,
    PALETTES,
    PEONY,
    RING,
    SALVO_GAP,
    SALVOS,
    STAR,
    WILLOW,
    FireworkShow,
)

WIDTH, HEIGHT = config.LOGICAL_SIZE
SKY = (34, 24, 64)


def run(show: FireworkShow, seconds: float, dt: float = 1 / 60) -> None:
    for _ in range(round(seconds / dt)):
        show.update(dt)


def run_to_first_burst(show: FireworkShow) -> None:
    """Ведёт время до самого первого разрыва (и ни на кадр дальше)."""
    for _ in range(60 * 5):
        show.update(1 / 60)
        if show.bursts_fired:
            return
    raise AssertionError("разрыва нет")


def caps_hold(show: FireworkShow) -> bool:
    return (len(show.sparks) <= MAX_SPARKS and len(show.confetti) <= MAX_CONFETTI
            and len(show.flashes) <= MAX_FLASHES and len(show.rockets) <= MAX_ROCKETS)


class SalvoPlanTest(unittest.TestCase):
    def test_salvos_are_short_sequences_of_different_colours(self) -> None:
        self.assertGreaterEqual(len(SALVOS), 3)
        for salvo in SALVOS:
            with self.subTest(first=salvo[0]):
                self.assertTrue(2 <= len(salvo) <= 4)  # короткий залп, а не поток
                delays = [launch.delay for launch in salvo]
                self.assertEqual(delays, sorted(delays))
                self.assertEqual(delays[0], 0.0)
                self.assertLessEqual(delays[-1], 2.0)
                self.assertGreaterEqual(len({launch.palette for launch in salvo}), 2)
        self.assertGreater(SALVO_GAP, 0.5)  # между залпами — пауза

    def test_bursts_stay_in_the_upper_sky_and_off_the_table_and_mosaic(self) -> None:
        kinds = set()
        for salvo in SALVOS:
            for launch in salvo:
                kinds.add(launch.kind)
                self.assertIn(launch.palette, PALETTES)
                if launch.second is not None:
                    self.assertIn(launch.second, PALETTES)
                self.assertLessEqual(launch.y, 56)  # в верхней части сцены
                self.assertGreaterEqual(launch.y, 24)
                self.assertGreater(abs(launch.x - WIDTH / 2), 40)  # над столом — фрагменты, а не разрывы
        self.assertGreaterEqual(kinds, {STAR, PEONY, RING, WILLOW})  # звёзды и другие разрывы


class LifecycleTest(unittest.TestCase):
    def test_nothing_happens_until_it_is_started(self) -> None:
        show = FireworkShow()
        self.assertTrue(show.idle)
        run(show, 5)
        self.assertEqual((show.particle_count, show.bursts_fired), (0, 0))

    def test_started_show_fires_salvo_after_salvo(self) -> None:
        show = FireworkShow()
        show.start()
        self.assertFalse(show.idle)
        run(show, 3.0)
        self.assertGreaterEqual(show.bursts_fired, 3)  # первый залп
        self.assertGreater(len(show.sparks), 20)
        run(show, 20)
        self.assertGreater(show.salvo_index, 3)  # залпы идут по кругу

    def test_start_twice_is_one_show(self) -> None:
        show = FireworkShow()
        show.start()
        run(show, 0.3)
        index, rockets = show.salvo_index, len(show.rockets)
        show.start()
        self.assertEqual((show.salvo_index, len(show.rockets)), (index, rockets))

    def test_stop_ends_new_bursts_and_the_sky_goes_quiet(self) -> None:
        show = FireworkShow()
        show.start()
        run(show, 3.0)
        show.stop()
        fired = show.bursts_fired
        self.assertFalse(show.running)
        run(show, 8.0)
        self.assertLessEqual(show.bursts_fired, fired + MAX_ROCKETS)  # только ракеты, уже взлетевшие
        self.assertEqual(show.particle_count, 0)  # всё догорело и упало само
        self.assertTrue(show.idle)

    def test_clear_removes_everything_at_once(self) -> None:
        show = FireworkShow()
        show.start()
        run(show, 3.0)
        self.assertGreater(show.particle_count, 0)
        show.clear()
        self.assertEqual(show.particle_count, 0)
        self.assertTrue(show.idle)

    def test_a_burst_has_a_flash_sparks_and_confetti(self) -> None:
        show = FireworkShow()
        show.start()
        run_to_first_burst(show)
        self.assertEqual(show.bursts_fired, 1)
        self.assertEqual(len(show.flashes), 1)
        self.assertGreaterEqual(len(show.sparks), 40)
        self.assertGreater(len(show.confetti), 0)
        run(show, show.FLASH_SECONDS + 0.05)
        self.assertEqual(len(show.flashes), 0)  # вспышка света короткая

    def test_sparks_spread_out_and_fade(self) -> None:
        show = FireworkShow()
        show.start()
        run_to_first_burst(show)
        spark = show.sparks[0]
        start = (spark.x, spark.y)
        first = show.spark_color(spark)
        run(show, 0.6)
        moved = ((spark.x - start[0]) ** 2 + (spark.y - start[1]) ** 2) ** 0.5
        self.assertGreater(moved, 4)
        self.assertGreater(sum(first), sum(show.spark_color(spark)) * 0.9)  # не светлеет к концу
        run(show, 3.0)
        self.assertNotIn(spark, show.sparks)  # искра исчезла


class LimitsTest(unittest.TestCase):
    def test_particle_lists_never_exceed_their_caps(self) -> None:
        show = FireworkShow()
        show.start()
        peak = 0
        for dt in (1 / 30, 1 / 60, 1 / 144):
            for _ in range(round(40 / dt)):
                show.update(dt)
                peak = max(peak, show.particle_count)
                self.assertTrue(caps_hold(show), show.particle_count)
        self.assertGreater(peak, 60)  # фейерверк настоящий, а не пустой
        self.assertLessEqual(peak, MAX_SPARKS + MAX_CONFETTI + MAX_FLASHES + MAX_ROCKETS)

    def test_a_full_sky_gives_a_burst_fewer_sparks_instead_of_growing(self) -> None:
        show = FireworkShow()
        show.start()
        for _ in range(3):  # лимит искр уже исчерпан
            show._burst(SALVOS[0][0])
        count = len(show.sparks)
        for _ in range(10):
            show._burst(SALVOS[0][1])
        self.assertLessEqual(len(show.sparks), MAX_SPARKS)
        self.assertGreaterEqual(len(show.sparks), count)
        self.assertLessEqual(len(show.flashes), MAX_FLASHES)
        self.assertLessEqual(len(show.confetti), MAX_CONFETTI)

    def test_old_particles_do_not_pile_up_over_a_long_run(self) -> None:
        show = FireworkShow()
        show.start()
        run(show, 120)
        self.assertTrue(caps_hold(show))
        show.stop()
        run(show, 10)
        self.assertEqual(show.particle_count, 0)

    def test_one_huge_frame_does_not_teleport_anything(self) -> None:
        show = FireworkShow()
        show.start()
        show.update(60.0)  # окно подвисло на минуту
        self.assertLess(show.clock, 1.0)  # время ограничено, как у всей игры
        self.assertLessEqual(show.bursts_fired, 4)
        for spark in show.sparks:
            self.assertTrue(-20 < spark.x < WIDTH + 20 and -20 < spark.y < HEIGHT + 20)

    def test_non_positive_dt_changes_nothing(self) -> None:
        show = FireworkShow()
        show.start()
        run(show, 1.5)
        before = (show.clock, len(show.sparks), show.bursts_fired)
        show.update(0)
        show.update(-1)
        self.assertEqual((show.clock, len(show.sparks), show.bursts_fired), before)


class FrameRateTest(unittest.TestCase):
    def test_the_same_seconds_give_the_same_show_at_any_frame_rate(self) -> None:
        results = {}
        for fps in (30, 60, 144):
            show = FireworkShow(seed=3)
            show.start()
            run(show, 6.0, 1 / fps)
            results[fps] = show
        reference = results[60]
        for fps, show in results.items():
            with self.subTest(fps=fps):
                self.assertEqual(show.bursts_fired, reference.bursts_fired)
                self.assertEqual(show.salvo_index, reference.salvo_index)
                self.assertAlmostEqual(len(show.sparks), len(reference.sparks), delta=len(reference.sparks) * 0.12 + 6)

    def test_same_seed_same_picture(self) -> None:
        shows = []
        for _ in range(2):
            show = FireworkShow(seed=11)
            show.start()
            run(show, 4.0)
            shows.append(show)
        canvases = []
        for show in shows:
            canvas = pygame.Surface(config.LOGICAL_SIZE)
            canvas.fill(SKY)
            show.draw(canvas)
            canvases.append(pygame.image.tobytes(canvas, "RGB"))
        self.assertEqual(canvases[0], canvases[1])


class DrawingTest(unittest.TestCase):
    def test_drawing_stays_on_the_canvas_and_never_whitens_the_screen(self) -> None:
        show = FireworkShow()
        show.start()
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        worst = 0.0
        for _ in range(60 * 30):
            show.update(1 / 60)
            canvas.fill(SKY)
            show.draw(canvas)
            untouched = pygame.mask.from_threshold(canvas, SKY, (1, 1, 1, 255)).count()  # пиксели цвета неба
            worst = max(worst, 1 - untouched / (WIDTH * HEIGHT))
        self.assertGreater(worst, 0.03)  # заметно: огни занимают часть неба
        self.assertLess(worst, 0.35)  # но экран никогда не заливается

    def test_flash_is_soft_never_opaque(self) -> None:
        self.assertLess(FireworkShow.FLASH_PEAK, 128)
        show = FireworkShow()
        show.start()
        run_to_first_burst(show)
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        canvas.fill(SKY)
        show.draw(canvas)
        corner = canvas.get_at((WIDTH - 1, HEIGHT - 1))[:3]
        self.assertEqual(corner, SKY)  # вспышка не достаёт до краёв экрана

    def test_idle_show_draws_nothing(self) -> None:
        show = FireworkShow()
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        canvas.fill(SKY)
        before = pygame.image.tobytes(canvas, "RGB")
        show.draw(canvas)
        self.assertEqual(pygame.image.tobytes(canvas, "RGB"), before)

    def test_module_constants_are_sane(self) -> None:
        self.assertLessEqual(fireworks.STEP, 1 / 30)
        for main, second in PALETTES.values():
            for color in (main, second):
                self.assertTrue(all(0 <= channel <= 255 for channel in color))


if __name__ == "__main__":
    unittest.main()
