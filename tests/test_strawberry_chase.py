"""Проверки клубники в кладовой: скорость, путь в обход стеллажей, остановки с репликами, поимка."""

import os

# Тестам не нужно настоящее окно. Задаём до импорта Pygame (см. CLAUDE.md).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import random  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import pygame  # noqa: E402

from game.story.cakes_dialogue import STRAWBERRY_LINES  # noqa: E402
from game.trials.cakes_maze import MAZE_BOUNDS, MAZE_START, STRAWBERRY_SPAWN, generate_layout  # noqa: E402
from game.trials.cakes_scene import WALK_SPEED  # noqa: E402
from game.trials.strawberry_chase import (  # noqa: E402
    CAUGHT,
    MIN_TRIP,
    RUN_SECONDS,
    RUNNING,
    SAFE_MARGIN,
    SPOOK_COOLDOWN,
    SPOOK_RADIUS,
    STOP_POSTPONE,
    TALK_SECONDS,
    TALKING,
    LineDeck,
    StrawberryChase,
)
from game.world.collision import FOOT_SIZE  # noqa: E402

DT = 1 / 60
FAR = MAZE_START  # Алиса стоит у двери — далеко от клубники


def make(seed: int = 3, pursuer=FAR, layout_seed: int = 3) -> StrawberryChase:
    return StrawberryChase(generate_layout(layout_seed), WALK_SPEED, random.Random(seed), STRAWBERRY_LINES,
                           pursuer=pursuer)


def run(chase: StrawberryChase, seconds: float, dt: float = DT, pursuer=None, each=None) -> None:
    for _ in range(round(seconds / dt)):
        before = chase.position
        chase.update(dt, pursuer)
        if each is not None:
            each(before, chase.position)


class MovementTest(unittest.TestCase):
    def test_speed_is_alices_and_movement_is_continuous(self) -> None:
        chase = make()
        self.assertEqual(chase.speed, WALK_SPEED)  # та же скорость, что у Алисы в кладовой
        running_time, moved = 0.0, 0.0

        def check(before, after):
            nonlocal running_time, moved
            step = math.dist(before, after)
            self.assertLessEqual(step, WALK_SPEED * DT + 1e-6)  # не быстрее и без телепортов
            if chase.state == RUNNING and step > 0:
                running_time += DT
                moved += step

        run(chase, 30, each=check)
        self.assertGreater(running_time, 10)
        self.assertGreater(moved, 0.9 * WALK_SPEED * running_time)  # бегает в полную скорость, не дрожит

    def test_never_inside_shelves_and_never_outside_the_room(self) -> None:
        for seed in range(6):
            chase = make(seed, layout_seed=seed)
            alice = [*MAZE_START]

            def check(before, after, chase=chase):
                self.assertTrue(chase.collision.is_free(*after), after)
                self.assertLessEqual(math.dist(before, after), WALK_SPEED * DT + 1e-6)

            for _ in range(60):  # Алиса бегает туда-сюда, клубника — от неё
                alice[0] = 60 + (alice[0] + 7) % 240
                run(chase, 0.5, pursuer=tuple(alice), each=check)
            x, y = chase.position
            self.assertTrue(MAZE_BOUNDS.left <= x - FOOT_SIZE[0] / 2 and x + FOOT_SIZE[0] / 2 <= MAZE_BOUNDS.right)
            self.assertTrue(MAZE_BOUNDS.top <= y - FOOT_SIZE[1] and y <= MAZE_BOUNDS.bottom)

    def test_large_dt_does_not_tunnel_and_keeps_the_speed(self) -> None:
        chase = make()
        real_move = chase.collision.move
        steps = []

        def recorded(x, y, dx, dy):
            result = real_move(x, y, dx, dy)
            steps.append(((x, y), result, math.hypot(dx, dy)))
            return result

        with mock.patch.object(chase.collision, "move", side_effect=recorded):
            for dt in (0.5, 2.0, 5.0, 0.25):
                before, travelled = chase.position, chase.travelled
                chase.update(dt, FAR)
                self.assertTrue(chase.collision.is_free(*chase.position))
                self.assertLessEqual(chase.travelled - travelled, WALK_SPEED * dt + 1e-6)
                self.assertLessEqual(math.dist(before, chase.position), WALK_SPEED * dt + 1e-6)
        # Даже за 5 секунд одним шагом клубника шла через столкновения отрезками не длиннее пикселя
        # и ни в одной промежуточной точке не оказалась внутри предмета.
        self.assertGreater(len(steps), 200)
        for start, end, length in steps:
            self.assertLessEqual(length, 1.0 + 1e-9)
            self.assertTrue(chase.collision.is_free(*end), end)
            self.assertLessEqual(math.dist(start, end), 1.0 + 1e-9)

    def test_frame_rate_does_not_change_the_pace(self) -> None:
        travelled = []
        for dt in (1 / 30, 1 / 60, 1 / 144):
            chase = make()
            chase.run_left = 99  # без остановок: сравниваем только бег
            run(chase, 2.0, dt, FAR)
            travelled.append(chase.travelled)
        self.assertTrue(max(travelled) - min(travelled) < 1.5, travelled)
        self.assertAlmostEqual(travelled[0], WALK_SPEED * 2.0, delta=2.0)

    def test_it_really_changes_direction(self) -> None:
        chase = make()
        headings = set()

        def check(before, after):
            if math.dist(before, after) > 0.5:
                angle = math.atan2(after[1] - before[1], after[0] - before[0])
                headings.add(round(angle / (math.pi / 4)) % 8)  # восемь секторов

        run(chase, 40, pursuer=(160, 110), each=check)
        self.assertGreaterEqual(len(headings), 6)
        self.assertGreater(chase.routes, 8)


