"""Проверки слоя высокого разрешения в испытаниях (суши, формуляры, торты) и в финале.

Тесты не зависят от того, какой именно шрифт установлен: надписи проверяются и с найденным
системным шрифтом, и с запасным встроенным шрифтом Pygame.
"""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import hashlib  # noqa: E402
from dataclasses import replace  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.display import fit_viewport  # noqa: E402
from game.graphics.animation import WALK, Direction  # noqa: E402
from game.graphics.fonts import TextFonts, TextStyle  # noqa: E402
from game.graphics.hires import (  # noqa: E402
    FillCommand,
    GroupCommand,
    HiResLayer,
    PatchCommand,
    SpriteCommand,
    TextCommand,
    ViewTransform,
)
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story import final_dialogue as final_text  # noqa: E402
from game.story.final_scene import (  # noqa: E402
    CREDIT_STYLES,
    CREDITS_SECONDS,
    END_INPUT_DELAY,
    LETTER_STYLE,
    NIGHT_COLOR,
    PANEL,
    PANEL_PADDING,
    PAUSE_SECONDS,
    THE_END_STYLE,
    FinalScene,
)
from game.story.intro_scene import IntroScene  # noqa: E402
from game.trials import cakes_scene as cakes  # noqa: E402
from game.trials import forms_scene as forms  # noqa: E402
from game.trials import sushi_scene as sushi  # noqa: E402
from game.trials.cakes_maze import MAZE_ROUTE, STRAWBERRY_POSITION, strawberry_in_reach  # noqa: E402
from game.trials.cakes_puzzle import STEP_NAMES, STEP_SHORT_NAMES  # noqa: E402
from game.trials.forms_puzzle import DOCUMENT_NAMES, SECTIONS  # noqa: E402
from game.trials.sushi_orders import INGREDIENT_NAMES, RECIPES, SushiOrders  # noqa: E402
from game.world.hub import PORTALS, HubScene  # noqa: E402
from game.world.progress import TRIALS, GameProgress  # noqa: E402

WIDTH, HEIGHT = config.LOGICAL_SIZE
WINDOWED = (960, 540)
FULLSCREEN = (1920, 1200)
SCENES = (sushi.SushiTrialScene, forms.FormsTrialScene, cakes.CakesTrialScene, FinalScene)


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press(scene, code: int, scancode: int = 0) -> None:
    scene.handle_event(key(code, scancode))
    scene.handle_event(key(code, scancode, pygame.KEYUP))


def press_e(scene) -> None:
    press(scene, pygame.K_e, pygame.KSCAN_E)


def finish_dialogue(scene) -> None:
    """Пролистывает текущий диалог Enter (только его, не следующий)."""
    script = scene.dialogue.script if scene.dialogue is not None else None
    for _ in range(200):
        if scene.dialogue is None or scene.dialogue.script is not script:
            return
        press(scene, pygame.K_RETURN)
    raise AssertionError("диалог не заканчивается")


def play_sushi(scene) -> None:
    finish_dialogue(scene)
    stations = {station.ingredient: station for station in sushi.STATIONS}
    for recipe in RECIPES:
        for ingredient in recipe.ingredients:
            scene.alice.set_position(*stations[ingredient].point)
            press_e(scene)
            scene.alice.set_position(sushi.TABLE.centerx, sushi.TABLE.top - 2)
            press_e(scene)
        finish_dialogue(scene)
    finish_dialogue(scene)


def play_forms(scene) -> None:
    finish_dialogue(scene)
    cabinets = {cabinet.section.id: cabinet.point for cabinet in forms.CABINETS}
    for section in ("holidays", "requests", "permits"):
        scene.alice.set_position(*cabinets[section])
        press_e(scene)
        finish_dialogue(scene)
    for slot in (2, 0, 2, 1):
        scene.alice.set_position(forms.SLOT_XS[slot], forms.SLOT_Y)
        press_e(scene)
    scene.alice.set_position(forms.GOOSE_POSITION[0] - 22, forms.GOOSE_POSITION[1])
    press_e(scene)
    finish_dialogue(scene)
    finish_dialogue(scene)


def play_cakes(scene) -> None:
    finish_dialogue(scene)
    for row in (0, 4, 1, 3, cakes.CHECK_ROW):
        scene.cursor = row
        press_e(scene)
    finish_dialogue(scene)
    scene.update(cakes.ESCAPE_SECONDS + 0.1)
    finish_dialogue(scene)
    for point in MAZE_ROUTE:  # по проверенному маршруту, а не прыжком к ягоде
        scene.alice.set_position(*point)
        scene.update(1 / 30)
    press_e(scene)
    finish_dialogue(scene)
    finish_dialogue(scene)


def play_finale(scene) -> None:
    press_e(scene)
    finish_dialogue(scene)
    for _ in final_text.LETTER_PAGES:
        press_e(scene)  # проявить
        press_e(scene)  # перелистнуть
    scene.update(PAUSE_SECONDS + 0.01)
    press_e(scene)
    press_e(scene)
    finish_dialogue(scene)
    scene.update(CREDITS_SECONDS + 0.01)
    scene.update(END_INPUT_DELAY + 0.01)
    press_e(scene)


