"""Проверки столкновений: границы, препятствия, скольжение вдоль стен, большой dt."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import unittest  # noqa: E402

import pygame  # noqa: E402

from game.graphics.animation import Animation, AnimationSet  # noqa: E402
from game.world.character import Character  # noqa: E402
from game.world.collision import CollisionMap  # noqa: E402

BOUNDS = pygame.Rect(0, 0, 200, 100)
WALL = pygame.Rect(100, 20, 10, 60)  # вертикальная стена 10×60


def make_map() -> CollisionMap:
    return CollisionMap(BOUNDS, [WALL], foot_size=(12, 6))


class CollisionMapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.map = make_map()

    def test_free_movement(self) -> None:
        self.assertEqual(self.map.move(50, 50, 10, -5), (60, 45))

    def test_bounds_keep_feet_inside(self) -> None:
        self.assertEqual(self.map.move(50, 50, -500, 0), (6, 50))
        self.assertEqual(self.map.move(50, 10, 500, 0), (194, 10))  # выше стены
        self.assertEqual(self.map.move(50, 50, 0, -500), (50, 6))
        self.assertEqual(self.map.move(50, 50, 0, 500), (50, 100))

    def test_wall_stops_at_contact(self) -> None:
        self.assertEqual(self.map.move(80, 50, 30, 0), (94, 50))  # ноги касаются стены слева
        self.assertEqual(self.map.move(130, 50, -30, 0), (116, 50))
        self.assertEqual(self.map.move(105, 10, 0, 30), (105, 20))  # сверху
        self.assertEqual(self.map.move(105, 95, 0, -30), (105, 86))  # снизу: верх ног на нижнем крае
        self.assertTrue(self.map.is_free(94, 50))
        self.assertFalse(self.map.is_free(95, 50))

    def test_no_tunnelling_with_huge_step(self) -> None:
        # За один шаг персонаж «перелетел» бы стену целиком — но упирается в неё.
        self.assertEqual(self.map.move(50, 50, 1000, 0), (94, 50))

    def test_diagonal_slides_along_the_wall(self) -> None:
        x, y = self.map.move(94, 50, 5, 5)
        self.assertEqual((x, y), (94, 55))  # по x упёрся, по y идёт дальше

    def test_sliding_along_flush_edge(self) -> None:
        # Стоит вплотную над стеной (ноги касаются её верха): идти вдоль можно.
        self.assertEqual(self.map.move(105, 20, 10, 0), (115, 20))

    def test_can_leave_an_overlapping_position(self) -> None:
        # Если ноги почему-то уже в препятствии, выйти из него можно, войти глубже — нет.
        self.assertEqual(self.map.move(102, 50, -10, 0), (92, 50))

    def test_is_free(self) -> None:
        self.assertTrue(self.map.is_free(50, 50))
        self.assertFalse(self.map.is_free(3, 50))  # ноги за левой границей
        self.assertFalse(self.map.is_free(50, 3))


class CharacterWithColliderTest(unittest.TestCase):
    def setUp(self) -> None:
        frame = pygame.Surface((8, 8))
        self.character = Character("Тест", AnimationSet(Animation([frame], 1)), position=(50, 50), speed=60)
        self.character.collider = make_map().move

    def press(self, key: int) -> None:
        self.character.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))

    def test_without_collider_moves_freely(self) -> None:
        free = Character("Свободный", AnimationSet(Animation([pygame.Surface((8, 8))], 1)), position=(50, 50))
        free.move(1, 0)
        free.update(10.0)
        self.assertEqual(free.x, 50 + 10 * free.speed)  # тест анимации и другие сцены без столкновений

    def test_collider_stops_character_at_wall(self) -> None:
        self.press(pygame.K_RIGHT)
        self.character.update(5.0)
        self.assertEqual(self.character.x, 94)
        self.assertEqual(self.character.state, "walk")  # клавиша зажата — упирается, а не исчезает

    def test_diagonal_speed_is_the_same_with_collider(self) -> None:
        self.press(pygame.K_LEFT)
        self.press(pygame.K_UP)
        self.character.update(0.5)
        self.assertAlmostEqual(math.dist((50, 50), (self.character.x, self.character.y)), 30)

    def test_result_does_not_depend_on_frame_rate(self) -> None:
        results = []
        for dt in (1 / 144, 1 / 60, 1 / 30, 0.1, 1.0):
            character = Character("Тест", AnimationSet(Animation([pygame.Surface((8, 8))], 1)), position=(50, 30))
            character.collider = make_map().move
            character.move(1, 1)
            for _ in range(round(2.0 / dt)):
                character.update(dt)
            results.append((round(character.x, 6), round(character.y, 6)))
        # Упёрся в стену, проскользил вниз, обогнул её нижний угол и дошёл до границы — при любом dt
        # в пределах пикселя (персонаж «не телепортируется» и не застревает у угла).
        reference = results[0]
        self.assertGreater(reference[0], 110)
        self.assertEqual(reference[1], 100)
        for x, y in results:
            self.assertAlmostEqual(x, reference[0], delta=1.0)
            self.assertEqual(y, 100)

    def test_release_controls_stops_and_forgets_keys(self) -> None:
        self.press(pygame.K_RIGHT)
        self.character.release_controls()
        self.assertFalse(self.character.is_moving)
        self.character.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0, unicode="", scancode=0))
        self.character.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_UP, mod=0, unicode="", scancode=0))
        self.assertFalse(self.character.is_moving)  # «зависшая» стрелка вправо забыта


if __name__ == "__main__":
    unittest.main()
