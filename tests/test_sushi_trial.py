"""Проверки сцены испытания суши: этапы, награда, отмена, переходы с площади и обратно."""

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
from game.story.sushi_dialogue import CHEF, FINAL, INTRO, REACTIONS, all_scripts, chef_tip  # noqa: E402
from game.trials.sushi_orders import INGREDIENT_NAMES, RECIPES  # noqa: E402
from game.trials.sushi_scene import (  # noqa: E402
    CHEF_POSITION,
    COOKING,
    DONE,
    FINAL_PHASE,
    HUD_HEIGHT,
    INTRO_PHASE,
    REACTION,
    SPAWN,
    SPRITE_SIZE,
    STATION_Y,
    STATIONS,
    STATUS_TOP,
    SUSHI_SCENE,
    TABLE,
    WALK_BOUNDS,
    SushiTrialScene,
)
from game.world.hub import HUB_SCENE, PORTALS, TRIAL_SCENES, HubScene  # noqa: E402
from game.world.progress import GameProgress  # noqa: E402

DT = 1 / 60
STATION = {station.ingredient: station for station in STATIONS}
PLATE_SPOT = (TABLE.centerx, TABLE.top - 2)  # над столом: там Алиса дотягивается до тарелки


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press(scene: Scene, code: int, scancode: int = 0) -> None:
    scene.handle_event(key(code, scancode))
    scene.handle_event(key(code, scancode, pygame.KEYUP))


def finish_dialogue(scene: SushiTrialScene) -> list[str]:
    """Пролистывает текущий диалог клавишей Enter (только его, не следующий) и возвращает показанные реплики."""
    shown = []
    script = scene.dialogue.script if scene.dialogue is not None else None
    while scene.dialogue is not None and scene.dialogue.script is script:
        shown.append(scene.dialogue.node.id)
        press(scene, pygame.K_RETURN)  # дописать
        if scene.dialogue is not None and scene.dialogue.script is script:
            press(scene, pygame.K_RETURN)  # дальше
    return shown


def stand_at(scene: SushiTrialScene, point: tuple[int, int]) -> None:
    scene.alice.set_position(*point)


def bring(scene: SushiTrialScene, ingredient: str) -> None:
    """Взять ингредиент на станции и положить на тарелку клавишей E."""
    stand_at(scene, STATION[ingredient].point)
    press(scene, pygame.K_e, pygame.KSCAN_E)
    stand_at(scene, PLATE_SPOT)
    press(scene, pygame.K_e, pygame.KSCAN_E)


def cook_all(scene: SushiTrialScene, stop_before_final_end: bool = False) -> None:
    """Проходит испытание: вступление, три заказа с реакциями, финальная реплика."""
    finish_dialogue(scene)
    for recipe in RECIPES:
        for ingredient in recipe.ingredients:
            bring(scene, ingredient)
        finish_dialogue(scene)  # реакция повара
    if not stop_before_final_end:
        finish_dialogue(scene)  # финал


class TrialTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.progress = GameProgress()
        self.manager = SceneManager()
        self.hub = self.manager.push(HubScene(self.progress))
        self.scene = self.manager.push(SushiTrialScene(self.progress))

    def tearDown(self) -> None:
        pygame.quit()


