"""Проверки персонажа: движение с клавиатуры, направления, состояния и резервные анимации."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import unittest  # noqa: E402

import pygame  # noqa: E402

from game.graphics.animation import IDLE, REACT, TALK, WALK, Animation, AnimationSet, Direction  # noqa: E402
from game.world.character import Character  # noqa: E402
from game.graphics.placeholder import placeholder_animations  # noqa: E402

ARROWS = {
    pygame.K_UP: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_RIGHT: Direction.RIGHT,
}


def key_event(event_type: int, key: int, scancode: int = 0) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key, mod=0, unicode="", scancode=scancode)


def press(character: Character, key: int, scancode: int = 0) -> bool:
    return character.handle_event(key_event(pygame.KEYDOWN, key, scancode))


def release(character: Character, key: int, scancode: int = 0) -> bool:
    return character.handle_event(key_event(pygame.KEYUP, key, scancode))


def make_animation(loop: bool = True) -> Animation:
    frame = pygame.Surface((8, 12), pygame.SRCALPHA)
    frame.fill((255, 0, 0, 255))
    return Animation([frame, frame.copy()], fps=4, loop=loop)


def labelled_animations() -> tuple[AnimationSet, dict[tuple[str, Direction], Animation]]:
    """Набор, где у idle и walk каждого направления своя анимация, — чтобы проверять выбор."""
    animations = AnimationSet(make_animation())
    table = {}
    for state in (IDLE, WALK):
        for direction in Direction:
            table[state, direction] = make_animation()
            animations.add(state, table[state, direction], direction)
    return animations, table


class CharacterMovementTest(unittest.TestCase):
    def setUp(self) -> None:
        animations, self.table = labelled_animations()
        self.character = Character("Тест", animations, position=(100, 100), speed=60)

    def test_starts_idle_facing_down(self) -> None:
        self.assertEqual(self.character.state, IDLE)
        self.assertEqual(self.character.direction, Direction.DOWN)
        self.assertIs(self.character.player.animation, self.table[IDLE, Direction.DOWN])
        self.assertEqual(self.character.velocity, pygame.Vector2())

    def test_arrow_keys_turn_and_switch_walk_animation(self) -> None:
        for key, direction in ARROWS.items():
            with self.subTest(direction=direction):
                self.assertTrue(press(self.character, key))
                self.assertEqual(self.character.direction, direction)
                self.assertEqual(self.character.state, WALK)
                self.assertIs(self.character.player.animation, self.table[WALK, direction])
                self.assertEqual(self.character.velocity, pygame.Vector2(direction.value) * 60)
                release(self.character, key)

    def test_walk_turns_into_idle_of_same_direction(self) -> None:
        press(self.character, pygame.K_LEFT)
        self.character.update(0.3)
        release(self.character, pygame.K_LEFT)
        self.assertEqual(self.character.state, IDLE)
        self.assertEqual(self.character.direction, Direction.LEFT)  # не развернулся при остановке
        self.assertIs(self.character.player.animation, self.table[IDLE, Direction.LEFT])
        press(self.character, pygame.K_LEFT)
        self.assertEqual(self.character.state, WALK)

    def test_walk_animation_continues_while_key_is_held(self) -> None:
        press(self.character, pygame.K_RIGHT)
        self.character.update(0.3)  # 1,2 кадра при 4 кадрах в секунду
        press(self.character, pygame.K_d, pygame.KSCAN_D)  # вторая клавиша того же направления
        self.assertEqual(self.character.player.frame_index, 1)

    def test_wasd_works_in_latin_and_russian_layouts(self) -> None:
        letters = {
            Direction.UP: (pygame.K_w, ord("ц"), pygame.KSCAN_W),
            Direction.LEFT: (pygame.K_a, ord("ф"), pygame.KSCAN_A),
            Direction.DOWN: (pygame.K_s, ord("ы"), pygame.KSCAN_S),
            Direction.RIGHT: (pygame.K_d, ord("в"), pygame.KSCAN_D),
        }
        for direction, (latin, russian, scancode) in letters.items():
            for key in (latin, russian):
                with self.subTest(direction=direction, key=key):
                    press(self.character, key, scancode)
                    self.assertEqual((self.character.direction, self.character.state), (direction, WALK))
                    release(self.character, key, scancode)
                    self.assertEqual(self.character.state, IDLE)

    def test_layout_switch_while_key_is_held(self) -> None:
        # Нажали W в немецкой раскладке, отпустили уже в русской: клавиша та же по скан-коду.
        press(self.character, pygame.K_w, pygame.KSCAN_W)
        release(self.character, ord("ц"), pygame.KSCAN_W)
        self.assertEqual(self.character.state, IDLE)

    def test_diagonal_speed_is_normalized(self) -> None:
        press(self.character, pygame.K_RIGHT)
        press(self.character, pygame.K_DOWN)
        velocity = self.character.velocity
        self.assertAlmostEqual(velocity.length(), 60)
        self.assertAlmostEqual(velocity.x, 60 / math.sqrt(2))
        self.assertAlmostEqual(velocity.y, 60 / math.sqrt(2))
        self.character.update(1.0)
        travelled = math.hypot(self.character.x - 100, self.character.y - 100)
        self.assertAlmostEqual(travelled, 60)

    def test_same_direction_twice_is_not_faster(self) -> None:
        press(self.character, pygame.K_UP)
        press(self.character, pygame.K_w, pygame.KSCAN_W)
        self.assertAlmostEqual(self.character.velocity.length(), 60)
        release(self.character, pygame.K_UP)
        self.assertEqual(self.character.state, WALK)  # W всё ещё зажата

    def test_opposite_keys_cancel_each_other(self) -> None:
        press(self.character, pygame.K_LEFT)
        press(self.character, pygame.K_RIGHT)
        self.assertFalse(self.character.is_moving)
        self.assertEqual(self.character.state, IDLE)
        release(self.character, pygame.K_RIGHT)
        self.assertEqual((self.character.state, self.character.direction), (WALK, Direction.LEFT))

    def test_last_pressed_key_sets_facing_on_diagonal(self) -> None:
        press(self.character, pygame.K_DOWN)
        press(self.character, pygame.K_RIGHT)
        self.assertEqual(self.character.direction, Direction.RIGHT)
        self.assertIs(self.character.player.animation, self.table[WALK, Direction.RIGHT])
        release(self.character, pygame.K_RIGHT)
        self.assertEqual(self.character.direction, Direction.DOWN)

    def test_programmatic_diagonal_keeps_current_facing(self) -> None:
        self.character.face(Direction.UP)
        self.character.move(1, -1)
        self.assertEqual(self.character.direction, Direction.UP)
        self.character.move(1, 1)  # вверх уже не участвует; оси равны — смотрит по горизонтали
        self.assertEqual(self.character.direction, Direction.RIGHT)
        self.character.move(0.2, 1)  # теперь вправо участвует в движении — не отворачивается
        self.assertEqual(self.character.direction, Direction.RIGHT)
        self.character.face(Direction.LEFT)
        self.character.move(0.2, 1)  # влево не участвует, преобладает ось y
        self.assertEqual(self.character.direction, Direction.DOWN)

    def test_no_movement_after_keys_released(self) -> None:
        press(self.character, pygame.K_RIGHT)
        self.character.update(0.5)
        self.assertAlmostEqual(self.character.x, 130)
        release(self.character, pygame.K_RIGHT)
        self.character.update(1.0)
        self.assertAlmostEqual(self.character.x, 130)
        self.assertEqual(self.character.velocity, pygame.Vector2())

    def test_stop_keeps_direction(self) -> None:
        self.character.move(-3, 0)
        self.character.stop()
        self.assertFalse(self.character.is_moving)
        self.assertEqual((self.character.state, self.character.direction), (IDLE, Direction.LEFT))
        self.character.update(1.0)
        self.assertEqual((self.character.x, self.character.y), (100, 100))

    def test_move_with_zero_vector_stops(self) -> None:
        self.character.move(1, 0)
        self.character.move(0, 0)
        self.assertEqual(self.character.state, IDLE)

    def test_movement_does_not_depend_on_frame_rate(self) -> None:
        slow = Character("Медленный", labelled_animations()[0], speed=60)
        fast = Character("Быстрый", labelled_animations()[0], speed=60)
        for character in (slow, fast):
            character.move(1, 1)
        slow.update(1.0)
        for _ in range(144):
            fast.update(1 / 144)
        self.assertAlmostEqual(slow.x, fast.x)
        self.assertAlmostEqual(slow.y, fast.y)

    def test_speed_is_in_pixels_per_second(self) -> None:
        self.character.set_speed(40)
        self.character.move(0, -1)
        self.character.update(0.5)
        self.assertAlmostEqual(self.character.y, 80)
        self.character.set_speed(10)  # новая скорость действует сразу
        self.assertAlmostEqual(self.character.velocity.y, -10)

    def test_window_focus_loss_releases_keys(self) -> None:
        press(self.character, pygame.K_RIGHT)
        self.character.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertEqual(self.character.state, IDLE)
        press(self.character, pygame.K_UP)
        release(self.character, pygame.K_UP)
        self.assertEqual(self.character.state, IDLE)  # «зависшая» стрелка вправо забыта

    def test_unrelated_events_are_ignored(self) -> None:
        self.assertFalse(press(self.character, pygame.K_RETURN))
        self.assertFalse(self.character.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))))
        self.assertEqual(self.character.state, IDLE)

    def test_invalid_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.character.set_position(math.nan, 0)
        with self.assertRaises(ValueError):
            self.character.set_speed(-1)
        with self.assertRaises(ValueError):
            self.character.move(math.inf, 0)
        with self.assertRaises(ValueError):
            self.character.update(-0.1)
        with self.assertRaises(ValueError):
            self.character.set_state("")

    def test_draw_places_frame_by_feet(self) -> None:
        self.character.set_position(20.4, 30.5)
        self.assertEqual(self.character.pixel_position, (20, 31))  # половина округляется вверх
        surface = pygame.Surface((64, 64), pygame.SRCALPHA)
        self.character.draw(surface)
        # Кадр 8×12, середина нижнего края — в точке (20, 31).
        self.assertEqual(self.character.rect, pygame.Rect(16, 19, 8, 12))
        self.assertEqual(tuple(surface.get_at((16, 19))), (255, 0, 0, 255))
        self.assertEqual(tuple(surface.get_at((23, 30))), (255, 0, 0, 255))
        self.assertEqual(surface.get_at((15, 19)).a, 0)
        self.assertEqual(surface.get_at((16, 31)).a, 0)


class CharacterStatesTest(unittest.TestCase):
    def setUp(self) -> None:
        # Манекен: у него есть одноразовая анимация реакции.
        self.character = Character("Манекен", position=(50, 50))
        self.react_duration = self.character.animations.get(REACT, Direction.DOWN).duration

    def test_talk_stops_movement_and_loops(self) -> None:
        self.character.move(1, 0)
        self.character.talk()
        self.assertEqual(self.character.state, TALK)
        self.assertFalse(self.character.is_moving)
        self.character.update(10.0)
        self.assertEqual(self.character.state, TALK)
        press(self.character, pygame.K_UP)  # ходьба прерывает разговор
        self.assertEqual(self.character.state, WALK)
        release(self.character, pygame.K_UP)
        self.assertEqual(self.character.state, IDLE)

    def test_react_plays_once_and_returns_to_idle(self) -> None:
        self.character.face(Direction.LEFT)
        self.character.react()
        self.assertEqual(self.character.state, REACT)
        self.character.update(self.react_duration * 0.9)
        self.assertEqual(self.character.state, REACT)
        self.character.update(self.react_duration * 0.2)
        self.assertEqual((self.character.state, self.character.direction), (IDLE, Direction.LEFT))

    def test_react_can_be_restarted(self) -> None:
        self.character.react()
        self.character.update(self.react_duration * 0.5)
        self.character.react()
        self.assertEqual(self.character.player.frame_index, 0)

    def test_after_react_walks_on_if_key_is_still_held(self) -> None:
        press(self.character, pygame.K_RIGHT)
        self.character.react()
        self.assertFalse(self.character.is_moving)
        self.character.update(self.react_duration + 0.01)
        self.assertEqual((self.character.state, self.character.direction), (WALK, Direction.RIGHT))
        self.assertTrue(self.character.is_moving)

    def test_key_release_does_not_interrupt_react(self) -> None:
        press(self.character, pygame.K_RIGHT)
        self.character.react()
        release(self.character, pygame.K_RIGHT)
        self.assertEqual(self.character.state, REACT)
        self.character.update(self.react_duration + 0.01)
        self.assertEqual(self.character.state, IDLE)

    def test_key_press_interrupts_react(self) -> None:
        self.character.react()
        press(self.character, pygame.K_DOWN)
        self.assertEqual(self.character.state, WALK)
        self.character.update(self.react_duration + 0.01)
        self.assertEqual(self.character.state, WALK)  # отложенный возврат в idle отменён

    def test_one_shot_state_holds_last_frame(self) -> None:
        # Клубника прячется сразу после реакции: прятки одноразовые и не заканчиваются возвратом в idle.
        hide = make_animation(loop=False)
        self.character.animations.add("hide", hide)
        self.character.react()
        self.character.set_state("hide")
        self.character.update(5.0)
        self.assertEqual(self.character.state, "hide")
        self.assertTrue(self.character.player.is_finished)
        self.assertIs(self.character.player.frame, hide.frames[-1])


class FallbackAnimationTest(unittest.TestCase):
    def test_character_without_frames_uses_placeholder(self) -> None:
        character = Character("Алиса")
        surface = pygame.Surface((64, 64), pygame.SRCALPHA)
        for state in (IDLE, WALK, TALK, REACT):
            for direction in Direction:
                with self.subTest(state=state, direction=direction):
                    self.assertTrue(character.animations.has(state, direction))
                    character.face(direction)
                    character.set_state(state)
                    character.update(0.1)
                    character.draw(surface)
        animations = character.animations
        self.assertIsNot(animations.get(IDLE, Direction.LEFT), animations.get(IDLE, Direction.RIGHT))

    def test_placeholder_animation_modes(self) -> None:
        animations = placeholder_animations()
        for direction in Direction:
            with self.subTest(direction=direction):
                self.assertTrue(animations.get(IDLE, direction).loop)
                self.assertGreater(len(animations.get(WALK, direction).frames), 1)
                self.assertFalse(animations.get(REACT, direction).loop)

    def test_placeholder_right_mirrors_left(self) -> None:
        animations = placeholder_animations()
        left = animations.get(IDLE, Direction.LEFT).frames[0]
        right = animations.get(IDLE, Direction.RIGHT).frames[0]
        width = left.get_width()
        for x in range(width):
            for y in range(left.get_height()):
                self.assertEqual(left.get_at((x, y)), right.get_at((width - 1 - x, y)))

    def test_missing_walk_falls_back_to_idle(self) -> None:
        idle_left = make_animation()
        animations = AnimationSet(make_animation())
        animations.add(IDLE, idle_left, Direction.LEFT)
        character = Character("Без ходьбы", animations)
        character.move(-1, 0)
        self.assertEqual(character.state, WALK)
        self.assertIs(character.player.animation, idle_left)
        character.update(1.0)

    def test_only_default_animation_is_enough(self) -> None:
        default = make_animation()
        character = Character("Только кадр по умолчанию", AnimationSet(default))
        character.move(0, 1)
        character.talk()
        character.set_state("surprised")
        self.assertEqual(character.state, "surprised")
        self.assertIs(character.player.animation, default)
        character.update(0.5)
        character.draw(pygame.Surface((32, 32)))

    def test_react_without_one_shot_animation_returns_at_once(self) -> None:
        # Реакции нет, замена — циклическая idle: ждать её конца бессмысленно.
        character = Character("Без реакции", labelled_animations()[0])
        character.react()
        self.assertEqual(character.state, IDLE)

    def test_custom_states_with_own_fallbacks(self) -> None:
        # Чучмек: удивление показывается как обычная реакция, своя есть только комическая.
        react, comic = make_animation(loop=False), make_animation(loop=False)
        animations = AnimationSet(make_animation(), fallbacks={"surprised": REACT})
        animations.add(REACT, react)
        animations.add("comic", comic)
        character = Character("Чучмек", animations)
        character.react("surprised")
        self.assertIs(character.player.animation, react)
        character.react("comic")
        self.assertIs(character.player.animation, comic)
        self.assertEqual(character.state, "comic")
        character.update(comic.duration + 0.01)
        self.assertEqual(character.state, IDLE)


if __name__ == "__main__":
    unittest.main()
