"""Проверки сцены испытания формуляров: поиск, раскладка, награда, отмена, переходы с площади."""

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
from game.story.forms_dialogue import (  # noqa: E402
    FINAL,
    GOOSE,
    GOOSE_IDLE_POSE,
    GOOSE_POSES,
    INSPECTION,
    INTRO,
    all_scripts,
)
from game.story.intro_dialogue import ALICE  # noqa: E402
from game.trials.forms_puzzle import CORRECT_ORDER, DOCUMENT_NAMES, SECTIONS  # noqa: E402
from game.trials.forms_scene import (  # noqa: E402
    CABINETS,
    DONE,
    EXPLORE,
    FINAL_PHASE,
    FORMS_SCENE,
    GOOSE_POSITION,
    HUD_HEIGHT,
    INTRO_PHASE,
    PAPER_COLOR,
    REACTION,
    SLOT_XS,
    SLOT_Y,
    SPAWN,
    SPRITE_SIZE,
    STATUS_TOP,
    WALK_BOUNDS,
    FormsTrialScene,
)
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import STATIONS, TABLE as SUSHI_TABLE, SushiTrialScene  # noqa: E402
from game.world.hub import PORTALS, TRIAL_SCENES, HubScene  # noqa: E402
from game.world.progress import GameProgress  # noqa: E402

DT = 1 / 60
CABINET = {cabinet.section.id: cabinet for cabinet in CABINETS}
SECTION_OF = {section.document: section.id for section in SECTIONS if section.document}
GOOSE_SPOT = (GOOSE_POSITION[0] - 22, GOOSE_POSITION[1])  # слева от гуся, вплотную к препятствию
WIDTH = config.LOGICAL_SIZE[0]


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
    """Со «архивного» порядка (Согласование, Разрешение, Заявление) — на правильный, двумя обменами."""
    use_slot(scene, 2)
    use_slot(scene, 0)
    use_slot(scene, 2)
    use_slot(scene, 1)


def talk_to_goose(scene: FormsTrialScene) -> None:
    stand_at(scene, GOOSE_SPOT)
    press_e(scene)


def play(scene: FormsTrialScene, stop_before_final_end: bool = False) -> None:
    """Проходит испытание: вступление, поиск, раскладка, сдача, реакция, финальная проверка."""
    finish_dialogue(scene)
    find_all(scene)
    arrange(scene)
    talk_to_goose(scene)
    finish_dialogue(scene)  # реакция гуся
    if not stop_before_final_end:
        finish_dialogue(scene)  # финальная проверка


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
            (GOOSE, "Стоять. Вход в архив разрешён при наличии разрешения на вход в архив."),
            (ALICE, "Мне нужно разрешение на праздник."),
            (GOOSE, "Тогда вы пришли по адресу. Здесь хранятся все разрешения, "
                    "кроме тех, которые мы ещё не разрешили хранить."),
            (ALICE, "И где искать моё?"),
            (GOOSE, "В соответствующем отделе. Если бы я знал, где он, я бы уже давно его закрыл."),
        ])
        self.assertEqual(self.scene.phase, EXPLORE)
        self.assertEqual(self.scene.goose_pose, GOOSE_IDLE_POSE)

    def test_nothing_moves_or_is_searched_during_dialogue(self) -> None:
        stand_at(self.scene, CABINET["holidays"].point)
        self.scene.handle_event(key(pygame.K_LEFT))
        self.scene.update(1.0)
        self.assertEqual((self.scene.alice.x, self.scene.alice.y), CABINET["holidays"].point)
        self.scene.handle_event(key(pygame.K_LEFT, event_type=pygame.KEYUP))
        press_e(self.scene)  # E в реплике только листает её
        self.assertEqual(self.scene.puzzle.found, [])
        self.assertEqual(sum(self.scene.puzzle.searches.values()), 0)


class SearchTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)

    def test_cabinet_gives_document_with_a_funny_line(self) -> None:
        stand_at(self.scene, CABINET["holidays"].point)
        self.assertEqual(self.scene.status_text(), "«Праздники, которые не состоялись»   E — искать")
        press_e(self.scene)
        self.assertEqual(self.scene.dialogue.node.speaker, ALICE)
        self.assertIn("Заявление на проведение праздника", self.scene.dialogue.node.text)
        self.assertIn("не состоялся", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.puzzle.order, (None, None, "application"))
        self.assertEqual(self.scene.status_text(), "На столе подачи: Заявление (1/3)")
        self.assertEqual(self.scene.task_text(), "Задача: найди документы 1/3")
        self.assertEqual(self.scene.order_text(), "Стол: 1 — → 2 — → 3 Заявление")

    def test_each_document_is_in_its_section(self) -> None:
        texts = {document: search(self.scene, SECTION_OF[document]) for document in CORRECT_ORDER}
        self.assertIn("Заявление на проведение праздника", texts["application"])
        self.assertIn("Согласование ответственного лица", texts["approval"])
        self.assertIn("Разрешение на праздник", texts["permission"])
        self.assertTrue(self.scene.puzzle.all_found)
        self.assertEqual(self.scene.toast, "Все документы на столе — разложи их по порядку")
        self.assertEqual(self.scene.task_text(), "Задача: разложи по порядку и сдай гусю")
        self.assertEqual(self.scene.order_text(), "Стол: 1 Согласование → 2 Разрешение → 3 Заявление")

    def test_wrong_shelf_is_a_joke_without_side_effects(self) -> None:
        jokes = [search(self.scene, "cakes") for _ in range(4)]
        self.assertIn("Наполеон", jokes[0])
        self.assertEqual(len(set(jokes[:3])), 3)  # шутки разные
        self.assertEqual(jokes[3], jokes[0])  # и идут по кругу
        self.assertIn("соответствующий отдел", search(self.scene, "department"))
        self.assertEqual(self.scene.puzzle.found, [])
        self.assertEqual(self.scene.puzzle.order, (None, None, None))
        self.assertEqual(self.scene.phase, EXPLORE)
        self.assertEqual(self.scene.task_text(), "Задача: найди документы 0/3")
        x = self.scene.alice.x
        hold(self.scene, [pygame.K_RIGHT], 20)  # управление вернулось
        self.assertGreater(self.scene.alice.x, x)

    def test_repeated_search_creates_no_extra_documents(self) -> None:
        first = search(self.scene, "permits")
        again = [search(self.scene, "permits") for _ in range(2)]
        self.assertIn("Разрешение на праздник", first)
        self.assertNotIn("Разрешение на праздник", again[0])  # там больше ничего нужного
        self.assertEqual(self.scene.puzzle.found, ["permission"])
        self.assertEqual(self.scene.puzzle.order.count("permission"), 1)
        self.assertEqual(self.scene.task_text(), "Задача: найди документы 1/3")

    def test_goose_hints_on_repeated_visits(self) -> None:
        talk_to_goose(self.scene)
        self.assertIn("заявления", self.scene.dialogue.node.text)
        self.assertEqual(self.scene.goose_pose, GOOSE_POSES["hint"])
        finish_dialogue(self.scene)
        talk_to_goose(self.scene)  # повторно — та же подсказка, ничего не сломалось
        self.assertIn("заявления", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        search(self.scene, "holidays")
        stand_at(self.scene, GOOSE_SPOT)
        self.scene.update(2.0)  # сообщение о находке уже не важнее подсказки
        self.assertEqual(self.scene.status_text(), "Гусь-инспектор   E — спросить совета")
        press_e(self.scene)
        self.assertIn("согласования", self.scene.dialogue.node.text)  # подсказка про следующий документ
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.puzzle.failed_checks, 0)
        self.assertEqual(self.scene.phase, EXPLORE)

    def test_table_waits_for_all_documents(self) -> None:
        search(self.scene, "holidays")
        search(self.scene, "requests")
        stand_at(self.scene, (SLOT_XS[0], SLOT_Y))
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Стол подачи   найдено документов: 2/3")
        press_e(self.scene)
        self.assertIsNone(self.scene.puzzle.held)
        self.assertEqual(self.scene.status_text(), "Сначала найди все документы: 2/3")
        self.assertEqual(self.scene.puzzle.order, ("approval", None, "application"))