PLAYS = {
    sushi.SushiTrialScene: play_sushi,
    forms.FormsTrialScene: play_forms,
    cakes.CakesTrialScene: play_cakes,
    FinalScene: play_finale,
}


def full_progress() -> GameProgress:
    progress = GameProgress()
    for trial in TRIALS:
        progress.complete(trial)
    return progress


def transform_for(window_size) -> ViewTransform:
    return ViewTransform(fit_viewport(window_size, config.LOGICAL_SIZE, config.INTEGER_SCALING))


class Recorder:
    """Рисует сцену в строгий слой после каждого события и каждого шага времени.

    Строгий слой падает, если логическая графика выходит за заявленную область. Записывает,
    какие кадры персонажей и надписи были в слое, — чтобы проверить их после прохождения.
    """

    def __init__(self, scene, fonts: TextFonts) -> None:
        self.scene = scene
        self.layer = HiResLayer(fonts, strict=True)
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.frames = 0
        self.sprite_images: set[int] = set()
        self.texts: set[str] = set()
        handle, update = scene.handle_event, scene.update

        def handle_event(event):
            handle(event)
            self.draw()

        def step(dt):
            while dt > 1e-9:  # мелкими шагами: кадр рисуется и в середине анимаций
                part = min(dt, 1 / 15)
                update(part)
                dt -= part
                self.draw()

        scene.handle_event, scene.update = handle_event, step

    def draw(self) -> None:
        self.layer.clear()
        self.scene.draw(self.canvas, self.layer)
        self.frames += 1
        for command in self.layer.commands:
            if isinstance(command, SpriteCommand):
                self.sprite_images.add(id(command.image))
            elif isinstance(command, TextCommand):
                self.texts.add(command.text)


class SceneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode(WINDOWED)
        self.fonts = TextFonts()

    def tearDown(self) -> None:
        pygame.quit()

    def draw(self, scene) -> tuple[HiResLayer, pygame.Surface]:
        layer, canvas = HiResLayer(self.fonts, strict=True), pygame.Surface(config.LOGICAL_SIZE)
        scene.draw(canvas, layer)
        return layer, canvas