class TargetTest(unittest.TestCase):
    def test_targets_are_reachable_floor_points_and_paths_go_around_shelves(self) -> None:
        chase = make()
        seen = 0
        for _ in range(40):
            self.assertTrue(chase._choose_target())
            target = chase.target
            self.assertIn(chase.nav.cell(*target), chase.nav.free)
            self.assertTrue(chase.collision.is_free(*target))
            for a, b in zip([chase.position, *chase.path], chase.path):
                self.assertTrue(chase.nav.segment_clear(a, b), (a, b))
            self.assertEqual(chase.path[-1], target)
            seen += 1
            chase.x, chase.y = target  # как будто добежала
        self.assertEqual(seen, 40)

    def test_targets_are_away_from_alice_but_not_always_the_same(self) -> None:
        chase = make()
        hunter = chase.nav.cell(*FAR)
        theirs, _ = chase.nav.steps_from(hunter)
        targets = set()
        for _ in range(20):
            chase._choose_target()
            mine, _ = chase.nav.steps_from(chase.nav.cell(*chase.position))
            cell = chase.nav.cell(*chase.target)
            self.assertLess(mine[cell] + SAFE_MARGIN, theirs[cell])  # успевает туда раньше Алисы
            trip = sum(math.dist(a, b) for a, b in zip([chase.position, *chase.path], chase.path))
            self.assertGreaterEqual(trip, MIN_TRIP - chase.nav.step)  # заметный пробег, а не шаг на месте
            targets.add(chase.target)
        self.assertGreater(len(targets), 10)

    def test_without_alice_targets_are_random_points(self) -> None:
        chase = make(pursuer=None)
        chase.pursuer = None
        points = set()
        for _ in range(15):
            self.assertTrue(chase._choose_target())
            points.add(chase.target)
        self.assertGreater(len(points), 10)

    def test_unreachable_target_is_replaced_and_no_target_means_a_stop(self) -> None:
        chase = make(pursuer=None)
        chase.pursuer = None
        real = chase.nav.find_path
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args)
            return None if len(calls) <= 2 else real(*args, **kwargs)

        with mock.patch.object(chase.nav, "find_path", side_effect=flaky):
            self.assertTrue(chase._choose_target())  # первые две цели недоступны — взята третья
        self.assertGreaterEqual(len(calls), 3)
        with mock.patch.object(chase.nav, "find_path", return_value=None):
            self.assertFalse(chase._choose_target())
            chase.path = []
            chase.run_left = 10
            started = time.perf_counter()
            chase.update(0.5)  # некуда бежать — безопасная остановка, а не зависание
            self.assertLess(time.perf_counter() - started, 0.5)
        self.assertEqual(chase.state, TALKING)
        run(chase, 3.0, pursuer=None)
        self.assertEqual(chase.state, RUNNING)  # поговорила и снова выбрала цель
        self.assertTrue(chase.path)

    def test_route_is_rebuilt_when_blocked_or_target_changes(self) -> None:
        chase = make()
        chase.run_left = 99
        routes = chase.routes
        first = chase.path[0]
        # Посреди пути вдруг «вырос» предмет: путь перегорожен — клубника прокладывает новый.
        x, y = chase.position
        tx, ty = first
        block = pygame.Rect(0, 0, 8, 8)
        block.center = (round(x + (tx - x) * 0.5), round(y + (ty - y) * 0.5) - 2)
        if not block.collidepoint(x, y) and not block.collidepoint(tx, ty):
            chase.collision.obstacles.append(block)
            run(chase, 1.0, pursuer=FAR)
            self.assertGreater(chase.routes, routes)
            self.assertTrue(chase.collision.is_free(*chase.position))
            chase.collision.obstacles.pop()
        routes = chase.routes
        chase.x, chase.y = chase.path[-1] if chase.path else chase.position
        chase.path = [chase.position]
        run(chase, 0.2, pursuer=FAR)  # добежала до конца пути — новая цель
        self.assertGreater(chase.routes, routes)

    def test_spooked_by_alice_but_not_every_frame(self) -> None:
        chase = make()
        chase.run_left = 99
        run(chase, 0.5, pursuer=FAR)
        routes = chase.routes
        near = (chase.x - SPOOK_RADIUS / 2, chase.y)
        run(chase, DT, pursuer=near)
        self.assertEqual(chase.routes, routes + 1)  # Алиса рядом — сразу новая цель
        changes = 0
        for _ in range(round(SPOOK_COOLDOWN / DT) - 2):
            before = chase.routes
            chase.update(DT, (chase.x - SPOOK_RADIUS / 2, chase.y))
            changes += chase.routes - before
        self.assertLessEqual(changes, 2)  # а не каждый кадр (сменить цель можно, только добежав)

    def test_update_never_loops_forever(self) -> None:
        chase = make()
        chase._cells = [chase.nav.cell(*chase.position)]  # пол «сжался» до одной точки: цели нет
        chase.path = []
        started = time.perf_counter()
        for _ in range(30):
            chase.update(1.0, FAR)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertGreater(chase.stops, 1)  # просто останавливается и говорит

    def test_one_frame_is_cheap(self) -> None:
        chase = make()
        slowest = 0.0
        alice = [*MAZE_START]
        for k in range(600):
            alice[0] = 60 + (k * 0.8) % 200
            started = time.perf_counter()
            chase.update(DT, tuple(alice))
            slowest = max(slowest, time.perf_counter() - started)
        self.assertLess(slowest, 0.05)


