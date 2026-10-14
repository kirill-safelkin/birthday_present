"""Проверки игрового цикла, демонстраций диалога и анимации, точки входа."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import faulthandler  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

from game.core.app import App  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent.parent


def key_down(key: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=scancode)


def post_keys(*keys: int) -> None:
    for key in keys:
        pygame.event.post(key_down(key))


class AppEventsTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App()
        # Если цикл не остановится, процесс упадёт с трассировкой, а не зависнет.
        faulthandler.dump_traceback_later(10, exit=True)

    def tearDown(self) -> None:
        faulthandler.cancel_dump_traceback_later()
        pygame.quit()

    def test_escape_stops_loop(self) -> None:
        pygame.event.post(key_down(pygame.K_ESCAPE))
        self.app.run()
        self.assertFalse(self.app.running)

    def test_window_close_stops_loop(self) -> None:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)

    def test_f11_toggles_fullscreen(self) -> None:
        pygame.event.post(key_down(pygame.K_F11))
        pygame.event.post(key_down(pygame.K_ESCAPE))
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)

    def test_demo_dialogue_runs_and_returns_to_debug_screen(self) -> None:
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))
        # Каждая реплика: Enter дописывает текст, следующий Enter продолжает.
        post_keys(pygame.K_RETURN, pygame.K_RETURN)  # «Так. Я проверил систему…»
        post_keys(pygame.K_RETURN, pygame.K_RETURN)  # «По крайней мере…»
        post_keys(pygame.K_RETURN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)  # третий вариант ответа
        post_keys(pygame.K_RETURN, pygame.K_RETURN)  # ответ Чучмека, конец диалога
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.dialogue)
        self.assertIsNotNone(self.app.screen.last_answer)
        self.assertEqual(self.app.screen.last_answer.text, "Ты вообще знаешь, что делаешь?")

    def test_demo_can_be_started_again(self) -> None:
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))
        post_keys(*[pygame.K_RETURN] * 8)  # четыре реплики по два нажатия, ответ по умолчанию «Продолжай.»
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.dialogue)
        self.assertEqual(self.app.screen.dialogue.node.id, "start")
        self.assertEqual(self.app.screen.last_answer.text, "Продолжай.")

    def test_demo_key_works_with_non_latin_layout(self) -> None:
        # При русской раскладке у клавиши D может быть код буквы «в», но скан-код тот же.
        pygame.event.post(key_down(ord("в"), pygame.KSCAN_D))
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.dialogue)

    def test_escape_and_f11_still_work_during_dialogue(self) -> None:
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))
        post_keys(pygame.K_F11, pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsNotNone(self.app.screen.dialogue)  # ESC закрыл игру, а не диалог

    def test_animation_demo_opens_and_returns_to_debug_screen(self) -> None:
        pygame.event.post(key_down(pygame.K_a, pygame.KSCAN_A))
        post_keys(pygame.K_BACKSPACE)
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))  # диалог после возврата работает как прежде
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.animation_demo)
        self.assertIsNotNone(self.app.screen.dialogue)

    def test_animation_demo_key_works_with_non_latin_layout(self) -> None:
        pygame.event.post(key_down(ord("ф"), pygame.KSCAN_A))
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.animation_demo)

    def test_d_in_animation_demo_moves_character_instead_of_dialogue(self) -> None:
        pygame.event.post(key_down(pygame.K_a, pygame.KSCAN_A))
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.dialogue)
        self.assertEqual(self.app.screen.animation_demo.character.state, "walk")

    def test_escape_and_f11_still_work_in_animation_demo(self) -> None:
        pygame.event.post(key_down(pygame.K_a, pygame.KSCAN_A))
        post_keys(pygame.K_F11, pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsNotNone(self.app.screen.animation_demo)  # ESC закрыл игру, а не тест анимации

    def test_window_close_works_in_animation_demo(self) -> None:
        pygame.event.post(key_down(pygame.K_a, pygame.KSCAN_A))
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)


class EntryPointTest(unittest.TestCase):
    def run_main(self, *python_args: str, unset_env: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
        env = {name: value for name, value in os.environ.items() if name not in unset_env}
        return subprocess.run(
            [sys.executable, *python_args, "main.py"],
            cwd=PROJECT_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_missing_pygame_gives_clear_message(self) -> None:
        # -S отключает site-packages, и Pygame становится недоступен.
        result = self.run_main("-S")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Pygame не установлен", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_no_graphical_session_gives_clear_message(self) -> None:
        # Как запуск по SSH или из cron: дисплея нет, драйвер SDL явно не выбран.
        result = self.run_main(unset_env=("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEODRIVER"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("графический дисплей не найден", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
