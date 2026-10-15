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
from game.graphics.hires import HiResLayer, SpriteCommand  # noqa: E402
from game.graphics.animation import Direction  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story.entrance import ENTER_DISTANCE, HOLE_X, TRIGGER_DISTANCE, WALK_MAX_X, WALK_MIN_X, Stage  # noqa: E402
from game.story.intro_dialogue import (  # noqa: E402
    ALICE,
    BEATS,
    CHOICE_ID,
    CHUCHMEK,
    ERROR_LINES,
    ORGANIZER_CHOICE_ID,
    ERROR_TITLE,
    POSES,
    RABBIT,
    RABBIT_REMARK_BREAKING,
    RABBIT_REMARK_READY,
    SPEAKER_ACTORS,
    TITLE_CLASSIC,
    TITLE_FINAL,
    TITLE_REWRITE,
    TITLE_REWRITE_SECONDS,
    Cue,
    Explore,
    Lines,
    Pause,
    all_scripts,
    title_step_at,
)
from game.story.intro_scene import (  # noqa: E402
    HOLE_COLOR,
    ALICE_BURROW_X,
    ALICE_LEAP,
    ALICE_LEAP_X,
    ALICE_START_X,
    ALICE_X,
    APPROACH_HINT,
    CAP_HEIGHT,
    CHUCHMEK_X,
    ENTER_HINT,
    ERROR_H,
    ERROR_W,
    GLITCH_ALICE_POSES,
    JUMP_HEIGHT,
    SPRITE_SIZE,
    TITLE_BOTTOM,
    WALK_HINT,
    IntroScene,
)
from game.world.hub import HubScene  # noqa: E402

CHOICES = ("Давай уже спасать праздник.", "Почему за праздник отвечает именно гриб?")
ORGANIZER_CHOICES = ("И кто тебя назначил?", "Ладно. Что нам нужно сделать?")
# Ветки выборов вступления: вопрос → (реплики первой ветки, реплики второй ветки, общая реплика после них).
BRANCHES = {
    ORGANIZER_CHOICE_ID: (("d_self_appointed", "d_democratic"), ("d_down_to_business", "d_thought_of"), "d_plan"),
    CHOICE_ID: (("e_rescue",), ("e_mushroom", "e_explains"), "e_ready"),
}
TITLE_TRUNCATED = "Алиса в стране чу…"
# Слова, которых не должно быть в сказке до сюжетного сбоя.
SPOILERS = ("чучмек", "гриб", "суши", "испытан", "формуляр", "торт", "компост", "должност")


def key(key_code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key_code, mod=0, unicode="", scancode=scancode)


def all_nodes():
    return [node for script in all_scripts() for node in script.nodes.values()]


def node_text() -> dict[str, str]:
    return {node.id: f"{node.speaker}: {node.text}" for node in all_nodes()}


RIGHT = (pygame.K_RIGHT, pygame.KSCAN_RIGHT)
LEFT = (pygame.K_LEFT, pygame.KSCAN_LEFT)
# Стадии эпизода с норой от начала свободной ходьбы до готовой норы — каждая по одному разу.
SHOW_STAGES = ["free_walk", "glitch_warning", "world_breaking", "hole_opening", "hole_ready"]


def walk_to_burrow(scene: IntroScene, dt: float = 1 / 60) -> None:
    """Шаг игрока в свободной ходьбе: зажать → и идти к месту норы, а у готовой норы — E.

    Когда управление возвращается (после появления норы), → нажимается заново: зажатые
    до постановки клавиши Алиса забывает, как и на площади после разговора."""
    entrance = scene.entrance
    if entrance.can_enter(scene.walker.x):
        scene.handle_event(key(*RIGHT, pygame.KEYUP))
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E, pygame.KEYUP))
        return
    if entrance.can_walk and not scene.walker.is_moving:
        scene.handle_event(key(*RIGHT, pygame.KEYUP))
        scene.handle_event(key(*RIGHT))
    scene.update(dt)


def step(scene: IntroScene, choice_index: int | dict = 0, dt: float = 1 / 60, state: dict | None = None) -> None:
    """Один шаг игрока: Enter, если реплика напечатана (в выборе — ↓ нужное число раз), иначе время;
    в свободной ходьбе — к норе и E у неё (walk_to_burrow).

    choice_index — номер ответа на каждом вопросе или словарь «id вопроса → номер ответа»."""
    state = state if state is not None else {}
    if scene.exploring:
        walk_to_burrow(scene, dt)
        return
    dialogue = scene.dialogue
    if dialogue is not None and dialogue.node is not None and not dialogue.is_typing:
        node = dialogue.node
        moved = state.setdefault("moved", set())
        if node.choices and node.id not in moved:
            index = choice_index.get(node.id, 0) if isinstance(choice_index, dict) else choice_index
            for _ in range(index):
                scene.handle_event(key(pygame.K_DOWN))
            moved.add(node.id)
        scene.handle_event(key(pygame.K_RETURN))
        scene.handle_event(key(pygame.K_RETURN, event_type=pygame.KEYUP))
    else:
        scene.update(dt)


def play_through(scene: IntroScene, choice_index: int | dict = 0, dt: float = 1 / 60, limit: int = 100000) -> list:
    state: dict = {}
    for _ in range(limit):
        if scene.completed or scene.is_finished:
            break
        step(scene, choice_index, dt, state)
    return scene.events


