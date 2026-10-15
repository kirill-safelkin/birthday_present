"""Проверки кладовой испытания тортов: случайная раскладка, проходимость, столкновения, поиск пути."""

import os

# Тестам не нужно настоящее окно. Задаём до импорта Pygame (см. CLAUDE.md).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import random  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from collections import deque  # noqa: E402
from unittest import mock  # noqa: E402

import pygame  # noqa: E402

from game.trials import cakes_maze  # noqa: E402
from game.trials.cakes_maze import (  # noqa: E402
    ATTEMPTS,
    FALLBACK_ITEMS,
    MAZE_BOUNDS,
    MAZE_START,
    MIN_GAP_X,
    MIN_GAP_Y,
    SPAWN_ZONE,
    START_ZONE,
    STRAWBERRY_SPAWN,
    PantryItem,
    PantryLayout,
    gap,
    generate_layout,
    layout_problems,
    line_of_sight,
)
from game.world.collision import FOOT_SIZE, CollisionMap  # noqa: E402

GRID = 2  # шаг сетки при проверке проходимости, px (мельче сетки клубники)
SEEDS = range(40)
HALF = FOOT_SIZE[0] / 2


def free_cells(collision: CollisionMap) -> set[tuple[int, int]]:
    """Все точки сетки, где могут стоять ноги."""
    bounds = collision.bounds
    return {
        (x, y)
        for x in range(bounds.left, bounds.right + 1, GRID)
        for y in range(bounds.top, bounds.bottom + 1, GRID)
        if collision.is_free(x, y)
    }


def reachable(collision: CollisionMap, start: tuple[int, int]) -> set[tuple[int, int]]:
    """Поиск в ширину по свободным точкам сетки от start — куда можно дойти."""
    cells = free_cells(collision)
    start = (start[0] - start[0] % GRID, start[1] - start[1] % GRID)
    assert start in cells, start
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + GRID, y), (x - GRID, y), (x, y + GRID), (x, y - GRID)):
            if (nx, ny) in cells and (nx, ny) not in seen:
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


