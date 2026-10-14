"""Проверки запуска: обычный режим для игрока и режим разработчика (--dev), путь от
вступления до закрытия игры через приложение."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import pygame  # noqa: E402

import main  # noqa: E402
from game.core.app import App  # noqa: E402
from game.debug.animation_demo import AnimationDemo  # noqa: E402
from game.debug.debug_screen import DebugScreen  # noqa: E402
from game.debug.dialogue_demo import DialogueDemo  # noqa: E402
from game.debug.sprite_gallery import SpriteGallery  # noqa: E402
from game.story import final_dialogue as text  # noqa: E402
from game.story import final_scene  # noqa: E402
from game.story.final_scene import DONE, FinalScene  # noqa: E402
from game.story.intro_scene import IntroScene  # noqa: E402
from game.trials.cakes_maze import MAZE_ROUTE  # noqa: E402
from game.trials.cakes_scene import CHECK_ROW, ESCAPE_SECONDS  # noqa: E402
from game.trials.forms_scene import CABINETS, GOOSE_POSITION, SLOT_XS, SLOT_Y  # noqa: E402
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import STATIONS, TABLE as SUSHI_TABLE  # noqa: E402
from game.world.hub import MOSAIC_CENTER, PORTALS, HubScene  # noqa: E402

PORTAL = {portal.id: portal.point for portal in PORTALS}


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


class LaunchTestCase(unittest.TestCase):
    dev_mode = False

    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App(dev_mode=self.dev_mode)
        self.app.running = True

    def tearDown(self) -> None:
        pygame.quit()

    def send(self, *events: pygame.event.Event) -> None:
        for event in events:
            pygame.event.post(event)
        self.app._handle_events()

    def press(self, code: int, scancode: int = 0) -> None:
        self.send(key(code, scancode), key(code, scancode, pygame.KEYUP))

    def press_e(self) -> None:
        self.press(pygame.K_e, pygame.KSCAN_E)

    def stack_names(self) -> list[str]:
        return [type(scene).__name__ for scene in self.app.scenes.stack]

    def finish_dialogue(self, scene) -> None:
        """Пролистывает текущий диалог сцены клавишей Enter через приложение."""
        script = scene.dialogue.script if scene.dialogue is not None else None
        for _ in range(200):
            if scene.dialogue is None or scene.dialogue.script is not script:
                return
            self.press(pygame.K_RETURN)
        raise AssertionError("диалог не заканчивается")

    def play_intro(self) -> IntroScene:
        """Вступление целиком, как игрок: ждать пауз и листать реплики Enter."""
        intro = self.app.scenes.current
        self.assertIsInstance(intro, IntroScene)
        for _ in range(20000):
            if self.app.scenes.current is not intro:
                return intro
            if intro.dialogue is not None:
                self.press(pygame.K_RETURN)
            self.app._update(1 / 30)
        raise AssertionError("вступление не закончилось")


class NormalLaunchTest(LaunchTestCase):
    def test_game_starts_with_the_intro_not_the_debug_screen(self) -> None:
        self.assertFalse(self.app.dev_mode)
        self.assertIsNone(self.app.screen)
        self.assertEqual(self.stack_names(), ["IntroScene"])
        self.assertFalse(any(isinstance(scene, DebugScreen) for scene in self.app.scenes.stack))
        self.app._update(0.5)
        self.app._draw()  # первая страница сказки рисуется в настоящий холст окна

    def test_debug_keys_do_nothing_for_the_player(self) -> None:
        for code, scancode in ((pygame.K_d, pygame.KSCAN_D), (pygame.K_a, pygame.KSCAN_A),
                               (pygame.K_p, pygame.KSCAN_P), (pygame.K_i, pygame.KSCAN_I),
                               (pygame.K_h, pygame.KSCAN_H)):
            self.press(code, scancode)
        self.assertEqual(self.stack_names(), ["IntroScene"])

    def test_intro_leads_to_the_hub_with_the_shared_progress(self) -> None:
        intro = self.play_intro()
        self.assertTrue(intro.completed)
        self.assertEqual(self.stack_names(), ["HubScene"])  # вступление заменено площадью, без экрана проверки
        hub = self.app.scenes.current
        self.assertIs(hub.progress, self.app.progress)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 0/3")

    def test_backspace_cannot_drop_the_player_out_of_the_story(self) -> None:
        intro = self.app.scenes.current
        self.press(pygame.K_BACKSPACE)  # во вступлении — некуда возвращаться: сказка продолжается
        self.assertIs(self.app.scenes.current, intro)
        self.assertTrue(self.app.running)
        self.play_intro()
        hub = self.app.scenes.current
        self.press(pygame.K_BACKSPACE)  # на площади — тоже
        self.assertIs(self.app.scenes.current, hub)
        self.assertTrue(self.app.running)
        hub.alice.set_position(*PORTAL["sushi"])
        self.press_e()
        self.press(pygame.K_BACKSPACE)  # а из испытания — обратно на ту же площадь
        self.assertIs(self.app.scenes.current, hub)

    def test_escape_f11_and_window_close_work_as_before(self) -> None:
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.app._update(0.2)
        self.app._draw()
        self.press(pygame.K_F11)
        self.assertFalse(self.app.display.is_fullscreen)
        self.press(pygame.K_ESCAPE)
        self.assertFalse(self.app.running)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)


class FullPlaythroughTest(LaunchTestCase):
    def play_sushi(self) -> None:
        sushi = self.app.scenes.current
        self.finish_dialogue(sushi)
        stations = {station.ingredient: station for station in STATIONS}
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                sushi.alice.set_position(*stations[ingredient].point)
                self.press_e()
                sushi.alice.set_position(SUSHI_TABLE.centerx, SUSHI_TABLE.top - 2)
                self.press_e()
            self.finish_dialogue(sushi)
        self.finish_dialogue(sushi)

    def play_forms(self) -> None:
        forms = self.app.scenes.current
        self.finish_dialogue(forms)
        cabinet = {cabinet.section.id: cabinet.point for cabinet in CABINETS}
        for section in ("holidays", "requests", "permits"):
            forms.alice.set_position(*cabinet[section])
            self.press_e()
            self.finish_dialogue(forms)
        for slot in (2, 0, 2, 1):
            forms.alice.set_position(SLOT_XS[slot], SLOT_Y)
            self.press_e()
        forms.alice.set_position(GOOSE_POSITION[0] - 22, GOOSE_POSITION[1])
        self.press_e()
        self.finish_dialogue(forms)
        self.finish_dialogue(forms)

    def play_cakes(self) -> None:
        cakes = self.app.scenes.current
        self.finish_dialogue(cakes)
        for row in (0, 4, 1, 3, CHECK_ROW):
            while cakes.cursor != row:
                self.press(pygame.K_DOWN)
            self.press_e()
        self.finish_dialogue(cakes)
        self.app._update(ESCAPE_SECONDS + 0.1)
        self.finish_dialogue(cakes)
        cakes.alice.set_position(*MAZE_ROUTE[-1])
        self.press_e()
        self.finish_dialogue(cakes)
        self.finish_dialogue(cakes)

    def enter(self, hub: HubScene, trial_id: str) -> None:
        hub.alice.set_position(*PORTAL[trial_id])
        self.press_e()
        self.assertIsNot(self.app.scenes.current, hub)

    def test_from_the_first_page_to_closing_the_game(self) -> None:
        self.play_intro()
        hub = self.app.scenes.current
        for trial_id, play in (("sushi", self.play_sushi), ("forms", self.play_forms), ("cakes", self.play_cakes)):
            self.enter(hub, trial_id)
            play()
            self.assertIs(self.app.scenes.current, hub)  # всегда та же площадь
        self.assertEqual(self.app.progress.completed, ("sushi", "forms", "cakes"))
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 3/3")
        for _ in range(20):
            self.app._update(0.5)  # сам финал не начинается
        self.assertEqual(self.stack_names(), ["HubScene"])

        hub.alice.set_position(*MOSAIC_CENTER)
        self.press_e()  # игрок сам восстанавливает последнюю страницу
        finale = self.app.scenes.current
        self.assertIsInstance(finale, FinalScene)
        self.assertIs(finale.progress, self.app.progress)
        for _ in range(400):
            if finale.phase == DONE:
                break
            self.press_e()
            self.app._update(0.4)
        self.assertEqual(finale.phase, DONE)
        self.assertFalse(self.app.running)  # последний экран штатно закрыл игру
        self.assertEqual(self.stack_names(), ["HubScene", "FinalScene"])
        self.assertEqual(self.app.progress.completed, ("sushi", "forms", "cakes"))
        # Порядок экранов финала — тот же, что задуман: ничего не пропущено и не переставлено.
        self.assertEqual(finale.shown, [
            "talk", "f_restored", "f_ending", "f_usually", "f_ours", "f_documents", "f_backside",
            "letter", "letter_0", "letter_1", "letter_2", "letter_3", "letter_4",
            "pause", "gift", "gift_reaction", "g_appeal", "credits", "the_end", "done",
        ])

    def test_finale_sequence_and_timings_are_unchanged(self) -> None:
        self.assertEqual(len(text.LETTER_PAGES), 5)  # пять листов письма, по два абзаца
        self.assertEqual([page.count("\n\n") + 1 for page in text.LETTER_PAGES], [2, 2, 2, 2, 2])
        self.assertEqual(
            (final_scene.ARRIVAL_SECONDS, final_scene.PAGE_FADE_SECONDS, final_scene.PAUSE_SECONDS,
             final_scene.CREDITS_SCROLL_SECONDS, final_scene.CREDITS_SECONDS, final_scene.CREDITS_SKIP_DELAY,
             final_scene.END_INPUT_DELAY),
            (3.6, 0.5, 2.5, 5.0, 8.0, 1.0, 1.5),
        )


class DevModeTest(LaunchTestCase):
    dev_mode = True

    def test_dev_mode_opens_the_debug_screen(self) -> None:
        self.assertTrue(self.app.dev_mode)
        self.assertIsInstance(self.app.screen, DebugScreen)
        self.assertEqual(self.stack_names(), ["DebugScreen"])

    def test_debug_tools_are_still_there(self) -> None:
        tools = (
            (pygame.K_d, pygame.KSCAN_D, DialogueDemo),
            (pygame.K_a, pygame.KSCAN_A, AnimationDemo),
            (pygame.K_p, pygame.KSCAN_P, SpriteGallery),
            (pygame.K_i, pygame.KSCAN_I, IntroScene),
            (pygame.K_h, pygame.KSCAN_H, HubScene),
        )
        for code, scancode, kind in tools:
            with self.subTest(tool=kind.__name__):
                self.press(code, scancode)
                self.assertIsInstance(self.app.scenes.current, kind)
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, self.app.screen)


class CommandLineTest(unittest.TestCase):
    def test_dev_flag(self) -> None:
        self.assertFalse(main.parse_args([]).dev)
        self.assertTrue(main.parse_args(["--dev"]).dev)
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            main.parse_args(["--unknown"])  # опечатка не запускает игру в неожиданном режиме

    def test_main_passes_the_mode_to_the_game(self) -> None:
        for argv, dev in (([], False), (["--dev"], True)):
            with self.subTest(argv=argv), mock.patch("game.core.app.run") as run:
                self.assertEqual(main.main(argv), 0)
                run.assert_called_once_with(dev_mode=dev)


if __name__ == "__main__":
    unittest.main()