def advance_to_free_walk(scene: IntroScene, limit: int = 100000) -> None:
    """Пролистывает вступление до момента, когда Алиса переходит к игроку."""
    for _ in range(limit):
        if scene.exploring:
            return
        step(scene)
    raise AssertionError("свободная ходьба не наступила")


def hold(scene: IntroScene, code: tuple[int, int], seconds: float, dt: float = 1 / 60) -> None:
    """Зажать клавишу, подождать seconds и отпустить."""
    scene.handle_event(key(*code))
    elapsed = 0.0
    while elapsed < seconds - 1e-9:
        chunk = min(dt, seconds - elapsed)
        scene.update(chunk)
        elapsed += chunk
    scene.handle_event(key(*code, pygame.KEYUP))


def advance_to_stage(scene: IntroScene, stage: Stage, limit: int = 100000) -> None:
    """Ведёт вступление как игрок до начала стадии эпизода с норой."""
    for _ in range(limit):
        if scene.stage is stage:
            return
        step(scene)
    raise AssertionError(f"стадия {stage} не наступила")


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
            "Ты гриб.",
            "Так. Карьера подождёт. У меня тут праздник.",
            "Чей?",
            "Твой, конечно! Сегодня твой день рождения. Вся сказка готовит тебе праздник.",
            "А я — временно главный организатор праздника.",
            "Я подготовил праздничный план. Потом немного его улучшил. Потом сказка сломалась.",
            "Это звучит как катастрофа.",
            "Не спеши с выводами. Катастрофа уже произошла: мой праздничный план разлетелся на три фрагмента.",
            "И что теперь?",
            "Три испытания — три фрагмента. Соберём их, восстановим план и наконец устроим твой праздник.",
            "Фрагменты сложатся на мозаике посреди площади в последнюю страницу плана. "
            "Открыть её сможешь только ты.",
            "А ты хотя бы знаешь, что в этих испытаниях?",
            "Конечно. То есть примерно. В общих чертах. Не мешай мне сохранять интригу.",
            "Подожди. Организатор — ты, а испытания проходить мне?",
            "Я пробовал сам. Меня вежливо выставили. Отовсюду. Одновременно.",
            "только именинница знает, каким должен быть её праздник.",
            "я назначил его главным инспектором праздничного настроения.",
            "достаточно ли в плане поводов улыбнуться.",
            "все три портала открыты. Порядок — на твой вкус. Ты же именинница.",
            "Но если мне понадобится справка о том, что у меня день рождения, я буду задавать вопросы.",
            "Разумно. Хотя для вопросов нужна форма № 12-Б. Бумажная волокита не щадит даже праздники.",
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
            "title_card", "rabbit_runs_in", "rabbit_points", "alice_prepares", "alice_jumps", "glitch",
            "error_message", "restart", "title_rewrite", "chuchmek_emerges", "alice_reacts", "finale",
        ]
        self.assertEqual(cues, expected)
        self.assertTrue(any(isinstance(beat, Pause) and beat.part == "A" for beat in BEATS))  # пауза в начале
        # Прежней автоматической прогулки к норе нет: её место занял один интерактивный шаг.
        explore = [index for index, beat in enumerate(BEATS) if isinstance(beat, Explore)]
        self.assertEqual(len(explore), 1)
        prepares = next(i for i, b in enumerate(BEATS) if isinstance(b, Cue) and b.name == "alice_prepares")
        self.assertEqual(explore[0] + 1, prepares)
        self.assertEqual(BEATS[explore[0]].part, "A")

    def test_script_before_the_glitch_does_not_mention_chuchmek(self) -> None:
        glitch = next(index for index, beat in enumerate(BEATS) if isinstance(beat, Cue) and beat.name == "glitch")
        texts = [TITLE_CLASSIC, RABBIT_REMARK_BREAKING, RABBIT_REMARK_READY, WALK_HINT, APPROACH_HINT, ENTER_HINT]
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
        walk = next(index for index, beat in enumerate(BEATS) if isinstance(beat, Explore))
        self.assertLess(rabbit, first_lines)
        self.assertLess(rabbit, invite)
        self.assertEqual(invite + 1, walk)  # управление — сразу после приглашения, без лишних реплик

    def test_choice_branches_join(self) -> None:
        nodes = {node.id: node for node in all_nodes()}
        self.assertEqual(tuple(choice.text for choice in nodes[CHOICE_ID].choices), CHOICES)
        self.assertEqual(tuple(choice.text for choice in nodes[ORGANIZER_CHOICE_ID].choices), ORGANIZER_CHOICES)
        self.assertEqual({node.id for node in all_nodes() if node.choices}, set(BRANCHES))  # других выборов нет
        for question, (first, second, join) in BRANCHES.items():
            with self.subTest(question=question):
                choices = nodes[question].choices
                self.assertEqual([choice.next_id for choice in choices], [first[0], second[0]])
                self.assertNotEqual(nodes[first[0]].text, nodes[second[0]].text)  # ответы Чучмека разные
                for branch in (first, second):  # каждая ветка — цепочка своих реплик до общей
                    for current, following in zip(branch, (*branch[1:], join)):
                        self.assertEqual(nodes[current].next_id, following)
                self.assertFalse(set(first) & set(second))

    def test_stage_directions_refer_to_real_nodes_and_frames(self) -> None:
        ids = {node.id for node in all_nodes()}
        sprites = {char_id: load_character_sprites(CHARACTERS_DIR / char_id) for char_id in SPEAKER_ACTORS.values()}
        for node_id, poses in POSES.items():
            self.assertIn(node_id, ids)
            for char_id, frame_id in poses.items():
                sprites[char_id].frame(frame_id)  # KeyError, если кадра нет
        for frame_id in GLITCH_ALICE_POSES:
            sprites["alice"].frame(frame_id)