class StopTest(unittest.TestCase):
    def test_stops_regularly_says_something_and_stands_still(self) -> None:
        chase = make()
        stops, talking_steps, starts = [], 0, []
        time_now = 0.0
        last_state = chase.state
        for _ in range(round(40 / DT)):
            before = chase.position
            chase.update(DT, FAR)
            time_now += DT
            if chase.state == TALKING:
                talking_steps += 1
                if last_state == TALKING:  # весь кадр — в остановке: стоит на месте
                    self.assertEqual(chase.position, before)
                    self.assertEqual(chase.velocity, (0.0, 0.0))
                self.assertIn(chase.line, STRAWBERRY_LINES)
                if last_state != TALKING:
                    starts.append(time_now)
            elif last_state == TALKING:
                stops.append(time_now)
                self.assertIsNone(chase.line)
            last_state = chase.state
        self.assertGreaterEqual(len(starts), 5)
        self.assertLess(starts[0], 2.0)  # первая реплика — вскоре после входа
        gaps = [b - a for a, b in zip(stops, starts[1:])]
        self.assertTrue(all(RUN_SECONDS[0] - 0.05 <= g <= RUN_SECONDS[1] + STOP_POSTPONE + 0.05 for g in gaps), gaps)
        self.assertGreater(len(set(round(g, 1) for g in gaps)), 1)  # непредсказуемо, а не по часам
        durations = [b - a for a, b in zip(starts, stops)]
        self.assertTrue(all(TALK_SECONDS[0] - 0.05 <= d <= 3.0 for d in durations), durations)

    def test_resumes_running_after_the_line(self) -> None:
        chase = make()
        run(chase, 2.5, pursuer=FAR)
        while chase.state != TALKING:
            chase.update(DT, FAR)
        stopped_at = chase.position
        while chase.state == TALKING:
            chase.update(DT, FAR)
        run(chase, 0.5, pursuer=FAR)
        self.assertGreater(math.dist(stopped_at, chase.position), 10)  # E нажимать не нужно

    def test_close_alice_delays_a_stop_but_not_forever(self) -> None:
        chase = make()
        run(chase, 2.5, pursuer=FAR)
        while chase.state == TALKING:
            chase.update(DT, FAR)
        elapsed = 0.0
        while chase.state != TALKING:
            chase.update(DT, (chase.x - 20, chase.y))  # Алиса буквально на пятках
            elapsed += DT
            self.assertLess(elapsed, RUN_SECONDS[1] + STOP_POSTPONE + 0.1)
        self.assertTrue(chase.line)

    def test_lines_vary_and_never_repeat_back_to_back(self) -> None:
        deck = LineDeck(STRAWBERRY_LINES, random.Random(9))
        said = [deck.next() for _ in range(len(STRAWBERRY_LINES) * 4)]
        for a, b in zip(said, said[1:]):
            self.assertNotEqual(a, b)
        for start in range(0, len(said), len(STRAWBERRY_LINES)):  # каждая колода — все реплики
            self.assertEqual(sorted(said[start:start + len(STRAWBERRY_LINES)]), sorted(STRAWBERRY_LINES))
        self.assertGreaterEqual(len(STRAWBERRY_LINES), 8)
        self.assertEqual(LineDeck(["одна"], random.Random(1)).next(), "одна")
        for seed in range(300):  # и на стыке колод — ни разу подряд
            deck = LineDeck(STRAWBERRY_LINES, random.Random(seed))
            said = [deck.next() for _ in range(len(STRAWBERRY_LINES) * 3)]
            self.assertFalse(any(a == b for a, b in zip(said, said[1:])), seed)

    def test_same_seed_same_chase(self) -> None:
        traces = []
        for _ in range(2):
            chase = make(seed=11)
            trace = []
            run(chase, 12, pursuer=(150, 120), each=lambda before, after, trace=trace: trace.append(after))
            traces.append((trace, chase.lines_said))
        self.assertEqual(traces[0], traces[1])
        other = make(seed=12)
        run(other, 12, pursuer=(150, 120))
        self.assertNotEqual(other.lines_said + [other.position], traces[0][1] + [traces[0][0][-1]])


