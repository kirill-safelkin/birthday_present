"""Проверки тестового экрана анимации."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.graphics.animation import IDLE, REACT, TALK, WALK  # noqa: E402
from game.debug.animation_demo import FLOOR_RECT, AnimationDemo  # noqa: E402


def key_event(event_type: int, key: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key, mod=0, unicode="", scancode=scancode)


class AnimationDemoTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.demo = AnimationDemo()

    def tearDown(self) -> None:
        pygame.quit()

    def press(self, key: int, scancode: int = 0) -> None:
        self.demo.handle_event(key_event(pygame.KEYDOWN, key, scancode))

    def release(self, key: int, scancode: int = 0) -> None:
        self.demo.handle_event(key_event(pygame.KEYUP, key, scancode))

    def test_character_starts_idle_in_middle_of_floor(self) -> None:
        rect = self.demo.character.rect
        self.assertTrue(FLOOR_RECT.contains(rect))
        self.assertEqual(rect.center, FLOOR_RECT.center)
        self.assertEqual(self.demo.character.state, IDLE)

    def test_arrows_and_wasd_move_character(self) -> None:
        start_x = self.demo.character.x
        self.press(pygame.K_RIGHT)
        self.demo.update(0.5)
        self.release(pygame.K_RIGHT)
        self.assertGreater(self.demo.character.x, start_x)
        start_y = self.demo.character.y
        self.press(ord("ц"), pygame.KSCAN_W)  # W в русской раскладке
        self.demo.update(0.25)
        self.assertLess(self.demo.character.y, start_y)
        self.assertEqual(self.demo.character.state, WALK)

    def test_character_stays_on_floor(self) -> None:
        for key in (pygame.K_LEFT, pygame.K_UP, pygame.K_RIGHT, pygame.K_DOWN):
            with self.subTest(key=key):
                self.press(key)
                for _ in range(600):  # 10 секунд при 60 кадрах в секунду — дальше любого края
                    self.demo.update(1 / 60)
                    self.assertTrue(FLOOR_RECT.contains(self.demo.character.rect))
                self.release(key)
        self.assertEqual(self.demo.character.rect.bottomright, FLOOR_RECT.bottomright)

    def test_space_starts_reaction_and_t_toggles_talk(self) -> None:
        self.press(pygame.K_SPACE)
        self.assertEqual(self.demo.character.state, REACT)
        self.press(ord("е"), pygame.KSCAN_T)  # T в русской раскладке
        self.assertEqual(self.demo.character.state, TALK)
        self.press(pygame.K_t, pygame.KSCAN_T)
        self.assertEqual(self.demo.character.state, IDLE)

    def test_backspace_finishes_demo(self) -> None:
        self.assertFalse(self.demo.is_finished)
        self.press(pygame.K_BACKSPACE)
        self.assertTrue(self.demo.is_finished)

    def test_info_shows_position_direction_and_state(self) -> None:
        self.press(pygame.K_LEFT)
        x, y = self.demo.character.pixel_position
        lines = self.demo.info_lines()
        self.assertEqual(lines[0], f"координаты: {x}, {y}")
        self.assertIn("направление: влево", lines)
        self.assertIn("состояние: walk", lines)
        self.assertIn("кадр 1/4", lines)

    def test_texts_fit_on_screen(self) -> None:
        screen = pygame.Rect((0, 0), config.LOGICAL_SIZE)
        for image, rect in self.demo.labels:
            self.assertTrue(screen.contains(rect), rect)
            self.assertFalse(rect.colliderect(FLOOR_RECT), rect)
        # Самая длинная строка сведений — с направлением «вправо».
        self.press(pygame.K_RIGHT)
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.demo.draw(canvas)


if __name__ == "__main__":
    unittest.main()
