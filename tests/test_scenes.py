"""Проверки менеджера сцен: переходы, вход и выход, передача управления, ошибки."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.input import ActionInput  # noqa: E402
from game.core.scenes import Scene, SceneError, SceneManager  # noqa: E402


class Recorder(Scene):
    """Сцена, записывающая все вызовы в общий журнал."""

    def __init__(self, name: str, log: list, color=(0, 0, 0)) -> None:
        self.name = name
        self.log = log
        self.color = color

    def enter(self) -> None:
        self.log.append((self.name, "enter"))

    def exit(self) -> None:
        self.log.append((self.name, "exit"))

    def handle_event(self, event: pygame.event.Event) -> None:
        self.log.append((self.name, "event"))

    def update(self, dt: float) -> None:
        self.log.append((self.name, "update"))

    def draw(self, surface: pygame.Surface) -> None:
        self.log.append((self.name, "draw"))
        surface.fill(self.color)


def event() -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, mod=0, unicode="", scancode=0)


class SceneManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.log: list = []
        self.manager = SceneManager()
        self.surface = pygame.Surface((8, 8))

    def scene(self, name: str, **kwargs) -> Recorder:
        return Recorder(name, self.log, **kwargs)

    def tick(self) -> None:
        self.manager.handle_event(event())
        self.manager.update(0.016)
        self.manager.draw(self.surface)


class TransitionsTest(SceneManagerTestCase):
    def test_first_scene_enters_and_becomes_current(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        self.assertIs(self.manager.current, debug)
        self.assertIs(debug.manager, self.manager)
        self.assertEqual(self.log, [("debug", "enter")])

    def test_push_pauses_previous_scene(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        gallery = self.manager.push(self.scene("gallery"))
        self.assertEqual(self.log[1:], [("debug", "exit"), ("gallery", "enter")])
        self.assertEqual(self.manager.stack, (debug, gallery))
        self.log.clear()
        self.tick()
        # Предыдущая сцена не получает ни ввода, ни обновления, ни отрисовки.
        self.assertEqual(self.log, [("gallery", "event"), ("gallery", "update"), ("gallery", "draw")])

    def test_pop_returns_to_previous_scene(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        gallery = self.manager.push(self.scene("gallery"))
        self.log.clear()
        self.assertIs(self.manager.pop(), gallery)
        self.assertEqual(self.log, [("gallery", "exit"), ("debug", "enter")])
        self.assertIs(self.manager.current, debug)
        self.assertIsNone(gallery.manager)
        self.assertTrue(gallery.is_finished)
        self.log.clear()
        self.tick()
        self.assertEqual({name for name, _ in self.log}, {"debug"})

    def test_replace_closes_current_scene(self) -> None:
        intro = self.manager.push(self.scene("intro"))
        hub = self.manager.replace(self.scene("hub"))
        self.assertEqual(self.log, [("intro", "enter"), ("intro", "exit"), ("hub", "enter")])
        self.assertEqual(self.manager.stack, (hub,))
        self.assertIsNone(intro.manager)

    def test_replace_keeps_scenes_below(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        self.manager.push(self.scene("gallery"))
        demo = self.manager.replace(self.scene("demo"))
        self.assertEqual(self.manager.stack, (debug, demo))
        self.manager.pop()
        self.assertIs(self.manager.current, debug)

    def test_replace_on_empty_manager_starts_scene(self) -> None:
        intro = self.manager.replace(self.scene("intro"))
        self.assertEqual(self.manager.stack, (intro,))
        self.assertEqual(self.log, [("intro", "enter")])

    def test_transition_during_event_handling_redirects_next_events(self) -> None:
        log = self.log
        manager = self.manager

        class Opener(Recorder):
            def handle_event(self, event: pygame.event.Event) -> None:
                super().handle_event(event)
                manager.push(Recorder("child", log))

        manager.push(Opener("debug", log))
        log.clear()
        manager.handle_event(event())
        manager.handle_event(event())
        manager.update(0.016)
        self.assertEqual(
            log, [("debug", "event"), ("debug", "exit"), ("child", "enter"), ("child", "event"), ("child", "update")]
        )


class FinishTest(SceneManagerTestCase):
    def test_finish_returns_to_previous_scene(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        gallery = self.manager.push(self.scene("gallery"))
        gallery.finish()
        self.assertIs(self.manager.current, debug)
        self.assertTrue(gallery.is_finished)

    def test_finish_of_last_scene_only_marks_it(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        debug.finish()
        self.assertTrue(debug.is_finished)
        self.assertEqual(self.manager.stack, (debug,))

    def test_closed_scene_cannot_change_manager(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        gallery = self.manager.push(self.scene("gallery"))
        self.manager.pop()
        demo = self.manager.push(self.scene("demo"))
        gallery.finish()  # устаревшая сцена: менеджер о ней уже не знает
        self.assertEqual(self.manager.stack, (debug, demo))

    def test_paused_scene_cannot_close_scene_above(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        gallery = self.manager.push(self.scene("gallery"))
        debug.finish()
        self.assertEqual(self.manager.stack, (debug, gallery))

    def test_scene_can_be_opened_again_after_closing(self) -> None:
        self.manager.push(self.scene("debug"))
        gallery = self.manager.push(self.scene("gallery"))
        self.manager.pop()
        self.manager.push(gallery)
        self.assertIs(self.manager.current, gallery)
        self.assertFalse(gallery.is_finished)


class ErrorsTest(SceneManagerTestCase):
    def assert_unchanged(self, action, pattern: str) -> None:
        stack_before, log_before = self.manager.stack, list(self.log)
        with self.assertRaisesRegex(SceneError, pattern):
            action()
        self.assertEqual(self.manager.stack, stack_before)
        self.assertEqual(self.log, log_before)

    def test_pop_without_previous_scene(self) -> None:
        self.assert_unchanged(self.manager.pop, "возвращаться некуда")
        self.manager.push(self.scene("debug"))
        self.assert_unchanged(self.manager.pop, "возвращаться некуда")

    def test_scene_cannot_be_opened_twice(self) -> None:
        debug = self.manager.push(self.scene("debug"))
        self.manager.push(self.scene("gallery"))
        self.assert_unchanged(lambda: self.manager.push(debug), "уже открыта")
        self.assert_unchanged(lambda: self.manager.replace(debug), "уже открыта")

    def test_only_scenes_can_be_opened(self) -> None:
        self.assert_unchanged(lambda: self.manager.push(None), "ожидалась сцена")
        self.assert_unchanged(lambda: self.manager.push(object()), "ожидалась сцена")

    def test_unknown_scene_name(self) -> None:
        self.assert_unchanged(lambda: self.manager.push("sushi"), "«sushi» не зарегистрирована")
        self.assert_unchanged(lambda: self.manager.replace("finale"), "«finale» не зарегистрирована")

    def test_invalid_registration(self) -> None:
        self.manager.register("hub", lambda: self.scene("hub"))
        with self.assertRaisesRegex(SceneError, "уже зарегистрирована"):
            self.manager.register("hub", lambda: self.scene("hub"))
        with self.assertRaisesRegex(SceneError, "непустой строкой"):
            self.manager.register(" ", lambda: self.scene("x"))
        with self.assertRaisesRegex(SceneError, "функция или класс"):
            self.manager.register("cakes", self.scene("cakes"))

    def test_factory_must_create_scene(self) -> None:
        self.manager.register("broken", lambda: "не сцена")
        self.assert_unchanged(lambda: self.manager.push("broken"), "ожидалась сцена, а получено str")

    def test_empty_manager_is_safe(self) -> None:
        self.manager.handle_event(event())
        self.manager.update(0.016)
        self.surface.fill((255, 255, 255))
        self.manager.draw(self.surface)
        self.assertEqual(tuple(self.surface.get_at((0, 0)))[:3], config.BACKGROUND_COLOR)
        self.assertIsNone(self.manager.current)


class RegistryAndDrawingTest(SceneManagerTestCase):
    def test_registered_scenes_are_created_on_each_transition(self) -> None:
        # Так будущие сцены (вступление, центральная локация, суши…) подключаются по имени.
        created = []

        def make_hub() -> Scene:
            created.append(self.scene("hub"))
            return created[-1]

        self.manager.register("hub", make_hub)
        self.manager.register("sushi", lambda: self.scene("sushi"))
        self.assertTrue(self.manager.is_registered("hub"))
        self.assertFalse(self.manager.is_registered("finale"))
        first = self.manager.replace("hub")
        self.manager.push("sushi")
        self.manager.pop()
        self.assertIs(self.manager.current, first)
        self.manager.replace("hub")
        self.assertEqual(len(created), 2)
        self.assertIsNot(self.manager.current, first)

    def test_overlay_is_drawn_over_paused_scene(self) -> None:
        self.manager.push(self.scene("debug", color=(10, 20, 30)))
        overlay = self.scene("dialogue")
        overlay.is_overlay = True
        self.manager.push(overlay)
        self.log.clear()
        self.tick()
        # Сцена под окном видна, но не получает ни ввода, ни обновления.
        expected = [("dialogue", "event"), ("dialogue", "update"), ("debug", "draw"), ("dialogue", "draw")]
        self.assertEqual(self.log, expected)

    def test_opaque_scene_hides_scenes_below(self) -> None:
        self.manager.push(self.scene("debug"))
        self.manager.push(self.scene("gallery"))
        self.log.clear()
        self.manager.draw(self.surface)
        self.assertEqual(self.log, [("gallery", "draw")])

    def test_shared_input_is_available_to_scenes(self) -> None:
        shared = ActionInput()
        manager = SceneManager(shared)
        scene = manager.push(self.scene("hub"))
        self.assertIs(scene.manager.input, shared)
        self.assertIsInstance(SceneManager().input, ActionInput)


if __name__ == "__main__":
    unittest.main()