class CatchTest(unittest.TestCase):
    def test_caught_once_then_nothing_happens(self) -> None:
        chase = make()
        run(chase, 1.0, pursuer=FAR)
        self.assertTrue(chase.catch())
        self.assertFalse(chase.catch())
        frozen = (chase.position, chase.routes, chase.stops, list(chase.lines_said))
        run(chase, 20, pursuer=FAR)
        self.assertEqual(chase.state, CAUGHT)
        self.assertEqual((chase.position, chase.routes, chase.stops, chase.lines_said), frozen)
        self.assertIsNone(chase.line)
        self.assertEqual(chase.velocity, (0.0, 0.0))

    def test_caught_while_talking_drops_the_line(self) -> None:
        chase = make()
        while chase.state != TALKING:
            chase.update(DT, FAR)
        self.assertTrue(chase.line)
        chase.catch()
        self.assertIsNone(chase.line)
        self.assertEqual(chase.talk_left, 0.0)

    def test_spawns_where_it_was_told_and_never_inside_a_shelf(self) -> None:
        chase = make()
        self.assertEqual(make().position, (float(STRAWBERRY_SPAWN[0]), float(STRAWBERRY_SPAWN[1])))
        with self.assertRaises(ValueError):
            StrawberryChase(chase.layout, WALK_SPEED, random.Random(1), STRAWBERRY_LINES,
                            start=chase.layout.obstacles[0].center)
        with self.assertRaises(ValueError):
            StrawberryChase(chase.layout, 0, random.Random(1), STRAWBERRY_LINES)
        with self.assertRaises(ValueError):
            chase.update(-1)


if __name__ == "__main__":
    unittest.main()
