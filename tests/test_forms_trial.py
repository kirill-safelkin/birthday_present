"""Проверки сцены испытания формуляров: поиск, раскладка, награда, отмена, переходы с площади."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import tempfile  # noqa: E402
from collections import deque  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.fonts import TextFonts  # noqa: E402
from game.graphics.hires import HiResLayer, TextCommand  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story.forms_dialogue import (  # noqa: E402
    FINAL,
    GOOSE,
    GOOSE_IDLE_POSE,
    GOOSE_POSES,
    INSPECTION,
    INTRO,
    OATH_CHOICE_ID,
    REGISTER_CHOICE_ID,
    all_scripts,
)
from game.story.intro_dialogue import ALICE  # noqa: E402
from game.trials.forms_puzzle import (  # noqa: E402
    CORRECT_ORDER,
    DOCUMENT_NAMES,
    DOCUMENT_TITLES,
    DOCUMENTS,
    ISSUED,
    SECTIONS,
)
from game.trials.forms_scene import (  # noqa: E402
    CABINETS,
    DONE,
    EXPLORE,
    FINAL_PHASE,
    FORMS_SCENE,
    GOOSE_POSITION,
    GOOSE_REACH,
    HUD_HEIGHT,
    INTRO_PHASE,
    ISSUED_LINES,
    ISSUED_SHEET,
    ISSUED_TEXT_STYLE,
    ISSUED_TITLE_STYLE,
    DOCUMENT_COLORS,
    HUD_STYLE,
    PAPER_COLOR,
    PAPER_SIZE,
    PAPER_TITLE_LINES,
    PAPER_TITLE_SIZE,
    PREVIEW_TITLE_SIZE,
    REACTION,
    SLOT_XS,
    SLOT_Y,
    SPAWN,
    SPRITE_SIZE,
    STATUS_TOP,
    TABLE,
    WALK_BOUNDS,
    FormsTrialScene,
    paper_title_layout,
    slot_paper,
)
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import STATIONS, TABLE as SUSHI_TABLE, SushiTrialScene  # noqa: E402
from game.world.hub import PORTALS, TRIAL_SCENES, HubScene  # noqa: E402
from game.world.progress import GameProgress  # noqa: E402

DT = 1 / 60
CABINET = {cabinet.section.id: cabinet for cabinet in CABINETS}
SECTION_OF = {section.document: section.id for section in SECTIONS if section.document}
GOOSE_SPOT = (GOOSE_POSITION[0] - 22, GOOSE_POSITION[1])  # слева от гуся, вплотную к препятствию
WIDTH, HEIGHT = config.LOGICAL_SIZE


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press(scene: Scene, code: int, scancode: int = 0) -> None:
    scene.handle_event(key(code, scancode))
    scene.handle_event(key(code, scancode, pygame.KEYUP))


def press_e(scene: Scene) -> None:
    press(scene, pygame.K_e, pygame.KSCAN_E)


def finish_dialogue(scene: FormsTrialScene) -> list[str]:
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


def stand_at(scene: FormsTrialScene, point: tuple[int, int]) -> None:
    scene.alice.set_position(*point)


def search(scene: FormsTrialScene, section_id: str) -> str:
    """Поиск в шкафу клавишей E. Возвращает текст находки и закрывает реплику."""
    stand_at(scene, CABINET[section_id].point)
    press_e(scene)
    text = scene.dialogue.node.text
    finish_dialogue(scene)
    return text


def find_all(scene: FormsTrialScene) -> None:
    for document in CORRECT_ORDER:
        search(scene, SECTION_OF[document])


def use_slot(scene: FormsTrialScene, index: int) -> None:
    stand_at(scene, (SLOT_XS[index], SLOT_Y))
    press_e(scene)


def arrange(scene: FormsTrialScene) -> None:
    """Со «архивного» порядка (разрешение на подачу, заявление о Лео, заявление на бланк) — на правильный,
    двумя обменами."""
    use_slot(scene, 2)
    use_slot(scene, 0)
    use_slot(scene, 2)
    use_slot(scene, 1)


def talk_to_goose(scene: FormsTrialScene) -> None:
    stand_at(scene, GOOSE_SPOT)
    press_e(scene)


def play(scene: FormsTrialScene, stop_before_final_end: bool = False) -> None:
    """Проходит испытание: вступление, поиск, раскладка, сдача, приём и разрешение, гражданство."""
    finish_dialogue(scene)
    find_all(scene)
    arrange(scene)
    talk_to_goose(scene)
    finish_dialogue(scene)  # приём документов и разрешение на получение гражданства
    if not stop_before_final_end:
        finish_dialogue(scene)  # гражданство и фрагмент


def until_node(scene: FormsTrialScene, node_id: str) -> None:
    """Листает Enter до реплики node_id (на вопросе Enter выбирает первый ответ) и дописывает её."""
    for _ in range(200):
        if scene.dialogue.node.id == node_id:
            scene.dialogue.update(30)
            return
        press(scene, pygame.K_RETURN)
        if scene.dialogue.node.id != node_id and not scene.dialogue.is_typing:
            press(scene, pygame.K_RETURN)
    raise AssertionError(f"не дошли до реплики {node_id}")


def answer(scene: FormsTrialScene, index: int) -> list[str]:
    """Пролистывает текущий диалог; на вопросе — ↓ до ответа index и E. Возвращает показанные реплики."""
    script = scene.dialogue.script
    shown = []
    for _ in range(200):
        dialogue = scene.dialogue
        if dialogue is None or dialogue.script is not script:
            return shown
        if not shown or shown[-1] != dialogue.node.id:
            shown.append(dialogue.node.id)
        if dialogue.is_typing:
            press_e(scene)
            continue
        if dialogue.choices:
            for _ in range(index):
                press(scene, pygame.K_DOWN)
        press_e(scene)
    raise AssertionError(f"диалог не заканчивается: {shown}")


def drawn_texts(scene: FormsTrialScene) -> list[TextCommand]:
    """Надписи кадра в слое высокого разрешения."""
    layer = HiResLayer()
    scene.draw(pygame.Surface(config.LOGICAL_SIZE), layer)
    return [command for command in layer.commands if isinstance(command, TextCommand)]


def paper_titles(scene: FormsTrialScene, size: float) -> list[TextCommand]:
    """Строки названий на листах документов шрифтом size (на столе или крупный лист находки)."""
    return [c for c in drawn_texts(scene) if c.style.size == size and c.style.background == PAPER_COLOR]


def table_titles(scene: FormsTrialScene) -> list[str | None]:
    """Что написано на листах стола подачи, место за местом: название целиком или None (место пустое)."""
    texts = paper_titles(scene, PAPER_TITLE_SIZE)
    titles = []
    for index in range(len(SLOT_XS)):
        paper = slot_paper(index)
        lines = [c.text for c in texts if paper.collidepoint(c.pos)]
        titles.append(" ".join(lines) or None)
    return titles


def hold(scene: FormsTrialScene, codes: list[int], frames: int) -> None:
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
        self.scene = self.manager.push(FormsTrialScene(self.progress))

    def tearDown(self) -> None:
        pygame.quit()


class IntroTest(TrialTestCase):
    def test_starts_with_goose_intro_and_alice_in_a_safe_spot(self) -> None:
        self.assertEqual(self.scene.phase, INTRO_PHASE)
        self.assertIs(self.scene.dialogue.script, INTRO)
        self.assertEqual(self.scene.dialogue.node.speaker, GOOSE)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), SPAWN)
        self.assertTrue(self.scene.collision.is_free(*SPAWN))
        self.assertIsNone(self.scene.nearby())  # у входа ни с чем не взаимодействует случайно

    def test_intro_lines(self) -> None:
        shown = finish_dialogue(self.scene)
        lines = [(INTRO.nodes[node_id].speaker, INTRO.nodes[node_id].text) for node_id in shown]
        self.assertEqual(lines[:5], [
            (GOOSE, "Стойте. Для подготовки праздника необходимо проверить реестр участников."),
            (ALICE, "Проверяйте. Лео уже здесь — спит в корзинке на площади."),
            (GOOSE, "В реестре Страны Чудес Лео не значится: ни рождения, ни гражданства. "
                    "Есть только отметка «сопит»."),
            (GOOSE, "Присутствие не заменяет регистрацию. Регистрация не заменяет разрешение. "
                    "А разрешение не заменяет разрешение на получение разрешения."),
            (GOOSE, "Итак. С чем пожаловали?"),
        ])
        # Задача и порядок процедуры — при любом ответе (Enter выбрал первый).
        text = " ".join(INTRO.nodes[node_id].text for node_id in shown)
        for words in ("заявление на выдачу бланка заявления", "разрешение на подачу заявления",
                      "заявление о регистрации рождения и гражданстве Лео", "стол подачи", "сдавать — мне"):
            self.assertIn(words, text)
        self.assertEqual(self.scene.phase, EXPLORE)
        self.assertEqual(self.scene.goose_pose, GOOSE_IDLE_POSE)

    def test_nothing_moves_or_is_searched_during_dialogue(self) -> None:
        stand_at(self.scene, CABINET["requests"].point)
        self.scene.handle_event(key(pygame.K_LEFT))
        self.scene.update(1.0)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), CABINET["requests"].point)
        self.scene.handle_event(key(pygame.K_LEFT, event_type=pygame.KEYUP))
        press_e(self.scene)  # E в реплике только листает её
        self.assertEqual(self.scene.puzzle.found, [])
        self.assertEqual(sum(self.scene.puzzle.searches.values()), 0)


class SearchTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)

    def test_cabinet_gives_document_with_a_funny_line(self) -> None:
        stand_at(self.scene, CABINET["requests"].point)
        self.assertEqual(self.scene.status_text(), "«Заявки, которые ещё не стали заявлениями»   E — искать")
        press_e(self.scene)
        self.assertEqual(self.scene.dialogue.node.speaker, ALICE)
        self.assertIn("Заявление на выдачу бланка заявления", self.scene.dialogue.node.text)
        self.assertIn("без бланка его не напишешь", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.puzzle.order, (None, None, "form_request"))
        self.assertEqual(self.scene.status_text(), "На столе подачи: Заявление на бланк (1/3)")
        self.assertEqual(self.scene.task_text(), "Задача: найди документы Лео 1/3")
        self.assertEqual(table_titles(self.scene), [None, None, "Заявление на выдачу бланка заявления"])

    def test_each_document_is_in_its_section(self) -> None:
        texts = {document: search(self.scene, SECTION_OF[document]) for document in CORRECT_ORDER}
        self.assertIn("Заявление на выдачу бланка заявления", texts["form_request"])
        self.assertIn("Разрешение на подачу заявления", texts["filing_permit"])
        self.assertIn("Заявление о регистрации рождения и гражданстве Лео", texts["leo_application"])
        self.assertEqual(SECTION_OF,
                         {"form_request": "requests", "filing_permit": "permits", "leo_application": "births"})
        self.assertTrue(self.scene.puzzle.all_found)
        self.assertEqual(self.scene.toast, "Все документы на столе — разложи их по порядку")
        self.assertEqual(self.scene.task_text(), "Задача: сложи по порядку и сдай гусю")
        self.assertEqual(table_titles(self.scene), [DOCUMENT_TITLES["filing_permit"], DOCUMENT_TITLES["leo_application"],
                                                    DOCUMENT_TITLES["form_request"]])

    def test_wrong_shelf_is_a_joke_without_side_effects(self) -> None:
        jokes = [search(self.scene, "cakes") for _ in range(4)]
        self.assertIn("Наполеон", jokes[0])
        self.assertEqual(len(set(jokes[:3])), 3)  # шутки разные
        self.assertEqual(jokes[3], jokes[0])  # и идут по кругу
        self.assertIn("соответствующий отдел", search(self.scene, "department"))
        self.assertEqual(self.scene.puzzle.found, [])
        self.assertEqual(self.scene.puzzle.order, (None, None, None))
        self.assertEqual(self.scene.phase, EXPLORE)
        self.assertEqual(self.scene.task_text(), "Задача: найди документы Лео 0/3")
        x = self.scene.alice.x
        hold(self.scene, [pygame.K_RIGHT], 20)  # управление вернулось
        self.assertGreater(self.scene.alice.x, x)

    def test_repeated_search_creates_no_extra_documents(self) -> None:
        first = search(self.scene, "births")
        again = [search(self.scene, "births") for _ in range(2)]
        self.assertIn("Заявление о регистрации рождения и гражданстве Лео", first)
        self.assertNotIn("Заявление о регистрации", again[0])  # там больше ничего нужного
        self.assertEqual(again[0], again[1])
        self.assertEqual(self.scene.puzzle.found, ["leo_application"])
        self.assertEqual(self.scene.puzzle.order.count("leo_application"), 1)
        self.assertEqual(self.scene.task_text(), "Задача: найди документы Лео 1/3")

    def test_goose_hints_on_repeated_visits(self) -> None:
        talk_to_goose(self.scene)
        hint = self.scene.dialogue.node.text
        self.assertIn("заявления на выдачу бланка", hint)
        self.assertIn("заявок, которые ещё не стали заявлениями", hint)  # где искать — только этот документ
        self.assertNotIn("Лео", hint)  # и не весь порядок сразу
        self.assertEqual(self.scene.goose_pose, GOOSE_POSES["hint"])
        finish_dialogue(self.scene)
        talk_to_goose(self.scene)  # повторно — та же подсказка, ничего не сломалось
        self.assertEqual(self.scene.dialogue.node.text, hint)
        finish_dialogue(self.scene)
        search(self.scene, "requests")
        stand_at(self.scene, GOOSE_SPOT)
        self.scene.update(2.0)  # сообщение о находке уже не важнее подсказки
        self.assertEqual(self.scene.status_text(), "Гусь-инспектор   E — спросить совета")
        press_e(self.scene)
        self.assertIn("разрешения на подачу", self.scene.dialogue.node.text)  # подсказка про следующий документ
        self.assertIn("среди других разрешений", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        search(self.scene, "permits")
        talk_to_goose(self.scene)
        self.assertIn("заявления о Лео", self.scene.dialogue.node.text)
        self.assertIn("рождений, ожидающих регистрации", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.puzzle.failed_checks, 0)  # без всех трёх сдать нельзя — это не ошибка
        self.assertFalse(self.scene.puzzle.solved)
        self.assertEqual(self.scene.phase, EXPLORE)

    def test_table_waits_for_all_documents(self) -> None:
        search(self.scene, "requests")
        search(self.scene, "permits")
        stand_at(self.scene, (SLOT_XS[0], SLOT_Y))
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Стол подачи   найдено документов: 2/3")
        press_e(self.scene)
        self.assertIsNone(self.scene.puzzle.held)
        self.assertEqual(self.scene.status_text(), "Сначала найди все документы: 2/3")
        self.assertEqual(self.scene.puzzle.order, ("filing_permit", None, "form_request"))


class TableTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)
        find_all(self.scene)

    def test_take_put_back_and_swap_are_shown(self) -> None:
        stand_at(self.scene, (SLOT_XS[0], SLOT_Y))
        self.assertEqual(self.scene.status_text(), "Все документы на столе — разложи их по порядку")  # свежее
        self.scene.update(2.0)  # сообщение о находке уже не важнее подсказки
        self.assertEqual(self.scene.status_text(), "Место 1: Разрешение на подачу   E — взять")
        press_e(self.scene)
        self.assertEqual(self.scene.held_text(), "В руках: Разрешение на подачу заявления")  # полное название
        self.assertEqual(self.scene.hud_text(), self.scene.held_text())
        self.assertEqual(self.scene.status_text(), "Взяла: Разрешение на подачу")
        self.assertEqual(table_titles(self.scene), [None, DOCUMENT_TITLES["leo_application"],
                                                    DOCUMENT_TITLES["form_request"]])
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Место 1   E — положить обратно")
        press_e(self.scene)
        self.assertEqual(self.scene.held_text(), "")
        self.assertEqual(self.scene.hud_text(), self.scene.task_text())
        self.assertEqual(self.scene.status_text(), "Положила обратно: Разрешение на подачу")
        use_slot(self.scene, 2)
        stand_at(self.scene, (SLOT_XS[0], SLOT_Y))
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Место 1: Разрешение на подачу   E — поменять местами")
        press_e(self.scene)
        self.assertEqual(self.scene.status_text(), "Поменяла местами: Заявление на бланк и Разрешение на подачу")
        self.assertEqual(table_titles(self.scene), [DOCUMENT_TITLES["form_request"], DOCUMENT_TITLES["leo_application"],
                                                    DOCUMENT_TITLES["filing_permit"]])

    def test_wrong_order_is_rejected_and_can_be_fixed(self) -> None:
        stand_at(self.scene, GOOSE_SPOT)
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Гусь-инспектор   E — сдать документы")
        press_e(self.scene)
        self.assertEqual(self.scene.phase, EXPLORE)
        self.assertEqual(self.scene.goose_pose, "reject")
        self.assertTrue(self.scene.dialogue.node.text.startswith("Отказано"))
        shown = finish_dialogue(self.scene)
        self.assertEqual(shown, ["reject_joke", "reject_hint"])
        # Стол не тронут.
        self.assertEqual(self.scene.puzzle.order, ("filing_permit", "leo_application", "form_request"))
        use_slot(self.scene, 2)
        use_slot(self.scene, 0)  # заявление — первым, остальное ещё перепутано
        talk_to_goose(self.scene)
        self.assertIn("Снова отказано", self.scene.dialogue.node.text)  # вторая попытка — другая шутка
        press(self.scene, pygame.K_RETURN)
        press(self.scene, pygame.K_RETURN)
        self.assertIn("только с разрешением на подачу — оно второе", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.progress.fragments, 0)
        use_slot(self.scene, 2)
        use_slot(self.scene, 1)
        talk_to_goose(self.scene)
        self.assertEqual(self.scene.phase, REACTION)
        self.assertIs(self.scene.dialogue.script, INSPECTION)

    def test_document_in_hands_is_not_submitted(self) -> None:
        arrange(self.scene)
        use_slot(self.scene, 1)
        stand_at(self.scene, GOOSE_SPOT)
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Гусь-инспектор   E — спросить совета")
        press_e(self.scene)
        self.assertIn("не документ, а намерение", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.puzzle.held, "filing_permit")
        self.assertEqual(self.scene.puzzle.failed_checks, 0)
        self.assertEqual(self.scene.phase, EXPLORE)
        use_slot(self.scene, 1)
        talk_to_goose(self.scene)
        self.assertEqual(self.scene.phase, REACTION)

    def test_held_document_floats_above_alice(self) -> None:
        use_slot(self.scene, 0)
        for spot in ((SLOT_XS[0], SLOT_Y), CABINET["births"].point, (WALK_BOUNDS.right - 6, 100)):
            stand_at(self.scene, spot)
            self.scene.update(0.25)  # значок не «подпрыгивает»
            self.scene.draw(self.canvas)
            x, y = self.scene.held_icon_center()
            self.assertGreaterEqual(y - 9, HUD_HEIGHT)  # не под полосой интерфейса
            self.assertLessEqual(x + 7, WIDTH)  # и не за краем экрана
            self.assertLessEqual(y + 8, self.scene.alice.rect.top)  # над головой, а не на лице
            self.assertEqual(tuple(self.canvas.get_at((x - 4, y + 4)))[:3], PAPER_COLOR)  # тот же лист бумаги

    def test_reaction_then_final_check(self) -> None:
        arrange(self.scene)
        talk_to_goose(self.scene)
        self.assertEqual(self.scene.goose_pose, "inspect")
        shown = finish_dialogue(self.scene)
        self.assertEqual(shown, ["r_oath_intro", OATH_CHOICE_ID, "r_snore", "r_inspect", "r_registered", "r_almost",
                                 "r_already", "r_different", "r_stamp", "r_approve"])
        self.assertIn("Все три документа в правильном порядке", INSPECTION.nodes["r_inspect"].text)
        self.assertIn("разрешение на получение гражданства", INSPECTION.nodes["r_almost"].text)
        self.assertIn("разные печати", INSPECTION.nodes["r_different"].text)
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertIs(self.scene.dialogue.script, FINAL)
        self.assertEqual(self.scene.puzzle.issued, ["citizenship_permit"])
        self.assertEqual(self.scene.task_text(), "Документы Лео приняты")
        texts = [FINAL.nodes[node_id].text for node_id in finish_dialogue(self.scene)]
        self.assertEqual(texts[0], "На основании разрешения на получение гражданства постановляю: "
                                   "Лео признан гражданином Страны Чудес.")
        self.assertIn("Рождение Лео зарегистрировано", texts[1])
        self.assertEqual(texts[3], "Поздравляю Лео! Теперь можно отмечать день рождения?")
        self.assertIn("за сон во время официальных мероприятий", texts[4])
        self.assertIn("фрагмент праздничного плана", texts[-1])
        self.assertTrue(self.scene.puzzle.citizen)
        self.assertEqual(self.scene.task_text(), "Лео — гражданин Страны Чудес")

    def test_table_is_locked_after_acceptance(self) -> None:
        arrange(self.scene)
        talk_to_goose(self.scene)
        press(self.scene, pygame.K_RIGHT)  # во время реакции Алиса стоит
        use_slot(self.scene, 0)
        self.assertIsNone(self.scene.puzzle.held)
        self.assertEqual(self.scene.puzzle.order, CORRECT_ORDER)


class LeoProcedureTest(TrialTestCase):
    """Сюжет формуляров: регистрация рождения Лео, разрешение на получение гражданства и гражданство."""

    def test_intro_answers_have_own_lines_and_give_the_same_task(self) -> None:
        branches = {0: ["i_simply", "i_not_rumour"], 1: ["i_expert"]}
        for index, own in branches.items():
            with self.subTest(answer=index):
                progress = GameProgress()
                scene = FormsTrialScene(progress)
                shown = answer(scene, index)
                question = shown.index(REGISTER_CHOICE_ID)
                self.assertEqual(shown[question + 1:question + 1 + len(own)], own)
                other = branches[1 - index]
                self.assertFalse(set(other) & set(shown))  # чужая ветка не показана
                self.assertEqual(shown[question + 1 + len(own):], ["i_first", "i_then", "i_procedure", "i_known",
                                                                   "i_table", "i_order"])
                self.assertEqual(scene.phase, EXPLORE)
                self.assertEqual(scene.puzzle.found, [])  # ответ не находит документы за игрока
                self.assertEqual(progress.completed, ())
        nodes = INTRO.nodes
        self.assertEqual([choice.text for choice in nodes[REGISTER_CHOICE_ID].choices],
                         ["Мы просто хотим зарегистрировать Лео.", "А есть заявление на разрешение заявления?"])
        self.assertIn("для архива — слух", nodes["i_simply"].text)  # присутствие — ещё не регистрация
        self.assertIn("Именно такая бумага нам и нужна", nodes["i_expert"].text)

    def test_oath_answers_change_only_the_goose_line(self) -> None:
        results = {}
        for index, own in ((0, "r_snore"), (1, "r_oath_permit")):
            with self.subTest(answer=index):
                scene = FormsTrialScene(GameProgress())
                finish_dialogue(scene)
                find_all(scene)
                arrange(scene)
                talk_to_goose(scene)
                shown = answer(scene, index)
                self.assertIn(own, shown)
                self.assertNotIn({"r_snore": "r_oath_permit", "r_oath_permit": "r_snore"}[own], shown)
                self.assertEqual(shown[shown.index(own) + 1:], ["r_inspect", "r_registered", "r_almost", "r_already",
                                                                "r_different", "r_stamp", "r_approve"])
                self.assertIs(scene.dialogue.script, FINAL)
                results[index] = (scene.phase, scene.puzzle.order, list(scene.puzzle.issued), scene.progress.completed)
        self.assertEqual(results[0], results[1])  # дальше — одно и то же

    def test_permit_is_issued_with_a_stamp_then_citizenship_with_a_certificate(self) -> None:
        scene = self.scene
        finish_dialogue(scene)
        find_all(scene)
        arrange(scene)
        talk_to_goose(scene)
        until_node(scene, "r_different")
        self.assertEqual(scene.puzzle.issued, [])  # пока только объясняет, что нужно ещё разрешение
        self.assertEqual(self.sheet_texts(), [])
        until_node(scene, "r_stamp")
        self.assertEqual(scene.goose_pose, "stamp")
        self.assertEqual(scene.puzzle.issued, ["citizenship_permit"])
        self.assertEqual(self.sheet_texts(), list(ISSUED_LINES["citizenship_permit"]))
        self.assertIn("Разрешение на получение гражданства Лео", scene.dialogue.node.text)
        finish_dialogue(scene)
        self.assertEqual(scene.dialogue.node.id, "f_decree")
        self.assertFalse(scene.puzzle.citizen)
        until_node(scene, "f_certificate")
        self.assertTrue(scene.puzzle.citizen)
        self.assertEqual(scene.goose_pose, "celebrate")
        self.assertEqual(self.sheet_texts(), ["СВИДЕТЕЛЬСТВО", "Рождение Лео зарегистрировано",
                                              "Лео — гражданин Страны Чудес"])
        self.assertEqual(scene.task_text(), "Лео — гражданин Страны Чудес")
        self.assertEqual(self.progress.fragments, 0)  # гражданство — ещё не награда
        until_node(scene, "f_fragment")
        self.assertEqual(self.progress.fragments, 0)
        finish_dialogue(scene)
        self.assertEqual(self.progress.completed, ("forms",))

    def sheet_texts(self) -> list[str]:
        layer = HiResLayer()
        self.scene.draw(self.canvas, layer)
        return [command.text for command in layer.commands if isinstance(command, TextCommand)
                and command.style in (ISSUED_TITLE_STYLE, ISSUED_TEXT_STYLE) and ISSUED_SHEET.collidepoint(command.pos)]

    def test_issued_sheet_fits_and_covers_nobody(self) -> None:
        fonts = TextFonts()
        for document, lines in ISSUED_LINES.items():
            for text, style, (x, y) in self.scene.issued_layout(document):
                with self.subTest(document=document, text=text):
                    for width in (fonts.metrics(style).width(text), self.scene._small_font.size(text)[0]):
                        self.assertLessEqual(x + width, ISSUED_SHEET.right - 18)  # левее печати
                    self.assertTrue(ISSUED_SHEET.top + 2 <= y <= ISSUED_SHEET.bottom - 2)
            self.assertLessEqual(len(lines), 3)
        self.assertGreaterEqual(ISSUED_SHEET.top, HUD_HEIGHT)
        box = DialogueBox()
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in all_scripts() for node in script.nodes.values())
        self.assertLessEqual(ISSUED_SHEET.bottom, lowest_box)  # окно реплики лист не закрывает
        # Лист выдают, когда Алиса у гуся: где бы она ни стояла рядом с ним, лист её не закрывает.
        goose = self.scene._goose_image().get_rect(midbottom=GOOSE_POSITION)
        self.assertFalse(ISSUED_SHEET.colliderect(goose))
        checked = 0
        for x in range(GOOSE_POSITION[0] - GOOSE_REACH, GOOSE_POSITION[0] + GOOSE_REACH + 1):
            for y in range(GOOSE_POSITION[1] - GOOSE_REACH, GOOSE_POSITION[1] + 1):
                stand_at(self.scene, (x, y))
                if self.scene.collision.is_free(x, y) and self.scene.nearby() is not None \
                        and self.scene.nearby().kind == "goose":
                    self.assertFalse(ISSUED_SHEET.colliderect(self.scene.alice.rect), (x, y))
                    checked += 1
        self.assertGreater(checked, 50)


class RewardTest(TrialTestCase):
    def test_fragment_only_after_final_line(self) -> None:
        play(self.scene, stop_before_final_end=True)
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertTrue(self.scene.puzzle.solved)
        self.assertEqual(self.progress.fragments, 0)  # документы приняты, но проверка ещё не закончена
        finish_dialogue(self.scene)
        self.assertEqual(self.progress.completed, ("forms",))
        self.assertTrue(self.scene.reward_given)
        self.assertTrue(self.scene.completed)
        self.assertEqual(self.scene.phase, DONE)
        self.assertIs(self.manager.current, self.hub)  # та же площадь, не новая

    def test_progress_does_not_change_before_the_end(self) -> None:
        finish_dialogue(self.scene)
        find_all(self.scene)
        talk_to_goose(self.scene)  # неверный порядок
        finish_dialogue(self.scene)
        arrange(self.scene)
        talk_to_goose(self.scene)
        self.assertEqual(self.progress.fragments, 0)
        finish_dialogue(self.scene)
        self.assertEqual(self.progress.fragments, 0)

    def test_paging_back_and_forth_repeats_no_procedure_step(self) -> None:
        # ← до начала разговора и → обратно вокруг выдачи разрешения и свидетельства: документы
        # не выдаются повторно, Алиса стоит, фрагмент — только после последней реплики, один раз.
        scene = self.scene
        finish_dialogue(scene)
        find_all(scene)
        arrange(scene)
        talk_to_goose(scene)
        position = (scene.alice.x, scene.alice.y)
        for node_id, issued in (("r_stamp", ["citizenship_permit"]), ("f_certificate", list(ISSUED))):
            if scene.dialogue.node.id != node_id:
                until_node(scene, node_id)
            self.assertEqual(scene.puzzle.issued, issued)
            for _ in range(2):
                steps = 0
                while scene.dialogue.can_go_back:
                    press(scene, pygame.K_LEFT, pygame.KSCAN_LEFT)
                    steps += 1
                self.assertGreater(steps, 0)
                for _ in range(steps):
                    press(scene, pygame.K_RIGHT, pygame.KSCAN_RIGHT)
                self.assertEqual((scene.dialogue.node.id, scene.dialogue.is_reviewing), (node_id, False))
                self.assertEqual(scene.puzzle.issued, issued)  # ни второго разрешения, ни второго свидетельства
            self.assertEqual(self.progress.fragments, 0)
            self.assertEqual((scene.alice.x, scene.alice.y), position)
            if node_id == "r_stamp":
                finish_dialogue(scene)  # приём закончен — гусь переходит к гражданству
        self.assertEqual(scene.phase, FINAL_PHASE)
        finish_dialogue(scene)
        self.assertEqual(self.progress.completed, ("forms",))
        self.assertTrue(scene.reward_given)
        self.assertIs(self.manager.current, self.hub)

    def test_cancel_returns_to_hub_without_reward_at_any_stage(self) -> None:
        stages = {
            "вступление": lambda scene: None,
            "исследование": lambda scene: (finish_dialogue(scene), search(scene, "requests")),
            "находка": lambda scene: (finish_dialogue(scene), stand_at(scene, CABINET["births"].point),
                                      press_e(scene)),
            "головоломка": lambda scene: (finish_dialogue(scene), find_all(scene), use_slot(scene, 2)),
            "отказ гуся": lambda scene: (finish_dialogue(scene), find_all(scene), talk_to_goose(scene)),
            "реакция": lambda scene: (finish_dialogue(scene), find_all(scene), arrange(scene), talk_to_goose(scene)),
            "присяга": lambda scene: (finish_dialogue(scene), find_all(scene), arrange(scene), talk_to_goose(scene),
                                      until_node(scene, OATH_CHOICE_ID)),
            "разрешение на получение гражданства": lambda scene: (
                finish_dialogue(scene), find_all(scene), arrange(scene), talk_to_goose(scene),
                until_node(scene, "r_stamp")),
            "финальная проверка": lambda scene: play(scene, stop_before_final_end=True),
            "гражданство": lambda scene: (play(scene, stop_before_final_end=True), until_node(scene, "f_certificate")),
            "последняя реплика": lambda scene: (play(scene, stop_before_final_end=True),
                                                until_node(scene, "f_fragment")),
        }
        for stage, prepare in stages.items():
            with self.subTest(stage=stage):
                progress = GameProgress()
                manager = SceneManager()
                manager.register(FORMS_SCENE, lambda: FormsTrialScene(progress))
                hub = manager.push(HubScene(progress))
                hub.alice.set_position(*next(portal for portal in PORTALS if portal.id == "forms").point)
                hub.interact()  # вход через верхний портал площади
                scene = manager.current
                self.assertIsInstance(scene, FormsTrialScene)
                prepare(scene)
                press(scene, pygame.K_BACKSPACE)
                self.assertIs(manager.current, hub)
                self.assertEqual(progress.completed, ())
                self.assertFalse(scene.completed)
                self.assertIn("«Формуляры» прервано", hub.toast)

    def test_second_run_gives_no_extra_fragment(self) -> None:
        play(self.scene)
        second = self.manager.push(FormsTrialScene(self.progress))
        play(second)
        self.assertTrue(second.completed)
        self.assertFalse(second.reward_given)
        self.assertEqual(self.progress.completed, ("forms",))
        self.assertEqual(self.progress.fragments, 1)

    def test_only_forms_is_marked(self) -> None:
        play(self.scene)
        self.assertTrue(self.progress.is_completed("forms"))
        self.assertFalse(self.progress.is_completed("sushi"))
        self.assertFalse(self.progress.is_completed("cakes"))
        self.assertFalse(self.progress.has_all_fragments)

    def test_sushi_stays_completed(self) -> None:
        self.progress.complete("sushi")  # как будто суши пройдены раньше (по-настоящему — в AppIntegrationTest)
        self.manager.pop()
        self.manager.register(FORMS_SCENE, lambda: FormsTrialScene(self.progress))
        self.hub.alice.set_position(*next(portal for portal in PORTALS if portal.id == "forms").point)
        self.hub.interact()
        play(self.manager.current)
        self.assertIs(self.manager.current, self.hub)
        self.assertEqual(self.progress.completed, ("sushi", "forms"))
        self.assertFalse(self.progress.is_completed("cakes"))
        self.assertIn("Теперь 2/3", self.hub.toast)
        self.assertEqual(self.hub.fragments_text(), "Фрагменты праздника: 2/3")


class LayoutTest(TrialTestCase):
    def test_dialogue_box_never_covers_characters(self) -> None:
        # Ходить можно по всей комнате, но разговор начинается только у входа, у шкафов и у гуся —
        # и где бы Алиса там ни стояла, её ноги (и гусь) выше любого окна реплики. Во время реплик
        # она не двигается.
        box = DialogueBox()
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in all_scripts() for node in script.nodes.values())
        self.assertLessEqual(SPAWN[1], lowest_box)  # вступление — у входа
        self.assertLessEqual(GOOSE_POSITION[1], lowest_box)
        scene = self.scene
        talks = 0
        for x in range(WALK_BOUNDS.left, WALK_BOUNDS.right + 1):
            for y in range(WALK_BOUNDS.top, WALK_BOUNDS.bottom + 1):
                if not scene.collision.is_free(x, y):
                    continue
                stand_at(scene, (x, y))
                target = scene.nearby()
                if target is not None and target.kind in ("cabinet", "goose"):  # здесь E открывает реплику
                    self.assertLessEqual(y, lowest_box, (x, y))
                    talks += 1
        self.assertGreater(talks, 1000)

    def test_alice_stays_between_interface_strips(self) -> None:
        for keys in ([pygame.K_UP], [pygame.K_DOWN], [pygame.K_LEFT], [pygame.K_RIGHT, pygame.K_UP],
                     [pygame.K_RIGHT, pygame.K_DOWN]):
            scene = FormsTrialScene()
            finish_dialogue(scene)
            for code in keys:
                scene.handle_event(key(code))
            for _ in range(400):
                scene.update(DT)
                rect = scene.alice.rect
                self.assertGreaterEqual(rect.top, HUD_HEIGHT)
                self.assertLessEqual(rect.bottom, STATUS_TOP)
                self.assertGreaterEqual(rect.left, 0)
                self.assertLessEqual(rect.right, WIDTH)
                self.assertTrue(scene.collision.is_free(scene.alice.x, scene.alice.y))

    def test_everything_is_reachable_on_foot(self) -> None:
        # От входа клавишами: вверх к шкафам, вдоль всех, вниз к местам стола, затем к гусю.
        finish_dialogue(self.scene)
        scene = self.scene
        hold(scene, [pygame.K_UP], 120)
        self.assertAlmostEqual(scene.alice.y, WALK_BOUNDS.top + 6)
        reached = set()
        scene.handle_event(key(pygame.K_RIGHT))
        for _ in range(300):
            scene.update(DT)
            target = scene.nearby()
            if target is not None and target.kind == "cabinet":
                reached.add(target.section)
        scene.handle_event(key(pygame.K_RIGHT, event_type=pygame.KEYUP))
        self.assertEqual(reached, set(CABINET))
        for index, x in enumerate(SLOT_XS):
            stand_at(scene, (x, WALK_BOUNDS.top + 6))
            hold(scene, [pygame.K_DOWN], 60)  # до столешницы
            target = scene.nearby()
            self.assertEqual((target.kind, target.slot), ("slot", index))
        hold(scene, [pygame.K_UP], 10)
        hold(scene, [pygame.K_RIGHT], 150)  # над столом — к правой стене
        hold(scene, [pygame.K_DOWN], 60)
        self.assertEqual(scene.nearby().kind, "goose")

    def test_alice_keeps_a_step_from_the_goose(self) -> None:
        finish_dialogue(self.scene)
        stand_at(self.scene, (TABLE.right + 8, GOOSE_POSITION[1]))  # между столом и гусем
        self.assertTrue(self.scene.collision.is_free(self.scene.alice.x, self.scene.alice.y))
        hold(self.scene, [pygame.K_RIGHT], 90)  # упереться в гуся слева
        self.assertLessEqual(self.scene.alice.x, GOOSE_POSITION[0] - 20)  # спрайты почти не перекрываются
        self.assertEqual(self.scene.nearby().kind, "goose")  # но поговорить можно

    def test_whole_cabinet_front_is_interactive(self) -> None:
        # Шкаф шириной CABINET_WIDTH отзывается, где бы перед ним ни стояла Алиса, а не только по центру.
        half = CABINETS[0].rect.width // 2
        for cabinet in CABINETS:
            for dx in (-half + 2, -half // 2, 0, half // 2, half - 2):
                with self.subTest(cabinet=cabinet.section.id, dx=dx):
                    stand_at(self.scene, (cabinet.x + dx, cabinet.point[1]))
                    target = self.scene.nearby()
                    self.assertIsNotNone(target)
                    self.assertEqual(target.section, cabinet.section.id)

    def test_targets_do_not_overlap(self) -> None:
        for cabinet in CABINETS:
            stand_at(self.scene, cabinet.point)
            self.assertEqual(self.scene.nearby().section, cabinet.section.id)
        for index, x in enumerate(SLOT_XS):
            stand_at(self.scene, (x, SLOT_Y))
            self.assertEqual(self.scene.nearby().slot, index)
        stand_at(self.scene, ((CABINETS[0].x + CABINETS[1].x) // 2, CABINETS[0].point[1]))
        self.assertIsNone(self.scene.nearby())
        stand_at(self.scene, ((SLOT_XS[0] + SLOT_XS[1]) // 2, SLOT_Y))
        self.assertIsNone(self.scene.nearby())

    def test_texts_fit_on_screen(self) -> None:
        font = self.scene._font
        names = list(DOCUMENT_NAMES.values())
        # Верхняя строка — задача, а с документом в руках — его полное название.
        for task in ("Задача: найди документы Лео 2/3", "Задача: сложи по порядку и сдай гусю", "Документы Лео приняты",
                     "Лео — гражданин Страны Чудес", *(f"В руках: {title}" for title in DOCUMENT_TITLES.values())):
            self.assertLessEqual(font.size(task)[0], WIDTH - 8, task)
        statuses = ["Стрелки/WASD — идти   E — действие   Backspace — уйти", "Гусь-инспектор   E — спросить совета",
                    "Все документы на столе — разложи их по порядку", "Стол подачи   найдено документов: 2/3"]
        statuses += [f"«{section.name}»   E — искать" for section in SECTIONS]
        statuses += [f"Поменяла местами: {a} и {b}" for a in names for b in names]
        statuses += [f"Место 1: {name}   E — поменять местами" for name in names]
        statuses += [f"На столе подачи: {name} (2/3)" for name in names]
        for text in statuses:
            self.assertLessEqual(font.size(text)[0], WIDTH - 8, text)
        for cabinet in CABINETS:  # надпись на табличке шкафа
            self.assertLessEqual(self.scene._small_font.size(cabinet.section.label)[0], cabinet.rect.width - 8)

    def test_goose_is_drawn_from_manifest_without_mirroring(self) -> None:
        sprites = load_character_sprites(CHARACTERS_DIR / "goose_inspector")
        self.assertEqual(self.scene.goose_pose, "reject")  # «Стоять» — с табличкой отказа
        expected = pygame.transform.scale(sprites.frame("reject").image, (SPRITE_SIZE, SPRITE_SIZE))
        actual = self.scene._goose_image()
        self.assertEqual(pygame.image.tobytes(actual, "RGBA"), pygame.image.tobytes(expected, "RGBA"))
        frames = {frame.id for frame in sprites.frames}
        self.assertLessEqual(set(GOOSE_POSES.values()) | {GOOSE_IDLE_POSE}, frames)  # все позы есть в манифесте

    def test_draws_every_phase(self) -> None:
        self.scene.draw(self.canvas)
        finish_dialogue(self.scene)
        for document in CORRECT_ORDER:
            search(self.scene, SECTION_OF[document])
            self.scene.update(0.1)
            self.scene.draw(self.canvas)
        use_slot(self.scene, 0)
        self.scene.draw(self.canvas)
        use_slot(self.scene, 0)
        arrange(self.scene)
        talk_to_goose(self.scene)
        self.scene.draw(self.canvas)
        finish_dialogue(self.scene)
        self.scene.draw(self.canvas)

    def test_missing_sprites_use_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            scene = FormsTrialScene(characters_dir=Path(empty))
            scene.draw(self.canvas)
            play(scene)
            self.assertTrue(scene.completed)


class RoomTest(TrialTestCase):
    """Компактная комната: весь пол доступен, большой стол в середине, шкафы и гусь на своих местах."""

    def reachable(self) -> set[tuple[int, int]]:
        """Точки сетки с шагом 2, куда Алиса доходит ногами от входа."""
        collision = self.scene.collision
        start = SPAWN
        seen, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x + 2, y), (x - 2, y), (x, y + 2), (x, y - 2)):
                if (nx, ny) not in seen and collision.is_free(nx, ny):
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return seen

    def test_table_is_big_central_and_reachable(self) -> None:
        self.assertGreaterEqual(TABLE.width * TABLE.height, 5 * 120 * 20)  # прежний стол был 120×20
        self.assertGreaterEqual(TABLE.width, WIDTH // 2)
        self.assertLessEqual(abs(TABLE.centerx - WIDTH // 2), 2)  # посередине комнаты
        self.assertTrue(TABLE.top < (HUD_HEIGHT + STATUS_TOP) // 2 < TABLE.bottom)
        reachable = self.reachable()
        for index, x in enumerate(SLOT_XS):
            paper = slot_paper(index)
            self.assertTrue(TABLE.contains(paper), index)
            self.assertIn((x, SLOT_Y), reachable)  # за столом у каждого места можно встать
        self.assertIn(CABINETS[0].point, reachable)
        self.assertTrue(any(math.dist(point, GOOSE_POSITION) <= 24 for point in reachable))

    def test_whole_floor_is_walkable_and_nothing_is_cut_off(self) -> None:
        # Каждая свободная точка пола доступна от входа: ни отрезанных углов, ни пустой недоступной полосы.
        reachable = self.reachable()
        collision = self.scene.collision
        free = {(x, y) for x in range(SPAWN[0] % 2, WIDTH, 2) for y in range(SPAWN[1] % 2, HEIGHT, 2)
                if collision.is_free(x, y)}
        self.assertEqual(free, reachable)
        lower = [point for point in reachable if point[1] > (HUD_HEIGHT + STATUS_TOP) // 2]
        self.assertTrue(any(x < TABLE.left for x, _ in lower) and any(x > TABLE.right for x, _ in lower))
        self.assertGreaterEqual(max(y for _, y in reachable), STATUS_TOP - 6)  # пол — до самого низа комнаты
        self.assertGreaterEqual(TABLE.bottom, STATUS_TOP - 6)  # под столом нет пустой полосы
        self.assertEqual(HUD_HEIGHT, 12)  # одна строка интерфейса: комнате больше места

    def test_lower_half_is_floor_not_a_dark_strip(self) -> None:
        background = self.scene._background_plain
        for y in range((HUD_HEIGHT + STATUS_TOP) // 2, STATUS_TOP, 4):
            for x in (WALK_BOUNDS.left + 4, WALK_BOUNDS.right - 30):
                color = tuple(background.get_at((x, y)))[:3]
                self.assertNotEqual(color, (0, 0, 0), (x, y))
                self.assertGreater(sum(color), 300, (x, y))  # светлый паркет, а не тёмная полоса


class PaperTest(TrialTestCase):
    """Документы — листы примерно A4 с полными названиями: на столе, в руках и при находке."""

    def test_full_titles_are_split_logically_and_fit_the_paper(self) -> None:
        width, height = PAPER_SIZE
        self.assertTrue(1.25 <= height / width <= 1.5)  # вертикальный лист, почти A4
        self.assertGreaterEqual(width, 44)
        for document, lines in PAPER_TITLE_LINES.items():
            with self.subTest(document=document):
                self.assertEqual(" ".join(lines), DOCUMENT_TITLES[document])  # целиком, ни одного сокращения
                for line in lines[:-1]:
                    self.assertNotIn(line.split()[-1], ("о", "и", "на", "в"))  # предлог не висит в конце строки
        fonts = {"системный": TextFonts(), "встроенный": TextFonts(None)}
        for name, font_set in fonts.items():
            for size, paper in ((PAPER_TITLE_SIZE, slot_paper(0)), (PREVIEW_TITLE_SIZE, self.scene.preview_rect())):
                for document in DOCUMENTS:
                    layout = paper_title_layout(paper, document, size)
                    for text, (x, y) in layout:
                        with self.subTest(font=name, size=size, text=text):
                            for scale in (3, 6):
                                line_width = font_set.font(size, scale, False).size(text)[0] / scale
                                self.assertLessEqual(x + line_width / 2, paper.right - 3)  # не обрезано справа
                                self.assertGreaterEqual(x - line_width / 2, paper.left + 3)  # и слева
                            self.assertLessEqual(y + size, paper.bottom - 12)  # под названием — строки бланка

    def test_titles_on_the_table_are_full_and_readable(self) -> None:
        finish_dialogue(self.scene)
        find_all(self.scene)
        texts = drawn_texts(self.scene)
        for document in DOCUMENTS:
            lines = [c for c in texts if c.text in PAPER_TITLE_LINES[document] and c.style.size == PAPER_TITLE_SIZE
                     and c.style.color == DOCUMENT_COLORS[document]]
            self.assertEqual(len(lines), len(PAPER_TITLE_LINES[document]), document)
        self.assertGreaterEqual(PAPER_TITLE_SIZE, 5)  # в окне 960×540 — не меньше 15 пикселей
        self.assertEqual(table_titles(self.scene), [DOCUMENT_TITLES[d] for d in ("filing_permit", "leo_application",
                                                                                  "form_request")])

    def test_found_document_is_shown_big_while_alice_talks_about_it(self) -> None:
        finish_dialogue(self.scene)
        box = DialogueBox()
        for document in CORRECT_ORDER:
            with self.subTest(document=document):
                stand_at(self.scene, CABINET[SECTION_OF[document]].point)
                press_e(self.scene)
                self.assertEqual(self.scene.found_document, document)
                preview = self.scene.preview_rect()
                titles = paper_titles(self.scene, PREVIEW_TITLE_SIZE)
                self.assertEqual(" ".join(c.text for c in titles), DOCUMENT_TITLES[document])
                self.assertTrue(all(preview.collidepoint(c.pos) for c in titles))
                self.assertGreater(preview.width, PAPER_SIZE[0])  # крупнее листа на столе
                self.assertFalse(preview.colliderect(self.scene.alice.rect))  # Алису не закрывает
                self.assertGreaterEqual(preview.top, HUD_HEIGHT)
                node = self.scene.dialogue.node
                layout = box.layout(node, hires=True)
                self.assertLessEqual(preview.bottom, (layout.name_tab or layout.box).top)  # над окном реплики
                finish_dialogue(self.scene)
                self.assertIsNone(self.scene.found_document)  # рассмотрела — лист лёг на стол
                self.assertFalse(paper_titles(self.scene, PREVIEW_TITLE_SIZE))
        search(self.scene, "births")  # повторный поиск — без находки и без листа
        self.assertIsNone(self.scene.found_document)

    def test_held_document_is_the_same_paper_and_named_in_full(self) -> None:
        finish_dialogue(self.scene)
        find_all(self.scene)
        use_slot(self.scene, 1)
        held = self.scene.puzzle.held
        self.scene.draw(self.canvas)
        x, y = self.scene.held_icon_center()
        colors = {tuple(self.canvas.get_at((px, py)))[:3] for px in range(x - 6, x + 6) for py in range(y - 9, y + 9)}
        self.assertIn(PAPER_COLOR, colors)
        self.assertIn(DOCUMENT_COLORS[held], colors)  # цветная шапка того же бланка
        hud = [c.text for c in drawn_texts(self.scene) if c.style == HUD_STYLE and c.pos[1] < HUD_HEIGHT]
        self.assertEqual(hud, [f"В руках: {DOCUMENT_TITLES[held]}"])

    def test_no_abbreviations_anywhere_in_a_full_run(self) -> None:
        scene = self.scene
        seen = set()
        original = scene.draw

        def record(surface, hires=None):
            layer = HiResLayer()
            original(surface, layer)
            seen.update(c.text for c in layer.commands if isinstance(c, TextCommand))

        scene.draw = record
        finish_dialogue(scene)
        for document in CORRECT_ORDER:
            stand_at(scene, CABINET[SECTION_OF[document]].point)
            press_e(scene)
            scene.draw(self.canvas)
            finish_dialogue(scene)
            scene.draw(self.canvas)
        use_slot(scene, 2)
        scene.draw(self.canvas)
        use_slot(scene, 0)
        scene.draw(self.canvas)
        for text in seen:
            for short in ("ЗВБЗ", "РПЗ", "ЗРГЛ", "Заявл.", "Разр."):
                self.assertNotIn(short, text)
        self.assertTrue(seen)


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
        hub.alice.set_position(*next(portal for portal in PORTALS if portal.id == trial_id).point)
        self.press(pygame.K_e, pygame.KSCAN_E)
        return self.app.scenes.current

    def test_forms_trial_is_registered_next_to_the_others(self) -> None:
        self.assertEqual(FORMS_SCENE, "trial_forms")
        self.assertEqual(FORMS_SCENE, TRIAL_SCENES["forms"])
        self.assertTrue(self.app.scenes.is_registered(FORMS_SCENE))
        self.assertTrue(self.app.scenes.is_registered(TRIAL_SCENES["sushi"]))
        self.assertTrue(self.app.scenes.is_registered(TRIAL_SCENES["cakes"]))  # торты — третье испытание
        hub = self.open_hub()
        cakes = self.enter_portal(hub, "cakes")
        self.assertIsNot(cakes, hub)
        self.assertNotIsInstance(cakes, FormsTrialScene)  # правый портал ведёт не в архив

    def test_upper_portal_opens_forms_and_success_returns_to_the_same_hub(self) -> None:
        hub = self.open_hub()
        trial = self.enter_portal(hub, "forms")
        self.assertIsInstance(trial, FormsTrialScene)
        self.assertIs(trial.progress, self.app.progress)
        self.assertEqual([type(scene).__name__ for scene in self.app.scenes.stack],
                         ["DebugScreen", "HubScene", "FormsTrialScene"])
        play(trial)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 1/3")
        self.assertIn("Получен фрагмент праздника! Теперь 1/3", hub.toast)
        self.assertIn("Формуляры (пройдено)", hub.nearby().prompt)
        hub.draw(self.app.display.canvas)

    def test_after_sushi_the_counter_shows_two_of_three(self) -> None:
        hub = self.open_hub()
        sushi = self.enter_portal(hub, "sushi")
        self.assertIsInstance(sushi, SushiTrialScene)
        finish_dialogue(sushi)  # пройти суши по-настоящему, теми же клавишами
        stations = {station.ingredient: station for station in STATIONS}
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                sushi.alice.set_position(*stations[ingredient].point)
                press_e(sushi)
                sushi.alice.set_position(SUSHI_TABLE.centerx, SUSHI_TABLE.top - 2)
                press_e(sushi)
            finish_dialogue(sushi)
        finish_dialogue(sushi)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 1/3")
        play(self.enter_portal(hub, "forms"))
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 2/3")
        self.assertIn("Теперь 2/3", hub.toast)
        self.assertEqual(self.app.progress.completed, ("sushi", "forms"))
        self.assertFalse(self.app.progress.is_completed("cakes"))

    def test_cancel_from_portal_gives_nothing(self) -> None:
        hub = self.open_hub()
        self.enter_portal(hub, "forms")
        self.press(pygame.K_BACKSPACE)
        self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.fragments, 0)
        self.assertIn("прервано", hub.toast)
        self.assertNotIn("(пройдено)", hub.nearby().prompt)

    def test_replay_from_portal_keeps_one_fragment(self) -> None:
        hub = self.open_hub()
        for _ in range(2):
            trial = self.enter_portal(hub, "forms")
            self.assertIsInstance(trial, FormsTrialScene)
            self.assertEqual(trial.puzzle.found, [])  # каждый заход — архив заново
            play(trial)
            self.assertIs(self.app.scenes.current, hub)
        self.assertEqual(self.app.progress.fragments, 1)
        self.assertIn("уже пройдено", hub.toast)

    def test_escape_f11_and_close_inside_trial(self) -> None:
        self.enter_portal(self.open_hub(), "forms")
        self.app.running = True
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.assertIsInstance(self.app.scenes.current, FormsTrialScene)
        self.app.scenes.update(0.2)
        self.app.scenes.draw(self.app.display.canvas)
        self.app.display.present()
        self.press(pygame.K_F11)
        self.press(pygame.K_ESCAPE)  # ESC — выход из игры, а не отмена испытания
        self.assertFalse(self.app.running)
        self.assertIsInstance(self.app.scenes.current, FormsTrialScene)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)

    def test_keys_go_through_the_app(self) -> None:
        trial = self.enter_portal(self.open_hub(), "forms")
        self.press(pygame.K_RETURN)
        self.press(pygame.K_RETURN)
        self.assertEqual(trial.dialogue.node.id, "i_here")  # Enter листает вступление
        for _ in range(2 * len(INTRO.nodes)):  # каждая реплика: дописать и дальше
            self.press(pygame.K_e, pygame.KSCAN_E)
        self.assertIsNone(trial.dialogue)
        self.assertEqual(trial.phase, EXPLORE)
        trial.alice.set_position(*CABINET["requests"].point)
        self.press(ord("у"), pygame.KSCAN_E)  # русская раскладка: та же физическая клавиша
        self.assertEqual(trial.puzzle.found, ["form_request"])
        self.assertTrue(trial.dialogue.is_typing)
        # Зажатая E: первое нажатие дописывает реплику, автоповтор её не закрывает.
        self.send(key(pygame.K_e, pygame.KSCAN_E), key(pygame.K_e, pygame.KSCAN_E), key(pygame.K_e, pygame.KSCAN_E))
        self.assertIsNotNone(trial.dialogue)
        self.assertFalse(trial.dialogue.is_typing)


if __name__ == "__main__":
    unittest.main()