class KeysTest(IntroTestCase):
    def test_e_continues_lines_and_picks_answers_like_enter(self) -> None:
        # E — главная клавиша во всей игре, и во вступлении она тоже листает реплики.
        scene = IntroScene()
        while scene.dialogue is None:
            scene.update(1 / 30)
        first = scene.dialogue.node.id
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))  # дописать
        self.assertEqual(scene.dialogue.node.id, first)
        self.assertFalse(scene.dialogue.is_typing)
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E, pygame.KEYUP))
        scene.handle_event(key(ord("у"), pygame.KSCAN_E))  # русская раскладка — та же клавиша
        self.assertNotEqual(scene.dialogue.node.id, first)  # дальше
        for _ in range(100000):  # до вопроса Алисы — реплики только клавишей E (к норе — стрелкой и E)
            dialogue = scene.dialogue
            if dialogue is not None and dialogue.node.choices and not dialogue.is_typing:
                break
            if scene.exploring:
                walk_to_burrow(scene)
            elif dialogue is not None and not dialogue.is_typing:
                scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
            else:
                scene.update(1 / 60)
        self.assertEqual(scene.dialogue.node.id, ORGANIZER_CHOICE_ID)  # первый вопрос — про организатора
        scene.handle_event(key(pygame.K_DOWN))
        chosen = scene.dialogue.node.choices[1]
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
        scene.update(1 / 60)
        self.assertIs(scene.answers[ORGANIZER_CHOICE_ID], chosen)  # E выбрал выделенный ответ, а не первый
        self.assertEqual(scene.dialogue.node.id, chosen.next_id)