class TableTest(TrialTestCase):
    def setUp(self) -> None:
        super().setUp()
        finish_dialogue(self.scene)
        find_all(self.scene)

    def test_take_put_back_and_swap_are_shown(self) -> None:
        stand_at(self.scene, (SLOT_XS[0], SLOT_Y))
        self.assertEqual(self.scene.status_text(), "Все документы на столе — разложи их по порядку")  # свежее
        self.scene.update(2.0)  # сообщение о находке уже не важнее подсказки
        self.assertEqual(self.scene.status_text(), "Место 1: Согласование   E — взять")
        press_e(self.scene)
        self.assertEqual(self.scene.held_text(), "В руках: Согласование")
        self.assertEqual(self.scene.status_text(), "Взяла: Согласование")
        self.assertEqual(self.scene.order_text(), "Стол: 1 — → 2 Разрешение → 3 Заявление")
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Место 1   E — положить обратно")
        press_e(self.scene)
        self.assertEqual(self.scene.held_text(), "")
        self.assertEqual(self.scene.status_text(), "Положила обратно: Согласование")
        use_slot(self.scene, 2)
        stand_at(self.scene, (SLOT_XS[0], SLOT_Y))
        self.scene.update(2.0)
        self.assertEqual(self.scene.status_text(), "Место 1: Согласование   E — поменять местами")
        press_e(self.scene)
        self.assertEqual(self.scene.status_text(), "Поменяла местами: Заявление и Согласование")
        self.assertEqual(self.scene.order_text(), "Стол: 1 Заявление → 2 Разрешение → 3 Согласование")

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
        self.assertEqual(self.scene.puzzle.order, ("approval", "permission", "application"))  # стол не тронут
        use_slot(self.scene, 2)
        use_slot(self.scene, 0)  # заявление — первым, остальное ещё перепутано
        talk_to_goose(self.scene)
        self.assertIn("Снова отказано", self.scene.dialogue.node.text)  # вторая попытка — другая шутка
        press(self.scene, pygame.K_RETURN)
        press(self.scene, pygame.K_RETURN)
        self.assertIn("согласование идёт раньше разрешения", self.scene.dialogue.node.text)
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
        self.assertEqual(self.scene.puzzle.held, "approval")
        self.assertEqual(self.scene.puzzle.failed_checks, 0)
        self.assertEqual(self.scene.phase, EXPLORE)
        use_slot(self.scene, 1)
        talk_to_goose(self.scene)
        self.assertEqual(self.scene.phase, REACTION)

    def test_held_document_floats_above_alice(self) -> None:
        use_slot(self.scene, 0)
        for spot in ((SLOT_XS[0], SLOT_Y), CABINET["permits"].point, (WALK_BOUNDS.right - 6, 100)):
            stand_at(self.scene, spot)
            self.scene.update(0.25)  # значок не «подпрыгивает»
            self.scene.draw(self.canvas)
            x, y = self.scene.held_icon_center()
            self.assertGreaterEqual(y - 6, HUD_HEIGHT)  # не под полосой интерфейса
            self.assertLessEqual(x + 13, WIDTH)  # и не за краем экрана
            self.assertEqual(tuple(self.canvas.get_at((x - 12, y)))[:3], PAPER_COLOR)  # левый край карточки

    def test_reaction_then_final_check(self) -> None:
        arrange(self.scene)
        talk_to_goose(self.scene)
        self.assertEqual(self.scene.goose_pose, "inspect")
        shown = finish_dialogue(self.scene)
        self.assertEqual(shown, ["r_inspect", "r_stamp", "r_approve"])
        self.assertEqual(self.scene.phase, FINAL_PHASE)
        self.assertIs(self.scene.dialogue.script, FINAL)
        self.assertEqual(self.scene.task_text(), "Документы приняты")
        texts = [FINAL.nodes[node_id].text for node_id in finish_dialogue(self.scene)]
        self.assertEqual(texts[:3], [
            "Заявление подано, согласование получено, разрешение разрешено. Формально праздник существует.",
            "А праздновать уже можно?",
            "Не торопитесь. На это потребуется отдельное разрешение.",
        ])

    def test_table_is_locked_after_acceptance(self) -> None:
        arrange(self.scene)
        talk_to_goose(self.scene)
        press(self.scene, pygame.K_RIGHT)  # во время реакции Алиса стоит
        use_slot(self.scene, 0)
        self.assertIsNone(self.scene.puzzle.held)
        self.assertEqual(self.scene.puzzle.order, CORRECT_ORDER)


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

    def test_cancel_returns_to_hub_without_reward_at_any_stage(self) -> None:
        stages = {
            "вступление": lambda scene: None,
            "исследование": lambda scene: (finish_dialogue(scene), search(scene, "holidays")),
            "находка": lambda scene: (finish_dialogue(scene), stand_at(scene, CABINET["permits"].point),
                                      press_e(scene)),
            "головоломка": lambda scene: (finish_dialogue(scene), find_all(scene), use_slot(scene, 2)),
            "отказ гуся": lambda scene: (finish_dialogue(scene), find_all(scene), talk_to_goose(scene)),
            "реакция": lambda scene: (finish_dialogue(scene), find_all(scene), arrange(scene), talk_to_goose(scene)),
            "финальная проверка": lambda scene: play(scene, stop_before_final_end=True),
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
        box = DialogueBox()
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in all_scripts() for node in script.nodes.values())
        self.assertLessEqual(WALK_BOUNDS.bottom, lowest_box)  # ноги Алисы всегда выше окна
        self.assertLessEqual(GOOSE_POSITION[1], lowest_box)

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
        stand_at(self.scene, (230, GOOSE_POSITION[1]))
        hold(self.scene, [pygame.K_RIGHT], 90)  # упереться в гуся слева
        self.assertLessEqual(self.scene.alice.x, GOOSE_POSITION[0] - 20)  # спрайты почти не перекрываются
        self.assertEqual(self.scene.nearby().kind, "goose")  # но поговорить можно

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
        widest_held = max(font.size(f"В руках: {name}")[0] for name in names)
        for task in ("Задача: найди документы 2/3", "Задача: разложи по порядку и сдай гусю", "Документы приняты"):
            self.assertLessEqual(font.size(task)[0] + widest_held, WIDTH - 16, task)
        order = "Стол: 1 Согласование → 2 Согласование → 3 Согласование"
        self.assertLessEqual(font.size(order)[0], WIDTH - 8)
        statuses = ["Стрелки/WASD — идти   E — действие   Backspace — уйти", "Гусь-инспектор   E — спросить совета",
                    "Все документы на столе — разложи их по порядку", "Стол подачи   найдено документов: 2/3"]
        statuses += [f"«{section.name}»   E — искать" for section in SECTIONS]
        statuses += [f"Поменяла местами: {a} и {b}" for a in names for b in names]
        statuses += [f"Место 1: {name}   E — поменять местами" for name in names]
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

    def open_hub(self) -> HubScene:
        self.press(pygame.K_h, pygame.KSCAN_H)
        return self.app.scenes.current

    def enter_portal(self, hub: HubScene, trial_id: str) -> Scene:
        hub.alice.set_position(*next(portal for portal in PORTALS if portal.id == trial_id).point)
        self.press(pygame.K_e, pygame.KSCAN_E)
        return self.app.scenes.current

    def test_forms_trial_is_registered_and_cakes_still_closed(self) -> None:
        self.assertEqual(FORMS_SCENE, "trial_forms")
        self.assertEqual(FORMS_SCENE, TRIAL_SCENES["forms"])
        self.assertTrue(self.app.scenes.is_registered(FORMS_SCENE))
        self.assertTrue(self.app.scenes.is_registered(TRIAL_SCENES["sushi"]))
        self.assertFalse(self.app.scenes.is_registered(TRIAL_SCENES["cakes"]))
        hub = self.open_hub()
        self.assertIs(self.enter_portal(hub, "cakes"), hub)
        self.assertIn("не готов", hub.dialogue.node.text)

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
        self.assertEqual(trial.dialogue.node.id, "i_need")  # Enter листает вступление
        for _ in range(2 * len(INTRO.nodes)):  # каждая реплика: дописать и дальше
            self.press(pygame.K_e, pygame.KSCAN_E)
        self.assertIsNone(trial.dialogue)
        self.assertEqual(trial.phase, EXPLORE)
        trial.alice.set_position(*CABINET["holidays"].point)
        self.press(ord("у"), pygame.KSCAN_E)  # русская раскладка: та же физическая клавиша
        self.assertEqual(trial.puzzle.found, ["application"])
        self.assertTrue(trial.dialogue.is_typing)
        # Зажатая E: первое нажатие дописывает реплику, автоповтор её не закрывает.
        self.send(key(pygame.K_e, pygame.KSCAN_E), key(pygame.K_e, pygame.KSCAN_E), key(pygame.K_e, pygame.KSCAN_E))
        self.assertIsNotNone(trial.dialogue)
        self.assertFalse(trial.dialogue.is_typing)


if __name__ == "__main__":
    unittest.main()
