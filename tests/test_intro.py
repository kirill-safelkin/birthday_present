"""Проверки вступления «Алиса в стране Чучмека?!»: порядок сюжета, сбой, заголовок, переходы."""

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
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.fonts import load_font  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story.intro_dialogue import (  # noqa: E402
    ALICE,
    BEATS,
    CHOICE_ID,
    CHUCHMEK,
    ERROR_LINES,
    ERROR_TITLE,
    POSES,
    RABBIT,
    SPEAKER_ACTORS,
    TITLE_CLASSIC,
    TITLE_FINAL,
    TITLE_REWRITE,
    TITLE_REWRITE_SECONDS,
    Cue,
    Lines,
    Pause,
    all_scripts,
    title_step_at,
)
from game.story.intro_scene import (  # noqa: E402
    ALICE_BURROW_X,
    ALICE_X,
    CAP_HEIGHT,
    CHUCHMEK_X,
    ERROR_H,
    ERROR_W,
    GLITCH_ALICE_POSES,
    JUMP_HEIGHT,
    SPRITE_SIZE,
    TITLE_BOTTOM,
    IntroScene,
)
from game.world.hub import HubScene  # noqa: E402

CHOICES = ("Начинаем с суши. У истории должен быть вкус.", "Сначала объясни, почему гриб разговаривает.")
TITLE_TRUNCATED = "Алиса в стране чу…"
# Слова, которых не должно быть в сказке до сюжетного сбоя.
SPOILERS = ("чучмек", "гриб", "суши", "испытан", "формуляр", "торт", "компост", "должност")


def key(key_code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key_code, mod=0, unicode="", scancode=scancode)


def all_nodes():
    return [node for script in all_scripts() for node in script.nodes.values()]


def node_text() -> dict[str, str]:
    return {node.id: f"{node.speaker}: {node.text}" for node in all_nodes()}


def step(scene: IntroScene, choice_index: int = 0, dt: float = 1 / 60, state: dict | None = None) -> None:
    """Один шаг игрока: Enter, если реплика напечатана (в выборе — ↓ нужное число раз), иначе время."""
    state = state if state is not None else {}
    dialogue = scene.dialogue
    if dialogue is not None and dialogue.node is not None and not dialogue.is_typing:
        if dialogue.node.choices and not state.get("moved"):
            for _ in range(choice_index):
                scene.handle_event(key(pygame.K_DOWN))
            state["moved"] = True
        scene.handle_event(key(pygame.K_RETURN))
        scene.handle_event(key(pygame.K_RETURN, event_type=pygame.KEYUP))
    else:
        scene.update(dt)


def play_through(scene: IntroScene, choice_index: int = 0, dt: float = 1 / 60, limit: int = 100000) -> list:
    state: dict = {}
    for _ in range(limit):
        if scene.completed or scene.is_finished:
            break
        step(scene, choice_index, dt, state)
    return scene.events


def advance_to_cue(scene: IntroScene, name: str, limit: int = 100000) -> None:
    for _ in range(limit):
        if scene.cue_name == name:
            return
        if scene.completed:
            break
        step(scene)
    raise AssertionError(f"событие {name} не наступило")