class PhasesTest(TrialTestCase):
    def test_starts_with_chef_intro_and_alice_in_a_safe_spot(self) -> None:
        self.assertEqual(self.scene.phase, INTRO_PHASE)
        self.assertIs(self.scene.dialogue.script, INTRO)
        self.assertEqual(self.scene.dialogue.node.speaker, CHEF)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), SPAWN)
        self.assertTrue(self.scene.collision.is_free(*SPAWN))
        self.assertIsNone(self.scene.nearby())  # у входа ни с чем не взаимодействует случайно

    def test_intro_lines(self) -> None:
        shown = finish_dialogue(self.scene)
        texts = [INTRO.nodes[node_id].text for node_id in shown]
        self.assertEqual(texts[:3], [
            "Добро пожаловать. На моей кухне всё подчиняется точности, чистоте и рису.",
            "А если я просто хочу приготовить суши?",
            "Это и есть самое подозрительное, что ты могла сказать.",
        ])
        self.assertEqual(self.scene.phase, COOKING)

    def test_nothing_moves_or_cooks_during_dialogue(self) -> None:
        stand_at(self.scene, STATION["rice"].point)
        self.scene.handle_event(key(pygame.K_LEFT))
        self.scene.update(1.0)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), STATION["rice"].point)
        self.scene.handle_event(key(pygame.K_LEFT, event_type=pygame.KEYUP))
        self.assertIsNone(self.scene.orders.held)  # E в реплике только листает её
        press(self.scene, pygame.K_e, pygame.KSCAN_E)
        self.assertIsNone(self.scene.orders.held)

    def test_each_order_gets_its_own_reaction_then_next_order(self) -> None:
        finish_dialogue(self.scene)
        for number, recipe in enumerate(RECIPES):
            with self.subTest(order=recipe.name):
                self.assertEqual(self.scene.order_text(), f"Заказ {number + 1}/3: {recipe.name}")
                for ingredient in recipe.ingredients:
                    self.assertEqual(self.scene.phase, COOKING)
                    bring(self.scene, ingredient)
                self.assertEqual(self.scene.phase, REACTION)
                self.assertIs(self.scene.dialogue.script, REACTIONS[number])
                stand_at(self.scene, STATION["rice"].point)
                press(self.scene, pygame.K_RETURN)  # Enter листает реплику, а не берёт рис
                self.assertIsNone(self.scene.orders.held)
                finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertIs(self.scene.dialogue.script, FINAL)

    def test_reaction_texts_are_different(self) -> None:
        texts = [" ".join(node.text for node in script.nodes.values()) for script in REACTIONS]
        self.assertEqual(len(set(texts)), 3)
        self.assertIn("Рис не пытался сбежать", texts[0])
        self.assertIn("Ни одной кулинарной катастрофы", " ".join(node.text for node in FINAL.nodes.values()))

    def test_wrong_and_duplicate_items_are_not_counted_and_explained(self) -> None:
        finish_dialogue(self.scene)
        bring(self.scene, "cucumber")  # не для нигири
        self.assertEqual(self.scene.orders.plate, ())
        self.assertEqual(self.scene.orders.held, "cucumber")
        self.assertIn("не для этого заказа", self.scene.status_text())  # видно даже рядом с тарелкой
        self.assertEqual(self.scene.chef_pose, "stern_side_pose")
        self.scene.update(2.0)
        self.assertEqual(self.scene.chef_pose, "idle_grumpy")
        stand_at(self.scene, STATION["cucumber"].point)
        press(self.scene, pygame.K_e, pygame.KSCAN_E)  # вернуть на место
        self.assertIsNone(self.scene.orders.held)
        bring(self.scene, "rice")
        bring(self.scene, "rice")
        self.assertEqual(self.scene.orders.plate, ("rice",))
        self.assertIn("уже на тарелке", self.scene.status_text())
        self.assertEqual(self.scene.phase, COOKING)  # ошибки не испортили испытание
        self.assertEqual(self.progress.fragments, 0)

    def test_held_item_is_shown(self) -> None:
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.held_text(), "В руках: —")
        stand_at(self.scene, STATION["salmon"].point)
        press(self.scene, pygame.K_e, pygame.KSCAN_E)
        self.assertEqual(self.scene.held_text(), "В руках: Лосось")
        # У стойки (значок сбоку), в правом углу у стойки (слева) и посреди кухни (над головой).
        for spot in (STATION["salmon"].point, (WALK_BOUNDS.right - 6, WALK_BOUNDS.top + 6), (160, 104)):
            stand_at(self.scene, spot)
            self.scene.update(0.25)  # значок не «подпрыгивает»
            self.scene.draw(self.canvas)
            x, y = self.scene.held_icon_center()
            self.assertGreaterEqual(y - 4, HUD_HEIGHT)  # не под полосой интерфейса
            self.assertLessEqual(x + 6, config.LOGICAL_SIZE[0])  # и не за краем экрана
            around = {tuple(self.canvas.get_at((x + dx, y + dy)))[:3] for dx in range(-3, 4) for dy in range(-2, 2)}
            self.assertIn((244, 128, 88), around)  # цвет лосося

    def test_chef_tip_names_what_is_missing(self) -> None:
        finish_dialogue(self.scene)
        bring(self.scene, "rice")
        stand_at(self.scene, (CHEF_POSITION[0] - 18, CHEF_POSITION[1]))
        self.assertEqual(self.scene.nearby().kind, "chef")
        press(self.scene, pygame.K_e, pygame.KSCAN_E)
        self.assertIn("лосось", self.scene.dialogue.node.text)
        self.assertNotIn("рис", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, COOKING)


