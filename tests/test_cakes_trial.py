"""Проверки сцены испытания тортов: рецепт, побег клубники, кладовая, награда, отмена, площадь."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story import cakes_dialogue as lines  # noqa: E402
from game.story.intro_dialogue import ALICE, CHUCHMEK  # noqa: E402
from game.trials.cakes_maze import MAZE_BOUNDS, MAZE_ROUTE, MAZE_START, MAZE_WALLS, STRAWBERRY_POSITION  # noqa: E402
from game.trials.cakes_puzzle import CORRECT_ORDER, START_ORDER, STEP_NAMES, STEP_SHORT_NAMES  # noqa: E402
from game.trials.cakes_scene import (  # noqa: E402
    ALICE_SPOT,
    BAKERY,
    BOARD,
    CAKES_SCENE,
    CHECK_ROW,
    CHUCHMEK_DOOR,
    CHUCHMEK_SPOT,
    DONE,
    ESCAPE_PHASE,
    ESCAPE_SECONDS,
    FINAL_PHASE,
    FOUND_PHASE,
    HUD_HEIGHT,
    INTRO_PHASE,
    MAZE,
    ORDERING,
    PANTRY,
    SPRITE_SIZE,
    STATUS_TOP,
    STRAWBERRY_COLOR,
    SUCCESS_PHASE,
    CakesTrialScene,
)
from game.trials.forms_scene import CABINETS, GOOSE_POSITION, SLOT_XS, SLOT_Y, FormsTrialScene  # noqa: E402
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import STATIONS, TABLE as SUSHI_TABLE, SushiTrialScene  # noqa: E402
from game.world.hub import PORTALS, TRIAL_SCENES, HubScene  # noqa: E402
from game.world.progress import GameProgress  # noqa: E402

DT = 1 / 60
WIDTH = config.LOGICAL_SIZE[0]
PORTAL = {portal.id: portal.point for portal in PORTALS}
# Два обмена превращают обратный порядок в правильный: 1 ↔ 5, затем 2 ↔ 4.
SOLVING_PICKS = (0, 4, 1, 3)


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press(scene: Scene, code: int, scancode: int = 0) -> None:
    scene.handle_event(key(code, scancode))
    scene.handle_event(key(code, scancode, pygame.KEYUP))


def press_e(scene: Scene) -> None:
    press(scene, pygame.K_e, pygame.KSCAN_E)


def finish_dialogue(scene: Scene) -> list[str]:
    """Пролистывает текущий диалог клавишей Enter (только его, не следующий) и возвращает показанные реплики."""
    shown = []
    script = scene.dialogue.script if scene.dialogue is not None else None
    while scene.dialogue is not None and scene.dialogue.script is script:
        if len(shown) > 2 * len(script.nodes):  # сломанный диалог — провал теста, а не зависание
            raise AssertionError(f"диалог не заканчивается: {shown}")
        shown.append(scene.dialogue.node.id)
        press(scene, pygame.K_RETURN)  # дописать
        if scene.dialogue is not None and scene.dialogue.script is script:
            press(scene, pygame.K_RETURN)  # дальше
    return shown


def move_cursor(scene: CakesTrialScene, row: int) -> None:
    """Стрелками вверх/вниз — до нужной строки доски."""
    for _ in range(2 * (CHECK_ROW + 1)):
        if scene.cursor == row:
            return
        press(scene, pygame.K_DOWN if scene.cursor < row else pygame.K_UP)
    raise AssertionError(f"курсор не дошёл до строки {row}")


def choose(scene: CakesTrialScene, row: int) -> None:
    move_cursor(scene, row)
    press_e(scene)


def check_recipe(scene: CakesTrialScene) -> None:
    choose(scene, CHECK_ROW)


def solve_recipe(scene: CakesTrialScene) -> None:
    for row in SOLVING_PICKS:
        choose(scene, row)
    check_recipe(scene)


def to_pantry(scene: CakesTrialScene) -> None:
    """От вступления до кладовой: рецепт, реакция, побег, реплики о побеге."""
    finish_dialogue(scene)
    solve_recipe(scene)
    finish_dialogue(scene)  # реакция Чучмека
    scene.update(ESCAPE_SECONDS + 0.1)  # клубника убегает
    finish_dialogue(scene)  # «Клубника сбежала!»


def walk_route(scene: CakesTrialScene) -> None:
    """Проводит Алису по MAZE_ROUTE стрелками, как игрок."""
    alice = scene.alice
    for x, y in MAZE_ROUTE[1:]:
        horizontal = abs(x - alice.x) > abs(y - alice.y)
        if horizontal:
            code = pygame.K_RIGHT if x > alice.x else pygame.K_LEFT
        else:
            code = pygame.K_DOWN if y > alice.y else pygame.K_UP
        scene.handle_event(key(code))
        for _ in range(600):
            remaining = abs(x - alice.x) if horizontal else abs(y - alice.y)
            if remaining <= 1.1:
                break
            before = (alice.x, alice.y)
            scene.update(DT)
            if (alice.x, alice.y) == before:
                raise AssertionError(f"Алиса застряла в {before} по пути к {(x, y)}")
        scene.handle_event(key(code, event_type=pygame.KEYUP))


def catch_strawberry(scene: CakesTrialScene) -> None:
    scene.alice.set_position(*MAZE_ROUTE[-1])
    press_e(scene)


def play(scene: CakesTrialScene, stop_before_final_end: bool = False) -> None:
    """Проходит испытание целиком; кладовую — коротким путём (сам маршрут проверяется отдельно)."""
    to_pantry(scene)
    catch_strawberry(scene)
    finish_dialogue(scene)  # реакция на находку
    if not stop_before_final_end:
        finish_dialogue(scene)  # финал


def hold(scene: CakesTrialScene, codes: list[int], frames: int) -> None:
    for code in codes:
        scene.handle_event(key(code))
    for _ in range(frames):
        scene.update(DT)
    for code in codes:
        scene.handle_event(key(code, event_type=pygame.KEYUP))


class TrialTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.progress = GameProgress()
        self.manager = SceneManager()
        self.hub = self.manager.push(HubScene(self.progress))
        self.scene = self.manager.push(CakesTrialScene(self.progress))

    def tearDown(self) -> None:
        pygame.quit()


class IntroTest(TrialTestCase):
    def test_starts_in_the_bakery_with_confident_chuchmek(self) -> None:
        self.assertEqual(self.scene.phase, INTRO_PHASE)
        self.assertEqual(self.scene.area, BAKERY)
        self.assertIs(self.scene.dialogue.script, lines.INTRO)
        self.assertEqual(self.scene.dialogue.node.speaker, CHUCHMEK)
        self.assertEqual(self.scene.chuchmek_pose, "clipboard_confident")
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), ALICE_SPOT)
        self.assertEqual(self.scene.recipe.order, START_ORDER)

    def test_intro_lines(self) -> None:
        shown = finish_dialogue(self.scene)
        said = [(lines.INTRO.nodes[node_id].speaker, lines.INTRO.nodes[node_id].text) for node_id in shown]
        self.assertEqual(said[:3], [
            (CHUCHMEK, "Всё готово! Я лично проверил рецепт, ингредиенты и саму реальность."),
            (ALICE, "Почему противень висит на потолке?"),
            (CHUCHMEK, "Экономия места. И тесто теперь не падает вниз. Обычно."),
        ])
        self.assertIn("Здесь всё наоборот", said[3][1])
        self.assertIn("в обратном порядке", said[4][1])
        self.assertEqual(self.scene.phase, ORDERING)
        self.assertEqual(self.scene.task_text(), "Задача: расставь этапы рецепта по порядку")
        self.assertEqual(self.scene.part_text(), "Часть 1 из 2 — рецепт")

    def test_keys_during_dialogue_touch_neither_board_nor_alice(self) -> None:
        for code in (pygame.K_DOWN, pygame.K_UP, pygame.K_LEFT):
            press(self.scene, code)
        self.scene.handle_event(key(pygame.K_RIGHT))
        self.scene.update(1.0)
        self.scene.handle_event(key(pygame.K_RIGHT, event_type=pygame.KEYUP))
        self.assertEqual(self.scene.cursor, 0)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), ALICE_SPOT)
        press_e(self.scene)  # E листает реплику
        self.assertIsNone(self.scene.recipe.picked)
        self.assertEqual(self.scene.recipe.order, START_ORDER)


class RecipeTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)

    def test_board_shows_reversed_steps_and_controls(self) -> None:
        self.assertEqual(self.scene.recipe.order, tuple(reversed(CORRECT_ORDER)))
        self.assertEqual(self.scene.status_text(), "Стрелки — выбрать этап   E — взять   Backspace — уйти")
        move_cursor(self.scene, CHECK_ROW)
        self.assertEqual(self.scene.status_text(), "E — проверить рецепт   Стрелки — к этапам")

    def test_cursor_moves_with_arrows_and_ws_and_wraps(self) -> None:
        press(self.scene, pygame.K_DOWN)
        self.assertEqual(self.scene.cursor, 1)
        press(self.scene, ord("ы"), pygame.KSCAN_S)  # S в русской раскладке
        self.assertEqual(self.scene.cursor, 2)
        press(self.scene, pygame.K_w, pygame.KSCAN_W)
        self.assertEqual(self.scene.cursor, 1)
        press(self.scene, pygame.K_UP)
        press(self.scene, pygame.K_UP)
        self.assertEqual(self.scene.cursor, CHECK_ROW)  # с первой строки — на кнопку проверки
        press(self.scene, pygame.K_DOWN)
        self.assertEqual(self.scene.cursor, 0)
        for code in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):  # по одной, чтобы не гасили друг друга
            hold(self.scene, [code], 30)
            self.assertEqual((self.scene.alice.x, self.scene.alice.y), ALICE_SPOT)  # Алиса не ходит по кондитерской
            self.assertFalse(self.scene.alice.is_moving)

    def test_pick_and_swap_two_steps(self) -> None:
        choose(self.scene, 0)
        self.assertEqual(self.scene.recipe.picked, 0)
        self.assertEqual(self.scene.held_text(), "Взят этап: Крем")
        self.assertEqual(self.scene.status_text(), "Взят этап: Крем")
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "E — положить обратно   Стрелки — с чем поменять")
        move_cursor(self.scene, 4)
        self.assertEqual(self.scene.status_text(), "Стрелки — куда поставить   E — поменять местами")
        press(self.scene, pygame.K_RETURN)  # Enter работает так же, как E
        self.assertEqual(self.scene.recipe.order, ("ingredients", "cool", "bake", "dough", "decorate"))
        self.assertEqual(self.scene.status_text(), "Поменяла местами: Крем и Ингредиенты")
        self.assertEqual(self.scene.held_text(), "")
        choose(self.scene, 2)
        choose(self.scene, 2)  # тот же этап — положить обратно
        self.assertIsNone(self.scene.recipe.picked)
        self.assertEqual(self.scene.status_text(), "Положила обратно: Выпечка")

    def test_wrong_order_is_not_accepted_and_game_goes_on(self) -> None:
        check_recipe(self.scene)
        self.assertEqual(self.scene.phase, ORDERING)
        self.assertEqual(self.scene.dialogue.node.speaker, CHUCHMEK)
        self.assertEqual(self.scene.chuchmek_pose, "confused")
        shown = finish_dialogue(self.scene)
        self.assertEqual(shown, ["wrong_joke", "wrong_hint"])
        self.assertEqual(lines.wrong_order(1, 0).nodes["wrong_hint"].speaker, ALICE)  # ошибку замечает Алиса
        self.assertEqual(self.scene.recipe.order, START_ORDER)  # порядок не сброшен
        choose(self.scene, 0)
        choose(self.scene, 4)  # ингредиенты первыми, остальное ещё перепутано
        check_recipe(self.scene)
        first_joke = self.scene.dialogue.node.text
        press(self.scene, pygame.K_RETURN)
        press(self.scene, pygame.K_RETURN)
        self.assertIn("замешивают тесто", self.scene.dialogue.node.text)  # подсказка про вторую позицию
        finish_dialogue(self.scene)
        self.assertNotEqual(first_joke, lines.WRONG_JOKES[0])  # вторая попытка — другая шутка
        self.assertEqual(self.scene.phase, ORDERING)
        self.assertEqual(self.progress.fragments, 0)
        choose(self.scene, 1)
        choose(self.scene, 3)
        check_recipe(self.scene)
        self.assertEqual(self.scene.phase, SUCCESS_PHASE)

    def test_correct_order_gives_reaction_but_no_fragment(self) -> None:
        solve_recipe(self.scene)
        self.assertTrue(self.scene.recipe.solved)
        self.assertEqual(self.scene.recipe.order, CORRECT_ORDER)
        self.assertEqual(self.scene.phase, SUCCESS_PHASE)
        self.assertIs(self.scene.dialogue.script, lines.SUCCESS)
        self.assertIn("духовку нельзя включать после украшения кремом", self.scene.dialogue.node.text)
        self.assertEqual(self.progress.fragments, 0)
        self.assertFalse(self.progress.is_completed("cakes"))

    def test_solved_recipe_ignores_further_board_input(self) -> None:
        solve_recipe(self.scene)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, ESCAPE_PHASE)
        for code in (pygame.K_UP, pygame.K_e, pygame.K_RETURN, pygame.K_DOWN):
            press(self.scene, code)
        self.scene.activate()  # и прямой вызов тоже ничего не делает
        self.assertEqual(self.scene.recipe.order, CORRECT_ORDER)
        self.assertEqual(self.scene.phase, ESCAPE_PHASE)
        self.assertIsNone(self.scene.dialogue)  # успех не запустился повторно
        self.assertEqual(self.scene.recipe.failed_checks, 0)


class EscapeTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)
        solve_recipe(self.scene)
        finish_dialogue(self.scene)

    def test_strawberry_runs_away_then_chuchmek_panics(self) -> None:
        self.assertEqual(self.scene.phase, ESCAPE_PHASE)
        self.assertEqual(self.scene.task_text(), "Клубника сбежала!")
        start = self.scene.strawberry_position()
        self.scene.update(ESCAPE_SECONDS / 2)
        middle = self.scene.strawberry_position()
        self.assertGreater(middle[0], start[0])
        self.assertIsNone(self.scene.dialogue)  # пока бежит — без реплик
        self.scene.update(ESCAPE_SECONDS / 2 + 0.01)
        self.assertGreater(self.scene.strawberry_position()[0], WIDTH)  # убежала за край
        self.assertIs(self.scene.dialogue.script, lines.ESCAPE)
        self.assertEqual(self.scene.dialogue.node.text, "Клубника сбежала!")
        self.assertEqual(self.scene.chuchmek_pose, "arms_up_panic")
        shown = finish_dialogue(self.scene)
        texts = [lines.ESCAPE.nodes[node_id].text for node_id in shown]
        self.assertEqual(texts[1:3], ["Она же клубника.", "Именно. У неё ни прописки, ни чувства ответственности."])
        self.assertIn("Найди её", texts[-1])  # явная подсказка, что делать дальше
        self.assertEqual(self.scene.phase, MAZE)
        self.assertEqual(self.scene.area, PANTRY)
        self.assertEqual(self.scene.task_text(), "Задача: найди сбежавшую клубнику")
        self.assertEqual(self.scene.part_text(), "Часть 2 из 2 — клубника")
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), MAZE_START)
        self.assertEqual(self.progress.fragments, 0)

    def test_keys_during_escape_do_nothing(self) -> None:
        self.scene.handle_event(key(pygame.K_DOWN))  # зажата и не отпущена
        press_e(self.scene)
        self.scene.update(ESCAPE_SECONDS + 0.1)
        finish_dialogue(self.scene)
        self.scene.update(0.5)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), MAZE_START)  # зажатая стрелка не ведёт Алису
        self.assertFalse(self.scene.strawberry_found)

    def test_long_frame_does_not_skip_the_escape_lines(self) -> None:
        self.scene.update(5.0)
        self.assertIs(self.scene.dialogue.script, lines.ESCAPE)
        self.assertEqual(self.scene.dialogue.node.id, "e_escaped")


class MazeTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        to_pantry(self.scene)

    def test_walk_the_maze_with_keys_and_catch_the_strawberry(self) -> None:
        self.assertEqual(self.scene.status_text(), "Кладовая: найди клубнику в дальнем углу")
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(),
                         "Стрелки/WASD — идти   E — поймать клубнику   Backspace — уйти")
        walk_route(self.scene)
        self.assertTrue(self.scene.near_strawberry())
        self.assertEqual(self.scene.status_text(), "Клубника   E — поймать")
        press_e(self.scene)
        self.assertTrue(self.scene.strawberry_found)
        self.assertEqual(self.scene.phase, FOUND_PHASE)
        self.assertIs(self.scene.dialogue.script, lines.FOUND)
        self.assertEqual(self.progress.fragments, 0)  # находка — ещё не награда

    def test_strawberry_cannot_be_caught_from_afar_or_through_a_wall(self) -> None:
        last_wall = MAZE_WALLS[-1].rect
        for spot in (MAZE_START, (last_wall.left - 6, STRAWBERRY_POSITION[1]), (232, 152)):
            self.scene.alice.set_position(*spot)
            self.assertTrue(self.scene.collision.is_free(*spot))
            press_e(self.scene)
            self.assertFalse(self.scene.strawberry_found, spot)
            self.assertEqual(self.scene.phase, MAZE)
            self.assertEqual(self.scene.status_text(), "Клубника не здесь — она в дальнем углу кладовой")

    def test_walls_stop_alice(self) -> None:
        first_wall = MAZE_WALLS[0].rect
        self.scene.alice.set_position(MAZE_START[0], 100)
        self.scene.handle_event(key(pygame.K_RIGHT))
        for _ in range(5):
            self.scene.update(0.5)  # крупные шаги тоже не «протаскивают» сквозь стеллаж
        self.scene.handle_event(key(pygame.K_RIGHT, event_type=pygame.KEYUP))
        self.assertAlmostEqual(self.scene.alice.x, first_wall.left - 6)

    def test_alice_stays_on_screen_and_off_the_walls(self) -> None:
        for keys in ([pygame.K_UP], [pygame.K_DOWN], [pygame.K_LEFT], [pygame.K_RIGHT, pygame.K_DOWN],
                     [pygame.K_RIGHT, pygame.K_UP]):
            scene = CakesTrialScene()
            to_pantry(scene)
            scene.alice.set_position(116, 110)
            for code in keys:
                scene.handle_event(key(code))
            for _ in range(300):
                scene.update(DT)
                rect = scene.alice.rect
                self.assertGreaterEqual(rect.top, HUD_HEIGHT)
                self.assertLessEqual(rect.bottom, STATUS_TOP)
                self.assertGreaterEqual(rect.left, 0)
                self.assertLessEqual(rect.right, WIDTH)
                self.assertTrue(scene.collision.is_free(scene.alice.x, scene.alice.y))

    def test_caught_strawberry_floats_above_alice(self) -> None:
        catch_strawberry(self.scene)
        self.scene.update(0.25)
        self.scene.draw(self.canvas)
        x, y = self.scene.held_icon_center()
        self.assertGreaterEqual(y - 9, HUD_HEIGHT)
        around = {tuple(self.canvas.get_at((x + dx, y + dy)))[:3] for dx in range(-3, 4) for dy in range(-2, 3)}
        self.assertIn(STRAWBERRY_COLOR, around)
        self.assertIsNone(self.scene.strawberry_position())  # в кладовой её больше нет


class RewardTest(TrialTestCase):
    def test_back_at_the_table_for_the_final_lines(self) -> None:
        play(self.scene, stop_before_final_end=True)
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertEqual(self.scene.area, BAKERY)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), ALICE_SPOT)
        self.assertIsNone(self.scene.alice.collider)
        self.assertIsNotNone(self.scene.strawberry_position())  # на вершине торта
        texts = [lines.FINAL.nodes[node_id].text for node_id in finish_dialogue(self.scene)]
        self.assertEqual(texts[:3], [
            "Нашла. Теперь можно наконец закончить торт?",
            "Конечно! Осталось только убедить клубнику, что она часть десерта, а не руководитель проекта.",
            "По-моему, она уже назначила себя руководителем.",
        ])

    def test_fragment_only_after_final_line(self) -> None:
        to_pantry(self.scene)
        self.assertEqual(self.progress.fragments, 0)  # рецепт решён, кладовая открыта
        catch_strawberry(self.scene)
        self.assertEqual(self.progress.fragments, 0)  # клубника найдена
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertEqual(self.progress.fragments, 0)  # финальный диалог ещё идёт
        finish_dialogue(self.scene)
        self.assertEqual(self.progress.completed, ("cakes",))
        self.assertTrue(self.scene.reward_given)
        self.assertTrue(self.scene.completed)
        self.assertEqual(self.scene.phase, DONE)
        self.assertIs(self.manager.current, self.hub)  # та же площадь, не новая

    def test_cancel_returns_to_hub_without_reward_at_any_stage(self) -> None:
        stages = {
            "вступление": lambda scene: None,
            "рецепт": lambda scene: (finish_dialogue(scene), choose(scene, 0)),
            "неверный рецепт": lambda scene: (finish_dialogue(scene), check_recipe(scene)),
            "реакция на успех": lambda scene: (finish_dialogue(scene), solve_recipe(scene)),
            "побег": lambda scene: (finish_dialogue(scene), solve_recipe(scene), finish_dialogue(scene),
                                    scene.update(0.5)),
            "реплики о побеге": lambda scene: (finish_dialogue(scene), solve_recipe(scene), finish_dialogue(scene),
                                               scene.update(ESCAPE_SECONDS + 0.1)),
            "кладовая": to_pantry,
            "находка": lambda scene: (to_pantry(scene), catch_strawberry(scene)),
            "финальный диалог": lambda scene: play(scene, stop_before_final_end=True),
        }
        for stage, prepare in stages.items():
            with self.subTest(stage=stage):
                progress = GameProgress()
                manager = SceneManager()
                manager.register(CAKES_SCENE, lambda: CakesTrialScene(progress))
                hub = manager.push(HubScene(progress))
                hub.alice.set_position(*PORTAL["cakes"])
                hub.interact()  # вход через правый портал площади
                scene = manager.current
                self.assertIsInstance(scene, CakesTrialScene)
                prepare(scene)
                press(scene, pygame.K_BACKSPACE)
                self.assertIs(manager.current, hub)
                self.assertEqual(progress.completed, ())
                self.assertFalse(scene.completed)
                self.assertIn("«Торты» прервано", hub.toast)

    def test_second_run_gives_no_extra_fragment(self) -> None:
        play(self.scene)
        second = self.manager.push(CakesTrialScene(self.progress))
        self.assertEqual(second.recipe.order, START_ORDER)  # повтор начинается с начала, без «хвостов»
        play(second)
        self.assertTrue(second.completed)
        self.assertFalse(second.reward_given)
        self.assertEqual(self.progress.completed, ("cakes",))

    def test_only_cakes_is_marked(self) -> None:
        play(self.scene)
        self.assertTrue(self.progress.is_completed("cakes"))
        self.assertFalse(self.progress.is_completed("sushi"))
        self.assertFalse(self.progress.is_completed("forms"))
        self.assertFalse(self.progress.has_all_fragments)

    def test_earlier_fragments_stay_and_hub_shows_three_of_three(self) -> None:
        self.progress.complete("sushi")  # как будто пройдены раньше (по-настоящему — в AppIntegrationTest)
        self.progress.complete("forms")
        self.manager.pop()
        self.manager.register(CAKES_SCENE, lambda: CakesTrialScene(self.progress))
        self.hub.alice.set_position(*PORTAL["cakes"])
        self.hub.interact()
        play(self.manager.current)
        self.assertIs(self.manager.current, self.hub)
        self.assertEqual(self.progress.completed, ("sushi", "forms", "cakes"))
        self.assertTrue(self.progress.has_all_fragments)
        self.assertEqual(self.hub.fragments_text(), "Фрагменты праздника: 3/3")
        self.assertIn("Теперь 3/3", self.hub.toast)
        self.assertEqual(len(self.manager.stack), 1)  # финальная локация сама не открылась


class LayoutTest(TrialTestCase):
    def test_dialogue_box_never_covers_characters_or_the_board(self) -> None:
        box = DialogueBox()
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in lines.all_scripts() for node in script.nodes.values())
        for y in (ALICE_SPOT[1], CHUCHMEK_SPOT[1], CHUCHMEK_DOOR[1], MAZE_START[1], MAZE_ROUTE[-1][1],
                  STRAWBERRY_POSITION[1] + 5, BOARD.bottom):
            self.assertLessEqual(y, lowest_box)

    def test_pantry_keeps_alice_between_interface_strips(self) -> None:
        self.assertGreaterEqual(MAZE_BOUNDS.top + 6 - SPRITE_SIZE, HUD_HEIGHT)  # голова не под верхней полосой
        self.assertLessEqual(MAZE_BOUNDS.bottom, STATUS_TOP)
        self.assertGreaterEqual(MAZE_BOUNDS.left + 6 - SPRITE_SIZE // 2, 0)
        self.assertLessEqual(MAZE_BOUNDS.right - 6 + SPRITE_SIZE // 2, WIDTH)

    def test_texts_fit_on_screen(self) -> None:
        font = self.scene._font
        for phase_task in ("Задача: расставь этапы рецепта по порядку", "Задача: найди сбежавшую клубнику"):
            self.assertLessEqual(font.size(phase_task)[0], WIDTH - 8)
        widest_held = max(font.size(f"Взят этап: {name}")[0] for name in STEP_SHORT_NAMES.values())
        self.assertLessEqual(font.size("Часть 2 из 2 — клубника")[0] + widest_held, WIDTH - 16)
        statuses = ["Стрелки — выбрать этап   E — взять   Backspace — уйти",
                    "Стрелки — куда поставить   E — поменять местами",
                    "E — положить обратно   Стрелки — с чем поменять", "E — проверить рецепт   Стрелки — к этапам",
                    "Стрелки/WASD — идти   E — поймать клубнику   Backspace — уйти",
                    "Клубника не здесь — она в дальнем углу кладовой", "Кладовая: найди клубнику в дальнем углу"]
        names = list(STEP_SHORT_NAMES.values())
        statuses += [f"Поменяла местами: {a} и {b}" for a in names for b in names]
        for text in statuses:
            self.assertLessEqual(font.size(text)[0], WIDTH - 8, text)
        row = self.scene.row_rect(0)
        for name in STEP_NAMES.values():  # полные названия этапов помещаются в строку доски
            self.assertLessEqual(28 + font.size(name)[0], row.width, name)
        self.assertLessEqual(self.scene.row_rect(CHECK_ROW).bottom, BOARD.bottom)

    def test_chuchmek_is_drawn_from_manifest_without_mirroring(self) -> None:
        sprites = load_character_sprites(CHARACTERS_DIR / "chuchmek")
        expected = pygame.transform.scale(sprites.frame("clipboard_confident").image, (SPRITE_SIZE, SPRITE_SIZE))
        actual = self.scene._chuchmek_image()
        self.assertEqual(pygame.image.tobytes(actual, "RGBA"), pygame.image.tobytes(expected, "RGBA"))
        frames = {frame.id for frame in sprites.frames}
        poses = set(lines.CHUCHMEK_POSES.values()) | {lines.CHUCHMEK_IDLE_POSE, lines.CHUCHMEK_PANIC_POSE}
        self.assertLessEqual(poses, frames)  # все позы есть в манифесте

    def test_draws_every_phase(self) -> None:
        scene = self.scene
        scene.draw(self.canvas)
        finish_dialogue(scene)
        choose(scene, 0)
        scene.draw(self.canvas)
        check_recipe(scene)
        scene.draw(self.canvas)
        finish_dialogue(scene)
        solve_recipe(scene)
        scene.draw(self.canvas)
        finish_dialogue(scene)
        for _ in range(4):
            scene.update(ESCAPE_SECONDS / 4)
            scene.draw(self.canvas)
        finish_dialogue(scene)
        scene.draw(self.canvas)
        catch_strawberry(scene)
        scene.draw(self.canvas)
        finish_dialogue(scene)
        scene.draw(self.canvas)

    def test_missing_sprites_use_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            scene = CakesTrialScene(characters_dir=Path(empty))
            scene.draw(self.canvas)
            play(scene)
            self.assertTrue(scene.completed)


def play_sushi(sushi: SushiTrialScene) -> None:
    """Суши теми же клавишами, что и в их тестах."""
    finish_dialogue(sushi)
    stations = {station.ingredient: station for station in STATIONS}
    for recipe in RECIPES:
        for ingredient in recipe.ingredients:
            sushi.alice.set_position(*stations[ingredient].point)
            press_e(sushi)
            sushi.alice.set_position(SUSHI_TABLE.centerx, SUSHI_TABLE.top - 2)
            press_e(sushi)
        finish_dialogue(sushi)
    finish_dialogue(sushi)


def play_forms(forms: FormsTrialScene) -> None:
    """Формуляры: три находки, два обмена на столе, сдача гусю."""
    finish_dialogue(forms)
    cabinet = {cabinet.section.id: cabinet.point for cabinet in CABINETS}
    for section in ("holidays", "requests", "permits"):
        forms.alice.set_position(*cabinet[section])
        press_e(forms)
        finish_dialogue(forms)
    for slot in (2, 0, 2, 1):
        forms.alice.set_position(SLOT_XS[slot], SLOT_Y)
        press_e(forms)
    forms.alice.set_position(GOOSE_POSITION[0] - 22, GOOSE_POSITION[1])
    press_e(forms)
    finish_dialogue(forms)
    finish_dialogue(forms)


class AppIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App(dev_mode=True)  # экран проверки и его клавиши

    def tearDown(self) -> None:
        pygame.quit()

    def send(self, *events: pygame.event.Event) -> None:
        for event in events:
            pygame.event.post(event)
        self.app._handle_events()

    def press(self, code: int, scancode: int = 0) -> None:
        self.send(key(code, scancode), key(code, scancode, pygame.KEYUP))

    def open_hub(self) -> HubScene:
        self.press(pygame.K_h, pygame.KSCAN_H)
        return self.app.scenes.current

    def enter_portal(self, hub: HubScene, trial_id: str) -> Scene:
        hub.alice.set_position(*PORTAL[trial_id])
        self.press(pygame.K_e, pygame.KSCAN_E)
        return self.app.scenes.current

    def test_every_portal_opens_its_own_trial(self) -> None:
        self.assertEqual(CAKES_SCENE, "trial_cakes")
        self.assertEqual(CAKES_SCENE, TRIAL_SCENES["cakes"])
        hub = self.open_hub()
        for trial_id, scene_type in (("sushi", SushiTrialScene), ("forms", FormsTrialScene),
                                     ("cakes", CakesTrialScene)):
            with self.subTest(trial=trial_id):
                self.assertTrue(self.app.scenes.is_registered(TRIAL_SCENES[trial_id]))
                trial = self.enter_portal(hub, trial_id)
                self.assertIsInstance(trial, scene_type)
                self.assertIs(trial.progress, self.app.progress)
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, hub)

    def test_right_portal_opens_cakes_and_success_returns_to_the_same_hub(self) -> None:
        hub = self.open_hub()
        trial = self.enter_portal(hub, "cakes")
        self.assertEqual([type(scene).__name__ for scene in self.app.scenes.stack],
                         ["DebugScreen", "HubScene", "CakesTrialScene"])
        play(trial)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 1/3")
        self.assertIn("Получен фрагмент праздника! Теперь 1/3", hub.toast)
        self.assertIn("Торты (пройдено)", hub.nearby().prompt)
        hub.draw(self.app.display.canvas)

    def test_all_three_trials_give_three_of_three_and_no_finale(self) -> None:
        hub = self.open_hub()
        play_sushi(self.enter_portal(hub, "sushi"))
        play_forms(self.enter_portal(hub, "forms"))
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 2/3")
        cakes = self.enter_portal(hub, "cakes")
        to_pantry(cakes)
        walk_route(cakes)  # кладовая — пешком по маршруту
        press_e(cakes)
        finish_dialogue(cakes)
        finish_dialogue(cakes)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 3/3")
        self.assertIn("Теперь 3/3", hub.toast)
        self.assertEqual(self.app.progress.completed, ("sushi", "forms", "cakes"))
        self.assertTrue(self.app.progress.has_all_fragments)
        self.assertEqual([type(scene).__name__ for scene in self.app.scenes.stack], ["DebugScreen", "HubScene"])
        hub.update(1.0)
        self.assertIs(self.app.scenes.current, hub)  # и потом площадь никуда не переключается
        hub.draw(self.app.display.canvas)

    def test_cancel_from_portal_gives_nothing(self) -> None:
        hub = self.open_hub()
        trial = self.enter_portal(hub, "cakes")
        to_pantry(trial)
        self.press(pygame.K_BACKSPACE)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.fragments, 0)
        self.assertIn("прервано", hub.toast)

    def test_replay_from_portal_keeps_one_fragment(self) -> None:
        hub = self.open_hub()
        for _ in range(2):
            trial = self.enter_portal(hub, "cakes")
            self.assertEqual(trial.phase, INTRO_PHASE)  # каждый заход — с начала
            self.assertFalse(trial.recipe.solved)
            play(trial)
            self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.fragments, 1)
        self.assertIn("уже пройдено", hub.toast)

    def test_escape_f11_and_close_inside_trial(self) -> None:
        trial = self.enter_portal(self.open_hub(), "cakes")
        to_pantry(trial)
        self.app.running = True
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.app.scenes.update(0.2)
        self.app.scenes.draw(self.app.display.canvas)
        self.app.display.present()
        self.press(pygame.K_F11)
        self.press(pygame.K_ESCAPE)  # ESC — выход из игры, а не отмена испытания
        self.assertFalse(self.app.running)
        self.assertIs(self.app.scenes.current, trial)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)

    def test_keys_go_through_the_app(self) -> None:
        trial = self.enter_portal(self.open_hub(), "cakes")
        for _ in range(2 * len(lines.INTRO.nodes)):  # каждая реплика: дописать и дальше
            self.press(pygame.K_e, pygame.KSCAN_E)
        self.assertEqual(trial.phase, ORDERING)
        self.press(ord("ы"), pygame.KSCAN_S)  # русская раскладка: S — вниз
        self.assertEqual(trial.cursor, 1)
        self.press(ord("у"), pygame.KSCAN_E)  # и E — та же физическая клавиша
        self.assertEqual(trial.recipe.picked, 1)
        # Зажатая стрелка: автоповтор не уводит курсор дальше одного шага.
        self.send(key(pygame.K_DOWN), key(pygame.K_DOWN), key(pygame.K_DOWN))
        self.assertEqual(trial.cursor, 2)


if __name__ == "__main__":
    unittest.main()
