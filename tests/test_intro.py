"""Проверки сюжетного вступления: сценарий, неблокирующая сцена, переходы и устойчивость к ресурсам."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.debug.debug_screen import DebugScreen  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story.intro_dialogue import (  # noqa: E402
    ALICE,
    BEATS,
    CHOICE_ID,
    CHUCHMEK,
    NARRATOR,
    POSES,
    RABBIT,
    SPEAKER_ACTORS,
    Cue,
    Lines,
    Pause,
    all_scripts,
)
from game.story.intro_scene import SPRITE_SIZE, IntroScene  # noqa: E402

CHOICES = ("Начинаем с суши. У истории должен быть вкус.", "Сначала объясни, почему гриб разговаривает.")


def key(key_code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key_code, mod=0, unicode="", scancode=scancode)


def all_nodes():
    return [node for script in all_scripts() for node in script.nodes.values()]


def play_through(scene: IntroScene, choice_index: int = 0, dt: float = 1 / 60, limit: float = 300.0) -> list[str]:
    """Проходит вступление как игрок: Enter, когда реплика напечатана; в выборе — ↓ нужное число раз.

    Возвращает идентификаторы показанных реплик по порядку.
    """
    shown: list[str] = []
    elapsed = 0.0
    moved = False
    while not scene.completed and not scene.is_finished and elapsed < limit:
        dialogue = scene.dialogue
        if dialogue is not None and dialogue.node is not None:
            if not shown or shown[-1] != dialogue.node.id:
                shown.append(dialogue.node.id)
            if not dialogue.is_typing:
                if dialogue.node.choices and not moved:
                    for _ in range(choice_index):
                        scene.handle_event(key(pygame.K_DOWN))
                    moved = True
                scene.handle_event(key(pygame.K_RETURN))
                scene.handle_event(key(pygame.K_RETURN, event_type=pygame.KEYUP))
                continue
        scene.update(dt)
        elapsed += dt
    return shown


class Base(Scene):
    pass


class IntroTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def tearDown(self) -> None:
        pygame.quit()


class ScriptTest(IntroTestCase):
    def test_scripts_are_valid_and_fit_the_dialogue_box(self) -> None:
        box = DialogueBox()
        for script in all_scripts():
            box.check_fits(script)  # DialogueScript проверил ссылки при создании, здесь — размер окна

    def test_node_ids_are_unique_across_parts(self) -> None:
        ids = [node.id for node in all_nodes()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_speakers_present_and_have_sprites(self) -> None:
        self.assertEqual({node.speaker for node in all_nodes()}, {NARRATOR, ALICE, RABBIT, CHUCHMEK})
        for char_id in SPEAKER_ACTORS.values():
            load_character_sprites(CHARACTERS_DIR / char_id)

    def test_required_lines_are_in_script(self) -> None:
        texts = [node.text for node in all_nodes()]
        joined = " ".join(texts)
        required = [
            "В одной совершенно чудесной стране жила Алиса. В этой стране происходили загадочные события, "
            "случались невероятные приключения, а каждый поворот дорожки обещал нечто необыкновенное.",
            "Звучит неплохо. А где здесь суши?",
            "Суши не предусмотрены классическими сказками.",
            "Тогда классические сказки нуждаются в доработке.",
            "Я опаздываю! По расписанию я должен был появиться три абзаца назад!",
            "Ты же Белый Кролик из Страны чудес?",
            "Да. Но мне сказали, что дальше будет сюжетный поворот, и я не подписывал согласие.",
            "Так. Не паникуем. Я всё контролирую. Кажется.",
            "Ты гриб.",
            "Это должность.",
            "Какая должность?",
            "Временно ответственный по непредсказуемости. Зарплату выдают в компосте.",
            "Нам нужны три сюжетных фрагмента. Без них финальная дверь не откроется.",
            "Что за дверью?",
            "Не знаю. Я гриб, а не экскурсовод.",
            "Три испытания. Суши, формуляры и торты.",
            "Почему формуляры?",
            "Потому что зло бывает разным.",
            "Ладно. Показывай, куда идти. Но если следующее испытание окажется про заполнение двенадцати "
            "формуляров на один суши, я буду задавать вопросы.",
            "Разумно. Хотя формуляр № 12-Б нужен именно для разрешения на вопросы.",
        ]
        for line in required:
            self.assertIn(line, joined)

    def test_parts_go_in_order_with_expected_cues(self) -> None:
        parts = [beat.part for beat in BEATS]
        self.assertEqual(parts, sorted(parts))
        self.assertEqual(sorted(set(parts)), list("ABCDEF"))
        cues = [beat.name for beat in BEATS if isinstance(beat, Cue)]
        expected = ["alice_appears", "rabbit_runs_in", "page_folds", "chuchmek_appears", "alice_reacts", "finale"]
        self.assertEqual(cues, expected)
        self.assertTrue(any(isinstance(beat, Pause) for beat in BEATS if beat.part == "A"))  # пауза для шутки
        rabbit_parts = {beat.part for beat in BEATS if isinstance(beat, Lines) and RABBIT in
                        {node.speaker for node in beat.script.nodes.values()}}
        self.assertEqual(rabbit_parts, {"B"})

    def test_choice_branches_join(self) -> None:
        nodes = {node.id: node for node in all_nodes()}
        choice_node = nodes[CHOICE_ID]
        self.assertEqual(tuple(choice.text for choice in choice_node.choices), CHOICES)
        replies = [nodes[choice.next_id] for choice in choice_node.choices]
        self.assertNotEqual(replies[0].text, replies[1].text)  # ответы Чучмека разные
        self.assertEqual({reply.next_id for reply in replies}, {"e_ready"})  # продолжение общее

    def test_stage_directions_refer_to_real_nodes_and_frames(self) -> None:
        ids = {node.id for node in all_nodes()}
        sprites = {char_id: load_character_sprites(CHARACTERS_DIR / char_id) for char_id in SPEAKER_ACTORS.values()}
        for node_id, poses in POSES.items():
            self.assertIn(node_id, ids)
            for char_id, frame_id in poses.items():
                sprites[char_id].frame(frame_id)  # KeyError, если кадра нет


class SceneFlowTest(IntroTestCase):
    def test_both_choices_lead_to_common_ending(self) -> None:
        for index, reply in ((0, "e_sushi"), (1, "e_talking")):
            with self.subTest(choice=index):
                scene = IntroScene()
                shown = play_through(scene, index)
                self.assertTrue(scene.completed)
                self.assertEqual(scene.choice.text, CHOICES[index])
                self.assertIn(reply, shown)
                other = ({"e_sushi", "e_talking"} - {reply}).pop()
                self.assertNotIn(other, shown)
                self.assertLess(shown.index(reply), shown.index("e_ready"))
                self.assertEqual(shown[-1], "f_form_12b")
                self.assertEqual(len(shown), len(all_nodes()) - 1)  # все реплики, кроме второй ветки

    def test_parts_are_played_in_order(self) -> None:
        scene = IntroScene()
        parts = [scene.part]
        original_update = scene.update

        def tracking_update(dt: float) -> None:
            original_update(dt)
            if scene.part is not None and scene.part != parts[-1]:
                parts.append(scene.part)

        scene.update = tracking_update
        play_through(scene)
        self.assertEqual(parts, list("ABCDEF"))

    def test_effects_depend_on_time_not_frame_count(self) -> None:
        # До первой реплики — эффект появления Алисы (1,2 с), при любом шаге dt.
        for dt in (1 / 30, 1 / 144, 1.0, 5.0):
            with self.subTest(dt=dt):
                scene = IntroScene()
                scene.update(dt)
                expected_beat = 0 if dt < 1.2 else 1
                self.assertEqual(scene.beat_index, expected_beat)
        # Сгиб страницы, появление Чучмека и пауза идут подряд: одно большое dt проходит их все.
        coarse, fine = IntroScene(), IntroScene()
        for scene in (coarse, fine):
            scene.beat_index = BEATS.index(next(b for b in BEATS if isinstance(b, Cue) and b.name == "page_folds"))
            scene._start_beat()
        coarse.update(4.0)
        for _ in range(400):
            fine.update(0.01)
        self.assertEqual(coarse.beat_index, fine.beat_index)
        self.assertIsInstance(coarse.beat, Lines)
        self.assertEqual(coarse.dialogue.node.id, "c_control")
        self.assertEqual(coarse.backdrop, "absurd")

    def test_enter_during_pauses_and_effects_is_ignored(self) -> None:
        scene = IntroScene()
        for _ in range(5):
            scene.handle_event(key(pygame.K_RETURN))
            scene.handle_event(key(pygame.K_RETURN, event_type=pygame.KEYUP))
        self.assertEqual(scene.beat_index, 0)  # эффект появления не пропущен
        scene.update(1.3)
        self.assertEqual(scene.dialogue.node.id, "a_once")
        self.assertTrue(scene.dialogue.is_typing)

    def test_one_enter_is_one_step(self) -> None:
        scene = IntroScene()
        scene.update(1.3)
        scene.handle_event(key(pygame.K_RETURN))  # дописывает реплику
        self.assertEqual(scene.dialogue.node.id, "a_once")
        self.assertFalse(scene.dialogue.is_typing)
        scene.handle_event(key(pygame.K_RETURN))
        self.assertEqual(scene.dialogue.node.id, "a_land")

    def test_characters_stand_above_every_dialogue_box(self) -> None:
        scene = IntroScene()
        box = DialogueBox()
        for node in all_nodes():
            layout = box.layout(node)
            self.assertLess(scene.ground, (layout.name_tab or layout.box).top, node.id)

    def test_sprites_are_scaled_by_nearest_neighbour_without_changing_source(self) -> None:
        scene = IntroScene()
        alice = scene.actors["alice"]
        source = alice.sprites.frame("idle_down").image
        before = pygame.image.tobytes(source, "RGBA")
        image = alice.image()
        self.assertEqual(image.get_size(), (SPRITE_SIZE, SPRITE_SIZE))
        expected = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
        self.assertEqual(pygame.image.tobytes(image, "RGBA"), pygame.image.tobytes(expected, "RGBA"))
        self.assertEqual(pygame.image.tobytes(source, "RGBA"), before)

    def test_draft_groups_are_not_played(self) -> None:
        scene = IntroScene()
        self.assertFalse(scene.actors["white_rabbit"].play("run_right"))
        self.assertFalse(scene.actors["chuchmek"].play("talk"))
        self.assertTrue(scene.actors["alice"].play("react_down"))

    def test_draws_every_moment_without_errors(self) -> None:
        scene = IntroScene()
        elapsed = 0.0
        while not scene.completed and elapsed < 300:
            scene.draw(self.canvas)
            if scene.dialogue is not None and not scene.dialogue.is_typing:
                scene.handle_event(key(pygame.K_RETURN))
            else:
                scene.update(0.05)
                elapsed += 0.05
        self.assertTrue(scene.completed)


class TransitionsTest(IntroTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.manager = SceneManager()
        self.base = self.manager.push(Base())
        self.completed: list[IntroScene] = []

    def test_completion_returns_to_previous_scene(self) -> None:
        intro = self.manager.push(IntroScene(on_complete=self.completed.append))
        play_through(intro)
        self.assertEqual(self.completed, [intro])
        self.assertIs(self.manager.current, self.base)
        self.assertTrue(intro.is_finished)

    def test_completion_can_lead_to_registered_scene(self) -> None:
        # Так вступление потом подключится к центральной локации.
        self.manager.register("hub", Base)
        intro = self.manager.push(IntroScene(next_scene="hub"))
        play_through(intro)
        self.assertEqual(len(self.manager.stack), 2)
        self.assertIsNot(self.manager.current, intro)
        self.assertIsInstance(self.manager.current, Base)
        self.assertIsNot(self.manager.current, self.base)

    def test_unregistered_next_scene_falls_back_to_previous(self) -> None:
        intro = self.manager.push(IntroScene(next_scene="hub"))
        play_through(intro)
        self.assertIs(self.manager.current, self.base)

    def test_backspace_aborts_without_completion(self) -> None:
        intro = self.manager.push(IntroScene(on_complete=self.completed.append))
        intro.update(1.3)
        intro.handle_event(key(pygame.K_BACKSPACE))
        self.assertIs(self.manager.current, self.base)
        self.assertEqual(self.completed, [])
        self.assertFalse(intro.completed)


class MissingSpritesTest(IntroTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        super().tearDown()

    def test_missing_and_broken_sprites_use_fallback(self) -> None:
        shutil.copytree(CHARACTERS_DIR / "alice", self.root / "alice")
        shutil.copytree(CHARACTERS_DIR / "chuchmek", self.root / "chuchmek")
        manifest = self.root / "chuchmek" / "chuchmek.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["frames"][0]["file"] = "frames/нет.png"  # повреждённый манифест; Кролика нет вовсе
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        scene = IntroScene(characters_dir=self.root)
        self.assertIsNone(scene.actors["white_rabbit"].sprites)
        self.assertIsNone(scene.actors["chuchmek"].sprites)
        self.assertIsNotNone(scene.actors["alice"].sprites)
        elapsed = 0.0
        while not scene.completed and elapsed < 300:
            scene.draw(self.canvas)
            if scene.dialogue is not None and not scene.dialogue.is_typing:
                scene.handle_event(key(pygame.K_RETURN))
            else:
                scene.update(0.1)
                elapsed += 0.1
        self.assertTrue(scene.completed)

    def test_missing_frame_uses_closest_available_pose(self) -> None:
        scene = IntroScene()
        rabbit = scene.actors["white_rabbit"]
        rabbit.set_pose("такого_кадра_нет")
        self.assertIs(rabbit._pose_image(), rabbit.sprites.frame("idle_front").image)


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

    def press(self, key_code: int, scancode: int = 0) -> None:
        self.send(key(key_code, scancode), key(key_code, scancode, pygame.KEYUP))

    def test_i_opens_intro_in_any_layout(self) -> None:
        for key_code in (pygame.K_i, ord("ш")):
            with self.subTest(key=key_code):
                self.press(key_code, pygame.KSCAN_I)
                self.assertIsInstance(self.app.scenes.current, IntroScene)
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, self.app.screen)

    def test_held_enter_does_not_skip_lines(self) -> None:
        self.press(pygame.K_i, pygame.KSCAN_I)
        intro = self.app.scenes.current
        self.app.scenes.update(1.3)
        self.send(key(pygame.K_RETURN), key(pygame.K_RETURN), key(pygame.K_RETURN))  # автоповтор без KEYUP
        self.assertEqual(intro.dialogue.node.id, "a_once")
        self.assertFalse(intro.dialogue.is_typing)

    def test_completed_intro_returns_with_message_and_other_keys_still_work(self) -> None:
        self.press(pygame.K_i, pygame.KSCAN_I)
        intro = self.app.scenes.current
        play_through(intro, choice_index=1)
        screen = self.app.screen
        self.assertIs(self.app.scenes.current, screen)
        self.assertEqual(screen.intro_choice.text, CHOICES[1])
        self.assertEqual(len(screen._result_labels), 2)
        canvas = pygame.Rect((0, 0), config.LOGICAL_SIZE)
        for _, rect in screen._labels + screen._result_labels:
            self.assertTrue(canvas.contains(rect), rect)
        for key_code, scancode, kind in (
            (pygame.K_a, pygame.KSCAN_A, "animation_demo"),
            (pygame.K_d, pygame.KSCAN_D, "dialogue"),
            (pygame.K_p, pygame.KSCAN_P, "sprite_gallery"),
            (pygame.K_i, pygame.KSCAN_I, "intro"),
        ):
            with self.subTest(kind=kind):
                self.press(key_code, scancode)
                self.assertIsNotNone(getattr(screen, kind))
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, screen)

    def test_escape_f11_and_window_close_in_intro(self) -> None:
        self.press(pygame.K_i, pygame.KSCAN_I)
        self.app.running = True
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsInstance(self.app.scenes.current, IntroScene)
        self.app.scenes.update(0.5)
        self.app.scenes.draw(self.app.display.canvas)
        self.app.display.present()
        self.press(pygame.K_ESCAPE)
        self.assertFalse(self.app.running)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)


if __name__ == "__main__":
    unittest.main()
