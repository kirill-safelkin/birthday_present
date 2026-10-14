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

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.debug.debug_screen import DebugScreen  # noqa: E402
from game.debug.sprite_gallery import SpriteGallery  # noqa: E402
from game.debug.demo_dialogue import DEMO_SCRIPT, QUESTION_ID  # noqa: E402
from game.dialogue.model import DialogueController  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent.parent


def key_down(key: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=scancode)


def key_up(key: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode="", scancode=scancode)


def press(key: int, scancode: int = 0) -> None:
    """Одно нажатие, как с настоящей клавиатуры: KEYDOWN, затем KEYUP.

    Повторный KEYDOWN без KEYUP игра считает системным автоповтором зажатой клавиши.
    """
    pygame.event.post(key_down(key, scancode))
    pygame.event.post(key_up(key, scancode))


def post_keys(*keys: int) -> None:
    for key in keys:
        press(key)


class AppEventsTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App(dev_mode=True)  # экран проверки и его клавиши
        # Если цикл не остановится, процесс упадёт с трассировкой, а не зависнет.
        faulthandler.dump_traceback_later(10, exit=True)

    def tearDown(self) -> None:
        faulthandler.cancel_dump_traceback_later()
        pygame.quit()

    def test_escape_stops_loop(self) -> None:
        press(pygame.K_ESCAPE)
        self.app.run()
        self.assertFalse(self.app.running)

    def test_window_close_stops_loop(self) -> None:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)

    def test_f11_toggles_fullscreen(self) -> None:
        press(pygame.K_F11)
        press(pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)

    def test_demo_dialogue_runs_and_returns_to_debug_screen(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
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
        press(pygame.K_d, pygame.KSCAN_D)
        post_keys(*[pygame.K_RETURN] * 8)  # четыре реплики по два нажатия, ответ по умолчанию «Продолжай.»
        press(pygame.K_d, pygame.KSCAN_D)
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.dialogue)
        self.assertEqual(self.app.screen.dialogue.node.id, "start")
        self.assertEqual(self.app.screen.last_answer.text, "Продолжай.")

    def test_demo_key_works_with_non_latin_layout(self) -> None:
        # При русской раскладке у клавиши D может быть код буквы «в», но скан-код тот же.
        press(ord("в"), pygame.KSCAN_D)
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.dialogue)

    def test_escape_and_f11_still_work_during_dialogue(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
        post_keys(pygame.K_F11, pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsNotNone(self.app.screen.dialogue)  # ESC закрыл игру, а не диалог

    def test_animation_demo_opens_and_returns_to_debug_screen(self) -> None:
        press(pygame.K_a, pygame.KSCAN_A)
        post_keys(pygame.K_BACKSPACE)
        press(pygame.K_d, pygame.KSCAN_D)  # диалог после возврата работает как прежде
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.animation_demo)
        self.assertIsNotNone(self.app.screen.dialogue)

    def test_animation_demo_key_works_with_non_latin_layout(self) -> None:
        press(ord("ф"), pygame.KSCAN_A)
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.animation_demo)

    def test_d_in_animation_demo_moves_character_instead_of_dialogue(self) -> None:
        press(pygame.K_a, pygame.KSCAN_A)
        pygame.event.post(key_down(pygame.K_d, pygame.KSCAN_D))  # D зажата
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.dialogue)
        self.assertEqual(self.app.screen.animation_demo.character.state, "walk")

    def test_escape_and_f11_still_work_in_animation_demo(self) -> None:
        press(pygame.K_a, pygame.KSCAN_A)
        post_keys(pygame.K_F11, pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsNotNone(self.app.screen.animation_demo)  # ESC закрыл игру, а не тест анимации

    def test_sprite_gallery_opens_and_returns_to_debug_screen(self) -> None:
        press(pygame.K_p, pygame.KSCAN_P)
        post_keys(pygame.K_RIGHT, pygame.K_DOWN, pygame.K_BACKSPACE)
        press(pygame.K_a, pygame.KSCAN_A)  # тест анимации после галереи открывается
        post_keys(pygame.K_BACKSPACE)
        press(pygame.K_d, pygame.KSCAN_D)  # и диалог тоже
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.sprite_gallery)
        self.assertIsNone(self.app.screen.animation_demo)
        self.assertIsNotNone(self.app.screen.dialogue)

    def test_sprite_gallery_key_works_with_non_latin_layout(self) -> None:
        press(ord("з"), pygame.KSCAN_P)
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNotNone(self.app.screen.sprite_gallery)

    def test_d_and_a_in_sprite_gallery_do_not_open_other_screens(self) -> None:
        press(pygame.K_p, pygame.KSCAN_P)
        press(pygame.K_d, pygame.KSCAN_D)
        press(pygame.K_a, pygame.KSCAN_A)
        post_keys(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.dialogue)
        self.assertIsNone(self.app.screen.animation_demo)
        self.assertIsNotNone(self.app.screen.sprite_gallery)

    def test_escape_and_f11_still_work_in_sprite_gallery(self) -> None:
        press(pygame.K_p, pygame.KSCAN_P)
        post_keys(pygame.K_F11, pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsNotNone(self.app.screen.sprite_gallery)  # ESC закрыл игру, а не галерею

    def test_window_close_works_in_sprite_gallery(self) -> None:
        press(pygame.K_p, pygame.KSCAN_P)
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.app.run()
        self.assertFalse(self.app.running)

    def test_held_enter_does_not_confirm_twice(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
        pygame.event.post(key_down(pygame.K_RETURN))  # дописывает первую реплику
        pygame.event.post(key_down(pygame.K_RETURN))  # системный автоповтор: Enter не отпускали
        pygame.event.post(key_down(pygame.K_RETURN))
        press(pygame.K_ESCAPE)
        self.app.run()
        dialogue = self.app.screen.dialogue
        self.assertEqual(dialogue.node.id, "start")  # реплика не пролистана повтором
        self.assertFalse(dialogue.is_typing)

    def test_held_f11_toggles_fullscreen_once(self) -> None:
        pygame.event.post(key_down(pygame.K_F11))
        pygame.event.post(key_down(pygame.K_F11))  # автоповтор
        press(pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)

    def test_dialogue_choices_with_letters_in_russian_layout(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
        post_keys(*[pygame.K_SPACE] * 4)  # пробел — тоже подтверждение
        post_keys(pygame.K_RETURN)  # вопрос напечатан
        press(ord("ы"), pygame.KSCAN_S)  # S в русской раскладке — вниз
        press(ord("ы"), pygame.KSCAN_S)
        press(ord("ц"), pygame.KSCAN_W)  # W — вверх
        post_keys(pygame.K_RETURN, pygame.K_RETURN, pygame.K_RETURN)  # выбор, «Это не крошки…»
        press(pygame.K_ESCAPE)
        self.app.run()
        self.assertEqual(self.app.screen.dialogue.node.id, "forgot")

    def test_backspace_closes_dialogue_without_answer(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
        post_keys(pygame.K_RETURN, pygame.K_BACKSPACE)
        press(pygame.K_ESCAPE)
        self.app.run()
        self.assertIsNone(self.app.screen.dialogue)
        self.assertIsNone(self.app.screen.last_answer)
        self.assertIs(self.app.scenes.current, self.app.screen)

    def test_screens_reopen_after_return_and_debug_screen_keeps_state(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
        post_keys(*[pygame.K_RETURN] * 8)  # диалог пройден, ответ «Продолжай.»
        for _ in range(2):
            press(pygame.K_p, pygame.KSCAN_P)
            post_keys(pygame.K_RIGHT, pygame.K_BACKSPACE)
            press(pygame.K_a, pygame.KSCAN_A)
            post_keys(pygame.K_BACKSPACE)
        press(pygame.K_p, pygame.KSCAN_P)
        press(pygame.K_ESCAPE)
        self.app.run()
        gallery = self.app.screen.sprite_gallery
        self.assertIsInstance(gallery, SpriteGallery)
        self.assertEqual(gallery.character_index, 0)  # галерея открыта заново, а не продолжена
        self.assertEqual([type(scene) for scene in self.app.scenes.stack], [DebugScreen, SpriteGallery])
        self.assertEqual(self.app.screen.last_answer.text, "Продолжай.")  # итог диалога сохранён
        self.assertEqual(len(self.app.screen._result_labels), 2)

    def test_transitions_work_in_fullscreen(self) -> None:
        press(pygame.K_F11)
        press(pygame.K_p, pygame.KSCAN_P)
        post_keys(pygame.K_BACKSPACE)
        press(pygame.K_a, pygame.KSCAN_A)
        post_keys(pygame.K_BACKSPACE)
        press(pygame.K_d, pygame.KSCAN_D)
        press(pygame.K_ESCAPE)
        self.app.run()
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsNotNone(self.app.screen.dialogue)
        self.app.scenes.draw(self.app.display.canvas)
        self.app.display.present()

    def test_debug_screen_is_frozen_while_another_scene_is_open(self) -> None:
        screen = self.app.screen
        press(pygame.K_p, pygame.KSCAN_P)
        press(pygame.K_ESCAPE)
        self.app.run()
        timer = screen._fps_timer
        self.app.scenes.update(1.0)
        self.app.scenes.handle_event(key_down(pygame.K_d, pygame.KSCAN_D))  # D в галерее не открывает диалог
        self.assertEqual(screen._fps_timer, timer)
        self.assertIsNone(screen.dialogue)

    def test_dialogue_is_drawn_over_debug_screen(self) -> None:
        press(pygame.K_d, pygame.KSCAN_D)
        press(pygame.K_ESCAPE)
        self.app.run()
        canvas = self.app.display.canvas
        self.app.scenes.draw(canvas)
        box = self.app.screen._dialogue_box.layout(self.app.screen.dialogue.node).box
        self.assertEqual(tuple(canvas.get_at((box.x + 3, box.bottom - 3)))[:3], config.DIALOGUE_BOX_COLOR)
        title_rect = self.app.screen._labels[0][1]
        row = title_rect.centery
        title_colors = {tuple(canvas.get_at((x, row)))[:3] for x in range(title_rect.left, title_rect.right)}
        self.assertIn(config.TITLE_COLOR, title_colors)  # экран проверки виден под окном диалога

    def test_debug_screen_texts_fit_on_screen(self) -> None:
        screen = self.app.screen
        # Самый длинный итог диалога: две строки, в ответе — самый длинный вариант.
        dialogue = DialogueController(DEMO_SCRIPT)
        dialogue.answers[QUESTION_ID] = max(DEMO_SCRIPT.nodes[QUESTION_ID].choices, key=lambda choice: len(choice.text))
        screen._finish_dialogue(dialogue)
        self.assertEqual(len(screen._result_labels), 2)
        canvas = pygame.Rect((0, 0), self.app.display.canvas.get_size())
        for _, rect in screen._labels + screen._result_labels:
            self.assertTrue(canvas.contains(rect), rect)

    def test_window_close_works_in_animation_demo(self) -> None:
        press(pygame.K_a, pygame.KSCAN_A)
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
