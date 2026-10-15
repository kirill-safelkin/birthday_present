"""Проверки сцены испытания тортов: рецепт, побег клубники, кладовая, награда, отмена, площадь."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.hires import HiResLayer, SpriteCommand, TextCommand, ViewTransform, scale_sprite  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story import cakes_dialogue as lines  # noqa: E402
from game.story.intro_dialogue import ALICE, CHUCHMEK  # noqa: E402
from game.trials.cakes_maze import MAZE_BOUNDS, MAZE_START, generate_layout, line_of_sight  # noqa: E402
from game.trials.cakes_puzzle import CORRECT_ORDER, START_ORDER, STEP_NAMES, STEP_SHORT_NAMES  # noqa: E402
from game.trials.strawberry_chase import CAUGHT, RUNNING, TALKING  # noqa: E402
from game.trials.cakes_scene import (  # noqa: E402
    ALICE_SPOT,
    BAKERY,
    BOARD,
    CAKES_SCENE,
    CATCH_REACH,
    CHASE_TOAST,
    CHECK_ROW,
    CHUCHMEK_DOOR,
    CHUCHMEK_SPOT,
    DONE,
    ESCAPE_PHASE,
    ESCAPE_SECONDS,
    FAR_TOAST,
    FINAL_PHASE,
    FOUND_PHASE,
    GREAT_CAKE_SIZE,
    GREAT_CAKE_SPOT,
    HUD_HEIGHT,
    INTRO_PHASE,
    MAZE,
    ORDERING,
    PANTRY,
    PANTRY_DOOR,
    SPEECH_AREA,
    SPEECH_STYLE,
    SPRITE_SIZE,
    STATUS_TOP,
    STRAWBERRY_COLOR,
    STRAWBERRY_ON_TABLE,
    SUCCESS_PHASE,
    TABLE_AREA,
    TOAST_SECONDS,
    WALK_SPEED,
    CakesTrialScene,
    draw_strawberry,
)
from game.trials.forms_scene import CABINETS, GOOSE_POSITION, SLOT_XS, SLOT_Y, FormsTrialScene  # noqa: E402
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import STATIONS, TABLE as SUSHI_TABLE, SushiTrialScene  # noqa: E402
from game.world.collision import FOOT_SIZE  # noqa: E402
from game.world.hub import PORTALS, TRIAL_SCENES, HubScene  # noqa: E402
from game.world.progress import GameProgress  # noqa: E402

DT = 1 / 60
WIDTH = config.LOGICAL_SIZE[0]
SEED = 2026  # раскладка кладовой и погоня в большинстве тестов — одни и те же
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


def listen_to_great_cake(scene: CakesTrialScene) -> list[str]:
    """Если после перестановки заговорил Тортище — дослушать его Enter, как игрок (первый ответ)."""
    if scene.dialogue is not None and scene.dialogue.script is lines.GREAT_CAKE_TALK:
        return finish_dialogue(scene)
    return []


def move_cursor(scene: CakesTrialScene, row: int) -> None:
    """Стрелками вверх/вниз — до нужной строки доски (сначала дослушав Тортища, если он говорит)."""
    listen_to_great_cake(scene)
    for _ in range(2 * (CHECK_ROW + 1)):
        if scene.cursor == row:
            return
        press(scene, pygame.K_DOWN if scene.cursor < row else pygame.K_UP)
    raise AssertionError(f"курсор не дошёл до строки {row}")


def choose(scene: CakesTrialScene, row: int) -> None:
    move_cursor(scene, row)
    press_e(scene)
    listen_to_great_cake(scene)  # первая перестановка — разговор с Тортищем


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


def chase_with_keys(scene: CakesTrialScene, limit: float = 90.0) -> float:
    """Догоняет клубнику стрелками, как игрок: каждые 0,1 с (у поворота пути — каждый кадр) смотрит,
    куда идти по пути к ней (путь — только подсказка «игроку»; Алису двигают клавиши и столкновения
    сцены). Клубника всё это время бегает сама. Возвращает, сколько секунд заняла погоня."""
    alice, nav = scene.alice, scene.pantry.nav()
    held: set[int] = set()
    elapsed = 0.0
    last, frames = None, 0

    def hold_keys(wanted: set[int]) -> None:
        for code in held - wanted:
            scene.handle_event(key(code, event_type=pygame.KEYUP))
        for code in wanted - held:
            scene.handle_event(key(code))
        held.clear()
        held.update(wanted)

    while elapsed < limit:
        if scene.near_strawberry():
            hold_keys(set())
            return elapsed
        path = nav.find_path((alice.x, alice.y), scene.chase.position) or []
        # Упёрлась: клавиши держали, а Алиса прошла меньше половины положенного (например, она на долю
        # пикселя ниже края стеллажа, вдоль которого идёт путь). Тогда «игрок» поправляет любой сдвиг.
        stuck = bool(held) and math.dist(last, (alice.x, alice.y)) < 0.5 * frames * alice.speed * DT
        last = (alice.x, alice.y)
        wanted: set[int] = set()
        frames = 6
        for x, y in path[:2]:
            dx, dy = x - alice.x, y - alice.y
            ahead = max(abs(dx), abs(dy))
            if ahead <= 0.5:  # уже у этой точки — к следующей
                continue
            near = ahead < 8
            # Издалека — одна из восьми сторон: вторую стрелку, только если по второй оси сдвиг заметный.
            # У самой точки (или упёршись) — точно в неё по обеим осям и по кадру, чтобы не проскочить.
            slack = 0 if stuck else 0.1 if near else 0.4 * ahead
            if abs(dx) > slack:
                wanted.add(pygame.K_RIGHT if dx > 0 else pygame.K_LEFT)
            if abs(dy) > slack:
                wanted.add(pygame.K_DOWN if dy > 0 else pygame.K_UP)
            if near:
                frames = 1
            break
        hold_keys(wanted)
        for _ in range(frames):
            scene.update(DT)
            elapsed += DT
            if scene.near_strawberry():
                break
    hold_keys(set())
    raise AssertionError(f"не догнали клубнику за {limit} с")


def catch_strawberry(scene: CakesTrialScene) -> None:
    """Вплотную к клубнике, где бы она ни бегала, и E (сама погоня — chase_with_keys)."""
    scene.alice.set_position(*scene.chase.position)
    press_e(scene)


def spot_beside(scene: CakesTrialScene, distance: float) -> tuple[float, float]:
    """Свободная точка на расстоянии distance от клубники, откуда её видно (не через стеллаж)."""
    x, y = scene.chase.position
    for k in range(16):
        angle = k * math.pi / 8
        point = (x + distance * math.cos(angle), y + distance * math.sin(angle))
        if scene.collision.is_free(*point) and line_of_sight(scene.pantry.obstacles, point, (x, y)):
            return point
    raise AssertionError("вокруг клубники нет свободного места")


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
        self.scene = self.manager.push(CakesTrialScene(self.progress, seed=SEED))

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
        self.assertIn("Догони её", texts[-1])  # явная подсказка, что делать дальше
        self.assertEqual(self.scene.phase, MAZE)
        self.assertEqual(self.scene.area, PANTRY)
        self.assertEqual(self.scene.task_text(), "Задача: догони и поймай клубнику")
        self.assertEqual(self.scene.part_text(), "Часть 2 из 2 — клубника")
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), MAZE_START)
        self.assertEqual(self.progress.fragments, 0)

    def test_escape_and_chase_texts_match_the_library_pantry(self) -> None:
        # Кладовая теперь — комната с книжными стеллажами, а не лабиринт между коробками и противнями
        # (противни остались только на потолке кондитерской).
        self.assertIn("книжным стеллажам", lines.ESCAPE.nodes["e_where"].text)
        self.assertIn("библиотеку", lines.FOUND.nodes["c_planned"].text)
        self.scene.update(ESCAPE_SECONDS + 0.1)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, MAZE)
        chase_texts = [node.text for script in (lines.ESCAPE, lines.FOUND) for node in script.nodes.values()]
        chase_texts += [*lines.STRAWBERRY_LINES, CHASE_TOAST, FAR_TOAST, self.scene.task_text(),
                        self.scene.part_text(), self.scene.prompt()]
        for text in chase_texts:
            for stale in ("противн", "коробк", "лабиринт"):
                self.assertNotIn(stale, text.lower(), text)

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

    def test_chase_the_strawberry_with_keys_and_catch_it(self) -> None:
        self.assertEqual(self.scene.status_text(), CHASE_TOAST)
        self.assertEqual(CHASE_TOAST, "Клубника сбежала! Поймай её: E — когда будешь рядом")
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(),
                         "Стрелки/WASD — догнать   E — поймать рядом   Backspace — уйти")
        seconds = chase_with_keys(self.scene)
        self.assertGreater(seconds, 1.0)  # клубника не стоит и ждёт — её пришлось догонять
        self.assertTrue(self.scene.near_strawberry())
        self.assertEqual(self.scene.status_text(), "Клубника   E — поймать")
        press_e(self.scene)
        self.assertTrue(self.scene.strawberry_found)
        self.assertEqual(self.scene.chase.state, CAUGHT)
        self.assertEqual(self.scene.phase, FOUND_PHASE)
        self.assertIs(self.scene.dialogue.script, lines.FOUND)
        self.assertEqual(self.scene.dialogue.node.speaker, lines.STRAWBERRY)  # сначала реакция клубники
        self.assertEqual(self.scene.area, BAKERY)  # и уже у рабочего стола
        self.assertEqual(self.progress.fragments, 0)  # поимка — ещё не награда

    def test_chase_with_keys_gets_round_shelf_corners(self) -> None:
        # Раскладки, где путь идёт вплотную к краю стеллажа: Алиса, оказавшись на долю пикселя ниже
        # этого края, упиралась в торец, а прежний помощник погони не поправлял такой маленький сдвиг
        # и топтался на месте — сквозной тест через App (раскладка там случайная) падал примерно в 6% запусков.
        # Сама Алиса там не застревает: шаг вверх (или по диагонали) освобождает её.
        for seed in (1, 23, 50, 265):
            with self.subTest(seed=seed):
                scene = CakesTrialScene(GameProgress(), seed=seed)
                to_pantry(scene)
                self.assertLess(chase_with_keys(scene), 30.0)  # остановки — не реже 9 с, догоняет на них
                press_e(scene)
                self.assertTrue(scene.strawberry_found)
        scene = CakesTrialScene(GameProgress(), seed=23)
        to_pantry(scene)
        self.assertIn(pygame.Rect(176, 74, 16, 42), [item.rect for item in scene.pantry.items])
        scene.alice.set_position(198, 75)  # на пиксель ниже верха стеллажа (176, 74, 16, 42), вплотную справа
        hold(scene, [pygame.K_LEFT], 6)
        self.assertEqual((scene.alice.x, scene.alice.y), (198, 75))  # влево — в торец
        hold(scene, [pygame.K_UP, pygame.K_LEFT], 6)
        self.assertLess(scene.alice.x, 198)  # а по диагонали — проходит над стеллажом

    def test_strawberry_cannot_be_caught_from_afar_or_through_a_shelf(self) -> None:
        scene = self.scene
        for spot in (MAZE_START, spot_beside(scene, CATCH_REACH + 4)):
            scene.alice.set_position(*spot)
            self.assertTrue(scene.collision.is_free(*spot))
            press_e(scene)
            self.assertFalse(scene.strawberry_found, spot)
            self.assertEqual(scene.phase, MAZE)
            self.assertEqual(scene.status_text(), FAR_TOAST)
            self.assertEqual((scene.alice.x, scene.alice.y), spot)  # E не переносит Алису к ягоде
        # Через угол стеллажа: близко, но прямую загораживает стеллаж.
        rect = scene.pantry.obstacles[0]
        alice, berry = (rect.left - 6, rect.top + 3), (rect.left + 3, rect.top)
        self.assertTrue(scene.collision.is_free(*alice) and scene.collision.is_free(*berry))
        self.assertLessEqual(math.dist(alice, berry), CATCH_REACH)
        scene.chase.x, scene.chase.y = berry
        scene.alice.set_position(*alice)
        self.assertFalse(scene.near_strawberry())
        press_e(scene)
        self.assertFalse(scene.strawberry_found)
        self.assertEqual(scene.status_text(), FAR_TOAST)
        # А без стеллажа между ними на том же расстоянии — можно.
        scene.alice.set_position(*spot_beside(scene, math.dist(alice, berry)))
        self.assertTrue(scene.near_strawberry())

    def test_chase_goes_on_after_a_miss(self) -> None:
        scene = self.scene
        scene.alice.set_position(*MAZE_START)
        for _ in range(3):
            press_e(scene)
        before = scene.chase.position
        scene.update(0.5)
        scene.update(0.5)
        self.assertEqual(scene.phase, MAZE)
        self.assertNotEqual(scene.chase.position, before)  # промах не останавливает и не сбрасывает погоню
        self.assertNotEqual(scene.chase.state, CAUGHT)

    def test_alice_walks_while_the_strawberry_talks(self) -> None:
        scene = self.scene
        for _ in range(round(6 / DT)):
            if scene.chase.state == TALKING:
                break
            scene.update(DT)
        self.assertEqual(scene.chase.state, TALKING)
        self.assertIsNone(scene.dialogue)  # реплика клубники — облачко, а не окно диалога
        self.assertIsNotNone(scene.speech_bubble())
        berry, feet = scene.chase.position, (scene.alice.x, scene.alice.y)
        scene.handle_event(key(pygame.K_DOWN))
        for _ in range(20):
            scene.update(DT)
            if scene.chase.state != TALKING:
                break
            self.assertEqual(scene.chase.position, berry)  # стоит и говорит
        scene.handle_event(key(pygame.K_DOWN, event_type=pygame.KEYUP))
        self.assertGreater(scene.alice.y, feet[1])  # а Алиса идёт

    def test_caught_while_talking_or_running(self) -> None:
        for wanted in (TALKING, RUNNING):
            with self.subTest(state=wanted):
                scene = CakesTrialScene(GameProgress(), seed=SEED + 1)
                to_pantry(scene)
                for _ in range(round(8 / DT)):
                    if scene.chase.state == wanted and (wanted == TALKING or scene.chase.is_moving):
                        break
                    scene.update(DT)
                self.assertEqual(scene.chase.state, wanted)
                scene.alice.set_position(*spot_beside(scene, CATCH_REACH - 2))
                press_e(scene)
                self.assertTrue(scene.strawberry_found)
                self.assertEqual(scene.chase.state, CAUGHT)
                self.assertIsNone(scene.chase.line)
                self.assertIsNone(scene.speech_bubble())

    def test_nothing_runs_or_talks_after_the_catch(self) -> None:
        scene = self.scene
        catch_strawberry(scene)
        chase = scene.chase
        frozen = (chase.position, chase.routes, chase.stops, list(chase.lines_said))
        press_e(scene)  # второй раз не поймать
        for _ in range(3):
            scene.update(2.0)
        self.assertEqual((chase.position, chase.routes, chase.stops, chase.lines_said), frozen)
        self.assertEqual(scene.phase, FOUND_PHASE)
        self.assertNotIn("Клубника   E — поймать", scene.status_text())

    def test_strawberry_runs_at_alices_speed(self) -> None:
        self.assertEqual(self.scene.chase.speed, self.scene.alice.speed)
        self.assertEqual(self.scene.alice.speed, WALK_SPEED)  # скорость Алисы прежняя

    def test_walls_stop_alice(self) -> None:
        scene = self.scene
        for rect in scene.pantry.obstacles:
            y = rect.bottom - 1
            start = (rect.left - 6 - 30, y)
            if all(scene.collision.is_free(start[0] + k, y) for k in range(31)):
                break
        else:
            self.fail("нет стеллажа со свободным подходом слева")
        scene.alice.set_position(*start)
        scene.handle_event(key(pygame.K_RIGHT))
        for _ in range(5):
            scene.update(0.5)  # крупные шаги тоже не «протаскивают» сквозь стеллаж
        scene.handle_event(key(pygame.K_RIGHT, event_type=pygame.KEYUP))
        self.assertAlmostEqual(scene.alice.x, rect.left - 6)

    def test_alice_stays_on_screen_and_off_the_walls(self) -> None:
        for keys in ([pygame.K_UP], [pygame.K_DOWN], [pygame.K_LEFT], [pygame.K_RIGHT, pygame.K_DOWN],
                     [pygame.K_RIGHT, pygame.K_UP]):
            scene = CakesTrialScene()  # каждый раз своя раскладка
            to_pantry(scene)
            nav = scene.pantry.nav()
            middle = min(nav.free, key=lambda cell: math.dist(nav.point(cell), (160, 110)))
            scene.alice.set_position(*nav.point(middle))
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
        self.assertIsNone(self.scene.strawberry_position())  # она у Алисы над головой, а не на полу


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
        # В кладовой окон реплик нет (см. test_no_dialogue_box_in_the_pantry): поймали — реакция у стола.
        for y in (ALICE_SPOT[1], CHUCHMEK_SPOT[1], CHUCHMEK_DOOR[1], MAZE_START[1], BOARD.bottom):
            self.assertLessEqual(y, lowest_box)

    def test_pantry_keeps_alice_between_interface_strips(self) -> None:
        self.assertGreaterEqual(MAZE_BOUNDS.top + 6 - SPRITE_SIZE, HUD_HEIGHT)  # голова не под верхней полосой
        self.assertLessEqual(MAZE_BOUNDS.bottom, STATUS_TOP)
        self.assertGreaterEqual(MAZE_BOUNDS.left + 6 - SPRITE_SIZE // 2, 0)
        self.assertLessEqual(MAZE_BOUNDS.right - 6 + SPRITE_SIZE // 2, WIDTH)

    def test_texts_fit_on_screen(self) -> None:
        font = self.scene._font
        for phase_task in ("Задача: расставь этапы рецепта по порядку", "Задача: догони и поймай клубнику"):
            self.assertLessEqual(font.size(phase_task)[0], WIDTH - 8)
        widest_held = max(font.size(f"Взят этап: {name}")[0] for name in STEP_SHORT_NAMES.values())
        self.assertLessEqual(font.size("Часть 2 из 2 — клубника")[0] + widest_held, WIDTH - 16)
        statuses = ["Стрелки — выбрать этап   E — взять   Backspace — уйти",
                    "Стрелки — куда поставить   E — поменять местами",
                    "E — положить обратно   Стрелки — с чем поменять", "E — проверить рецепт   Стрелки — к этапам",
                    "Стрелки/WASD — догнать   E — поймать рядом   Backspace — уйти", FAR_TOAST, CHASE_TOAST]
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


class ChaseSceneTest(TrialTestCase):
    """Погоня в сцене: когда начинается, одна геометрия на всё, облачко реплик, дальность поимки."""

    def test_no_chase_until_the_recipe_is_fixed(self) -> None:
        scene = self.scene
        finish_dialogue(scene)
        for _ in range(2):  # взять и положить обратно, подождать
            choose(scene, 0)
            scene.update(2.0)
        self.assertIsNone(scene.chase)
        self.assertIsNone(scene.pantry)
        self.assertEqual(scene.strawberry_position(), STRAWBERRY_ON_TABLE)  # лежит на столе
        self.assertFalse(scene.recipe.solved)  # и сам рецепт не решается
        solve_recipe(scene)
        self.assertIsNone(scene.chase)  # и при реакции на успех — ещё нет
        finish_dialogue(scene)
        scene.update(ESCAPE_SECONDS + 0.1)
        self.assertIsNone(scene.chase)  # и пока клубника убегает со стола
        finish_dialogue(scene)
        self.assertIsNotNone(scene.chase)

    def test_new_layout_each_run_same_with_the_same_seed_and_one_geometry(self) -> None:
        def layout(seed):
            scene = CakesTrialScene(GameProgress(), seed=seed)
            to_pantry(scene)
            return scene

        first, again, other = layout(5), layout(5), layout(6)
        items = [(i.kind, tuple(i.rect)) for i in first.pantry.items]
        self.assertEqual(items, [(i.kind, tuple(i.rect)) for i in again.pantry.items])
        self.assertNotEqual(items, [(i.kind, tuple(i.rect)) for i in other.pantry.items])
        randoms = {tuple(tuple(r) for r in layout(None).pantry.obstacles) for _ in range(4)}
        self.assertGreater(len(randoms), 1)  # без seed — каждый раз своя кладовая
        # Рисование, столкновения Алисы, клубники и поиск пути — по одним и тем же прямоугольникам.
        rects = [tuple(r) for r in first.pantry.obstacles]
        self.assertEqual([tuple(r) for r in first.collision.obstacles], rects)
        self.assertEqual([tuple(r) for r in first.chase.collision.obstacles], rects)
        self.assertEqual([tuple(r) for r in first.pantry.nav().collision.obstacles], rects)
        self.assertEqual(first.alice.collider, first.collision.move)
        self.assertEqual(rects, [tuple(r) for r in generate_layout(first.pantry.seed).obstacles])

    def test_no_dialogue_box_in_the_pantry(self) -> None:
        scene = self.scene
        to_pantry(scene)
        for _ in range(round(20 / DT)):
            scene.update(DT)
            self.assertIsNone(scene.dialogue)  # окно реплики закрыло бы Алису внизу комнаты
            self.assertEqual(scene.area, PANTRY)
        catch_strawberry(scene)
        self.assertEqual(scene.area, BAKERY)
        self.assertIsNotNone(scene.dialogue)

    def test_catch_reach_is_measured_between_feet(self) -> None:
        scene = self.scene
        to_pantry(scene)
        scene.alice.set_position(*spot_beside(scene, CATCH_REACH))
        self.assertTrue(scene.near_strawberry())
        scene.alice.set_position(*spot_beside(scene, CATCH_REACH + 1))
        self.assertFalse(scene.near_strawberry())
        # «Рядом» — это действительно рядом: ноги почти касаются (ноги Алисы шириной 12 px).
        self.assertLessEqual(CATCH_REACH, FOOT_SIZE[0] + 6)

    def test_speech_bubble_is_readable_and_keeps_clear(self) -> None:
        scene = self.scene
        to_pantry(scene)
        chase, nav = scene.chase, scene.pantry.nav()
        spots = [nav.point(cell) for cell in sorted(nav.free)[::37]]
        self.assertGreater(len(spots), 20)
        for text in lines.STRAWBERRY_LINES:
            for hires in (True, False):
                chase.state, chase.line = TALKING, text
                chase.x, chase.y = spots[0]
                rect, text_lines = scene.speech_bubble(hires)
                self.assertLessEqual(len(text_lines), 2, text)  # коротко: не больше двух строк
                self.assertEqual(" ".join(text_lines), text)
        for x, y in spots:
            chase.x, chase.y = x, y
            center = scene.strawberry_position()
            berry = pygame.Rect(round(center[0]) - 6, round(center[1]) - 9, 13, 15)
            for side in (-14, 14):
                scene.alice.set_position(x + side, y)
                for hires in (True, False):
                    rect, _ = scene.speech_bubble(hires)
                    with self.subTest(spot=(x, y), side=side, hires=hires):
                        self.assertTrue(SPEECH_AREA.contains(rect))  # между полосами интерфейса
                        self.assertFalse(rect.colliderect(berry))  # ягоду не закрывает
                        if MAZE_BOUNDS.top + 30 <= y <= MAZE_BOUNDS.bottom - 30:  # не у самого края
                            self.assertFalse(rect.colliderect(scene.alice.rect.inflate(-14, -4)))
        chase.state, chase.line = RUNNING, None
        self.assertIsNone(scene.speech_bubble())  # молчит — облачка нет

    def test_speech_goes_through_the_hires_layer_without_double_sprites(self) -> None:
        scene = self.scene
        to_pantry(scene)
        for _ in range(round(6 / DT)):
            if scene.chase.state == TALKING:
                break
            scene.update(DT)
        layer = HiResLayer(strict=True)
        scene.draw(self.canvas, layer)
        rect, text_lines = scene.speech_bubble(hires=True)
        texts = [c for c in layer.commands if isinstance(c, TextCommand) and c.style == SPEECH_STYLE]
        self.assertEqual([c.text for c in texts], text_lines)
        for command in texts:
            self.assertTrue(rect.collidepoint(command.pos))
        sprites = [c for c in layer.commands if isinstance(c, SpriteCommand)]
        self.assertEqual(len([c for c in sprites if c.rect == scene.alice.rect]), 1)
        self.assertEqual(len(sprites), 2)  # Алиса и Чучмек в дверях — по одному разу
        scene.draw(self.canvas)  # и без слоя — пиксельным шрифтом, без ошибок


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
    for section in ("requests", "permits", "births"):
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
        chase_with_keys(cakes)  # кладовая — погоня стрелками
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


# --- Тортище ---

# Позы Тортища (псевдонимы poses манифеста great_cake) и их кадры — по манифесту, а не по номерам.
GREAT_CAKE_FRAMES = {
    "idle": "idle_front",
    "wink": "wink_front",
    "angry": "angry_shout",
    "smug": "unimpressed",
    "threaten": "angry_scepter",
    "stern": "crossed_arms",
}
USED_GREAT_CAKE_POSES = {
    *lines.GREAT_CAKE_POSES.values(),
    lines.GREAT_CAKE_IDLE_POSE,
    lines.GREAT_CAKE_WATCH_POSE,
    lines.GREAT_CAKE_ESCAPE_POSE,
}
WINDOW = ViewTransform(pygame.Rect((0, 0), (960, 540)))


def first_swap(scene: CakesTrialScene) -> None:
    """Первая перестановка (строки 1 и 5) — без дослушивания: разговор с Тортищем остаётся открытым."""
    move_cursor(scene, 0)
    press_e(scene)
    move_cursor(scene, 4)
    press_e(scene)


def talk(scene: CakesTrialScene, answer: int) -> dict[str, str]:
    """Проходит разговор с Тортищем E, на вопросе — ↓ до ответа answer. Возвращает позы по репликам."""
    poses = {}
    for _ in range(4 * len(lines.GREAT_CAKE_TALK.nodes)):
        dialogue = scene.dialogue
        if dialogue is None or dialogue.script is not lines.GREAT_CAKE_TALK:
            return poses
        poses[dialogue.node.id] = scene.great_cake_pose
        if dialogue.is_typing:
            press_e(scene)  # дописать
            continue
        for _ in range(answer if dialogue.choices else 0):
            press(scene, pygame.K_DOWN)
        press_e(scene)
    raise AssertionError(f"разговор с Тортищем не заканчивается: {poses}")


def great_cake_commands(layer: HiResLayer) -> list[SpriteCommand]:
    return [c for c in layer.commands if isinstance(c, SpriteCommand) and c.rect.midbottom == GREAT_CAKE_SPOT]


def body(image: pygame.Surface, rect: pygame.Rect) -> pygame.Rect:
    """Непрозрачная часть кадра image, растянутого на rect холста."""
    scaled = pygame.transform.scale(image, rect.size)
    return scaled.get_bounding_rect(min_alpha=40).move(rect.topleft)


def strawberry_body(center: tuple[float, float]) -> pygame.Rect:
    surface = pygame.Surface(config.LOGICAL_SIZE, pygame.SRCALPHA)
    draw_strawberry(surface, center)
    return surface.get_bounding_rect()


class GreatCakeSpritesTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sprites = load_character_sprites(CHARACTERS_DIR / "great_cake")

    def test_loaded_through_the_manifest_with_the_approved_name(self) -> None:
        sprites = self.scene.great_cake_sprites
        self.assertIsNotNone(sprites)
        self.assertEqual(sprites.id, "great_cake")
        self.assertEqual(sprites.display_name, lines.GREAT_CAKE)  # «Тортище» в окне реплики
        self.assertEqual(lines.GREAT_CAKE_TALK.nodes[lines.EVENT_CHOICE_ID].text, "Я не десерт. Я событие!")

    def test_each_pose_is_its_own_manifest_frame(self) -> None:
        self.assertLessEqual(USED_GREAT_CAKE_POSES, set(GREAT_CAKE_FRAMES))
        for pose, frame_id in GREAT_CAKE_FRAMES.items():
            with self.subTest(pose=pose):
                self.assertEqual(self.sprites.poses[pose], frame_id)
                frame = self.sprites.frame(frame_id)
                self.scene.great_cake_pose = pose
                source, image = self.scene._great_cake_frame()
                self.assertIs(source, self.scene.great_cake_sprites.frame(frame_id).image)
                on_disk = pygame.image.load(str(CHARACTERS_DIR / "great_cake" / frame.file))
                self.assertEqual(pygame.image.tobytes(source, "RGBA"), pygame.image.tobytes(on_disk, "RGBA"))
                expected = pygame.transform.scale(on_disk, (GREAT_CAKE_SIZE, GREAT_CAKE_SIZE))
                self.assertEqual(pygame.image.tobytes(image, "RGBA"), pygame.image.tobytes(expected, "RGBA"))

    def test_draft_walk_frames_are_never_used(self) -> None:
        walking = {frame_id for name in ("walk_left", "walk_right") for frame_id in self.sprites.groups[name].frame_ids}
        self.assertTrue(all(self.sprites.groups[name].draft for name in ("walk_left", "walk_right")))
        used = {self.sprites.poses[pose] for pose in USED_GREAT_CAKE_POSES}
        self.assertFalse(used & walking)

    def test_missing_pose_falls_back_to_the_main_pose(self) -> None:
        idle = self.sprites.frame("idle_front")
        without_angry = {alias: frame for alias, frame in self.sprites.poses.items() if alias != "angry"}
        # Первым — не основной кадр: так видно, что замена — именно поза idle, а не первый кадр.
        profile = self.sprites.frame("profile_right")
        reordered = (profile, *(frame for frame in self.sprites.frames if frame is not profile))
        self.sprites = replace(self.sprites, frames=reordered)
        self.scene.great_cake_sprites = replace(self.sprites, poses=without_angry)
        self.scene._great_cake_frames.clear()
        for pose in ("angry", "no_such_pose"):
            with self.subTest(pose=pose):
                self.scene.great_cake_pose = pose
                source, _ = self.scene._great_cake_frame()
                self.assertEqual(pygame.image.tobytes(source, "RGBA"), pygame.image.tobytes(idle.image, "RGBA"))
                self.assertEqual(self.scene.great_cake_rect().midbottom, GREAT_CAKE_SPOT)
        # Нет даже основной позы — первый кадр манифеста; испытание проходится до конца.
        self.scene.great_cake_sprites = replace(self.sprites, poses={})
        self.scene._great_cake_frames.clear()
        self.scene.great_cake_pose = "angry"
        self.assertIs(self.scene._great_cake_frame()[0], profile.image)
        self.scene.draw(self.canvas, HiResLayer(strict=True))
        play(self.scene)
        self.assertTrue(self.scene.completed)
        self.assertEqual(self.progress.completed, ("cakes",))

    def test_broken_or_missing_manifest_shows_a_placeholder_and_the_trial_goes_on(self) -> None:
        for case in ("нет кадра одной позы", "нет папки"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                for char_id in ("alice", "chuchmek"):
                    shutil.copytree(CHARACTERS_DIR / char_id, Path(root) / char_id)
                if case == "нет кадра одной позы":
                    shutil.copytree(CHARACTERS_DIR / "great_cake", Path(root) / "great_cake")
                    (Path(root) / "great_cake" / self.sprites.frame("angry_shout").file).unlink()
                progress = GameProgress()
                scene = CakesTrialScene(progress, characters_dir=root)
                self.assertIsNone(scene.great_cake_sprites)
                self.assertIsNotNone(scene.chuchmek_sprites)  # остальные персонажи на месте
                for pose in USED_GREAT_CAKE_POSES:
                    scene.great_cake_pose = pose
                    layer = HiResLayer(strict=True)
                    scene.draw(self.canvas, layer)
                    self.assertEqual(len(great_cake_commands(layer)), 1)  # временный манекен на подставке
                play(scene)
                self.assertTrue(scene.completed)
                self.assertEqual(progress.completed, ("cakes",))


class GreatCakeDrawingTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sprites = load_character_sprites(CHARACTERS_DIR / "great_cake")

    def draw_layer(self) -> HiResLayer:
        layer = HiResLayer(strict=True)
        self.scene.draw(self.canvas, layer)
        return layer

    def test_drawn_by_the_hires_layer_from_the_source_frame_without_mirroring(self) -> None:
        frame = self.sprites.frame(GREAT_CAKE_FRAMES[self.scene.great_cake_pose]).image
        layer = self.draw_layer()
        (command,) = great_cake_commands(layer)
        self.assertEqual(command.rect, self.scene.great_cake_rect())
        self.assertEqual(command.rect.size, (GREAT_CAKE_SIZE, GREAT_CAKE_SIZE))
        self.assertEqual(command.image.get_size(), (64, 64))
        self.assertEqual(pygame.image.tobytes(command.image, "RGBA"), pygame.image.tobytes(frame, "RGBA"))
        mirrored = pygame.transform.flip(frame, True, False)
        self.assertNotEqual(pygame.image.tobytes(command.image, "RGBA"), pygame.image.tobytes(mirrored, "RGBA"))
        # На холсте Тортища нет (только фон с подставкой), в окне — исходный кадр на своём месте.
        above_plate = command.rect.clip(pygame.Rect(0, 0, WIDTH, GREAT_CAKE_SPOT[1] - 3))
        self.assertEqual(pygame.image.tobytes(self.canvas.subsurface(above_plate), "RGB"),
                         pygame.image.tobytes(self.scene._bakery_plain.subsurface(above_plate), "RGB"))
        window = pygame.Surface(WINDOW.viewport.size)  # чёрное окно: виден ровно вклад слоя
        layer.render(window, WINDOW)
        place = WINDOW.rect(command.rect)
        self.assertEqual(place.size, (3 * GREAT_CAKE_SIZE, 3 * GREAT_CAKE_SIZE))
        expected = scale_sprite(frame, place.size)  # предумноженная альфа: на чёрном — сам цвет
        body_pixels = [(x, y) for y in range(0, place.height, 5) for x in range(0, place.width, 5)
                       if expected.get_at((x, y)).a >= 128]
        self.assertGreater(len(body_pixels), 300)
        for x, y in body_pixels:
            self.assertEqual(window.get_at((place.x + x, place.y + y))[:3], expected.get_at((x, y))[:3])

    def test_only_in_the_bakery(self) -> None:
        to_pantry(self.scene)
        self.assertEqual(great_cake_commands(self.draw_layer()), [])
        catch_strawberry(self.scene)
        finish_dialogue(self.scene)  # назад в кондитерскую на финальный разговор
        self.assertEqual(len(great_cake_commands(self.draw_layer())), 1)

    def test_size_place_and_feet_stay_the_same_for_every_pose(self) -> None:
        rects = set()
        for pose in GREAT_CAKE_FRAMES:
            self.scene.great_cake_pose = pose
            (command,) = great_cake_commands(self.draw_layer())
            rects.add(tuple(command.rect))
        self.assertEqual(rects, {tuple(self.scene.great_cake_rect())})
        # Ноги во всех позах на одной строке кадра — на блюде, без скачков при смене позы.
        feet = {self.sprites.frame(frame_id).image.get_bounding_rect(min_alpha=40).bottom
                for frame_id in GREAT_CAKE_FRAMES.values()}
        self.assertEqual(len(feet), 1)

    def test_stays_in_place_through_the_whole_conversation(self) -> None:
        finish_dialogue(self.scene)
        first_swap(self.scene)
        rects, poses = set(), set()
        while self.scene.dialogue is not None:
            (command,) = great_cake_commands(self.draw_layer())
            rects.add(tuple(command.rect))
            poses.add(self.scene.great_cake_pose)
            press(self.scene, pygame.K_RETURN)
        self.assertEqual(rects, {tuple(self.scene.great_cake_rect())})
        self.assertGreaterEqual(len(poses), 4)  # реагирует на разговор, а не стоит одной картинкой

    def test_bigger_than_alice(self) -> None:
        alice = load_character_sprites(CHARACTERS_DIR / "alice").frame("idle_right").image
        alice_height = body(alice, self.scene.alice.rect).height
        for pose, frame_id in GREAT_CAKE_FRAMES.items():
            with self.subTest(pose=pose):
                height = body(self.sprites.frame(frame_id).image, self.scene.great_cake_rect()).height
                self.assertGreaterEqual(height, 1.3 * alice_height)

    def test_covers_no_board_interface_dialogue_table_strawberry_door_or_neighbours(self) -> None:
        rect = self.scene.great_cake_rect()
        self.assertGreaterEqual(rect.top, HUD_HEIGHT)  # не под верхней полосой
        self.assertLessEqual(rect.right, WIDTH)
        box = DialogueBox()
        dialogue_areas = [box.layout(node, hires).area for script in lines.all_scripts()
                          for node in script.nodes.values() for hires in (False, True)]
        chuchmek = load_character_sprites(CHARACTERS_DIR / "chuchmek")
        chuchmek_rect = pygame.Rect(0, 0, SPRITE_SIZE, SPRITE_SIZE)
        chuchmek_rect.midbottom = CHUCHMEK_SPOT
        chuchmek_poses = {*lines.CHUCHMEK_POSES.values(), lines.CHUCHMEK_IDLE_POSE, lines.CHUCHMEK_PANIC_POSE}
        # Клубника на столе, весь её побег до края экрана и она же на вершине торта в финале.
        scene = CakesTrialScene()
        finish_dialogue(scene)
        solve_recipe(scene)
        finish_dialogue(scene)
        strawberries = [strawberry_body(STRAWBERRY_ON_TABLE)]
        for _ in range(30):
            scene.escape_time += ESCAPE_SECONDS / 30
            strawberries.append(strawberry_body(scene._escape_position()))
        final = CakesTrialScene()
        play(final, stop_before_final_end=True)
        strawberries.append(strawberry_body(final.strawberry_position()))
        for pose, frame_id in GREAT_CAKE_FRAMES.items():
            cake = body(self.sprites.frame(frame_id).image, rect)
            with self.subTest(pose=pose):
                self.assertFalse(cake.colliderect(BOARD.inflate(4, 4)))  # доска с рамкой
                self.assertFalse(cake.colliderect(TABLE_AREA))  # рабочий стол с тортом
                self.assertFalse(cake.colliderect(PANTRY_DOOR))
                self.assertFalse(cake.colliderect(self.scene.alice.rect))
                self.assertEqual(cake.collidelist(dialogue_areas), -1)
                self.assertEqual(cake.collidelist(strawberries), -1)
                for chuchmek_pose in chuchmek_poses:
                    self.assertFalse(cake.colliderect(body(chuchmek.frame(chuchmek_pose).image, chuchmek_rect)))
        lowest = min(area.top for area in dialogue_areas)
        self.assertLessEqual(GREAT_CAKE_SPOT[1], lowest)  # ноги выше любого окна реплики


class GreatCakeTalkTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)  # вступление Чучмека — без Тортища

    def test_quiet_until_alice_first_changes_the_recipe(self) -> None:
        self.assertEqual(self.scene.phase, ORDERING)
        choose(self.scene, 0)
        self.assertIsNone(self.scene.dialogue)  # взять этап — ещё не изменить рецепт
        choose(self.scene, 0)
        self.assertIsNone(self.scene.dialogue)
        check_recipe(self.scene)
        self.assertIsNot(self.scene.dialogue.script, lines.GREAT_CAKE_TALK)  # отказ — реплики Чучмека
        self.assertEqual(self.scene.dialogue.node.speaker, CHUCHMEK)
        finish_dialogue(self.scene)
        first_swap(self.scene)
        dialogue = self.scene.dialogue
        self.assertIs(dialogue.script, lines.GREAT_CAKE_TALK)
        self.assertEqual(dialogue.node.id, "g_halt")
        self.assertEqual(dialogue.node.speaker, lines.GREAT_CAKE)
        self.assertEqual(self.scene.phase, ORDERING)
        self.assertEqual(self.scene.recipe.order, ("ingredients", "cool", "bake", "dough", "decorate"))  # обмен сделан
        self.assertIsNone(self.scene.recipe.picked)
        self.assertEqual(self.scene.great_cake_pose, "threaten")

    def test_keys_in_the_talk_touch_neither_the_board_nor_alice(self) -> None:
        first_swap(self.scene)
        order, cursor = self.scene.recipe.order, self.scene.cursor
        for code, scancode in ((pygame.K_UP, 0), (pygame.K_DOWN, 0), (pygame.K_LEFT, 0), (pygame.K_RIGHT, 0),
                               (pygame.K_w, pygame.KSCAN_W), (pygame.K_a, pygame.KSCAN_A),
                               (pygame.K_s, pygame.KSCAN_S), (pygame.K_d, pygame.KSCAN_D)):
            self.scene.handle_event(key(code, scancode))
            for _ in range(20):
                self.scene.update(DT)
            self.scene.handle_event(key(code, scancode, pygame.KEYUP))
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), ALICE_SPOT)
        self.assertFalse(self.scene.alice.is_moving)
        self.assertEqual((self.scene.recipe.order, self.scene.cursor), (order, cursor))
        self.assertIs(self.scene.dialogue.script, lines.GREAT_CAKE_TALK)

    def test_question_needs_e_or_enter_and_space_does_not_answer(self) -> None:
        first_swap(self.scene)
        while self.scene.dialogue.node.id != lines.EVENT_CHOICE_ID:
            press(self.scene, pygame.K_SPACE)  # пробел листает обычные реплики
        press(self.scene, pygame.K_SPACE)  # дописать вопрос
        self.assertTrue(self.scene.dialogue.choices)
        press(self.scene, pygame.K_SPACE)  # на вопросе пробел ничего не выбирает
        self.assertEqual(self.scene.dialogue.node.id, lines.EVENT_CHOICE_ID)
        press(self.scene, ord("ы"), pygame.KSCAN_S)  # S в русской раскладке — выбор ответа, а не Алиса
        self.assertEqual(self.scene.dialogue.selected_index, 1)
        press(self.scene, pygame.K_UP)
        self.assertEqual(self.scene.dialogue.selected_index, 0)
        self.assertEqual(self.scene.cursor, 4)
        press(self.scene, pygame.K_RETURN)
        self.assertEqual(self.scene.dialogue.node.id, "g_plate")

    def test_answers_get_different_reactions_and_rejoin_without_touching_the_recipe(self) -> None:
        own = {0: ("g_plate", "wink"), 1: ("g_normal", "threaten")}
        outcomes = []
        for answer, (reaction, pose) in own.items():
            with self.subTest(answer=answer):
                progress = GameProgress()
                scene = CakesTrialScene(progress)
                finish_dialogue(scene)
                first_swap(scene)
                swapped = repr(sorted(vars(scene.recipe).items()))
                poses = talk(scene, answer)
                self.assertIn(reaction, poses)
                self.assertNotIn(own[1 - answer][0], poses)
                self.assertEqual(poses[reaction], pose)
                self.assertEqual(list(poses)[-1], "g_watch")  # общий конец разговора
                self.assertEqual(poses["g_event"], "angry")
                self.assertIsNone(scene.dialogue)
                self.assertEqual(scene.phase, ORDERING)
                self.assertEqual(repr(sorted(vars(scene.recipe).items())), swapped)  # ни этапов, ни проверок
                self.assertEqual(progress.completed, ())
                self.assertEqual(scene.great_cake_pose, lines.GREAT_CAKE_WATCH_POSE)  # дальше строго следит
                scene.update(TOAST_SECONDS)
                self.assertEqual(scene.status_text(), "Стрелки — выбрать этап   E — взять   Backspace — уйти")
                for row in (1, 3):  # без помощника choose: он сам дослушал бы Тортища
                    move_cursor(scene, row)
                    press_e(scene)
                self.assertEqual(scene.recipe.order, CORRECT_ORDER)
                self.assertIsNone(scene.dialogue)  # второй раз Тортище не заговаривает
                check_recipe(scene)
                self.assertEqual(scene.phase, SUCCESS_PHASE)
                finish_dialogue(scene)
                path = []
                for _ in range(10):  # клубника убегает так же, как и без Тортища
                    scene.update(ESCAPE_SECONDS / 10)
                    path.append(scene.strawberry_position())
                scene.update(0.05)
                self.assertIs(scene.dialogue.script, lines.ESCAPE)
                outcomes.append((path, scene.recipe.order, scene.recipe.failed_checks))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_cancel_in_the_talk_gives_no_fragment(self) -> None:
        for node_id in ("g_halt", lines.EVENT_CHOICE_ID, "g_watch"):
            with self.subTest(node=node_id):
                progress = GameProgress()
                manager = SceneManager()
                manager.register(CAKES_SCENE, lambda: CakesTrialScene(progress))
                hub = manager.push(HubScene(progress))
                hub.alice.set_position(*PORTAL["cakes"])
                hub.interact()
                scene = manager.current
                finish_dialogue(scene)
                first_swap(scene)
                while scene.dialogue.node.id != node_id:
                    press(scene, pygame.K_RETURN)
                press(scene, pygame.K_BACKSPACE)
                self.assertIs(manager.current, hub)
                self.assertEqual(progress.completed, ())
                self.assertFalse(scene.completed)
                self.assertIn("«Торты» прервано", hub.toast)

    def test_poses_follow_the_whole_trial(self) -> None:
        scene = CakesTrialScene()
        self.assertEqual(scene.great_cake_pose, "smug")  # Чучмек «лично проверил рецепт»
        finish_dialogue(scene)
        self.assertEqual(scene.great_cake_pose, "idle")
        check_recipe(scene)
        self.assertEqual(scene.great_cake_pose, "smug")
        finish_dialogue(scene)
        first_swap(scene)
        poses = talk(scene, 0)
        self.assertEqual({node: poses[node] for node in ("g_halt", "g_finally", "g_event", "g_watch")},
                         {"g_halt": "threaten", "g_finally": "smug", "g_event": "angry", "g_watch": "stern"})
        choose(scene, 1)
        choose(scene, 3)
        self.assertEqual(scene.great_cake_pose, "stern")
        check_recipe(scene)
        press(scene, pygame.K_RETURN)
        press(scene, pygame.K_RETURN)
        self.assertEqual(scene.dialogue.node.id, "s_obvious")
        self.assertEqual(scene.great_cake_pose, "wink")
        finish_dialogue(scene)
        self.assertEqual(scene.great_cake_pose, "angry")  # клубника убегает
        scene.update(ESCAPE_SECONDS + 0.1)
        self.assertEqual(scene.great_cake_pose, "angry")
        finish_dialogue(scene)
        catch_strawberry(scene)
        finish_dialogue(scene)
        self.assertEqual(scene.great_cake_pose, "idle")
        while scene.dialogue.node.id != "f_fragment":
            press(scene, pygame.K_RETURN)
        self.assertEqual(scene.great_cake_pose, "wink")


class GreatCakeAppTest(unittest.TestCase):
    """Тортище в испытании, открытом через приложение: клавиши идут через App и ActionInput."""

    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App(dev_mode=True)

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

    def to_ordering(self) -> CakesTrialScene:
        trial = self.enter_portal(self.open_hub(), "cakes")
        for _ in range(2 * len(lines.INTRO.nodes)):
            if trial.phase == ORDERING:
                break
            self.press(pygame.K_e, pygame.KSCAN_E)
        self.assertEqual(trial.phase, ORDERING)
        return trial

    def test_holding_e_does_not_skip_lines_or_answer_twice(self) -> None:
        trial = self.to_ordering()
        self.press(pygame.K_e, pygame.KSCAN_E)  # взять первый этап
        for _ in range(4):
            self.press(pygame.K_DOWN)
        # Зажатая E: обмен и начало разговора — один раз, автоповтор не листает реплику.
        self.send(*(key(pygame.K_e, pygame.KSCAN_E) for _ in range(4)))
        self.assertIs(trial.dialogue.script, lines.GREAT_CAKE_TALK)
        self.assertEqual(trial.dialogue.node.id, "g_halt")
        self.assertTrue(trial.dialogue.is_typing)
        self.send(key(pygame.K_e, pygame.KSCAN_E, pygame.KEYUP))
        while trial.dialogue.node.id != lines.EVENT_CHOICE_ID:
            self.press(pygame.K_RETURN)
        self.press(pygame.K_RETURN)  # дописать вопрос
        self.press(pygame.K_DOWN)
        self.send(*(key(pygame.K_e, pygame.KSCAN_E) for _ in range(4)))  # ответ — один, реакция не пропущена
        self.assertEqual(trial.dialogue.node.id, "g_normal")
        self.assertTrue(trial.dialogue.is_typing)
        self.send(key(pygame.K_e, pygame.KSCAN_E, pygame.KEYUP))
        while trial.dialogue is not None:
            self.press(pygame.K_RETURN)
        self.assertEqual(trial.phase, ORDERING)
        self.assertEqual(trial.recipe.order, ("ingredients", "cool", "bake", "dough", "decorate"))
        self.press(pygame.K_UP)  # управление доской вернулось
        self.assertEqual(trial.cursor, 3)

    def test_replay_talks_again_but_gives_one_fragment(self) -> None:
        hub = self.open_hub()
        for answer in (0, 1):
            trial = self.enter_portal(hub, "cakes")
            self.assertFalse(trial.great_cake_met)
            finish_dialogue(trial)
            first_swap(trial)
            self.assertIs(trial.dialogue.script, lines.GREAT_CAKE_TALK)
            talk(trial, answer)
            choose(trial, 1)
            choose(trial, 3)
            check_recipe(trial)
            finish_dialogue(trial)
            trial.update(ESCAPE_SECONDS + 0.1)
            finish_dialogue(trial)
            catch_strawberry(trial)
            finish_dialogue(trial)
            finish_dialogue(trial)
            self.assertTrue(trial.completed)
            self.assertEqual(trial.reward_given, answer == 0)
            self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.completed, ("cakes",))
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 1/3")


if __name__ == "__main__":
    unittest.main()
