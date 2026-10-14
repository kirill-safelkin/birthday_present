"""Проверки кладовой-лабиринта испытания тортов: раскладка, проходимость, столкновения."""

import os

# Тестам не нужно настоящее окно. Задаём до импорта Pygame (см. CLAUDE.md).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402
from collections import deque  # noqa: E402

from game.trials.cakes_maze import (  # noqa: E402
    MAZE_BOUNDS,
    MAZE_ROUTE,
    MAZE_START,
    MAZE_WALLS,
    STRAWBERRY_OBSTACLE,
    STRAWBERRY_POSITION,
    STRAWBERRY_REACH,
    maze_collision,
    strawberry_in_reach,
)
from game.world.collision import FOOT_SIZE, CollisionMap  # noqa: E402

GRID = 2  # шаг сетки при поиске пути, px


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
    def test_start_and_strawberry_are_fixed(self) -> None:
        self.assertEqual(MAZE_START, (58, 66))
        self.assertEqual(STRAWBERRY_POSITION, (292, 104))
        self.assertEqual(MAZE_ROUTE[0], MAZE_START)
        first = [(wall.kind, tuple(wall.rect)) for wall in MAZE_WALLS]
        self.assertEqual(len(first), 4)
        again = maze_collision()
        self.assertEqual([tuple(rect) for rect in again.obstacles],
                         [rect for _, rect in first] + [tuple(STRAWBERRY_OBSTACLE)])  # без случайностей

    def test_walls_stay_inside_the_pantry(self) -> None:
        for wall in MAZE_WALLS:
            self.assertTrue(MAZE_BOUNDS.contains(wall.rect), wall.kind)
        self.assertTrue(MAZE_BOUNDS.contains(STRAWBERRY_OBSTACLE))

    def test_start_is_free_and_far_from_the_strawberry(self) -> None:
        collision = maze_collision()
        self.assertTrue(collision.is_free(*MAZE_START))
        self.assertFalse(strawberry_in_reach(*MAZE_START))


class PassabilityTest(unittest.TestCase):
    def test_path_from_start_to_strawberry_exists(self) -> None:
        cells = reachable(maze_collision(), MAZE_START)
        self.assertTrue(any(strawberry_in_reach(x, y) for x, y in cells))

    def test_corridors_have_room_to_spare(self) -> None:
        # Даже с «ногами» заметно шире и выше настоящих путь всё равно есть.
        wide = maze_collision(foot_size=(FOOT_SIZE[0] + 12, FOOT_SIZE[1] + 12))
        cells = reachable(wide, MAZE_ROUTE[1])  # старт у самой стены — «широким ногам» там тесно
        self.assertTrue(any(strawberry_in_reach(x, y) for x, y in cells))

    def test_whole_pantry_is_one_connected_area(self) -> None:
        collision = maze_collision()
        self.assertEqual(reachable(collision, MAZE_START), free_cells(collision))  # нет недостижимых закутков

    def test_planned_route_is_walkable(self) -> None:
        collision = maze_collision()
        for (x1, y1), (x2, y2) in zip(MAZE_ROUTE, MAZE_ROUTE[1:]):
            self.assertTrue(x1 == x2 or y1 == y2, "маршрут идёт по прямым")
            steps = max(abs(x2 - x1), abs(y2 - y1))
            for k in range(steps + 1):
                x = x1 + (x2 - x1) * k / steps
                y = y1 + (y2 - y1) * k / steps
                self.assertTrue(collision.is_free(x, y), (x, y))
            self.assertEqual(collision.move(x1, y1, x2 - x1, y2 - y1), (x2, y2))  # ничто не мешает отрезку
        self.assertTrue(strawberry_in_reach(*MAZE_ROUTE[-1]))
        turns = len(MAZE_ROUTE) - 2
        self.assertGreaterEqual(turns, 4)  # несколько поворотов
        self.assertLessEqual(sum(abs(x2 - x1) + abs(y2 - y1) for (x1, y1), (x2, y2) in zip(MAZE_ROUTE, MAZE_ROUTE[1:])),
                             800)  # и путь короткий: около 10 секунд пешком


class CollisionTest(unittest.TestCase):
    def test_walls_cannot_be_crossed_even_with_a_huge_step(self) -> None:
        collision = maze_collision()
        for wall in MAZE_WALLS:
            rect = wall.rect
            y = (rect.top + rect.bottom) // 2  # по середине стеллажа, где прохода нет
            left = rect.left - 10
            if not collision.is_free(left, y):
                continue
            x, _ = collision.move(left, y, 400, 0)
            self.assertLessEqual(x + FOOT_SIZE[0] / 2, rect.left + 1e-6, wall.kind)
            right = rect.right + 10
            x, _ = collision.move(right, y, -400, 0)
            self.assertGreaterEqual(x - FOOT_SIZE[0] / 2, rect.right - 1e-6, wall.kind)

    def test_wall_ends_cannot_be_cut_vertically(self) -> None:
        collision = maze_collision()
        for wall in MAZE_WALLS:
            x = wall.rect.centerx
            if wall.rect.top == MAZE_BOUNDS.top:  # проход снизу — сверху вниз сквозь стеллаж нельзя
                _, y = collision.move(x, wall.rect.bottom + 20, 0, -300)
                self.assertGreaterEqual(y - FOOT_SIZE[1], wall.rect.bottom - 1e-6, wall.kind)
            else:  # проход сверху
                _, y = collision.move(x, wall.rect.top - 4, 0, 300)
                self.assertLessEqual(y, wall.rect.top + 1e-6, wall.kind)

    def test_strawberry_only_from_the_last_nook(self) -> None:
        collision = maze_collision()
        last_wall = MAZE_WALLS[-1].rect
        in_reach = [(x, y) for x, y in free_cells(collision) if strawberry_in_reach(x, y)]
        self.assertTrue(in_reach)
        for x, y in in_reach:
            self.assertGreaterEqual(x - FOOT_SIZE[0] / 2, last_wall.right)  # только за последним стеллажом
        # Ближайшая к ягоде точка по ту сторону стеллажа — не дотянуться.
        self.assertFalse(strawberry_in_reach(last_wall.left - FOOT_SIZE[0] / 2, STRAWBERRY_POSITION[1]))
        self.assertGreater(STRAWBERRY_REACH, 0)


if __name__ == "__main__":
    unittest.main()