class SequenceTest(IntroTestCase):
    def test_full_order_of_events(self) -> None:
        events = play_through(IntroScene())
        assert_in_order(self, events, [
            ("cue", "title_card"), ("title", TITLE_CLASSIC),
            ("cue", "rabbit_runs_in"), ("node", "r_hello"), ("node", "r_burrow"), ("node", "r_ok"),
            ("cue", "rabbit_points"), ("node", "r_invite"),
            ("stage", "free_walk"), ("stage", "glitch_warning"), ("stage", "world_breaking"),
            ("stage", "hole_opening"), ("stage", "hole_ready"), ("stage", "entering_hole"),
            ("cue", "alice_prepares"), ("node", "a_go"), ("cue", "alice_jumps"),
            ("cue", "glitch"), ("cue", "error_message"), ("cue", "restart"),
            ("title", TITLE_CLASSIC), ("title", TITLE_TRUNCATED), ("title", TITLE_FINAL),
            ("cue", "chuchmek_emerges"), ("node", "c_who"), ("node", "c_name"), ("node", "c_title"),
            ("cue", "alice_reacts"), ("node", "d_wait"), ("node", "d_yours"), ("node", ORGANIZER_CHOICE_ID),
            ("node", "d_plan"), ("node", "d_pieces"), ("node", "d_trials"), ("node", "d_mosaic"),
            ("node", "d_intrigue"), ("node", "d_leo"), ("node", CHOICE_ID), ("node", "e_ready"),
            ("node", "f_form_12b"), ("cue", "finale"),
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

    def test_alice_stands_still_until_the_player_gets_her(self) -> None:
        scene = IntroScene()
        positions = []
        state: dict = {}
        while not scene.exploring:
            scene.handle_event(key(*RIGHT))  # до конца разговора стрелки ничего не делают
            scene.handle_event(key(*RIGHT, pygame.KEYUP))
            step(scene, state=state)
            positions.append(scene.actors["alice"].x)
        self.assertEqual(set(positions), {float(ALICE_START_X)})  # сама Алиса никуда не идёт
        self.assertIn(("node", "r_ok"), scene.events)
        self.assertEqual(scene.events[-2:], [("node", "r_invite"), ("stage", "free_walk")])
        self.assertIs(scene.actors["alice"].body, scene.walker)
        self.assertNotIn(("cue", "alice_prepares"), scene.events)

    def test_held_right_walks_steadily_and_release_stops(self) -> None:
        scene = IntroScene()
        advance_to_free_walk(scene)
        alice = scene.actors["alice"]
        scene.handle_event(key(*RIGHT))
        xs = [alice.x]
        for _ in range(60):
            scene.update(1 / 60)
            xs.append(alice.x)
        deltas = [b - a for a, b in zip(xs, xs[1:])]
        for delta in deltas:  # ровный шаг: WALK_SPEED пикселей в секунду
            self.assertAlmostEqual(delta, scene.walker.speed / 60, places=6)
        self.assertTrue(scene.actors["alice"].body.is_moving)
        scene.handle_event(key(*RIGHT, pygame.KEYUP))
        stopped = alice.x
        scene.update(1.0)
        self.assertEqual(alice.x, stopped)
        self.assertIs(scene.stage, Stage.FREE_WALK)

    def test_walking_depends_on_time_not_on_frame_rate(self) -> None:
        positions = []
        for dt in (1 / 144, 1 / 60, 1 / 30, 0.5):
            scene = IntroScene()
            advance_to_free_walk(scene)
            hold(scene, RIGHT, 1.3, dt)
            positions.append(scene.actors["alice"].x)
        self.assertAlmostEqual(positions[0], ALICE_START_X + scene.walker.speed * 1.3, places=6)
        for x in positions:
            self.assertAlmostEqual(x, positions[0], places=6)

    def test_glitch_starts_over_the_burrow_after_the_jump(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "glitch")
        alice = scene.actors["alice"]
        self.assertEqual(alice.x, ALICE_LEAP_X)  # уже над норой
        self.assertEqual(alice.lift, ALICE_LEAP)  # сказка зависла посреди прыжка
        self.assertEqual(scene.burrow_open, 1.0)
        self.assertEqual(scene.events[-3:-1], [("node", "a_go"), ("cue", "alice_jumps")])
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

    def test_birthday_plan_follows_after_chuchmek_appears(self) -> None:
        events = play_through(IntroScene())
        emerge = events.index(("cue", "chuchmek_emerges"))
        after = [value for kind, value in events[emerge:] if kind == "node"]
        for node_id in ("d_wait", "d_yours", ORGANIZER_CHOICE_ID, "d_plan", "d_disaster", "d_pieces", "d_now",
                        "d_trials", "d_mosaic", "d_inside", "d_intrigue", "d_why_me", "d_tried", "d_only_you",
                        "d_leo", "d_leo_job", "d_leo_smile", CHOICE_ID, "e_ready", "f_go", "f_questions",
                        "f_form_12b"):
            self.assertIn(node_id, after)
        self.assertEqual(after[-1], "f_form_12b")

    def test_every_combination_of_answers_leads_to_common_ending(self) -> None:
        nodes_by_id = {node.id: node for node in all_nodes()}
        branch_nodes = {node_id for first, second, _ in BRANCHES.values() for node_id in (*first, *second)}
        for organizer in (0, 1):
            for start in (0, 1):
                with self.subTest(organizer=organizer, start=start):
                    scene = IntroScene()
                    answers = {ORGANIZER_CHOICE_ID: organizer, CHOICE_ID: start}
                    events = play_through(scene, answers)
                    nodes = [value for kind, value in events if kind == "node"]
                    self.assertTrue(scene.completed)
                    self.assertEqual(scene.answers[ORGANIZER_CHOICE_ID].text, ORGANIZER_CHOICES[organizer])
                    self.assertEqual(scene.choice.text, CHOICES[start])
                    chosen = set()
                    for question, index in answers.items():
                        first, second, join = BRANCHES[question]
                        taken, skipped = (first, second) if index == 0 else (second, first)
                        chosen.update(taken)
                        self.assertEqual([node for node in nodes if node in taken], list(taken))
                        self.assertFalse(set(skipped) & set(nodes))  # чужая ветка не показана
                        self.assertLess(nodes.index(taken[-1]), nodes.index(join))
                    # Все общие реплики — при любых ответах, каждая по одному разу.
                    expected = [node_id for node_id in nodes_by_id if node_id not in branch_nodes or node_id in chosen]
                    self.assertEqual(sorted(nodes), sorted(expected))
                    self.assertEqual(nodes[-1], "f_form_12b")

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

    def test_rabbit_points_to_the_place_but_there_is_no_burrow_yet(self) -> None:
        scene = IntroScene()
        advance_to_cue(scene, "rabbit_points")
        self.assertEqual(scene.burrow_open, 0.0)
        while scene.cue_name == "rabbit_points":
            scene.update(1 / 60)
            self.assertEqual(scene.burrow_open, 0.0)  # норы ещё не существует
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
            if scene.exploring:
                walk_to_burrow(scene, 0.03)
                elapsed += 0.03
            elif dialogue is not None and not dialogue.is_typing:
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


class InteractiveEntranceTest(IntroTestCase):
    """После разговора с Кроликом Алисой управляет игрок: ходьба, сбой у места норы, нора, вход."""

    def free_walk(self) -> IntroScene:
        scene = IntroScene()
        advance_to_free_walk(scene)
        return scene

    def ready(self) -> IntroScene:
        scene = self.free_walk()
        advance_to_stage(scene, Stage.HOLE_READY)
        return scene

    def walk_until(self, scene: IntroScene, code: tuple[int, int], stop, limit: float = 30.0) -> None:
        """Держит клавишу, пока stop() не станет истинным (не дольше limit секунд)."""
        scene.handle_event(key(*code))
        elapsed = 0.0
        while not stop() and elapsed < limit:
            scene.update(1 / 60)
            elapsed += 1 / 60
        scene.handle_event(key(*code, pygame.KEYUP))
        self.assertTrue(stop(), "не дошла")

    def hole_pixels(self, scene: IntroScene) -> int:
        """Сколько пикселей цвета глубины норы видно на месте норы."""
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        scene.draw(canvas)
        area = pygame.Rect(HOLE_X - 30, scene.ground - 12, 60, 24)
        return sum(
            1 for x in range(area.left, area.right) for y in range(area.top, area.bottom)
            if tuple(canvas.get_at((x, y)))[:3] == HOLE_COLOR
        )

    # --- Управление ---

    def test_control_is_given_once_right_after_the_last_line(self) -> None:
        scene = IntroScene()
        while not (scene.dialogue is not None and scene.dialogue.node.id == "r_invite"):
            step(scene)
        while scene.dialogue.is_typing:
            scene.update(1 / 60)
        self.assertFalse(scene.exploring)
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))  # закрыть приглашение
        self.assertTrue(scene.exploring)
        self.assertIsNone(scene.dialogue)  # между разговором и ходьбой нет лишних страниц
        self.assertIs(scene.stage, Stage.FREE_WALK)
        self.assertEqual(scene.events.count(("stage", "free_walk")), 1)
        self.assertEqual(scene.walker.x, ALICE_START_X)
        self.assertFalse(scene.walker.is_moving)
        self.assertEqual(scene.hint_text, WALK_HINT)
        for _ in range(3):  # повторные E ничего не запускают: норы ещё нет
            scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
            scene.update(0.2)
        self.assertIs(scene.stage, Stage.FREE_WALK)
        self.assertEqual(scene.walker.x, ALICE_START_X)

    def test_alice_walks_both_ways_with_arrows_and_letters_in_both_layouts(self) -> None:
        layouts = {
            "стрелки": (LEFT, RIGHT),
            "A/D": ((pygame.K_a, pygame.KSCAN_A), (pygame.K_d, pygame.KSCAN_D)),
            "ф/в (русская раскладка)": ((ord("ф"), pygame.KSCAN_A), (ord("в"), pygame.KSCAN_D)),
        }
        for name, (left, right) in layouts.items():
            with self.subTest(keys=name):
                scene = self.free_walk()
                start = scene.walker.x
                hold(scene, right, 0.5)
                self.assertAlmostEqual(scene.walker.x, start + scene.walker.speed * 0.5, places=6)
                self.assertEqual(scene.actors["alice"].x, scene.walker.x)
                hold(scene, left, 1.0)
                self.assertAlmostEqual(scene.walker.x, start - scene.walker.speed * 0.5, places=6)
                self.assertIs(scene.stage, Stage.FREE_WALK)

    def test_without_input_alice_does_not_move(self) -> None:
        scene = self.free_walk()
        hold(scene, RIGHT, 0.4)
        x = scene.walker.x
        for _ in range(120):
            scene.update(1 / 60)
        self.assertEqual(scene.walker.x, x)
        self.assertFalse(scene.walker.is_moving)

    def test_speed_follows_dt(self) -> None:
        for seconds in (0.1, 0.37, 1.0):
            for dt in (1 / 144, 1 / 30, 0.25):
                with self.subTest(seconds=seconds, dt=dt):
                    scene = self.free_walk()
                    hold(scene, RIGHT, seconds, dt)
                    self.assertAlmostEqual(scene.walker.x - ALICE_START_X, scene.walker.speed * seconds, places=6)

    def test_alice_does_not_leave_the_page(self) -> None:
        scene = self.free_walk()
        hold(scene, LEFT, 20.0, 0.1)
        self.assertEqual(scene.walker.x, WALK_MIN_X)
        body = scene.actors["alice"].bounds(scene.ground)
        self.assertGreater(body.centerx, 6)  # середина Алисы — внутри рамки страницы
        self.assertIs(scene.stage, Stage.FREE_WALK)

    def test_turning_changes_direction_and_walk_animation(self) -> None:
        scene = self.free_walk()
        alice = scene.actors["alice"]
        sprites = alice.sprites
        walk_right = {id(sprites.frame(f).image) for f in sprites.groups["walk_right"].frame_ids}
        walk_left = {id(sprites.frame(f).image) for f in sprites.groups["walk_left"].frame_ids}
        scene.handle_event(key(*RIGHT))
        scene.update(0.3)
        self.assertIs(scene.walker.direction, Direction.RIGHT)
        self.assertIn(id(alice.source_image()), walk_right)
        x = scene.walker.x
        scene.handle_event(key(*RIGHT, pygame.KEYUP))
        scene.handle_event(key(*LEFT))
        scene.update(0.3)
        self.assertIs(scene.walker.direction, Direction.LEFT)
        self.assertIn(id(alice.source_image()), walk_left)
        self.assertLess(scene.walker.x, x)
        scene.handle_event(key(*LEFT, pygame.KEYUP))
        scene.update(0.1)
        self.assertIs(alice.source_image(), sprites.frame("idle_left").image)  # стоит и смотрит влево

    def test_up_and_down_keys_do_not_move_or_turn_alice(self) -> None:
        scene = self.free_walk()
        direction, x = scene.walker.direction, scene.walker.x
        for code in ((pygame.K_UP, pygame.KSCAN_UP), (pygame.K_w, pygame.KSCAN_W),
                     (pygame.K_DOWN, pygame.KSCAN_DOWN), (ord("ы"), pygame.KSCAN_S)):
            hold(scene, code, 0.3)
        self.assertEqual((scene.walker.direction, scene.walker.x), (direction, x))

    def test_lost_focus_releases_held_keys(self) -> None:
        scene = self.free_walk()
        scene.handle_event(key(*RIGHT))
        scene.update(0.2)
        scene.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        x = scene.walker.x
        scene.update(1.0)
        self.assertEqual(scene.walker.x, x)  # KEYUP потерялся вместе с фокусом, но Алиса не идёт сама

    # --- Триггер ---

    def test_far_from_the_place_nothing_breaks(self) -> None:
        scene = self.free_walk()
        hold(scene, LEFT, 2.0)
        for _ in range(600):
            scene.update(0.05)
        self.assertIs(scene.stage, Stage.FREE_WALK)
        self.assertEqual(scene.burrow_open, 0.0)
        self.assertEqual(scene.events.count(("stage", "glitch_warning")), 0)

    def test_walking_back_and_forth_keeps_control_until_the_place(self) -> None:
        scene = self.free_walk()
        edge = HOLE_X - TRIGGER_DISTANCE
        for code, target in ((RIGHT, edge - 6), (LEFT, edge - 60), (RIGHT, edge - 4), (LEFT, edge - 30)):
            going_right = code is RIGHT
            self.walk_until(scene, code, lambda: scene.walker.x >= target if going_right else scene.walker.x <= target)
            self.assertIs(scene.stage, Stage.FREE_WALK)
            self.assertTrue(scene.entrance.can_walk)
        self.walk_until(scene, RIGHT, lambda: scene.stage is not Stage.FREE_WALK)
        self.assertIs(scene.stage, Stage.GLITCH_WARNING)
        self.assertGreaterEqual(scene.actors["alice"].x, edge)

    def test_trigger_works_at_any_frame_rate_and_only_once(self) -> None:
        edge = HOLE_X - TRIGGER_DISTANCE
        for dt in (1 / 144, 1 / 60, 1 / 30, 0.1, 0.5, 5.0):
            with self.subTest(dt=dt):
                scene = self.free_walk()
                scene.handle_event(key(*RIGHT))
                while scene.stage is Stage.FREE_WALK:
                    scene.update(dt)
                trigger_x = scene._lock_x
                self.assertGreaterEqual(trigger_x, edge)
                self.assertLess(trigger_x, edge + 3.5)  # не проскочила место, даже за один большой кадр
                for _ in range(400):
                    scene.update(1 / 30)
                stages = [value for kind, value in scene.events if kind == "stage"]
                self.assertEqual(stages, SHOW_STAGES)

    def test_one_huge_dt_passes_every_stage(self) -> None:
        scene = self.free_walk()
        scene.handle_event(key(*RIGHT))
        scene.update(60.0)
        stages = [value for kind, value in scene.events if kind == "stage"]
        self.assertEqual(stages, SHOW_STAGES)
        self.assertTrue(scene.entrance.can_walk)
        self.assertIs(scene.actors["alice"].body, scene.walker)
        self.assertEqual(scene.burrow_open, 1.0)
        self.assertEqual(scene.flash, 0.0)

    def test_keys_during_the_show_change_nothing(self) -> None:
        scene = self.free_walk()
        self.walk_until(scene, RIGHT, lambda: scene.stage is not Stage.FREE_WALK)
        alice = scene.actors["alice"]
        self.assertIsNone(alice.body)  # Алису ведёт постановка
        while scene.stage is not Stage.HOLE_READY:
            for code in (LEFT, RIGHT, (pygame.K_e, pygame.KSCAN_E), (pygame.K_RETURN, 0), (pygame.K_SPACE, 0)):
                scene.handle_event(key(*code))
                scene.handle_event(key(*code, pygame.KEYUP))
            x = alice.x
            scene.update(1 / 30)
            if scene.stage is Stage.HOLE_OPENING:
                self.assertEqual(alice.x, x)  # стоит и смотрит, как появляется нора
        self.assertEqual(scene.events.count(("stage", "entering_hole")), 0)
        self.assertFalse(scene.walker.is_moving)  # зажатое во время постановки не тянет Алису дальше

    def test_world_reacts_step_by_step(self) -> None:
        scene = self.free_walk()
        self.walk_until(scene, RIGHT, lambda: scene.stage is not Stage.FREE_WALK)
        rabbit, alice = scene.actors["white_rabbit"], scene.actors["alice"]
        seen = {}
        while scene.stage is not Stage.HOLE_READY:
            fx = scene.entrance_effects()
            info = seen.setdefault(scene.stage, {"flicker": 0, "shift": 0, "tear": 0, "flash": 0, "sparks": 0,
                                                 "remark": set(), "rabbit": set()})
            for name in ("flicker", "shift", "tear", "flash"):
                info[name] = max(info[name], getattr(fx, name))
            info["sparks"] = max(info["sparks"], len(fx.sparks))
            info["remark"].add(scene.rabbit_remark)
            info["rabbit"].add(rabbit.pose)
            scene.update(1 / 60)
        warning, breaking = seen[Stage.GLITCH_WARNING], seen[Stage.WORLD_BREAKING]
        # Сначала только странности: мерцание, сдвиги мелочей, первые искры — без рывков страницы.
        self.assertGreater(warning["flicker"], 0)
        self.assertGreater(warning["shift"], 0)
        self.assertGreater(warning["sparks"], 0)
        self.assertEqual((warning["tear"], warning["flash"]), (0, 0))
        self.assertEqual(warning["remark"], {""})
        # Потом сильнее: полосы страницы съезжают, вспышки, вихрь искр, Кролик в панике.
        self.assertGreater(breaking["tear"], 0)
        self.assertGreater(breaking["flash"], 0)
        self.assertGreater(breaking["sparks"], warning["sparks"])
        self.assertEqual(breaking["remark"], {RABBIT_REMARK_BREAKING})
        self.assertIn("panics_watch", breaking["rabbit"])
        self.assertLess(alice.x, scene._lock_x)  # Алиса отшатнулась от места сбоя
        self.assertEqual(rabbit.pose, "confident_point")
        self.assertEqual(scene.rabbit_remark, RABBIT_REMARK_READY)

    # --- Появление норы ---

    def test_no_hole_is_drawn_before_the_event(self) -> None:
        scene = IntroScene()
        while not scene.exploring:
            self.assertEqual(self.hole_pixels(scene), 0)
            for _ in range(10):
                step(scene)
        self.walk_until(scene, RIGHT, lambda: scene.walker.x > HOLE_X - TRIGGER_DISTANCE - 2)
        self.assertIs(scene.stage, Stage.FREE_WALK)
        for _ in range(100):  # и подсказки у места норы не похожи на открытую нору
            scene.update(0.03)
            self.assertEqual(self.hole_pixels(scene), 0)
            self.assertEqual(scene.burrow_open, 0.0)

    def test_hole_opens_gradually_and_settles(self) -> None:
        scene = self.free_walk()
        self.walk_until(scene, RIGHT, lambda: scene.stage is not Stage.FREE_WALK)
        opening, rims, pixels = [], [], []
        while scene.stage is not Stage.HOLE_READY:
            scene.update(1 / 30)
            if scene.stage is Stage.HOLE_OPENING:
                opening.append(scene.burrow_open)
                rims.append(scene.burrow_rim)
                pixels.append(self.hole_pixels(scene))
            self.assertFalse(scene.entrance.can_enter(scene.actors["alice"].x))
        self.assertEqual(opening, sorted(opening))
        self.assertEqual(rims, sorted(rims))
        self.assertEqual(opening[0], 0.0)
        self.assertEqual(rims[0], 0.0)  # окантовка складывается последней, уже вокруг открытой глубины
        first_rim = next(index for index, rim in enumerate(rims) if rim > 0)
        self.assertGreaterEqual(opening[first_rim], 0.5)
        self.assertEqual(scene.burrow_rim, 1.0)
        self.assertGreater(len({round(value, 2) for value in opening}), 10)  # не включается одной картинкой
        self.assertEqual(pixels[0], 0)
        self.assertGreater(max(pixels), 100)
        self.assertEqual(scene.burrow_open, 1.0)
        scene.update(3.0)  # эффекты затихли, Кролик договорил: нора стоит и не мерцает
        self.assertEqual(scene.rabbit_remark, "")
        frames = []
        for _ in range(3):
            canvas = pygame.Surface(config.LOGICAL_SIZE)
            scene.draw(canvas)
            frames.append(pygame.image.tobytes(canvas, "RGB"))
            scene.update(0.37)
        self.assertEqual(len(set(frames)), 1)
        self.assertTrue(scene.entrance_effects().is_calm)

    def test_control_returns_after_the_hole_opens(self) -> None:
        scene = self.ready()
        self.assertIs(scene.actors["alice"].body, scene.walker)
        self.assertEqual(scene.walker.x, scene.actors["alice"].x)
        self.assertIs(scene.walker.direction, Direction.RIGHT)
        x = scene.walker.x
        hold(scene, LEFT, 0.5)
        self.assertAlmostEqual(scene.walker.x, x - scene.walker.speed * 0.5, places=6)
        hold(scene, RIGHT, 0.5)
        self.assertAlmostEqual(scene.walker.x, x, places=6)

    def test_alice_cannot_walk_over_the_hole(self) -> None:
        scene = self.ready()
        hold(scene, RIGHT, 10.0)
        self.assertEqual(scene.walker.x, WALK_MAX_X)
        self.assertLess(scene.actors["alice"].x, HOLE_X)

    # --- Вход в нору ---

    def test_e_far_from_the_hole_does_not_enter(self) -> None:
        scene = self.ready()
        self.assertGreater(HOLE_X - scene.walker.x, ENTER_DISTANCE)  # после сбоя Алиса стоит поодаль
        self.assertEqual(scene.hint_text, APPROACH_HINT)
        keys = ((pygame.K_e, pygame.KSCAN_E), (ord("у"), pygame.KSCAN_E), (pygame.K_RETURN, 0), (pygame.K_SPACE, 0))
        for code in keys:
            scene.handle_event(key(*code))
            scene.handle_event(key(*code, pygame.KEYUP))
            scene.update(0.1)
        self.assertIs(scene.stage, Stage.HOLE_READY)
        self.assertTrue(scene.exploring)
        self.assertNotIn(("cue", "alice_prepares"), scene.events)

    def test_e_near_the_hole_enters_exactly_once(self) -> None:
        scene = self.ready()
        self.walk_until(scene, RIGHT, lambda: scene.entrance.can_enter(scene.walker.x))
        self.assertEqual(scene.hint_text, ENTER_HINT)
        scene.handle_event(key(pygame.K_SPACE))  # пробел — не «войти»
        self.assertTrue(scene.exploring)
        beat = scene.beat_index
        for _ in range(5):  # первое E входит, остальные ничего не добавляют
            scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
            scene.handle_event(key(pygame.K_RETURN))
        self.assertEqual(scene.beat_index, beat + 1)
        self.assertEqual(scene.cue_name, "alice_prepares")
        self.assertEqual(scene.events.count(("stage", "entering_hole")), 1)
        self.assertEqual(scene.events.count(("cue", "alice_prepares")), 1)
        self.assertFalse(scene.exploring)
        self.assertIsNone(scene.actors["alice"].body)  # дальше Алису ведёт сценарий

    def test_enter_key_works_like_e(self) -> None:
        scene = self.ready()
        self.walk_until(scene, RIGHT, lambda: scene.entrance.can_enter(scene.walker.x))
        scene.handle_event(key(pygame.K_RETURN))
        self.assertIs(scene.stage, Stage.ENTERING_HOLE)

    def test_walking_away_and_back_to_the_hole(self) -> None:
        scene = self.ready()
        self.walk_until(scene, LEFT, lambda: scene.walker.x <= 120)
        self.assertEqual(scene.hint_text, APPROACH_HINT)
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
        self.assertIs(scene.stage, Stage.HOLE_READY)
        self.assertEqual(scene.burrow_open, 1.0)  # нора на месте
        self.walk_until(scene, RIGHT, lambda: scene.entrance.can_enter(scene.walker.x))
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
        self.assertIs(scene.stage, Stage.ENTERING_HOLE)

    def test_after_entering_alice_crouches_jumps_and_the_old_glitch_follows(self) -> None:
        scene = self.ready()
        self.walk_until(scene, RIGHT, lambda: scene.entrance.can_enter(scene.walker.x))
        scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
        alice = scene.actors["alice"]
        while scene.cue_name == "alice_prepares":
            scene.update(1 / 60)
        self.assertEqual((alice.x, alice.squash), (ALICE_BURROW_X, 0.88))  # на самом краю и присела
        self.assertEqual(scene.dialogue.node.id, "a_go")  # «Ну, поехали.»
        while scene.cue_name != "alice_jumps":
            step(scene)
        lifts = []
        while scene.cue_name == "alice_jumps":
            scene.update(1 / 60)
            lifts.append(alice.lift)
        self.assertEqual(lifts[:-1], sorted(lifts[:-1]))  # взлетает
        self.assertEqual(scene.cue_name, "glitch")
        for cue in ("error_message", "restart", "title_rewrite", "chuchmek_emerges"):
            advance_to_cue(scene, cue)
        self.assertEqual(scene.title, TITLE_FINAL)

    def test_explore_frames_draw_through_a_strict_layer_without_double_alice(self) -> None:
        scene = self.free_walk()
        alice = scene.actors["alice"]
        alice_images = {id(frame.image) for frame in alice.sprites.frames}
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        stages = set()
        while scene.exploring:
            layer = HiResLayer(strict=True)  # логическая графика не выходит за свои области
            scene.draw(canvas, layer)
            sprites = [c for c in layer.commands if isinstance(c, SpriteCommand) and id(c.image) in alice_images]
            self.assertEqual(len(sprites), 1, scene.stage)  # ни двойного силуэта, ни пропавшей Алисы
            self.assertEqual(sprites[0].rect, alice.bounds(scene.ground))
            stages.add(scene.stage)
            walk_to_burrow(scene, 1 / 30)
        self.assertEqual(stages, set(Stage) - {Stage.ENTERING_HOLE})

    def test_rabbit_stays_visible_and_reacts(self) -> None:
        scene = self.free_walk()
        rabbit = scene.actors["white_rabbit"]
        self.assertEqual(rabbit.pose, "hurries_pointing")  # показывает, куда идти
        scene.handle_event(key(*LEFT))
        scene.update(0.3)
        self.assertEqual(rabbit.pose, "annoyed_watch")  # Алиса пошла не туда — Кролик смотрит на часы
        scene.handle_event(key(*LEFT, pygame.KEYUP))
        scene.update(0.1)
        self.assertEqual(rabbit.pose, "hurries_pointing")
        while scene.exploring:
            self.assertTrue(rabbit.visible)
            self.assertNotIn("white_rabbit", scene.hidden)
            walk_to_burrow(scene, 1 / 30)


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
            if scene.exploring:
                walk_to_burrow(scene, 0.1)
                elapsed += 0.1
            elif dialogue is not None and not dialogue.is_typing:
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

    def test_held_e_closes_the_last_line_and_does_nothing_more(self) -> None:
        self.press(pygame.K_i, pygame.KSCAN_I)
        intro = self.app.scenes.current
        while not (intro.dialogue is not None and intro.dialogue.node.id == "r_invite"):
            step(intro)
        while intro.dialogue.is_typing:
            intro.update(1 / 60)
        e = (pygame.K_e, pygame.KSCAN_E)
        self.send(key(*e))  # нажала E и держит: системный автоповтор шлёт KEYDOWN без KEYUP
        self.assertTrue(intro.exploring)
        for _ in range(10):
            self.send(key(*e))
            self.app.scenes.update(0.1)
        self.assertIs(intro.stage, Stage.FREE_WALK)
        self.assertEqual(intro.walker.x, ALICE_START_X)
        self.assertEqual(intro.events.count(("stage", "free_walk")), 1)
        self.send(key(*e, pygame.KEYUP))
        # Стрелка через приложение ведёт Алису, а её автоповтор не сбивает шаг.
        self.send(key(*RIGHT))
        self.app.scenes.update(0.5)
        self.send(key(*RIGHT), key(*RIGHT))
        self.app.scenes.update(0.5)
        self.send(key(*RIGHT, pygame.KEYUP))
        self.assertAlmostEqual(intro.walker.x, ALICE_START_X + intro.walker.speed, places=6)

    def test_escape_f11_and_window_close_while_exploring(self) -> None:
        for stage in (Stage.FREE_WALK, Stage.WORLD_BREAKING, Stage.HOLE_OPENING, Stage.HOLE_READY):
            with self.subTest(stage=stage):
                self.press(pygame.K_i, pygame.KSCAN_I)
                intro = self.app.scenes.current
                advance_to_stage(intro, stage)
                intro.update(0.2 if stage is not Stage.FREE_WALK else 0.0)
                before = intro.stage
                self.app.running = True
                self.press(pygame.K_F11)
                self.assertTrue(self.app.display.is_fullscreen)
                self.app.scenes.draw(self.app.display.canvas, self.app.display.hires)
                self.app.display.present()
                self.press(pygame.K_F11)
                self.assertFalse(self.app.display.is_fullscreen)
                self.press(pygame.K_ESCAPE)
                self.assertFalse(self.app.running)
                self.app.running = True
                self.send(pygame.event.Event(pygame.QUIT))
                self.assertFalse(self.app.running)
                self.assertIs(intro.stage, before)  # события окна не сбили эпизод
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
