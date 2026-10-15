"""Проверки масштабирования холста и переключения режимов окна."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.display import Display, fit_viewport  # noqa: E402

LOGICAL = (320, 180)


class FitViewportTest(unittest.TestCase):
    def test_exact_multiple_fills_window(self) -> None:
        self.assertEqual(fit_viewport((960, 540), LOGICAL, True), pygame.Rect(0, 0, 960, 540))

    def test_16_10_monitor_gets_bars_top_and_bottom(self) -> None:
        self.assertEqual(fit_viewport((1920, 1200), LOGICAL, True), pygame.Rect(0, 60, 1920, 1080))

    def test_ultrawide_monitor_gets_bars_left_and_right(self) -> None:
        self.assertEqual(fit_viewport((2560, 1080), LOGICAL, True), pygame.Rect(320, 0, 1920, 1080))

    def test_integer_scaling_rounds_scale_down(self) -> None:
        # 1366×768: помещается масштаб ≈4,27, целый — ×4.
        self.assertEqual(fit_viewport((1366, 768), LOGICAL, True), pygame.Rect(43, 24, 1280, 720))

    def test_fractional_scaling_uses_all_available_height(self) -> None:
        self.assertEqual(fit_viewport((1366, 768), LOGICAL, False), pygame.Rect(0, 0, 1365, 768))

    def test_window_smaller_than_canvas_scales_down(self) -> None:
        self.assertEqual(fit_viewport((160, 120), LOGICAL, True), pygame.Rect(0, 15, 160, 90))

    def test_zero_size_window_gives_empty_viewport(self) -> None:
        self.assertEqual(fit_viewport((0, 540), LOGICAL, True).size, (0, 0))

    def test_any_window_keeps_aspect_and_center(self) -> None:
        for integer_scaling in (True, False):
            for width in range(1, 2600, 37):
                for height in range(1, 1500, 41):
                    rect = fit_viewport((width, height), LOGICAL, integer_scaling)
                    with self.subTest(window=(width, height), integer=integer_scaling):
                        self.assertTrue(pygame.Rect(0, 0, width, height).contains(rect))
                        # 16:9 с точностью до округления каждой стороны на полпикселя.
                        self.assertLessEqual(abs(rect.width * 9 - rect.height * 16), 12)
                        self.assertLessEqual(abs(rect.left - (width - rect.right)), 1)
                        self.assertLessEqual(abs(rect.top - (height - rect.bottom)), 1)


class DisplayTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        self.display = Display()

    def tearDown(self) -> None:
        pygame.quit()

    def test_starts_windowed_with_logical_canvas(self) -> None:
        self.assertEqual(self.display.canvas.get_size(), config.LOGICAL_SIZE)
        self.assertEqual(pygame.display.get_surface().get_size(), config.WINDOW_SIZE)
        self.assertFalse(self.display.is_fullscreen)

    def test_present_scales_without_smoothing(self) -> None:
        canvas = self.display.canvas
        canvas.fill((0, 0, 0))
        canvas.set_at((0, 0), (255, 0, 0))
        canvas.set_at((1, 0), (0, 0, 255))
        self.display.present()

        # Окно 960×540 — масштаб ×3: каждый пиксель холста становится квадратом 3×3
        # ровно того же цвета, без промежуточных оттенков на границе.
        screen = pygame.display.get_surface()
        for x in range(6):
            for y in range(3):
                expected = (255, 0, 0) if x < 3 else (0, 0, 255)
                self.assertEqual(tuple(screen.get_at((x, y)))[:3], expected, (x, y))
        self.assertEqual(tuple(screen.get_at((0, 3)))[:3], (0, 0, 0))

    def test_opaque_backdrop_replaces_only_the_covered_canvas_rows(self) -> None:
        # Подробный фон закрывает середину холста: её холст не увеличивается, а полосы сверху и снизу — как обычно.
        canvas = self.display.canvas
        for factor_size in (config.WINDOW_SIZE, (1920, 1200)):
            pygame.display.set_mode(factor_size, pygame.RESIZABLE)
            canvas.fill((10, 20, 30))
            canvas.fill((200, 100, 50), (0, 0, 320, 12))
            canvas.fill((50, 100, 200), (0, 168, 320, 12))
            backdrop = pygame.Surface((640, 312))
            backdrop.fill((1, 2, 3))
            backdrop.fill((250, 250, 0), (0, 0, 2, 2))
            self.display.hires.sprite(backdrop, pygame.Rect(0, 12, 320, 156), opaque=True)
            self.assertEqual(self.display.hires.backdrop_rows(), (12, 168))
            self.display.present()
            screen = pygame.display.get_surface()
            viewport = self.display.transform().viewport
            scale = viewport.width // 320
            self.assertEqual(tuple(screen.get_at((viewport.left + 5, viewport.top + 5)))[:3], (200, 100, 50))
            self.assertEqual(tuple(screen.get_at((viewport.left + 5, viewport.top + 179 * scale)))[:3], (50, 100, 200))
            self.assertEqual(tuple(screen.get_at((viewport.left + 3 * scale, viewport.top + 100 * scale)))[:3], (1, 2, 3))
            # Слева вверху фона светлая клетка 2×2 пикселя картинки (одна клетка холста); соседняя — тёмная.
            self.assertEqual(tuple(screen.get_at((viewport.left + 1, viewport.top + 12 * scale + 1)))[:3], (250, 250, 0))
            self.assertEqual(tuple(screen.get_at((viewport.left + scale + 1, viewport.top + 12 * scale + 1)))[:3], (1, 2, 3))

    def test_backdrop_rows_only_for_a_full_width_opaque_first_sprite(self) -> None:
        layer = self.display.hires
        picture = pygame.Surface((640, 312))
        self.assertIsNone(layer.backdrop_rows())
        layer.sprite(picture, pygame.Rect(0, 12, 320, 156))
        self.assertIsNone(layer.backdrop_rows())  # непрозрачный флаг не задан
        layer.clear()
        layer.sprite(picture, pygame.Rect(10, 12, 300, 156), opaque=True)
        self.assertIsNone(layer.backdrop_rows())  # не во всю ширину
        layer.clear()
        layer.fill((0, 0, 0), pygame.Rect(0, 0, 5, 5))
        layer.sprite(picture, pygame.Rect(0, 12, 320, 156), opaque=True)
        self.assertIsNone(layer.backdrop_rows())  # фон не первый: под ним что-то уже нарисовано
        layer.clear()

    def test_present_adds_bars_for_non_16_9_window(self) -> None:
        # 1200×500: целый масштаб ×2, картинка 640×360 с полями со всех сторон.
        pygame.display.set_mode((1200, 500), pygame.RESIZABLE)
        screen = pygame.display.get_surface()
        screen.fill((255, 255, 255))  # «мусор» от прошлого кадра должен закраситься
        self.display.canvas.fill((200, 100, 50))
        self.display.present()

        content = (200, 100, 50)
        expected = {
            (600, 69): config.LETTERBOX_COLOR, (600, 70): content,
            (600, 429): content, (600, 430): config.LETTERBOX_COLOR,
            (279, 250): config.LETTERBOX_COLOR, (280, 250): content,
            (919, 250): content, (920, 250): config.LETTERBOX_COLOR,
            (0, 0): config.LETTERBOX_COLOR, (1199, 499): config.LETTERBOX_COLOR,
        }
        for point, color in expected.items():
            self.assertEqual(tuple(screen.get_at(point))[:3], color, point)

    def test_present_survives_unusual_window_sizes(self) -> None:
        for size in [(1, 1), (100, 30), (2000, 50), (321, 181), (3840, 2160)]:
            with self.subTest(size=size):
                pygame.display.set_mode(size, pygame.RESIZABLE)
                self.display.present()

    def test_toggle_fullscreen_uses_desktop_size(self) -> None:
        self.display.toggle_fullscreen()
        pygame.event.pump()  # новый размер окна Pygame получает при обработке событий
        screen = pygame.display.get_surface()
        self.assertTrue(self.display.is_fullscreen)
        self.assertTrue(screen.get_flags() & pygame.FULLSCREEN)
        self.assertEqual(screen.get_size(), pygame.display.get_desktop_sizes()[0])
        self.display.present()

        self.display.toggle_fullscreen()
        pygame.event.pump()
        self.assertFalse(self.display.is_fullscreen)
        self.assertFalse(pygame.display.get_surface().get_flags() & pygame.FULLSCREEN)
        self.display.present()


if __name__ == "__main__":
    unittest.main()
