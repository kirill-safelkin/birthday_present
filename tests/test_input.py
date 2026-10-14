"""Проверки слоя ввода: клавиши → логические действия, удержание, автоповтор, раскладки."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

import pygame  # noqa: E402

from game.core.input import Action, ActionInput, KeyBinding, actions_for, matches_key  # noqa: E402


def key_event(key: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key, mod=0, unicode="", scancode=scancode)


def up(key: int, scancode: int = 0) -> pygame.event.Event:
    return key_event(key, scancode, pygame.KEYUP)


class ActionMappingTest(unittest.TestCase):
    def test_arrows_and_letters_in_latin_and_russian_layouts(self) -> None:
        cases = {
            Action.MOVE_UP: [(pygame.K_UP, pygame.KSCAN_UP), (pygame.K_w, pygame.KSCAN_W), (ord("ц"), pygame.KSCAN_W)],
            Action.MOVE_DOWN: [(pygame.K_DOWN, 0), (pygame.K_s, pygame.KSCAN_S), (ord("ы"), pygame.KSCAN_S)],
            Action.MOVE_LEFT: [(pygame.K_LEFT, 0), (pygame.K_a, pygame.KSCAN_A), (ord("ф"), pygame.KSCAN_A)],
            Action.MOVE_RIGHT: [(pygame.K_RIGHT, 0), (pygame.K_d, pygame.KSCAN_D), (ord("в"), pygame.KSCAN_D)],
            Action.INTERACT: [(pygame.K_e, pygame.KSCAN_E), (ord("у"), pygame.KSCAN_E)],
            Action.CANCEL: [(pygame.K_BACKSPACE, pygame.KSCAN_BACKSPACE)],
        }
        for action, keys in cases.items():
            for key, scancode in keys:
                with self.subTest(action=action, key=key):
                    self.assertEqual(actions_for(key_event(key, scancode)), {action})
                    self.assertEqual(actions_for(up(key, scancode)), {action})  # отпускание тоже распознаётся

    def test_letter_without_scancode_in_german_layout(self) -> None:
        # В немецкой раскладке W, A, S, D, E на своих местах: хватает и кода клавиши.
        self.assertEqual(actions_for(key_event(pygame.K_w)), {Action.MOVE_UP})

    def test_confirm_keys(self) -> None:
        self.assertEqual(actions_for(key_event(pygame.K_RETURN)), {Action.CONFIRM, Action.INTERACT})
        self.assertEqual(actions_for(key_event(pygame.K_KP_ENTER)), {Action.CONFIRM, Action.INTERACT})
        self.assertEqual(actions_for(key_event(pygame.K_SPACE)), {Action.CONFIRM})

    def test_global_and_unrelated_keys_have_no_actions(self) -> None:
        for key in (pygame.K_ESCAPE, pygame.K_F11, pygame.K_p, pygame.K_TAB, pygame.K_1):
            self.assertEqual(actions_for(key_event(key)), frozenset(), key)
        self.assertEqual(actions_for(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))), frozenset())

    def test_matches_key_without_scancode(self) -> None:
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)  # события без поля scancode
        self.assertTrue(matches_key(event, pygame.K_SPACE, None))
        self.assertFalse(matches_key(event, pygame.K_RETURN, None))
        self.assertTrue(matches_key(key_event(ord("в"), pygame.KSCAN_D), pygame.K_d, pygame.KSCAN_D))

    def test_custom_bindings_change_keys_not_game_logic(self) -> None:
        bindings = [KeyBinding(Action.CONFIRM, pygame.K_z, pygame.KSCAN_Z)]
        controls = ActionInput(bindings)
        self.assertEqual(controls.pressed(key_event(pygame.K_z, pygame.KSCAN_Z)), {Action.CONFIRM})
        self.assertEqual(controls.pressed(key_event(pygame.K_RETURN)), frozenset())


class ActionInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.controls = ActionInput()

    def test_press_and_release(self) -> None:
        self.assertTrue(self.controls.handle_event(key_event(pygame.K_LEFT)))
        self.assertTrue(self.controls.is_held(Action.MOVE_LEFT))
        self.controls.handle_event(up(pygame.K_LEFT))
        self.assertFalse(self.controls.is_held(Action.MOVE_LEFT))
        self.assertEqual(self.controls.held_actions(), [])

    def test_system_repeat_is_not_a_new_press(self) -> None:
        self.assertTrue(self.controls.handle_event(key_event(pygame.K_RETURN)))
        for _ in range(5):  # автоповтор: KEYDOWN без KEYUP
            self.assertFalse(self.controls.handle_event(key_event(pygame.K_RETURN)))
        self.controls.handle_event(up(pygame.K_RETURN))
        self.assertTrue(self.controls.handle_event(key_event(pygame.K_RETURN)))  # новое нажатие

    def test_repeat_of_keys_without_actions_is_detected_too(self) -> None:
        self.assertTrue(self.controls.handle_event(key_event(pygame.K_F11)))
        self.assertFalse(self.controls.handle_event(key_event(pygame.K_F11)))

    def test_pressed_only_on_key_down(self) -> None:
        self.assertEqual(self.controls.pressed(key_event(pygame.K_SPACE)), {Action.CONFIRM})
        self.assertEqual(self.controls.pressed(up(pygame.K_SPACE)), frozenset())

    def test_several_directions_at_once(self) -> None:
        self.controls.handle_event(key_event(pygame.K_UP))
        self.controls.handle_event(key_event(pygame.K_d, pygame.KSCAN_D))
        self.assertTrue(self.controls.is_held(Action.MOVE_UP))
        self.assertTrue(self.controls.is_held(Action.MOVE_RIGHT))
        self.assertEqual(self.controls.held_actions(), [Action.MOVE_UP, Action.MOVE_RIGHT])

    def test_held_actions_ordered_by_latest_press(self) -> None:
        self.controls.handle_event(key_event(pygame.K_UP))
        self.controls.handle_event(key_event(pygame.K_LEFT))
        self.controls.handle_event(key_event(pygame.K_w, pygame.KSCAN_W))  # вверх нажат снова, другой клавишей
        self.assertEqual(self.controls.held_actions(), [Action.MOVE_LEFT, Action.MOVE_UP])

    def test_same_action_from_two_keys(self) -> None:
        self.controls.handle_event(key_event(pygame.K_UP))
        self.controls.handle_event(key_event(pygame.K_w, pygame.KSCAN_W))
        self.controls.handle_event(up(pygame.K_UP))
        self.assertTrue(self.controls.is_held(Action.MOVE_UP))  # W всё ещё зажата
        self.controls.handle_event(up(pygame.K_w, pygame.KSCAN_W))
        self.assertFalse(self.controls.is_held(Action.MOVE_UP))

    def test_layout_switch_while_key_is_held(self) -> None:
        # Нажали W в немецкой раскладке, отпустили в русской: та же клавиша по скан-коду.
        self.controls.handle_event(key_event(pygame.K_w, pygame.KSCAN_W))
        self.controls.handle_event(up(ord("ц"), pygame.KSCAN_W))
        self.assertFalse(self.controls.is_held(Action.MOVE_UP))

    def test_focus_loss_releases_everything(self) -> None:
        self.controls.handle_event(key_event(pygame.K_RIGHT))
        self.controls.handle_event(key_event(pygame.K_RETURN))
        self.controls.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertEqual(self.controls.held_actions(), [])
        self.assertTrue(self.controls.handle_event(key_event(pygame.K_RETURN)))  # снова новое нажатие

    def test_release_of_unknown_key_is_harmless(self) -> None:
        self.assertTrue(self.controls.handle_event(up(pygame.K_LEFT)))
        self.assertTrue(self.controls.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(0, 0), rel=(0, 0))))


if __name__ == "__main__":
    unittest.main()