def assert_in_order(test: unittest.TestCase, events: list, markers: list) -> None:
    """Все маркеры есть в журнале и идут в заданном порядке (между ними могут быть другие события)."""
    position = 0
    for marker in markers:
        try:
            position = events.index(marker, position) + 1
        except ValueError:
            test.fail(f"{marker} не найден после позиции {position}; журнал: {events}")


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

    def test_speakers_have_sprites_and_narrator_is_gone(self) -> None:
        self.assertEqual({node.speaker for node in all_nodes()}, {ALICE, RABBIT, CHUCHMEK})
        for char_id in SPEAKER_ACTORS.values():
            load_character_sprites(CHARACTERS_DIR / char_id)

    def test_required_lines_are_in_script(self) -> None:
        joined = " ".join(node.text for node in all_nodes())
        required = [
            "Алиса! Наконец-то! Мы уже начинаем опаздывать!",
            "Куда?",
            "В нору. По расписанию мы должны были прыгнуть туда ещё четырнадцать секунд назад!",
            "А почему я должна прыгать в незнакомую нору?",
            "Потому что это Страна чудес. Здесь сначала прыгают, а потом заполняют документы.",
            "Документы?",
            "Не волнуйтесь. Форму 27-Б заполнять необязательно. Если у вас есть форма 27-А.",
            "И что там внизу?",
            "Неизвестно. Но по расписанию там должно быть приключение.",
            "Ладно. Только если там нет приключения, мы вернёмся.",
            "Конечно! Я предусмотрел даже такую возможность.",
            "Ну, поехали.",
            "Так. Кто перезапустил сказку? Я ещё даже не проснулся.",
            "Ты кто?",
            "Чучмек. Временно ответственный по непредсказуемости.",
            "Это должность?",
            "Теперь да.",
            "не знаю, почему оказался в заголовке книги. Но считаю это повышением.",
            "Нам нужны три сюжетных фрагмента. Без них финальная дверь не откроется.",
            "Что за дверью?",
            "Не знаю. Я гриб, а не экскурсовод.",
            "Три испытания. Суши, формуляры и торты.",
            "Почему формуляры?",
            "Потому что зло бывает разным.",
            "Но если следующее испытание окажется про заполнение двенадцати формуляров на один суши, "
            "я буду задавать вопросы.",
            "Разумно. Хотя формуляр № 12-Б нужен именно для разрешения на вопросы.",
        ]
        for line in required:
            self.assertIn(line, joined)

    def test_titles_and_error_text_are_exact(self) -> None:
        self.assertEqual(TITLE_CLASSIC, "Алиса в стране чудес")
        self.assertEqual(TITLE_FINAL, "Алиса в стране Чучмека?!")
        self.assertEqual(ERROR_TITLE, "ОШИБКА СКАЗОЧНОГО ДВИЖКА")
        self.assertEqual(
            ERROR_LINES,
            ("Обнаружено слишком много чудес.", "Попытка восстановить предыдущую версию истории…"),
        )
        for text in (ERROR_TITLE, *ERROR_LINES):
            for word in ("traceback", "exception", "error", "pygame", "python", "segmentation"):
                self.assertNotIn(word, text.lower())

    def test_title_steps_go_classic_then_truncated_then_final(self) -> None:
        texts = [step_.text for step_ in TITLE_REWRITE]
        self.assertEqual(texts[0], TITLE_CLASSIC)
        self.assertEqual(texts[-1], TITLE_FINAL)
        self.assertEqual(texts.count(TITLE_FINAL), 1)  # финальное название — только в последней ступеньке
        self.assertIn(TITLE_TRUNCATED, texts)
        self.assertLess(texts.index(TITLE_TRUNCATED), texts.index(TITLE_FINAL))
        # Буквы пропадают по одной: каждая ступенька до «чу…» не длиннее предыдущей.
        for earlier, later in zip(texts[: texts.index(TITLE_TRUNCATED)], texts[1 : texts.index(TITLE_TRUNCATED) + 1]):
            if later != TITLE_TRUNCATED:
                self.assertLessEqual(len(later), len(earlier))
        self.assertTrue(any(not step_.visible for step_ in TITLE_REWRITE))  # заголовок моргает
        self.assertAlmostEqual(TITLE_REWRITE_SECONDS, sum(step_.seconds for step_ in TITLE_REWRITE))
        self.assertGreaterEqual(TITLE_REWRITE_SECONDS, 6.0)  # игрок успевает понять, что происходит

    def test_title_step_lookup(self) -> None:
        self.assertEqual(title_step_at(0.0).text, TITLE_CLASSIC)
        self.assertEqual(title_step_at(1.3).text, TITLE_CLASSIC)
        self.assertEqual(title_step_at(TITLE_REWRITE_SECONDS - 0.01).text, TITLE_FINAL)
        self.assertEqual(title_step_at(TITLE_REWRITE_SECONDS + 5).text, TITLE_FINAL)
        self.assertEqual(title_step_at(3.4).text, TITLE_TRUNCATED)

    def test_titles_fit_on_screen(self) -> None:
        font = load_font(16)
        for step_ in TITLE_REWRITE:
            self.assertLessEqual(font.size(step_.text)[0] + 2 * step_.shake, config.LOGICAL_SIZE[0] - 20, step_.text)

    def test_parts_go_in_order_with_expected_cues(self) -> None:
        parts = [beat.part for beat in BEATS]
        self.assertEqual(parts, sorted(parts))
        self.assertEqual(sorted(set(parts)), list("ABCDEF"))
        cues = [beat.name for beat in BEATS if isinstance(beat, Cue)]
        expected = [
            "title_card", "rabbit_runs_in", "rabbit_points", "alice_walks", "alice_prepares", "glitch",
            "error_message", "restart", "title_rewrite", "chuchmek_emerges", "alice_reacts", "finale",
        ]
        self.assertEqual(cues, expected)
        self.assertTrue(any(isinstance(beat, Pause) and beat.part == "A" for beat in BEATS))  # пауза в начале

    def test_script_before_the_glitch_does_not_mention_chuchmek(self) -> None:
        glitch = next(index for index, beat in enumerate(BEATS) if isinstance(beat, Cue) and beat.name == "glitch")
        texts = [TITLE_CLASSIC]
        early_nodes = set()
        for beat in BEATS[:glitch]:
            if isinstance(beat, Lines):
                for node in beat.script.nodes.values():
                    early_nodes.add(node.id)
                    texts += [node.speaker, node.text]
                    texts += [choice.text for choice in node.choices or ()]
        for text in texts:
            for word in SPOILERS:
                self.assertNotIn(word, text.lower(), text)
        self.assertEqual({beat.part for beat in BEATS[:glitch]}, {"A"})
        for node_id in early_nodes:  # ремарки до сбоя тоже не показывают Чучмека
            self.assertNotIn("chuchmek", POSES.get(node_id, {}))
        for step_ in TITLE_REWRITE[:-1]:  # в заголовке его нет нигде, кроме последней ступеньки
            self.assertNotIn("чучмек", step_.text.lower())

    def test_rabbit_comes_before_the_jump_is_proposed(self) -> None:
        names = [(type(beat).__name__, getattr(beat, "name", None)) for beat in BEATS]
        rabbit = names.index(("Cue", "rabbit_runs_in"))
        first_lines = next(index for index, beat in enumerate(BEATS) if isinstance(beat, Lines))
        invite = next(i for i, b in enumerate(BEATS) if isinstance(b, Lines) and "r_invite" in b.script.nodes)
        walk = names.index(("Cue", "alice_walks"))
        self.assertLess(rabbit, first_lines)
        self.assertLess(rabbit, invite)
        self.assertLess(invite, walk)

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
        for frame_id in GLITCH_ALICE_POSES:
            sprites["alice"].frame(frame_id)