class LayoutTest(unittest.TestCase):
    def test_same_seed_same_layout_other_seeds_differ(self) -> None:
        first = [(i.kind, tuple(i.rect)) for i in generate_layout(7).items]
        again = [(i.kind, tuple(i.rect)) for i in generate_layout(7).items]
        self.assertEqual(first, again)  # воспроизводимо для тестов
        layouts = {tuple((i.kind, tuple(i.rect)) for i in generate_layout(seed).items) for seed in SEEDS}
        self.assertGreater(len(layouts), len(SEEDS) * 0.9)  # почти каждый раз своя комната

    def test_items_are_scattered_not_a_corridor(self) -> None:
        for seed in SEEDS:
            items = generate_layout(seed).items
            with self.subTest(seed=seed):
                rects = [item.rect for item in items]
                self.assertGreaterEqual(len(rects), cakes_maze.MIN_ITEMS)
                self.assertGreaterEqual(len({item.kind for item in items}), 3)  # стеллажи, стопки, коробки
                self.assertGreaterEqual(len({r.size for r in rects}), 4)  # разного размера
                xs = sorted(r.centerx for r in rects)
                steps = {b - a for a, b in zip(xs, xs[1:])}
                self.assertGreater(len(steps), 2)  # не через одинаковые промежутки
                self.assertGreater(len({r.top for r in rects}), 3)  # и не в одну линию
                thirds = {min(2, (r.centerx - MAZE_BOUNDS.left) * 3 // MAZE_BOUNDS.width) for r in rects}
                self.assertEqual(thirds, {0, 1, 2})
                self.assertTrue(any(r.width > r.height for r in rects) and any(r.height > r.width for r in rects))
                floor = sum(r.width * r.height for r in rects) / (MAZE_BOUNDS.width * MAZE_BOUNDS.height)
                self.assertTrue(cakes_maze.COVERAGE[0] <= floor <= cakes_maze.COVERAGE[1], floor)

    def test_items_stay_inside_do_not_overlap_and_keep_passages(self) -> None:
        for seed in SEEDS:
            rects = generate_layout(seed).obstacles
            with self.subTest(seed=seed):
                for index, rect in enumerate(rects):
                    self.assertTrue(MAZE_BOUNDS.contains(rect), rect)
                    for other in rects[index + 1:]:
                        self.assertFalse(rect.colliderect(other))
                        dx, dy = gap(rect, other)
                        self.assertTrue(dx >= MIN_GAP_X or dy >= MIN_GAP_Y, (rect, other))  # проход шире ног
                    self.assertGreaterEqual(rect.left - MAZE_BOUNDS.left, MIN_GAP_X)
                    self.assertGreaterEqual(MAZE_BOUNDS.right - rect.right, MIN_GAP_X)
                    self.assertGreaterEqual(MAZE_BOUNDS.bottom - rect.bottom, MIN_GAP_Y)
                    top = rect.top - MAZE_BOUNDS.top
                    self.assertTrue(top == 0 or top >= MIN_GAP_Y, rect)  # вплотную к стене или с проходом
        self.assertGreater(MIN_GAP_X, FOOT_SIZE[0])
        self.assertGreater(MIN_GAP_Y, FOOT_SIZE[1])

    def test_start_and_strawberry_spawn_are_never_covered(self) -> None:
        for seed in SEEDS:
            layout = generate_layout(seed)
            with self.subTest(seed=seed):
                for rect in layout.obstacles:
                    self.assertFalse(rect.colliderect(START_ZONE))
                    self.assertFalse(rect.colliderect(SPAWN_ZONE))
                collision = layout.collision()
                self.assertTrue(collision.is_free(*MAZE_START))
                self.assertTrue(collision.is_free(*STRAWBERRY_SPAWN))
                for decor in layout.decor:  # бумаги на полу не лежат на предметах
                    self.assertEqual(decor.rect.collidelist(layout.obstacles), -1)
        self.assertGreater(math.dist(MAZE_START, STRAWBERRY_SPAWN), 150)  # клубника далеко от входа

    def test_fallback_is_valid_and_used_instead_of_endless_retries(self) -> None:
        self.assertEqual(layout_problems(FALLBACK_ITEMS), [])
        layout = generate_layout(5, attempts=0)
        self.assertTrue(layout.fallback)
        self.assertEqual(layout.items, FALLBACK_ITEMS)
        broken = (PantryItem("bookcase", pygame.Rect(MAZE_START[0] - 10, MAZE_START[1] - 10, 40, 14)),)
        self.assertTrue(layout_problems(broken))  # на входе — негодная
        with mock.patch.object(cakes_maze, "_random_items", return_value=broken) as attempt:
            started = time.perf_counter()
            layout = generate_layout(1)
        self.assertTrue(layout.fallback)
        self.assertEqual(attempt.call_count, ATTEMPTS)  # ограниченное число попыток
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_generation_is_quick(self) -> None:
        slowest = 0.0
        for seed in range(200, 230):
            started = time.perf_counter()
            layout = generate_layout(seed)
            slowest = max(slowest, time.perf_counter() - started)
            self.assertEqual(layout_problems(layout.items), [])  # и запасная, и случайная — годные
        self.assertLess(slowest, 0.5)


class PassabilityTest(unittest.TestCase):
    def test_whole_pantry_is_one_connected_area(self) -> None:
        for seed in range(12):
            collision = generate_layout(seed).collision()
            with self.subTest(seed=seed):
                cells = reachable(collision, MAZE_START)
                self.assertEqual(cells, free_cells(collision))  # нет недостижимых закутков
                x, y = STRAWBERRY_SPAWN
                self.assertIn((x - x % GRID, y - y % GRID), cells)  # и клубника там же, где Алиса

    def test_passages_have_room_to_spare(self) -> None:
        # Даже с «ногами» заметно шире и выше настоящих вся комната связна: проходы не впритык.
        wide_feet = (FOOT_SIZE[0] + 6, FOOT_SIZE[1] + 6)
        for seed in range(12):
            wide = generate_layout(seed).collision(wide_feet)
            with self.subTest(seed=seed):
                self.assertEqual(reachable(wide, MAZE_START), free_cells(wide))

    def test_fallback_is_connected_too(self) -> None:
        collision = PantryLayout(FALLBACK_ITEMS).collision()
        self.assertEqual(reachable(collision, MAZE_START), free_cells(collision))


class CollisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.layouts = [generate_layout(seed) for seed in range(8)]

    def test_shelves_cannot_be_crossed_even_with_a_huge_step(self) -> None:
        for layout in self.layouts:
            collision = layout.collision()
            for rect in layout.obstacles:
                with self.subTest(seed=layout.seed, item=tuple(rect)):
                    y = rect.bottom - 1  # ноги на уровне основания предмета
                    if collision.is_free(rect.left - HALF - 1, y):
                        x, _ = collision.move(rect.left - HALF - 1, y, 400, 0)
                        self.assertLessEqual(x + HALF, rect.left + 1e-6)
                    if collision.is_free(rect.right + HALF + 1, y):
                        x, _ = collision.move(rect.right + HALF + 1, y, -400, 0)
                        self.assertGreaterEqual(x - HALF, rect.right - 1e-6)
                    x = rect.centerx
                    if collision.is_free(x, rect.top - 1):
                        _, y2 = collision.move(x, rect.top - 1, 0, 300)
                        self.assertLessEqual(y2, rect.top + 1e-6)
                    if collision.is_free(x, rect.bottom + FOOT_SIZE[1] + 1):
                        _, y2 = collision.move(x, rect.bottom + FOOT_SIZE[1] + 1, 0, -300)
                        self.assertGreaterEqual(y2 - FOOT_SIZE[1], rect.bottom - 1e-6)

    def test_sliding_along_a_shelf_and_out_of_corners(self) -> None:
        for layout in self.layouts:
            collision = layout.collision()
            for rect in layout.obstacles:
                below = (rect.centerx, rect.bottom + FOOT_SIZE[1])  # вплотную под предметом
                if not collision.is_free(*below):
                    continue
                with self.subTest(seed=layout.seed, item=tuple(rect)):
                    x, y = collision.move(*below, 5, -5)  # по диагонали вверх-вправо: скользит вдоль
                    self.assertAlmostEqual(y, below[1])
                    self.assertGreater(x, below[0])
                    corner = (rect.left - HALF, rect.top)  # в углу у предмета — выйти можно
                    if collision.is_free(*corner):
                        self.assertNotEqual(collision.move(*corner, -3, -3), corner)

    def test_room_bounds_hold(self) -> None:
        collision = self.layouts[0].collision()
        for dx, dy in ((-999, 0), (999, 0), (0, -999), (0, 999)):
            x, y = collision.move(*MAZE_START, dx, dy)
            self.assertTrue(collision.is_free(x, y))
            self.assertTrue(MAZE_BOUNDS.left + HALF - 1e-6 <= x <= MAZE_BOUNDS.right - HALF + 1e-6)
            self.assertTrue(MAZE_BOUNDS.top + FOOT_SIZE[1] - 1e-6 <= y <= MAZE_BOUNDS.bottom + 1e-6)


class NavGridTest(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = generate_layout(3)
        self.nav = self.layout.nav()
        self.collision = self.layout.collision()

    def assert_walkable(self, start, path) -> None:
        for a, b in zip([start, *path], path):
            steps = max(1, math.ceil(math.dist(a, b)))
            for k in range(steps + 1):
                x, y = a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps
                self.assertTrue(self.collision.is_free(x, y), (a, b, (x, y)))

    def test_grid_points_are_free_and_neighbours_are_close(self) -> None:
        for cell in self.nav.free:
            self.assertTrue(self.collision.is_free(*self.nav.point(cell)))
            for nxt, step in self.nav.neighbours(cell):
                self.assertIn(nxt, self.nav.free)
                self.assertLessEqual(math.dist(cell, nxt), math.sqrt(2) + 1e-9)
                self.assertAlmostEqual(step, math.dist(cell, nxt))

    def test_paths_between_random_points_go_around_shelves(self) -> None:
        rng = random.Random(4)
        cells = sorted(self.nav.free)
        for _ in range(40):
            start, goal = self.nav.point(rng.choice(cells)), self.nav.point(rng.choice(cells))
            path = self.nav.find_path(start, goal)
            self.assertIsNotNone(path)
            self.assertEqual(path[-1], goal)
            self.assert_walkable(start, path)

    def test_blocked_goal_has_no_path_and_search_is_bounded(self) -> None:
        inside = self.layout.obstacles[0].center
        self.assertIsNone(self.nav.find_path(MAZE_START, inside))
        self.assertIsNone(self.nav.cell(*inside))
        far = self.nav.point(max(self.nav.free))
        self.assertIsNone(self.nav.find_path(MAZE_START, far, max_expanded=3))  # предел работы соблюдается

    def test_line_of_sight_is_blocked_by_shelves(self) -> None:
        rect = self.layout.obstacles[0]
        self.assertFalse(line_of_sight([rect], (rect.left - 5, rect.centery), (rect.right + 5, rect.centery)))
        self.assertTrue(line_of_sight([rect], (rect.left, rect.top - 3), (rect.right, rect.top - 3)))
        self.assertTrue(line_of_sight([rect], (rect.left, rect.top), (rect.right, rect.top)))  # касание края


if __name__ == "__main__":
    unittest.main()