class RewardTest(TrialTestCase):
    def test_fragment_only_after_final_line(self) -> None:
        cook_all(self.scene, stop_before_final_end=True)
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertEqual(self.progress.fragments, 0)  # все заказы готовы, но финал ещё не сказан
        finish_dialogue(self.scene)
        self.assertEqual(self.progress.completed, ("sushi",))
        self.assertTrue(self.scene.reward_given)
        self.assertEqual(self.scene.phase, DONE)
        self.assertIs(self.manager.current, self.hub)  # та же площадь, не новая

    def test_progress_does_not_change_while_cooking(self) -> None:
        finish_dialogue(self.scene)
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                bring(self.scene, ingredient)
                self.assertEqual(self.progress.fragments, 0)
            finish_dialogue(self.scene)
            self.assertEqual(self.progress.fragments, 0)

    def test_cancel_returns_to_hub_without_reward_at_any_stage(self) -> None:
        stages = {
            "вступление": lambda scene: None,
            "готовка": lambda scene: (finish_dialogue(scene), bring(scene, "rice")),
            "реакция": lambda scene: (finish_dialogue(scene), bring(scene, "rice"), bring(scene, "salmon")),
            "финал": lambda scene: cook_all(scene, stop_before_final_end=True),
        }
        for stage, prepare in stages.items():
            with self.subTest(stage=stage):
                progress = GameProgress()
                manager = SceneManager()
                manager.register(SUSHI_SCENE, lambda: SushiTrialScene(progress))
                hub = manager.push(HubScene(progress))
                hub.alice.set_position(*next(portal for portal in PORTALS if portal.id == "sushi").point)
                hub.interact()  # вход через портал площади
                scene = manager.current
                self.assertIsInstance(scene, SushiTrialScene)
                prepare(scene)
                press(scene, pygame.K_BACKSPACE)
                self.assertIs(manager.current, hub)
                self.assertEqual(progress.completed, ())
                self.assertFalse(scene.completed)
                self.assertIn("прервано", hub.toast)

    def test_second_run_gives_no_extra_fragment(self) -> None:
        cook_all(self.scene)
        second = self.manager.push(SushiTrialScene(self.progress))
        cook_all(second)
        self.assertTrue(second.completed)
        self.assertFalse(second.reward_given)
        self.assertEqual(self.progress.completed, ("sushi",))
        self.assertEqual(self.progress.fragments, 1)

    def test_only_sushi_is_marked(self) -> None:
        cook_all(self.scene)
        self.assertTrue(self.progress.is_completed("sushi"))
        self.assertFalse(self.progress.is_completed("forms"))
        self.assertFalse(self.progress.is_completed("cakes"))
        self.assertFalse(self.progress.has_all_fragments)