class PlaythroughTest(SceneTestCase):
    def test_every_scene_plays_through_the_layer_with_the_same_outcome(self) -> None:
        for scene_class, play in PLAYS.items():
            with self.subTest(scene=scene_class.__name__):
                self.assertTrue(scene_class.supports_hires)
                progress = full_progress() if scene_class is FinalScene else GameProgress()
                scene = scene_class(progress)
                recorder = Recorder(scene, self.fonts)
                play(scene)
                self.assertGreater(recorder.frames, 40)
                self.assertTrue(scene.completed)
                if scene_class is not FinalScene:
                    self.assertTrue(scene.reward_given)  # фрагмент выдан, как и без слоя
                    self.assertEqual(progress.fragments, 1)

    def test_finale_shows_the_same_screens_with_and_without_the_layer(self) -> None:
        plain, drawn = FinalScene(full_progress()), FinalScene(full_progress())
        play_finale(plain)
        Recorder(drawn, self.fonts)
        play_finale(drawn)
        self.assertEqual(drawn.shown, plain.shown)
        self.assertEqual(drawn.shown.count("pause"), 1)
        self.assertEqual([item for item in drawn.shown if item.startswith("letter_")],
                         [f"letter_{page}" for page in range(len(final_text.LETTER_PAGES))])

    def test_cancel_still_returns_without_a_reward(self) -> None:
        for scene_class in SCENES[:3]:
            with self.subTest(scene=scene_class.__name__):
                progress = GameProgress()
                scene = scene_class(progress)
                Recorder(scene, self.fonts)
                finish_dialogue(scene)
                press(scene, pygame.K_BACKSPACE)
                self.assertTrue(scene.is_finished)
                self.assertFalse(scene.completed)
                self.assertEqual(progress.fragments, 0)

    def test_scenes_without_sprites_draw_placeholders_through_the_layer(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            for scene_class, play in PLAYS.items():
                with self.subTest(scene=scene_class.__name__):
                    progress = full_progress() if scene_class is FinalScene else GameProgress()
                    scene = scene_class(progress, characters_dir=Path(empty))
                    recorder = Recorder(scene, self.fonts)
                    play(scene)
                    self.assertTrue(scene.completed)
                    self.assertTrue(recorder.sprite_images)


class CharacterTest(SceneTestCase):
    def sprites(self, layer: HiResLayer) -> list[SpriteCommand]:
        return [c for c in layer.commands if isinstance(c, SpriteCommand)]

    def assert_same_pixels(self, first: pygame.Surface, second: pygame.Surface) -> None:
        self.assertEqual(pygame.image.tobytes(first, "RGBA"), pygame.image.tobytes(second, "RGBA"))

    def test_npcs_use_their_own_manifest_frames_unmirrored_on_the_same_place(self) -> None:
        cases = [
            (sushi.SushiTrialScene(), "cat_chef", "chef_pose", sushi.CHEF_POSITION),
            (forms.FormsTrialScene(), "goose_inspector", "goose_pose", forms.GOOSE_POSITION),
            (cakes.CakesTrialScene(), "chuchmek", "chuchmek_pose", cakes.CHUCHMEK_SPOT),
        ]
        for scene, char_id, pose_attr, feet in cases:
            manifest = load_character_sprites(CHARACTERS_DIR / char_id)
            for frame in manifest.frames[:6]:
                setattr(scene, pose_attr, frame.id)
                layer, canvas = self.draw(scene)
                rect = pygame.Rect(0, 0, 32, 32)
                rect.midbottom = feet
                npc = [c for c in self.sprites(layer) if c.rect == rect]
                with self.subTest(character=char_id, pose=frame.id):
                    self.assertEqual(len(npc), 1)
                    self.assertEqual(npc[0].image.get_size(), (64, 64))
                    self.assert_same_pixels(npc[0].image, frame.image)  # тот же кадр, не отражённый

    def test_finale_actors_use_original_frames_at_their_feet(self) -> None:
        scene = FinalScene(full_progress())
        alice = load_character_sprites(CHARACTERS_DIR / "alice")
        chuchmek = load_character_sprites(CHARACTERS_DIR / "chuchmek")
        layer, _ = self.draw(scene)
        rects = {}
        for command in self.sprites(layer):
            rects[command.rect.midbottom] = command
        for who, manifest, pose, feet in (("alice", alice, scene.alice_pose, (104, 108)),
                                          ("chuchmek", chuchmek, scene.chuchmek_pose, (218, 108))):
            with self.subTest(who=who):
                command = rects[feet]
                self.assertEqual(command.rect.size, (48, 48))
                self.assert_same_pixels(command.image, manifest.frame(pose).image)

    def test_no_character_stays_on_the_canvas(self) -> None:
        # Двойного силуэта нет: там, где стоят персонажи, холст — тот же, что и фон без них.
        scene = sushi.SushiTrialScene()
        finish_dialogue(scene)
        layer, canvas = self.draw(scene)
        chef = pygame.Rect(0, 0, 32, 32)
        chef.midbottom = sushi.CHEF_POSITION
        for rect in (scene.alice.rect, chef):
            area = rect.clip(pygame.Rect(0, sushi.HUD_HEIGHT, WIDTH, sushi.STATUS_TOP - sushi.HUD_HEIGHT))
            self.assertEqual(pygame.image.tobytes(canvas.subsurface(area), "RGB"),
                             pygame.image.tobytes(scene._background_plain.subsurface(area), "RGB"))

    def test_alice_walks_with_the_same_frames_and_pace(self) -> None:
        scene = forms.FormsTrialScene()
        finish_dialogue(scene)
        scene.alice.set_position(160, 74)
        scene.handle_event(key(pygame.K_RIGHT, pygame.KSCAN_RIGHT))
        walk = scene.alice.animations.get(WALK, Direction.RIGHT)
        seen = []
        for _ in range(40):
            scene.update(1 / 60)
            layer, _ = self.draw(scene)
            (alice,) = [c for c in self.sprites(layer) if c.rect == scene.alice.rect]
            self.assertIs(alice.image, walk.sources[scene.alice.player.frame_index])
            seen.append(scene.alice.player.frame_index)
        self.assertEqual(seen, [int((k + 1) / 60 * walk.fps + 1e-9) % len(walk.frames) for k in range(40)])

    def test_drawing_never_moves_anyone(self) -> None:
        scene = cakes.CakesTrialScene()
        play_cakes_until_maze(scene)
        scene.alice.set_position(*MAZE_ROUTE[3])
        before = (scene.alice.x, scene.alice.y, scene.alice.direction)
        for size in (WINDOWED, FULLSCREEN):
            layer, _ = self.draw(scene)
            layer.render(pygame.Surface(size), transform_for(size))
        self.assertEqual((scene.alice.x, scene.alice.y, scene.alice.direction), before)


def play_cakes_until_maze(scene) -> None:
    finish_dialogue(scene)
    for row in (0, 4, 1, 3, cakes.CHECK_ROW):
        scene.cursor = row
        press_e(scene)
    finish_dialogue(scene)
    scene.update(cakes.ESCAPE_SECONDS + 0.1)
    finish_dialogue(scene)


class LayerOrderTest(SceneTestCase):
    def index(self, layer: HiResLayer, predicate) -> int:
        return next(i for i, command in enumerate(layer.commands) if predicate(command))

    def test_sushi_interface_lies_over_alice_at_the_counter(self) -> None:
        scene = sushi.SushiTrialScene()
        finish_dialogue(scene)
        scene.alice.set_position(sushi.STATION_XS[2], sushi.WALK_BOUNDS.top)  # голова — у полосы интерфейса
        layer, _ = self.draw(scene)
        alice = self.index(layer, lambda c: isinstance(c, SpriteCommand) and c.rect == scene.alice.rect)
        hud = self.index(layer, lambda c: isinstance(c, PatchCommand) and c.rect.top == 0)
        label = self.index(layer, lambda c: isinstance(c, TextCommand) and c.text == INGREDIENT_NAMES["nori"])
        self.assertLess(label, alice)  # подпись станции — часть фона
        self.assertLess(alice, hud)

    def test_forms_table_covers_alice_behind_it_and_cards_are_on_top(self) -> None:
        scene = forms.FormsTrialScene()
        play_forms_until_table(scene)
        scene.alice.set_position(forms.SLOT_XS[1], forms.SLOT_Y)  # за столом
        layer, _ = self.draw(scene)
        alice = self.index(layer, lambda c: isinstance(c, SpriteCommand) and c.rect == scene.alice.rect)
        table = self.index(layer, lambda c: isinstance(c, PatchCommand) and c.rect == forms.TABLE_AREA)
        cards = [i for i, c in enumerate(layer.commands) if isinstance(c, TextCommand)
                 and c.text in forms.DOCUMENT_ABBREVIATIONS.values()]
        self.assertLess(alice, table)
        self.assertTrue(cards and min(cards) > table)

    def test_cakes_strawberry_and_dialogue_order(self) -> None:
        scene = cakes.CakesTrialScene()
        play_cakes_until_maze(scene)
        scene.alice.set_position(*MAZE_ROUTE[-1])  # в последнем закутке, откуда ягоду ловят
        scene.update(cakes.TOAST_PRIORITY_SECONDS + 0.1)  # свежее сообщение о кладовой уступило подсказке
        layer, _ = self.draw(scene)
        self.assertTrue(any(isinstance(c, SpriteCommand) and c.rect == scene.alice.rect for c in layer.commands))
        hint = [c.text for c in layer.commands if isinstance(c, TextCommand)]
        self.assertIn("Клубника   E — поймать", hint)
        press_e(scene)
        for alice_feet in (MAZE_ROUTE[-1], (MAZE_ROUTE[-1][0], 150)):  # как в игре и ниже края окна
            scene.alice.set_position(*alice_feet)
            layer, _ = self.draw(scene)
            self.assert_box_over_sprites(scene, layer)

    def assert_box_over_sprites(self, scene, layer: HiResLayer) -> None:
        """Окно реплики поверх героев: кого оно задевает, того закрывает заплатка после него."""
        layout = scene.box.layout(scene.dialogue.node, hires=True)
        box = layout.box.union(layout.name_tab) if layout.name_tab else layout.box
        for index, command in enumerate(layer.commands):
            if isinstance(command, SpriteCommand) and command.rect.colliderect(box):
                later = [c for c in layer.commands[index:] if isinstance(c, PatchCommand) and c.rect.contains(box)]
                self.assertTrue(later, command.rect)

    def test_finale_veil_dim_letter_and_words_go_in_order(self) -> None:
        scene = FinalScene(full_progress())
        scene.update(0.2)
        layer, _ = self.draw(scene)
        sprites = [i for i, c in enumerate(layer.commands) if isinstance(c, SpriteCommand)]
        veil = self.index(layer, lambda c: isinstance(c, FillCommand))
        self.assertLess(max(sprites), veil)  # страница проявляется вместе с героями
        press_e(scene)
        finish_dialogue(scene)
        scene.update(0.25)  # лист наполовину проявился
        layer, _ = self.draw(scene)
        sprites = [i for i, c in enumerate(layer.commands) if isinstance(c, SpriteCommand)]
        dim = self.index(layer, lambda c: isinstance(c, FillCommand))
        sheet = self.index(layer, lambda c: isinstance(c, GroupCommand) and c.rect == PANEL)
        group = layer.commands[sheet]
        words = [c for c in group.commands if isinstance(c, TextCommand) and c.style == LETTER_STYLE]
        self.assertIsNone(layer.commands[dim].rect)  # пока лист прозрачен — притушено всё
        self.assertLess(max(sprites), dim)
        self.assertLess(dim, sheet)
        self.assertTrue(0 < group.alpha < 255)  # лист проявляется целиком, вместе со словами
        self.assertEqual([c.text for c in words], [line for line, _ in scene.letter_layout(0)["lines"] if line])
        self.assertIsInstance(group.commands[0], FillCommand)  # сначала бумага, потом слова
        scene.update(1.0)  # лист проявился целиком: под ним ничего не видно, притушены только поля
        layer, _ = self.draw(scene)
        dims = [c for c in layer.commands if isinstance(c, FillCommand) and c.color == NIGHT_COLOR]
        self.assertTrue(dims and all(c.rect is not None and not c.rect.colliderect(PANEL) for c in dims))
        self.assertEqual(sum(c.rect.width * c.rect.height for c in dims) + PANEL.width * PANEL.height, WIDTH * HEIGHT)
        sheet = next(c for c in layer.commands if isinstance(c, GroupCommand))
        self.assertEqual(sheet.alpha, 255)


def play_forms_until_table(scene) -> None:
    finish_dialogue(scene)
    cabinets = {cabinet.section.id: cabinet.point for cabinet in forms.CABINETS}
    for section in ("holidays", "requests", "permits"):
        scene.alice.set_position(*cabinets[section])
        press_e(scene)
        finish_dialogue(scene)


class UpsideDownTest(SceneTestCase):
    def test_board_title_and_signs_stay_upside_down(self) -> None:
        scene = cakes.CakesTrialScene()
        layer, _ = self.draw(scene)
        angles = {c.text: c.angle for c in layer.commands if isinstance(c, TextCommand)}
        self.assertEqual(angles["РЕЦЕПТ ТОРТА"], 180)
        self.assertEqual(angles["ТОРТЫ"], 180)
        play_cakes_until_maze(scene)
        layer, _ = self.draw(scene)
        angles = {c.text: c.angle for c in layer.commands if isinstance(c, TextCommand)}
        self.assertEqual(angles["КЛАДОВАЯ"], 180)
        solved = cakes.CakesTrialScene()
        finish_dialogue(solved)
        for row in (0, 4, 1, 3, cakes.CHECK_ROW):
            solved.cursor = row
            press_e(solved)
        layer, _ = self.draw(solved)
        angles = {c.text: c.angle for c in layer.commands if isinstance(c, TextCommand)}
        self.assertEqual(angles["РЕЦЕПТ ТОРТА"], 0)  # рецепт исправлен — заголовок встал ровно

    def test_rotated_text_is_the_same_letters_turned_over(self) -> None:
        layer = HiResLayer(self.fonts)
        style = cakes.SIGN_STYLE
        for scale in (3, 6):
            upright = layer.text_image("ТОРТЫ", style, scale)
            turned = layer.text_image("ТОРТЫ", style, scale, 180)
            expected = pygame.transform.flip(upright, True, True)
            self.assertEqual(pygame.image.tobytes(turned, "RGBA"), pygame.image.tobytes(expected, "RGBA"))

    def test_turned_text_is_drawn_upside_down_in_the_window(self) -> None:
        style = TextStyle(9, (255, 255, 255))
        for angle in (0, 180):
            layer = HiResLayer(self.fonts)
            layer.text("Т", style, (160, 90), anchor="center", angle=angle)
            screen = pygame.Surface(WINDOWED)
            layer.render(screen, transform_for(WINDOWED))
            rows = [y for y in range(200, 340) if any(screen.get_at((x, y)).r > 200 for x in range(440, 520))]
            columns_top = sum(screen.get_at((x, rows[0] + 1)).r > 200 for x in range(440, 520))
            columns_bottom = sum(screen.get_at((x, rows[-1] - 1)).r > 200 for x in range(440, 520))
            # У «Т» перекладина сверху; у перевёрнутой — снизу.
            if angle:
                self.assertGreater(columns_bottom, columns_top)
            else:
                self.assertGreater(columns_top, columns_bottom)


class StrawberryTest(SceneTestCase):
    def test_strawberry_is_drawn_where_it_can_be_caught(self) -> None:
        scene = cakes.CakesTrialScene()
        play_cakes_until_maze(scene)
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer(self.fonts, strict=True)
        scene.alice.set_position(*MAZE_ROUTE[-1])
        self.assertTrue(strawberry_in_reach(*MAZE_ROUTE[-1]))
        scene.draw(canvas, layer)
        for size in (WINDOWED, FULLSCREEN):
            transform = transform_for(size)
            screen = pygame.Surface(size)
            pygame.transform.scale(canvas, transform.viewport.size, screen.subsurface(transform.viewport))
            layer.render(screen, transform)
            red = pygame.mask.from_threshold(screen, cakes.STRAWBERRY_COLOR, (1, 1, 1, 255))
            body = max(red.get_bounding_rects(), key=lambda rect: rect.width * rect.height)
            expected = transform.point(STRAWBERRY_POSITION)
            with self.subTest(window=size):
                # Середина ягоды — в точке клубники с точностью до пары логических пикселей.
                self.assertLessEqual(abs(body.centerx - expected[0]), 2 * transform.scale)
                self.assertLessEqual(abs(body.centery - expected[1]), 3 * transform.scale)


class TextFitTest(SceneTestCase):
    def variants(self):
        return {"системный": self.fonts, "встроенный": TextFonts(None)}

    def assert_fits(self, fonts: TextFonts, style: TextStyle, text: str, width: float) -> None:
        for scale in (3, 6):
            font = fonts.font(style.size, scale, style.bold)
            self.assertLessEqual(font.size(text)[0], width * scale, (text, scale))

    def test_sushi_texts(self) -> None:
        scene = sushi.SushiTrialScene()
        names = list(INGREDIENT_NAMES.values())
        statuses = [f"Вернула на место: {a}. Взяла: {b}" for a in names for b in names]
        statuses += [f"{n}: не для этого заказа — верни на место" for n in names]
        statuses += [f"{n}   E — вернуть на место" for n in names]
        statuses += ["Руки пусты — сначала возьми ингредиент", "Тарелка   сначала возьми ингредиент",
                     "Стрелки/WASD — идти   E — действие   Backspace — уйти"]
        statuses += [f"Новый заказ: {recipe.name}" for recipe in RECIPES]
        for name, fonts in self.variants().items():
            with self.subTest(font=name):
                for text in statuses:
                    self.assert_fits(fonts, sushi.HUD_STYLE, text, WIDTH - 8)
                for station in sushi.STATIONS:
                    self.assert_fits(fonts, sushi.LABEL_STYLE, station.name, 46)  # между соседними мисками
                for recipe in RECIPES:
                    order = f"Заказ 3/3: {recipe.name}"
                    for held in names:
                        width = sum(fonts.metrics(sushi.HUD_STYLE).width(t) for t in (order, f"В руках: {held}"))
                        self.assertLess(width + 16, WIDTH)  # две половины верхней строки не сходятся
        for recipe in RECIPES:  # вторая строка: значки, подписи и все галочки помещаются в ширину
            scene.orders = SushiOrders([recipe])
            for ingredient in recipe.ingredients:
                scene.orders.held = ingredient
                scene.orders.place()
            for name, fonts in self.variants().items():
                scene.text_metrics = fonts.metrics(sushi.HUD_STYLE)
                items = scene.hud_items(hires=True)
                with self.subTest(recipe=recipe.name, font=name):
                    self.assertEqual(len(items), len(recipe.ingredients))
                    self.assertTrue(all(done for _, done, _, _ in items))
                    self.assertLess(items[-1][3] + 8, WIDTH)

    def test_forms_texts(self) -> None:
        scene = forms.FormsTrialScene()
        long_names = [section.name for section in SECTIONS]
        self.assertIn("Праздники, которые не состоялись", long_names)
        statuses = [f"«{name}»   E — искать" for name in long_names]
        documents = list(DOCUMENT_NAMES.values())
        statuses += [f"Поменяла местами: {a} и {b}" for a in documents for b in documents]
        statuses += [f"Место 3: {d}   E — поменять местами" for d in documents]
        statuses += ["Стол подачи   найдено документов: 2/3", "Все документы на столе — разложи их по порядку"]
        for name, fonts in self.variants().items():
            with self.subTest(font=name):
                for text in statuses:
                    self.assert_fits(fonts, forms.HUD_STYLE, text, WIDTH - 8)
                for cabinet in forms.CABINETS:
                    plaque = scene.cabinet_plaque(cabinet)
                    self.assert_fits(fonts, forms.PLAQUE_STYLE, cabinet.section.label, plaque.width - 2)
                for abbreviation in forms.DOCUMENT_ABBREVIATIONS.values():
                    self.assert_fits(fonts, forms.CARD_STYLES["application"], abbreviation, 17)  # до пометки вида
                metrics = fonts.metrics(forms.HUD_STYLE)
                task = metrics.width("Задача: разложи по порядку и сдай гусю")
                held = max(metrics.width(f"В руках: {d}") for d in documents)
                self.assertLess(task + held + 8, WIDTH)
                order = "Стол: 1 Согласование → 2 Разрешение → 3 Заявление"
                self.assertLess(metrics.width(order) + 8, WIDTH)
                for text, x in forms.COUNTER_SIGNS:
                    self.assert_fits(fonts, forms.PLAQUE_STYLE, text, 150)

    def test_cakes_texts(self) -> None:
        scene = cakes.CakesTrialScene()
        row_width = scene.row_rect(0).width - 28 - 2
        short = STEP_SHORT_NAMES.values()
        statuses = [f"Поменяла местами: {a} и {b}" for a in short for b in short]
        statuses += ["Стрелки — выбрать этап   E — взять   Backspace — уйти",
                     "E — проверить рецепт   Стрелки — к этапам",
                     "Стрелки/WASD — идти   E — поймать клубнику   Backspace — уйти",
                     "Клубника не здесь — она в дальнем углу кладовой", "Клубника   E — поймать"]
        for name, fonts in self.variants().items():
            with self.subTest(font=name):
                for step in STEP_NAMES.values():
                    self.assert_fits(fonts, cakes.CHALK_STYLE, step, row_width)
                self.assert_fits(fonts, cakes.CHALK_STYLE, "Проверить рецепт", cakes.CHECK_BUTTON.width - 4)
                self.assert_fits(fonts, cakes.CHALK_STYLE, "РЕЦЕПТ ТОРТА", cakes.BOARD.width - 8)
                for text in statuses:
                    self.assert_fits(fonts, cakes.HUD_STYLE, text, WIDTH - 8)
                metrics = fonts.metrics(cakes.HUD_STYLE)
                part = metrics.width("Часть 2 из 2 — клубника")
                held = max(metrics.width(f"Взят этап: {n}") for n in STEP_SHORT_NAMES.values())
                self.assertLess(part + held + 8, WIDTH)
                for text, center in cakes.SIGNS.values():
                    rect = cakes.CakesTrialScene.sign_rect(scene, text, center, hires=True)
                    self.assertTrue(pygame.Rect(0, cakes.HUD_HEIGHT, WIDTH, HEIGHT).contains(rect))

    def test_letter_fits_its_sheet_with_real_font_metrics(self) -> None:
        for name, fonts in self.variants().items():
            scene = FinalScene(full_progress())
            scene._fonts = fonts
            scene.letter_metrics = fonts.metrics(LETTER_STYLE)
            pages = [scene._wrap(page, hires=True) for page in final_text.LETTER_PAGES]
            gift = scene._wrap(final_text.GIFT_TEXT, hires=True)
            with self.subTest(font=name):
                self.assertEqual(len(pages), 5)  # листов столько же
                for source, lines in zip((*final_text.LETTER_PAGES, final_text.GIFT_TEXT), (*pages, gift)):
                    self.assertEqual(" ".join(lines).split(), source.split())  # ни одно слово не потеряно
                    self.assertLessEqual(len(lines), scene.max_letter_lines(hires=True))
                    for line in lines:
                        self.assert_fits(fonts, LETTER_STYLE, line, PANEL.width - 2 * PANEL_PADDING)
        scene = FinalScene(full_progress())
        for key in (len(final_text.LETTER_PAGES) - 1, -1):  # подпись — на последнем листе и под подарком
            layout = scene.letter_layout(key)
            self.assertIsNotNone(layout["signature"])
            self.assertLessEqual(layout["lines_bottom"], layout["signature_top"])
            self.assertLess(layout["signature_top"] + 12, PANEL.bottom)
        for key in range(len(final_text.LETTER_PAGES) - 1):
            self.assertIsNone(scene.letter_layout(key)["signature"])

    def test_no_line_of_any_dialogue_or_the_letter_starts_with_a_dash(self) -> None:
        # Тире посреди фразы не переносится в начало строки — ни в репликах, ни в письме.
        from game.dialogue.box import DialogueBox, wrap_spans
        from game.story import cakes_dialogue, forms_dialogue, hub_dialogue, intro_dialogue, sushi_dialogue

        def assert_no_dash_at_line_start(text: str, spans, where: str) -> None:
            for start, _ in spans:
                inside_paragraph = start > 0 and text[start - 1] != "\n"
                self.assertFalse(inside_paragraph and text[start] in "—–", (where, text[start:start + 30]))

        box = DialogueBox(self.fonts)
        for module in (intro_dialogue, hub_dialogue, sushi_dialogue, forms_dialogue, cakes_dialogue, final_text):
            for script in module.all_scripts():
                for node in script.nodes.values():
                    for hires in (False, True):
                        assert_no_dash_at_line_start(node.text, box.layout(node, hires).text_spans, node.id)
        scene = FinalScene(full_progress())
        for page in (*final_text.LETTER_PAGES, final_text.GIFT_TEXT):
            spans = wrap_spans(page, scene.letter_metrics, PANEL.width - 2 * PANEL_PADDING)
            assert_no_dash_at_line_start(page, spans, "письмо")

    def test_finale_titles_credits_and_end_fit(self) -> None:
        for name, fonts in self.variants().items():
            with self.subTest(font=name):
                for kind, line in final_text.CREDITS:
                    if line:
                        self.assert_fits(fonts, CREDIT_STYLES[kind], line, WIDTH - 8)
                for line in final_text.THE_END_LINES:
                    self.assert_fits(fonts, THE_END_STYLE, line, WIDTH - 16)
                self.assert_fits(fonts, TextStyle(9, (0, 0, 0)), final_text.EXIT_HINT, WIDTH - 8)
                self.assert_fits(fonts, TextStyle(6, (0, 0, 0), bold=True), "F-17: ОТКАЗАНО", 72)


class SolidBackgroundTextTest(SceneTestCase):
    """Строки, нарисованные сразу на своём фоне (TextStyle.background), должны выглядеть так же,
    как прозрачные поверх того же места: прямоугольник фона ничего рядом не закрывает."""

    def render(self, canvas: pygame.Surface, layer: HiResLayer, size) -> pygame.Surface:
        transform = transform_for(size)
        screen = pygame.Surface(size)
        pygame.transform.scale(canvas, transform.viewport.size, screen.subsurface(transform.viewport))
        layer.render(screen, transform)
        return screen

    def assert_like_transparent(self, scene, name: str) -> None:
        layer, canvas = self.draw(scene)
        solid = [c for c in layer.commands if isinstance(c, TextCommand) and c.style.background is not None]
        self.assertTrue(solid, name)
        for size in (WINDOWED, FULLSCREEN):
            fast = self.render(canvas, layer, size)
            layer.commands = [replace(c, style=replace(c.style, background=None)) if c in solid else c
                              for c in layer.commands]
            plain = self.render(canvas, layer, size)
            layer.commands = [c for c in layer.commands]
            difference = fast.copy()
            difference.blit(plain, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
            other = plain.copy()
            other.blit(fast, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
            difference.blit(other, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            close = pygame.mask.from_threshold(difference, (0, 0, 0), (6, 6, 6, 255))
            with self.subTest(state=name, window=size):
                # Сглаживание на фоне и поверх фона отличается лишь округлением.
                self.assertEqual(close.count(), size[0] * size[1])
            layer, canvas = self.draw(scene)

    def test_texts_on_solid_backgrounds_look_like_transparent_ones(self) -> None:
        hub = HubScene()
        self.assert_like_transparent(hub, "площадь")
        hub.alice.set_position(214, 100)
        hub.interact()
        hub.update(30.0)
        self.assert_like_transparent(hub, "площадь: реплика")
        sushi_scene = sushi.SushiTrialScene()
        sushi_scene.update(30.0)
        self.assert_like_transparent(sushi_scene, "суши: реплика")
        finish_dialogue(sushi_scene)
        sushi_scene.alice.set_position(*sushi.STATIONS[1].point)
        press_e(sushi_scene)
        sushi_scene.update(2.0)
        self.assert_like_transparent(sushi_scene, "суши: интерфейс")
        forms_scene = forms.FormsTrialScene()
        finish_dialogue(forms_scene)
        self.assert_like_transparent(forms_scene, "формуляры")
        cakes_scene = cakes.CakesTrialScene()
        cakes_scene.update(30.0)
        self.assert_like_transparent(cakes_scene, "торты: реплика")
        finale = FinalScene(full_progress())
        press_e(finale)
        finish_dialogue(finale)
        finale.update(1.0)
        self.assert_like_transparent(finale, "письмо")
        for _ in final_text.LETTER_PAGES:
            press_e(finale)
            press_e(finale)
        finale.update(PAUSE_SECONDS + 0.01)
        finale.update(1.0)  # лист секрета проявился
        self.assert_like_transparent(finale, "секрет подарка")
        press_e(finale)
        finish_dialogue(finale)
        finale.update(2.0)
        self.assert_like_transparent(finale, "титры")
        intro = IntroScene()
        for _ in range(20000):
            if intro.cue_name == "error_message" and intro.beat_time > 2.2:
                break
            if intro.dialogue is not None and not intro.dialogue.is_typing:
                intro.dialogue.confirm()
                intro._sync_dialogue()
            else:
                intro.update(1 / 30)
        self.assert_like_transparent(intro, "вступление: сообщение об ошибке")


class LeakTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App()

    def tearDown(self) -> None:
        pygame.quit()

    def test_commands_of_a_closed_scene_do_not_leak_into_the_next_one(self) -> None:
        hub = HubScene(self.app.progress)
        self.app.scenes.replace(hub)
        for name in ("trial_sushi", "trial_forms", "trial_cakes"):
            trial = self.app.scenes.push(name)
            seen = []
            original = self.app.display.hires.render

            def spy(target, transform, seen=seen, original=original):
                seen.append([getattr(c, "text", None) for c in self.app.display.hires.commands])
                original(target, transform)

            self.app.display.hires.render = spy
            self.app._draw()
            trial.finish()
            self.app._draw()
            self.app.display.hires.render = original
            # Верхняя строка испытания: у суши — заказ, у остальных — задача.
            marker = trial.order_text() if name == "trial_sushi" else trial.task_text()
            with self.subTest(trial=name):
                self.assertIn(marker, seen[0])
                self.assertIn("Центральная площадь", seen[1])
                self.assertNotIn(marker, seen[1])  # ни надписей, ни персонажей испытания
                self.assertEqual(self.app.display.hires.commands, [])

    def test_original_assets_and_manifests_are_not_changed(self) -> None:
        files = sorted((config.PROJECT_DIR / "assets" / "characters").rglob("*"))
        digest = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()}
        for size in (WINDOWED, FULLSCREEN):
            pygame.display.set_mode(size, pygame.RESIZABLE)
            for scene_class, play in PLAYS.items():
                progress = full_progress() if scene_class is FinalScene else GameProgress()
                scene = scene_class(progress)
                self.app.scenes.push(scene)
                original_update = scene.update

                def update(dt, original_update=original_update):
                    original_update(dt)
                    self.app._draw()

                scene.update = update
                play(scene)
                if self.app.scenes.current is scene:
                    self.app.scenes.pop()
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()}
        self.assertEqual(after, digest)
        self.assertTrue(any(path.suffix == ".json" for path in digest))


if __name__ == "__main__":
    unittest.main()