class SequenceTest(IntroTestCase):
    def test_full_order_of_events(self) -> None:
        events = play_through(IntroScene())
        assert_in_order(self, events, [
            ("cue", "title_card"), ("title", TITLE_CLASSIC),
            ("cue", "rabbit_runs_in"), ("node", "r_hello"), ("node", "r_burrow"), ("node", "r_ok"),
            ("cue", "rabbit_points"), ("node", "r_invite"),
            ("cue", "alice_walks"), ("cue", "alice_prepares"), ("node", "a_go"),
            ("cue", "glitch"), ("cue", "error_message"), ("cue", "restart"),
            ("title", TITLE_CLASSIC), ("title", TITLE_TRUNCATED), ("title", TITLE_FINAL),
            ("cue", "chuchmek_emerges"), ("node", "c_who"), ("node", "c_name"), ("node", "c_title"),
            ("cue", "alice_reacts"), ("node", "d_fragments"), ("node", "d_trials"),
            ("node", CHOICE_ID), ("node", "e_ready"), ("node", "f_form_12b"), ("cue", "finale"),
        ])

    def test_title_returns_to_classic_before_truncation_and_final_comes_last(self) -> None:
        scene = IntroScene()
        play_through(scene)
        titles = scene.title_history
        restart = scene.events.index(("cue", "restart"))
        after_restart = [value for kind, value in scene.events[restart:] if kind == "title"]
        self.assertEqual(after_restart[0], TITLE_CLASSIC)  # нормальный заголовок возвращается первым
        self.assertLess(after_restart.index(TITLE_CLASSIC), after_restart.index(TITLE_TRUNCATED))
        self.assertLess(after_restart.index(TITLE_TRUNCATED), after_restart.index(TITLE_FINAL))
        self.assertEqual(titles.count(TITLE_FINAL), 1)
        self.assertEqual(titles[-1], TITLE_FINAL)
        self.assertEqual(titles[0], TITLE_CLASSIC)
        self.assertIn("", titles)  # пока длится сообщение об ошибке, заголовок убран
        allowed = {"", TITLE_CLASSIC, TITLE_FINAL, *(step_.text for step_ in TITLE_REWRITE)}
        for text in titles:  # никаких случайных нечитаемых надписей
            self.assertIn(text, allowed)

    def test_nothing_mentions_chuchmek_before_the_glitch_while_playing(self) -> None:
        scene = IntroScene()
        play_through(scene)
        glitch = scene.events.index(("cue", "glitch"))
        texts = node_text()
        for kind, value in scene.events[:glitch]:
            shown = texts[value] if kind == "node" else value
            for word in SPOILERS:
                self.assertNotIn(word, shown.lower(), shown)

    def test_alice_starts_walking_only_after_she_agrees(self) -> None:
        scene = IntroScene()
        positions = []
        state: dict = {}
        while scene.cue_name != "alice_walks":
            step(scene, state=state)
            positions.append(scene.actors["alice"].x)
        self.assertEqual(set(positions), {float(ALICE_X)})  # до согласия Алиса стоит на месте
        self.assertIn(("node", "r_ok"), scene.events)
        self.assertEqual(scene.beat_time, 0.0)
        self.assertTrue(scene.actors["alice"].is_playing)  # идёт анимацией walk_right, не черновой

    def test_alice_walk_is_continuous_and_slows_down_at_the_burrow(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "alice_walks")
        alice = scene.actors["alice"]
        xs = [alice.x]
        while scene.cue_name == "alice_walks":
            scene.update(1 / 60)
            xs.append(alice.x)
        deltas = [b - a for a, b in zip(xs, xs[1:])]
        self.assertTrue(all(delta >= -1e-9 for delta in deltas))  # только вперёд
        self.assertAlmostEqual(alice.x, ALICE_BURROW_X)
        middle = deltas[len(deltas) // 3]
        self.assertGreater(middle, 0.5)  # идёт заметными шагами
        self.assertLess(deltas[-3], middle * 0.5)  # а у самой норы притормаживает
        self.assertEqual(scene.cue_name, "alice_prepares")

    def test_alice_walk_depends_on_time_not_on_frame_rate(self) -> None:
        positions = []
        for dt in (1 / 144, 1 / 60, 1 / 30, 0.5):
            scene = IntroScene()
            advance_to_cue(scene, "alice_walks")
            elapsed = 0.0
            while elapsed < 1.3 - 1e-9:
                chunk = min(dt, 1.3 - elapsed)
                scene.update(chunk)
                elapsed += chunk
            positions.append(scene.actors["alice"].x)
        for x in positions:
            self.assertAlmostEqual(x, positions[0], places=6)

    def test_glitch_starts_only_at_the_burrow_after_the_last_line(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "glitch")
        self.assertEqual(scene.actors["alice"].x, ALICE_BURROW_X)
        self.assertEqual(scene.burrow_open, 1.0)
        self.assertEqual(scene.events[-2], ("node", "a_go"))
        self.assertEqual(scene.error_text, ())
        self.assertEqual(scene.title, TITLE_CLASSIC)

    def test_error_message_appears_after_the_glitch_has_begun(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "glitch")
        seen: set[str] = set()
        in_glitch_texts, in_error_texts = [], []
        while scene.cue_name in ("glitch", "error_message"):
            scene.update(1 / 60)
            (in_glitch_texts if scene.cue_name == "glitch" else in_error_texts).append(scene.error_text)
            seen.update(scene.error_text)
        self.assertTrue(all(texts == () for texts in in_glitch_texts))  # при рывках сообщения ещё нет
        self.assertEqual(seen, {ERROR_TITLE, *ERROR_LINES})
        self.assertEqual(scene.error_text, ())  # к концу оно разваливается и исчезает
        self.assertTrue(any(texts == (ERROR_TITLE,) for texts in in_error_texts))  # строки идут по очереди
        self.assertTrue(any(texts == (ERROR_TITLE, ERROR_LINES[0]) for texts in in_error_texts))

    def test_glitch_is_visual_only_and_short(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "glitch")
        glitch_beat = scene.beat
        self.assertTrue(1.0 <= glitch_beat.seconds <= 2.0)
        clean = pygame.Surface(config.LOGICAL_SIZE)
        scene._compose(clean)
        hidden_seen: set[str] = set()
        alice_poses: set[str] = set()
        updates = different_frames = 0
        while scene.cue_name == "glitch":
            scene.update(1 / 60)
            updates += 1
            hidden_seen |= scene.hidden
            alice_poses.add(scene.actors["alice"].pose)
            scene.draw(self.canvas)
            if pygame.image.tobytes(self.canvas, "RGB") != pygame.image.tobytes(clean, "RGB"):
                different_frames += 1
        self.assertLessEqual(updates, round(glitch_beat.seconds * 60) + 2)  # длится ровно столько, сколько задано
        self.assertGreaterEqual(len(hidden_seen), 2)  # отдельные элементы на миг пропадали
        self.assertGreaterEqual(len(alice_poses & set(GLITCH_ALICE_POSES)), 3)  # неправильные фазы движения
        self.assertGreater(different_frames, updates // 2)  # изображение рвётся
        self.assertEqual(scene.cue_name, "error_message")

    def test_restart_returns_to_the_classic_title_card(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "restart")
        alice = scene.actors["alice"]
        self.assertEqual(scene.title, TITLE_CLASSIC)
        self.assertEqual((alice.x, alice.squash, alice.alpha), (ALICE_X, 1.0, 255))
        self.assertFalse(scene.actors["white_rabbit"].visible)
        self.assertFalse(scene.actors["chuchmek"].visible)
        self.assertEqual(scene.page_blend, 0.0)
        self.assertEqual(scene.hidden, set())

    def test_title_goes_through_every_stage_in_order(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "title_rewrite")
        seen: list[tuple[str, bool]] = []
        while scene.cue_name == "title_rewrite":
            scene.update(1 / 60)
            state = (scene.title, scene.title_visible)
            if not seen or seen[-1] != state:
                seen.append(state)
        texts = [text for text, _ in seen]
        chain = [TITLE_CLASSIC, "Алиса в стране чуде", "Алиса в стране чуд", "Алиса в стране чу"]
        chain += [TITLE_TRUNCATED, TITLE_FINAL]
        for earlier, later in zip(chain, chain[1:]):
            self.assertLess(texts.index(earlier), texts.index(later))
        self.assertIn(("Алиса в сртане чу…", True), seen)
        self.assertIn((TITLE_TRUNCATED, False), seen)  # моргание
        self.assertEqual(seen[-1], (TITLE_FINAL, True))
        self.assertEqual(texts.count(TITLE_FINAL), 1)
        self.assertNotIn(TITLE_FINAL, texts[: texts.index(TITLE_TRUNCATED)])
        self.assertEqual(scene.page_blend, 1.0)

    def test_chuchmek_is_hidden_until_the_final_title(self) -> None:
        scene = IntroScene()
        state: dict = {}
        chuchmek = scene.actors["chuchmek"]
        while scene.cue_name != "chuchmek_emerges":
            self.assertFalse(chuchmek.visible)
            step(scene, state=state)
        self.assertEqual(scene.title, TITLE_FINAL)
        self.assertTrue(chuchmek.visible)

    def test_chuchmek_climbs_out_jumps_too_high_and_wobbles(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "chuchmek_emerges")
        chuchmek = scene.actors["chuchmek"]
        self.assertTrue(scene.chuchmek_clipped)
        scene.update(0.02)
        self.assertEqual(chuchmek.lift, -(SPRITE_SIZE - CAP_HEIGHT))  # снаружи только покосившаяся шляпка
        self.assertGreater(chuchmek.tilt, 5)
        timeline = []
        while scene.cue_name == "chuchmek_emerges":
            scene.update(1 / 60)
            timeline.append((chuchmek.lift, chuchmek.tilt, scene.chuchmek_clipped))
        lifts = [lift for lift, _, _ in timeline]
        peak = lifts.index(max(lifts))
        self.assertAlmostEqual(max(lifts), JUMP_HEIGHT, delta=1.0)
        self.assertTrue(any(lift < -5 for lift in lifts[:peak]))  # сначала медленно поднимается
        leap_start = next(index for index, lift in enumerate(lifts) if lift > 0)
        self.assertTrue(all(clipped for _, _, clipped in timeline[: leap_start - 1]))  # пока внутри норы — обрезан
        self.assertFalse(any(clipped for _, _, clipped in timeline[peak:]))  # прыгнул — над землёй целиком
        after_landing = [tilt for lift, tilt, _ in timeline[peak:] if lift == 0.0]
        self.assertTrue(any(abs(tilt) > 5 for tilt in after_landing))  # теряет равновесие
        # Итог выхода проверяем на сцене, где следом идёт пауза: в обычной сцене в тот же момент
        # начинается реплика Чучмека, и она сразу меняет позу и покачивает его.
        quiet = IntroScene(beats=(Cue("C", "chuchmek_emerges", 4.6), Pause("C", 5.0)))
        quiet.update(4.7)
        end = quiet.actors["chuchmek"]
        self.assertEqual((end.x, end.lift, end.tilt, end.dx), (CHUCHMEK_X, 0.0, 0.0, 0.0))
        self.assertEqual(end.pose, "clipboard_confident")  # важный вид, будто так и задумано
        self.assertFalse(quiet.chuchmek_clipped)

    def test_old_plot_follows_after_chuchmek_appears(self) -> None:
        events = play_through(IntroScene())
        emerge = events.index(("cue", "chuchmek_emerges"))
        after = [value for kind, value in events[emerge:] if kind == "node"]
        for node_id in ("d_fragments", "d_door", "d_trials", "d_why_forms", "d_evil", "d_cat", "d_goose",
                        CHOICE_ID, "e_ready", "f_questions", "f_form_12b"):
            self.assertIn(node_id, after)
        self.assertEqual(after[-1], "f_form_12b")

    def test_both_choices_lead_to_common_ending(self) -> None:
        for index, reply in ((0, "e_sushi"), (1, "e_talking")):
            with self.subTest(choice=index):
                scene = IntroScene()
                events = play_through(scene, index)
                nodes = [value for kind, value in events if kind == "node"]
                self.assertTrue(scene.completed)
                self.assertEqual(scene.choice.text, CHOICES[index])
                other = ({"e_sushi", "e_talking"} - {reply}).pop()
                self.assertIn(reply, nodes)
                self.assertNotIn(other, nodes)
                self.assertLess(nodes.index(reply), nodes.index("e_ready"))
                self.assertEqual(nodes[-1], "f_form_12b")
                self.assertEqual(len(nodes), len(all_nodes()) - 1)  # все реплики, кроме второй ветки

    def test_sequence_does_not_depend_on_dt(self) -> None:
        reference = play_through(IntroScene())
        for dt in (1 / 144, 1 / 30, 0.1, 0.5, 5.0):
            with self.subTest(dt=dt):
                self.assertEqual(play_through(IntroScene(), dt=dt), reference)

    def test_enter_during_pauses_and_effects_is_ignored(self) -> None:
        scene = IntroScene()
        for _ in range(5):
            scene.handle_event(key(pygame.K_RETURN))
            scene.handle_event(key(pygame.K_RETURN, event_type=pygame.KEYUP))
        self.assertEqual(scene.cue_name, "title_card")  # заставка не пропущена
        self.assertEqual(scene.beat_index, 0)
        advance_to_cue(scene, "glitch")
        for _ in range(5):
            scene.handle_event(key(pygame.K_RETURN))
        self.assertEqual(scene.cue_name, "glitch")

    def test_one_enter_is_one_step(self) -> None:
        scene = IntroScene()
        while scene.dialogue is None:
            scene.update(1 / 60)
        self.assertEqual(scene.dialogue.node.id, "r_hello")
        scene.handle_event(key(pygame.K_RETURN))  # дописывает реплику
        self.assertEqual(scene.dialogue.node.id, "r_hello")
        self.assertFalse(scene.dialogue.is_typing)
        scene.handle_event(key(pygame.K_RETURN))
        self.assertEqual(scene.dialogue.node.id, "r_where")


class StagingTest(IntroTestCase):
    def test_characters_stand_above_every_dialogue_box(self) -> None:
        scene = IntroScene()
        box = DialogueBox()
        for node in all_nodes():
            layout = box.layout(node)
            self.assertLess(scene.ground, (layout.name_tab or layout.box).top, node.id)

    def test_sprites_never_cover_the_title(self) -> None:
        scene = IntroScene()
        state: dict = {}
        checked = 0
        while not scene.completed:
            step(scene, state=state)
            for actor in scene.actors.values():
                if actor.visible and actor.alpha > 0 and actor.id not in scene.hidden:
                    checked += 1
                    self.assertGreaterEqual(actor.bounds(scene.ground).top, TITLE_BOTTOM, (actor.id, scene.cue_name))
        self.assertGreater(checked, 1000)

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

    def test_chuchmek_is_never_mirrored(self) -> None:
        # Сравниваем то, что реально нарисовано: асимметричные глаза не должны поменяться местами.
        scene = IntroScene()
        chuchmek = scene.actors["chuchmek"]
        chuchmek.visible = True
        for frame_id in ("idle", "clipboard_confident", "panicked", "arms_up_panic", "smug_wink"):
            chuchmek.set_pose(frame_id)
            drawn, expected = pygame.Surface(config.LOGICAL_SIZE), pygame.Surface(config.LOGICAL_SIZE)
            chuchmek.draw(drawn, scene.ground)
            source = chuchmek.sprites.frame(frame_id).image
            expected.blit(pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE)), chuchmek.bounds(scene.ground))
            self.assertEqual(pygame.image.tobytes(drawn, "RGB"), pygame.image.tobytes(expected, "RGB"), frame_id)

    def test_tear_shifts_whole_bands_and_wraps_them(self) -> None:
        scene = IntroScene()
        source = pygame.Surface(config.LOGICAL_SIZE)
        for x in range(config.LOGICAL_SIZE[0]):  # столбики разных цветов: сдвиг виден в любой строке
            source.fill((x % 256, (x * 3) % 256, (x * 7) % 256), (x, 0, 1, config.LOGICAL_SIZE[1]))
        torn = pygame.Surface(config.LOGICAL_SIZE)
        scene._tear(torn, source, slot=1, amplitude=6)
        width, height = config.LOGICAL_SIZE
        shifted_rows = same_rows = 0
        for y in range(height):
            row = [tuple(torn.get_at((x, y))) for x in range(width)]
            original = [tuple(source.get_at((x, y))) for x in range(width)]
            if row == original:
                same_rows += 1
                continue
            shifted_rows += 1
            # Полоса сдвинута целиком на несколько пикселей, и вылезшее за край вернулось с другой стороны.
            offsets = [o for o in range(-6, 7) if o and row == original[-o:] + original[:-o]]
            self.assertTrue(offsets, y)
        self.assertGreater(shifted_rows, height // 4)
        self.assertGreater(same_rows, height // 4)  # рвётся лишь часть полос

    def test_draft_groups_are_not_played(self) -> None:
        scene = IntroScene()
        self.assertFalse(scene.actors["white_rabbit"].play("run_right"))
        self.assertFalse(scene.actors["chuchmek"].play("talk"))
        self.assertFalse(scene.actors["alice"].play("walk_down"))
        self.assertTrue(scene.actors["alice"].play("walk_right"))
        self.assertTrue(scene.actors["alice"].play("react_down"))

    def test_title_card_has_only_title_background_and_alice(self) -> None:
        scene = IntroScene()
        scene.update(2.0)
        self.assertEqual(scene.title, TITLE_CLASSIC)
        self.assertTrue(scene.actors["alice"].visible)
        self.assertFalse(scene.actors["white_rabbit"].visible)
        self.assertFalse(scene.actors["chuchmek"].visible)
        self.assertEqual(scene.burrow_open, 0.0)  # норы ещё нет
        self.assertIsNone(scene.dialogue)
        self.assertEqual(scene.error_text, ())

    def test_burrow_appears_when_the_rabbit_points_to_it(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "rabbit_points")
        self.assertEqual(scene.burrow_open, 0.0)
        while scene.cue_name == "rabbit_points":
            scene.update(1 / 60)
        self.assertEqual(scene.burrow_open, 1.0)
        self.assertEqual(scene.actors["white_rabbit"].pose, "hurries_pointing")

    def test_error_box_text_fits_inside_the_box(self) -> None:
        scene = IntroScene()
        box = scene._render_error_box(4.0)
        self.assertEqual(box.get_size(), (ERROR_W, ERROR_H))
        self.assertLessEqual(scene._font10.size(ERROR_TITLE)[0], ERROR_W - 40)
        for line in ERROR_LINES:
            self.assertLessEqual(scene._font.size(line)[0], ERROR_W - 24, line)

    def test_draws_every_moment_without_errors(self) -> None:
        scene = IntroScene()
        elapsed, state = 0.0, {}
        while not scene.completed and elapsed < 300:
            scene.draw(self.canvas)
            dialogue = scene.dialogue
            if dialogue is not None and not dialogue.is_typing:
                step(scene, state=state)
            else:
                scene.update(0.03)
                elapsed += 0.03
        self.assertTrue(scene.completed)

    def test_glitch_and_error_cannot_stall_the_scene(self) -> None:
        # Даже одно огромное dt проходит сбой и сообщение за конечное число шагов, без зависания.
        scene = IntroScene()
        advance_to_cue(scene, "glitch")
        scene.update(100.0)
        self.assertIn(("cue", "chuchmek_emerges"), scene.events)  # дальше диалогов не уходит ничего
        self.assertEqual(scene.dialogue.node.id, "c_who")
        self.assertEqual(scene.title, TITLE_FINAL)
        self.assertEqual(scene.error_text, ())
        self.assertEqual(scene.hidden, set())
        scene.draw(self.canvas)


class Base(Scene):
    pass


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

    def test_backspace_aborts_at_any_moment_without_completion(self) -> None:
        for cue in ("title_card", "glitch", "error_message", "title_rewrite", "chuchmek_emerges"):
            with self.subTest(cue=cue):
                manager = SceneManager()
                base = manager.push(Base())
                intro = manager.push(IntroScene(on_complete=self.completed.append))
                advance_to_cue(intro, cue)
                intro.update(0.3)
                intro.handle_event(key(pygame.K_BACKSPACE))
                self.assertIs(manager.current, base)
                self.assertFalse(intro.completed)
        self.assertEqual(self.completed, [])


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
        elapsed, state = 0.0, {}
        while not scene.completed and elapsed < 300:
            scene.draw(self.canvas)
            dialogue = scene.dialogue
            if dialogue is not None and not dialogue.is_typing:
                step(scene, state=state)
            else:
                scene.update(0.1)
                elapsed += 0.1
        self.assertTrue(scene.completed)
        self.assertEqual(scene.title_history[-1], TITLE_FINAL)

    def test_no_sprites_at_all_still_plays(self) -> None:
        scene = IntroScene(characters_dir=self.root)  # пустая папка
        self.assertTrue(all(actor.sprites is None for actor in scene.actors.values()))
        play_through(scene, dt=0.05)
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
        self.app = App(dev_mode=True)  # экран проверки и его клавиши

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
        while intro.dialogue is None:
            self.app.scenes.update(0.1)
        self.send(key(pygame.K_RETURN), key(pygame.K_RETURN), key(pygame.K_RETURN))  # автоповтор без KEYUP
        self.assertEqual(intro.dialogue.node.id, "r_hello")
        self.assertFalse(intro.dialogue.is_typing)

    def test_completed_intro_leads_to_hub_then_back_with_message_and_keys_work(self) -> None:
        self.press(pygame.K_i, pygame.KSCAN_I)
        intro = self.app.scenes.current
        play_through(intro, choice_index=1)
        screen = self.app.screen
        # После вступления — центральная площадь; экран проверки под ней, но неактивен.
        self.assertIsInstance(self.app.scenes.current, HubScene)
        self.assertEqual([type(scene) for scene in self.app.scenes.stack], [type(screen), HubScene])
        self.press(pygame.K_BACKSPACE)
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

    def test_escape_f11_and_window_close_during_glitch_and_error(self) -> None:
        for cue in ("glitch", "error_message", "title_rewrite"):
            with self.subTest(cue=cue):
                self.press(pygame.K_i, pygame.KSCAN_I)
                intro = self.app.scenes.current
                advance_to_cue(intro, cue)
                intro.update(0.5)
                self.app.running = True
                self.press(pygame.K_F11)  # полный экран и обратно, пока идёт сбой
                self.assertTrue(self.app.display.is_fullscreen)
                self.app.scenes.draw(self.app.display.canvas)
                self.app.display.present()
                self.press(pygame.K_F11)
                self.assertFalse(self.app.display.is_fullscreen)
                self.press(pygame.K_ESCAPE)
                self.assertFalse(self.app.running)
                self.app.running = True
                self.send(pygame.event.Event(pygame.QUIT))
                self.assertFalse(self.app.running)
                self.assertEqual(intro.cue_name, cue)  # события не сбили сцену
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, self.app.screen)

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