class LayoutTest(TrialTestCase):
    def test_dialogue_box_never_covers_characters(self) -> None:
        box = DialogueBox()
        scripts = all_scripts() + [
            chef_tip(recipe.name, [INGREDIENT_NAMES[item].lower() for item in recipe.ingredients]) for recipe in RECIPES
        ]
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in scripts for node in script.nodes.values())
        self.assertLessEqual(WALK_BOUNDS.bottom, lowest_box)  # ноги Алисы всегда выше окна
        self.assertLessEqual(CHEF_POSITION[1], lowest_box)

    def test_alice_stays_between_interface_strips(self) -> None:
        finish_dialogue(self.scene)
        for keys in ([pygame.K_UP], [pygame.K_DOWN], [pygame.K_LEFT], [pygame.K_RIGHT, pygame.K_DOWN]):
            scene = SushiTrialScene()
            finish_dialogue(scene)
            for code in keys:
                scene.handle_event(key(code))
            for _ in range(300):
                scene.update(DT)
                rect = scene.alice.rect
                self.assertGreaterEqual(rect.top, HUD_HEIGHT)
                self.assertLessEqual(rect.bottom, STATUS_TOP)
                self.assertGreaterEqual(rect.left, 0)
                self.assertLessEqual(rect.right, config.LOGICAL_SIZE[0])
                self.assertTrue(scene.collision.is_free(scene.alice.x, scene.alice.y))

    def test_all_stations_plate_and_chef_are_reachable_on_foot(self) -> None:
        # От входа клавишами: вверх к стойке, вдоль неё ко всем станциям, затем к столу и к повару.
        finish_dialogue(self.scene)
        scene = self.scene
        reached = set()
        scene.handle_event(key(pygame.K_UP))
        for _ in range(120):
            scene.update(DT)
        scene.handle_event(key(pygame.K_UP, event_type=pygame.KEYUP))
        self.assertAlmostEqual(scene.alice.y, WALK_BOUNDS.top + 6)
        scene.handle_event(key(pygame.K_RIGHT))
        for _ in range(240):
            scene.update(DT)
            target = scene.nearby()
            if target is not None and target.kind == "station":
                reached.add(target.ingredient)
        scene.handle_event(key(pygame.K_RIGHT, event_type=pygame.KEYUP))
        self.assertEqual(reached, set(STATION))
        stand_at(scene, (TABLE.centerx, TABLE.bottom + 8))  # снизу стола
        self.assertEqual(scene.nearby().kind, "plate")
        stand_at(scene, (TABLE.left - 8, TABLE.centery))  # сбоку
        self.assertEqual(scene.nearby().kind, "plate")

    def test_stations_do_not_overlap(self) -> None:
        for station in STATIONS:
            stand_at(self.scene, station.point)
            self.assertEqual(self.scene.nearby().ingredient, station.ingredient)
        stand_at(self.scene, (60, STATION_Y))  # между рисом и лососем
        self.assertIsNone(self.scene.nearby())

    def test_texts_fit_on_screen(self) -> None:
        font = self.scene._font
        width = config.LOGICAL_SIZE[0]
        for number, recipe in enumerate(RECIPES):
            order = f"Заказ {number + 1}/3: {recipe.name}"
            self.assertLessEqual(font.size(order)[0] + font.size("В руках: Авокадо")[0], width - 16, order)
            chips = sum(font.size(INGREDIENT_NAMES[item])[0] + 22 for item in recipe.ingredients)
            self.assertLessEqual(chips, width - 8)
        statuses = ["Стрелки/WASD — идти   E — действие   Backspace — уйти", "Кот-повар   E — спросить про заказ",
                    "Руки пусты — сначала возьми ингредиент", "Тарелка   сначала возьми ингредиент"]
        names = list(INGREDIENT_NAMES.values())
        statuses += [f"Вернула на место: {a}. Взяла: {b}" for a in names for b in names]
        statuses += [f"{name}: не для этого заказа — верни на место" for name in INGREDIENT_NAMES.values()]
        statuses += [f"{name}   E — вернуть на место" for name in INGREDIENT_NAMES.values()]
        for text in statuses:
            self.assertLessEqual(font.size(text)[0], width - 8, text)

    def test_chef_is_drawn_from_manifest_without_mirroring(self) -> None:
        source = load_character_sprites(CHARACTERS_DIR / "cat_chef").frame("stern_arms_crossed").image
        self.assertEqual(self.scene.chef_pose, "stern_arms_crossed")  # первая реплика
        expected = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
        self.assertEqual(pygame.image.tobytes(self.scene._chef_image(), "RGBA"), pygame.image.tobytes(expected, "RGBA"))

    def test_draws_every_phase(self) -> None:
        self.scene.draw(self.canvas)
        finish_dialogue(self.scene)
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                bring(self.scene, ingredient)
                self.scene.update(0.1)
                self.scene.draw(self.canvas)
            finish_dialogue(self.scene)
            self.scene.draw(self.canvas)

    def test_missing_sprites_use_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            scene = SushiTrialScene(characters_dir=Path(empty))
            scene.draw(self.canvas)
            cook_all(scene)
            self.assertTrue(scene.completed)


class AppIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App()

    def tearDown(self) -> None:
        pygame.quit()

    def send(self, *events: pygame.event.Event) -> None:
        for event in events:
            pygame.event.post(event)
        self.app._handle_events()

    def press(self, code: int, scancode: int = 0) -> None:
        self.send(key(code, scancode), key(code, scancode, pygame.KEYUP))

    def go_to_sushi_portal(self) -> HubScene:
        self.press(pygame.K_h, pygame.KSCAN_H)
        hub = self.app.scenes.current
        portal = next(portal for portal in PORTALS if portal.id == "sushi")
        hub.alice.set_position(*portal.point)
        return hub

    def test_only_sushi_trial_is_registered(self) -> None:
        self.assertEqual(SUSHI_SCENE, TRIAL_SCENES["sushi"])
        self.assertTrue(self.app.scenes.is_registered("trial_sushi"))
        self.assertFalse(self.app.scenes.is_registered(TRIAL_SCENES["forms"]))
        self.assertFalse(self.app.scenes.is_registered(TRIAL_SCENES["cakes"]))

    def test_portal_opens_trial_and_success_returns_to_the_same_hub(self) -> None:
        hub = self.go_to_sushi_portal()
        self.press(pygame.K_e, pygame.KSCAN_E)
        trial = self.app.scenes.current
        self.assertIsInstance(trial, SushiTrialScene)
        self.assertIs(trial.progress, self.app.progress)
        self.assertEqual([type(scene).__name__ for scene in self.app.scenes.stack],
                         ["DebugScreen", "HubScene", "SushiTrialScene"])
        cook_all(trial)
        self.assertIs(self.app.scenes.current, hub)  # та же площадь, со своим состоянием
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 1/3")
        self.assertIn("Получен фрагмент праздника", hub.toast)
        self.assertIn("(пройдено)", hub.nearby().prompt)
        hub.draw(self.app.display.canvas)

    def test_cancelling_a_completed_trial_is_reported_as_cancelled(self) -> None:
        hub = self.go_to_sushi_portal()
        self.press(pygame.K_e, pygame.KSCAN_E)
        cook_all(self.app.scenes.current)
        self.assertIn("Получен фрагмент", hub.status_text())  # видно, хотя Алиса стоит у портала
        self.press(pygame.K_e, pygame.KSCAN_E)
        self.press(pygame.K_BACKSPACE)
        self.assertIn("прервано", hub.status_text())
        self.assertEqual(self.app.progress.fragments, 1)
        hub.update(2.5)
        self.assertIn("(пройдено)", hub.status_text())  # потом снова подсказка у портала

    def test_replay_from_portal_keeps_one_fragment(self) -> None:
        hub = self.go_to_sushi_portal()
        for run in range(2):
            self.press(pygame.K_e, pygame.KSCAN_E)
            cook_all(self.app.scenes.current)
            self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.fragments, 1)
        self.assertIn("уже пройдено", hub.toast)

    def test_cancel_from_portal_gives_nothing(self) -> None:
        hub = self.go_to_sushi_portal()
        self.press(pygame.K_e, pygame.KSCAN_E)
        self.press(pygame.K_BACKSPACE)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.fragments, 0)
        self.assertIn("прервано", hub.toast)

    def test_other_portals_still_closed(self) -> None:
        self.press(pygame.K_h, pygame.KSCAN_H)
        hub = self.app.scenes.current
        for portal in PORTALS:
            if portal.id == "sushi":
                continue
            hub.alice.set_position(*portal.point)
            self.press(pygame.K_e, pygame.KSCAN_E)
            self.assertIs(self.app.scenes.current, hub)
            self.assertIn("не готов", hub.dialogue.node.text)
            self.press(pygame.K_BACKSPACE)

    def test_escape_f11_and_close_inside_trial(self) -> None:
        self.go_to_sushi_portal()
        self.press(pygame.K_e, pygame.KSCAN_E)
        self.app.running = True
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsInstance(self.app.scenes.current, SushiTrialScene)
        self.app.scenes.update(0.2)
        self.app.scenes.draw(self.app.display.canvas)
        self.app.display.present()
        self.press(pygame.K_F11)
        self.press(pygame.K_ESCAPE)  # ESC — выход из игры, а не отмена испытания
        self.assertFalse(self.app.running)
        self.assertIsInstance(self.app.scenes.current, SushiTrialScene)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)

    def test_debug_keys_still_work_after_the_trial(self) -> None:
        self.go_to_sushi_portal()
        self.press(pygame.K_e, pygame.KSCAN_E)
        cook_all(self.app.scenes.current)
        self.press(pygame.K_BACKSPACE)  # с площади на экран проверки
        screen = self.app.screen
        self.assertIs(self.app.scenes.current, screen)
        keys = (
            (pygame.K_a, pygame.KSCAN_A, "animation_demo"),
            (pygame.K_d, pygame.KSCAN_D, "dialogue"),
            (pygame.K_p, pygame.KSCAN_P, "sprite_gallery"),
            (pygame.K_i, pygame.KSCAN_I, "intro"),
            (pygame.K_h, pygame.KSCAN_H, "hub"),
        )
        for code, scancode, kind in keys:
            with self.subTest(kind=kind):
                self.press(code, scancode)
                self.assertIsNotNone(getattr(screen, kind))
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, screen)
        # Новая площадь видит тот же общий прогресс.
        self.press(pygame.K_h, pygame.KSCAN_H)
        self.assertEqual(self.app.scenes.current.fragments_text(), "Фрагменты праздника: 1/3")
        self.assertIs(self.app.scenes.current.progress, self.app.progress)
        self.assertEqual(HUB_SCENE, "hub")


if __name__ == "__main__":
    unittest.main()
