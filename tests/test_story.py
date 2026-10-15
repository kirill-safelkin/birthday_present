"""Проверки сюжета праздника: цель приключения, Лео в истории, выборы в диалогах и их ветки."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import hashlib  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.dialogue.model import DialogueScript  # noqa: E402
from game.graphics.hires import HiResLayer, SpriteCommand  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story import (  # noqa: E402
    cakes_dialogue,
    final_dialogue,
    forms_dialogue,
    hub_dialogue,
    intro_dialogue,
    sushi_dialogue,
)
from game.story.final_scene import (  # noqa: E402
    ALICE_POSITION,
    CHUCHMEK_POSITION,
    LEO_POSITION,
    LEO_SIZE,
    LETTER,
    PAUSE,
    SPRITE_SIZE as FINALE_SPRITE_SIZE,
    FinalScene,
)
from game.story.intro_dialogue import BEATS, Cue, Lines  # noqa: E402
from game.trials import cakes_scene, forms_scene, sushi_scene  # noqa: E402
from game.trials.cakes_puzzle import CakeRecipe  # noqa: E402
from game.trials.forms_puzzle import FormsPuzzle  # noqa: E402
from game.trials.sushi_orders import SushiOrders  # noqa: E402
from game.world.progress import TRIALS, GameProgress  # noqa: E402

# Главные разговоры с выбором Алисы: сценарий, реплика-вопрос и реплики, которые игрок
# видит при любом ответе (главная информация разговора), — последняя из них завершает разговор.
CONVERSATIONS = {
    "вступление: праздничный план": (
        intro_dialogue.PART_D_PLAN,
        intro_dialogue.ORGANIZER_CHOICE_ID,
        ("d_yours", "d_plan", "d_disaster", "d_pieces", "d_now", "d_trials", "d_mosaic", "d_inside", "d_intrigue",
         "d_why_me", "d_tried", "d_only_you", "d_leo", "d_leo_job", "d_leo_smile"),
    ),
    "вступление: последний вопрос": (intro_dialogue.PART_E_CHOICE, intro_dialogue.CHOICE_ID, ("e_ready",)),
    "площадь: первый разговор": (
        hub_dialogue.CHUCHMEK_TALK, hub_dialogue.HUB_CHOICE_ID, ("h_welcome", hub_dialogue.HUB_JOIN_ID, "h_mosaic"),
    ),
    "площадь: снова": (hub_dialogue.CHUCHMEK_TALK_AGAIN, "h_again", (hub_dialogue.HUB_JOIN_ID, "h_mosaic")),
    "суши": (
        sushi_dialogue.INTRO, sushi_dialogue.TRUST_CHOICE_ID, ("s_welcome", "s_tasty", "s_rules", "s_forgives"),
    ),
    "формуляры": (
        forms_dialogue.INTRO, forms_dialogue.REGISTER_CHOICE_ID,
        ("i_stop", "i_registry", "i_first", "i_procedure", "i_table", "i_order"),
    ),
    "формуляры: приём документов": (
        forms_dialogue.INSPECTION, forms_dialogue.OATH_CHOICE_ID,
        ("r_oath_intro", "r_inspect", "r_almost", "r_different", "r_stamp", "r_approve"),
    ),
    "торты": (
        cakes_dialogue.INTRO, cakes_dialogue.CHECK_CHOICE_ID, ("i_ready", "i_reversed", "i_backwards", "i_fix"),
    ),
    "торты: Тортище": (
        cakes_dialogue.GREAT_CAKE_TALK,
        cakes_dialogue.EVENT_CHOICE_ID,
        ("g_halt", "g_me", "g_finally", "g_who", cakes_dialogue.EVENT_CHOICE_ID, "g_watch"),
    ),
    "финал": (
        final_dialogue.FINALE_TALK, final_dialogue.CREDIT_CHOICE_ID,
        ("f_restored", "f_documents", "f_commission", "f_verdict", "f_backside"),
    ),
}
# Что внутри испытаний: Чучмек не называет этого ни во вступлении, ни на площади — игрок узнаёт
# в самом портале. Слова целиком или с окончаниями («кот», но не «который»).
TRIAL_SPOILERS = re.compile(
    r"\b(суши|ролл\w*|кот|кота|повар\w*|кухн\w*|формуляр\w*|архив\w*|гус\w*|регистрац\w*|гражданств\w*|"
    r"бланк\w*|торт\w*|кондитер\w*|клубник\w*|рецепт\w*|вкусн\w*|официальн\w*|сладк\w*)\b",
    re.IGNORECASE,
)

# Тексты письма, секрета подарка, реакции на F-17, титров и последнего экрана — как в коммите
# до этого этапа (5bdfc28…f9e55d9). Сумма меняется только при правке самих текстов.
LETTER_SHA256 = "fb2685c46c8af91e2d29cb0895982850769be76dfed72901cda9a9dfba0307aa"


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press(scene, code: int, scancode: int = 0) -> None:
    scene.handle_event(key(code, scancode))
    scene.handle_event(key(code, scancode, pygame.KEYUP))


def paths(script: DialogueScript) -> list[list[str]]:
    """Все пути по сценарию от первой реплики до последней. Цикл — провал теста."""
    found: list[list[str]] = []

    def walk(node_id: str, path: list[str]) -> None:
        if node_id in path:
            raise AssertionError(f"в сценарии цикл: {[*path, node_id]}")
        path = [*path, node_id]
        targets = script.nodes[node_id].targets
        if not targets:
            found.append(path)
        for target in targets:
            walk(target, path)

    walk(script.start_id, [])
    return found


def story_scripts() -> list[DialogueScript]:
    """Все сценарии сюжета, включая собранные по ходу игры."""
    scripts = []
    for module in (intro_dialogue, hub_dialogue, sushi_dialogue, forms_dialogue, cakes_dialogue, final_dialogue):
        scripts += module.all_scripts()
    return scripts


def answer_dialogue(scene, answer: int) -> list[str]:
    """Пролистывает текущий диалог сцены E, как игрок; на вопросе — ↓ до ответа номер answer."""
    script = scene.dialogue.script
    shown = []
    for _ in range(200):
        dialogue = scene.dialogue
        if dialogue is None or dialogue.script is not script:
            return shown
        if not shown or shown[-1] != dialogue.node.id:
            shown.append(dialogue.node.id)
        if dialogue.choices:
            for _ in range(answer):
                press(scene, pygame.K_DOWN)
        press(scene, pygame.K_e, pygame.KSCAN_E)
    raise AssertionError(f"диалог не заканчивается: {shown}")


class PygameTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def tearDown(self) -> None:
        pygame.quit()


class BirthdayGoalTest(unittest.TestCase):
    def test_birthday_plan_starts_only_after_chuchmek_appears(self) -> None:
        emerge = next(i for i, beat in enumerate(BEATS) if isinstance(beat, Cue) and beat.name == "chuchmek_emerges")
        self.assertEqual(BEATS[0].name, "title_card")  # сказка по-прежнему начинается с «Алисы в стране чудес»
        early = " ".join(node.text.lower() for beat in BEATS[:emerge] if isinstance(beat, Lines)
                         for node in beat.script.nodes.values())
        for word in ("праздни", "день рождения", "лео", "фрагмент", "именинниц"):
            self.assertNotIn(word, early)
        plan = next(i for i, beat in enumerate(BEATS) if isinstance(beat, Lines)
                    and beat.script is intro_dialogue.PART_D_PLAN)
        self.assertGreater(plan, emerge)

    def test_every_path_explains_the_birthday_and_the_three_fragments(self) -> None:
        for path in paths(intro_dialogue.PART_D_PLAN):
            with self.subTest(path=path):
                text = " ".join(intro_dialogue.PART_D_PLAN.nodes[node_id].text for node_id in path)
                for words in ("твой день рождения", "готовит тебе праздник", "организатор", "праздничный план",
                              "разлетелся на три фрагмента", "Три испытания — три фрагмента", "устроим твой праздник",
                              "на мозаике посреди площади", "Открыть её сможешь только ты",
                              "главным инспектором праздничного настроения", "сохранять интригу"):
                    self.assertIn(words, text)
                self.assertTrue("назначил себя" in text or "Я сам" in text)  # организатор самоназначенный
        # Ни новых целей, ни лишних фрагментов: только три.
        whole = " ".join(node.text for script in intro_dialogue.all_scripts() for node in script.nodes.values())
        self.assertNotRegex(whole.lower(), r"(четыр|пят)\w* (фрагмент|испытан)")

    def test_trials_are_not_revealed_before_their_portals(self) -> None:
        emerge = next(i for i, beat in enumerate(BEATS) if isinstance(beat, Cue) and beat.name == "chuchmek_emerges")
        intro = [node for beat in BEATS[emerge:] if isinstance(beat, Lines) for node in beat.script.nodes.values()]
        hub = list(hub_dialogue.CHUCHMEK_TALK.nodes.values())  # у неготовых порталов — свои сообщения
        self.assertGreater(len(intro), 30)
        for node in (*intro, *hub):
            with self.subTest(node=node.id):
                self.assertIsNone(TRIAL_SPOILERS.search(node.text), node.text)
                for choice in node.choices or ():
                    self.assertIsNone(TRIAL_SPOILERS.search(choice.text), choice.text)
        self.assertIsNotNone(TRIAL_SPOILERS.search("Кот-повар, торт и гусь"))  # сам фильтр работает
        self.assertIsNone(TRIAL_SPOILERS.search("который готовит праздник"))
        # Что внутри, Алиса узнаёт в самих испытаниях.
        self.assertIn("вкусная часть праздника", sushi_dialogue.INTRO.nodes["s_tasty"].text)
        self.assertIn("вкусную часть праздника", sushi_dialogue.FINAL.nodes["f_fragment"].text)
        self.assertIn("Для подготовки праздника", forms_dialogue.INTRO.nodes["i_stop"].text)
        self.assertIn("фрагмент праздничного плана", forms_dialogue.FINAL.nodes["f_fragment"].text)
        self.assertIn("Сладкая часть праздника", cakes_dialogue.INTRO.nodes[cakes_dialogue.CHECK_CHOICE_ID].text)
        self.assertIn("сладкую часть праздника", cakes_dialogue.FINAL.nodes["f_fragment"].text)

    def test_forms_trial_registers_leo_in_wonderland(self) -> None:
        intro = " ".join(node.text for node in forms_dialogue.INTRO.nodes.values())
        for words in ("реестр участников", "Лео не значится", "ни рождения, ни гражданства",
                      "Присутствие не заменяет регистрацию"):
            self.assertIn(words, intro)
        inspection = forms_dialogue.INSPECTION.nodes
        self.assertIn("разрешение на получение гражданства", inspection["r_almost"].text)
        self.assertIn("Разрешение на получение гражданства Лео", inspection["r_stamp"].text)
        final = forms_dialogue.FINAL.nodes
        self.assertIn("Лео признан гражданином Страны Чудес", final["f_decree"].text)
        self.assertIn("Рождение Лео зарегистрировано", final["f_certificate"].text)
        # Сказочная бюрократия, а не настоящие правила какой-либо страны.
        everything = " ".join(node.text for script in forms_dialogue.all_scripts() for node in script.nodes.values())
        for real in ("Герман", "немецк", "закон", "ведомств", "паспорт"):
            self.assertNotIn(real, everything)

    def test_chuchmek_explains_why_alice_goes_herself(self) -> None:
        nodes = intro_dialogue.PART_D_PLAN.nodes
        self.assertEqual(nodes["d_why_me"].speaker, intro_dialogue.ALICE)
        self.assertIn("Я пробовал сам", nodes["d_tried"].text)
        self.assertIn("только именинница знает", nodes["d_only_you"].text)

    def test_leo_is_part_of_the_story_and_only_babbles(self) -> None:
        # Лео — младенец: взрослых фраз у него нет нигде. Его голос — только короткие звуки
        # у корзинки на площади («*сопит*», «Хи-хи!», «Агу-агу!»).
        sounds = {text for texts in hub_dialogue.LEO_SOUNDS.values() for text in texts}
        leo_lines = [node for script in story_scripts() for node in script.nodes.values() if node.speaker == "Лео"]
        self.assertEqual({node.text for node in leo_lines}, sounds)
        for node in leo_lines:
            self.assertEqual(node.id, "leo")  # реплика у корзинки, а не в сюжетных разговорах
            self.assertLessEqual(len(node.text.split()), 3, node.text)
        mentions = [node for script in story_scripts() for node in script.nodes.values() if "Лео" in node.text]
        self.assertTrue(any(node.id == "d_leo" for node in mentions))  # вступление
        self.assertTrue(any(node.id == "h_leo" for node in mentions))  # площадь
        self.assertTrue(any(node.id == "f_decree" for node in mentions))  # формуляры: его гражданство
        self.assertTrue(any(node.id == "f_verdict" for node in mentions))  # финал
        for node in final_dialogue.FINALE_TALK.nodes.values():
            self.assertNotIn("подар", node.text.lower())  # про настоящий подарок здесь ни слова


class DialogueChoicesTest(unittest.TestCase):
    def test_every_story_dialogue_is_finite(self) -> None:
        for script in story_scripts():
            for path in paths(script):
                self.assertFalse(script.nodes[path[-1]].targets)

    def test_major_conversations_have_one_question_with_two_answers(self) -> None:
        for name, (script, question, _) in CONVERSATIONS.items():
            with self.subTest(name):
                questions = {node_id for path in paths(script) for node_id in path if script.nodes[node_id].choices}
                self.assertEqual(questions, {question})
                self.assertEqual(len(script.nodes[question].choices), 2)

    def test_letter_gift_and_credits_have_no_choices(self) -> None:
        self.assertFalse(any(node.choices for node in final_dialogue.GIFT_REACTION.nodes.values()))
        for page in (*final_dialogue.LETTER_PAGES, final_dialogue.GIFT_TEXT):
            self.assertIsInstance(page, str)

    def test_answers_have_own_lines_then_return_to_the_common_story(self) -> None:
        for name, (script, question, _) in CONVERSATIONS.items():
            with self.subTest(name):
                nodes = script.nodes
                choices = nodes[question].choices
                self.assertNotEqual(nodes[choices[0].next_id].text, nodes[choices[1].next_id].text)
                self.assertNotEqual(choices[0].text, choices[1].text)
                tails = {}
                for choice in choices:
                    sub = DialogueScript(choice.next_id, nodes.values())
                    (tail,) = paths(sub)  # после ответа — одна дорога, без новых развилок
                    tails[choice.next_id] = tail
                first, second = tails.values()
                join = next(node_id for node_id in first if node_id in second)
                own_first, own_second = first[: first.index(join)], second[: second.index(join)]
                self.assertFalse(set(own_first) & set(own_second))  # у каждого ответа свои реплики
                for own in (own_first, own_second):
                    self.assertTrue(1 <= len(own) <= 3, own)  # ветка — пара коротких реплик, не второй разговор
                self.assertEqual(first[first.index(join):], second[second.index(join):])  # и общая дорога дальше

    def test_main_information_is_on_every_path(self) -> None:
        for name, (script, _, required) in CONVERSATIONS.items():
            with self.subTest(name):
                for path in paths(script):
                    for node_id in required:
                        self.assertIn(node_id, path)
                    self.assertEqual(path[-1], required[-1])  # разговор заканчивается одинаково

    def test_story_dialogues_fit_the_dialogue_box(self) -> None:
        pygame.display.init()
        pygame.font.init()
        try:
            box = DialogueBox()
            for script in story_scripts():
                box.check_fits(script)
        finally:
            pygame.quit()


class ChoicesKeepTheMechanicsTest(PygameTestCase):
    TRIAL_SCENES = (
        (sushi_scene.SushiTrialScene, sushi_scene.COOKING, "orders", SushiOrders),
        (forms_scene.FormsTrialScene, forms_scene.EXPLORE, "puzzle", FormsPuzzle),
        (cakes_scene.CakesTrialScene, cakes_scene.ORDERING, "recipe", CakeRecipe),
    )

    @staticmethod
    def state(puzzle) -> str:
        return repr(sorted(vars(puzzle).items()))

    def test_trial_intro_answers_lead_to_the_same_trial(self) -> None:
        for scene_class, phase, attribute, puzzle_class in self.TRIAL_SCENES:
            for answer in (0, 1):
                with self.subTest(trial=scene_class.__name__, answer=answer):
                    progress = GameProgress()
                    scene = scene_class(progress)
                    shown = answer_dialogue(scene, answer)
                    self.assertGreater(len(shown), 4)
                    self.assertEqual(scene.phase, phase)  # игра там же, где после прежнего вступления
                    self.assertEqual(self.state(getattr(scene, attribute)), self.state(puzzle_class()))
                    self.assertEqual(progress.completed, ())  # ответ — не фрагмент
                    self.assertFalse(scene.completed)

    def test_finale_answer_changes_only_the_lines(self) -> None:
        for answer, own, other in ((0, "f_together", "f_upside_down"), (1, "f_upside_down", "f_together")):
            with self.subTest(answer=answer):
                progress = GameProgress()
                for trial_id in TRIALS:
                    progress.complete(trial_id)
                scene = FinalScene(progress)
                press(scene, pygame.K_e, pygame.KSCAN_E)  # появление страницы можно не ждать
                answer_dialogue(scene, answer)
                self.assertIn(own, scene.shown)
                self.assertNotIn(other, scene.shown)
                self.assertEqual((scene.phase, scene.page), (LETTER, 0))  # дальше — то же письмо с первой страницы
                self.assertEqual(progress.completed, TRIALS)


class LeoInTheFinaleTest(PygameTestCase):
    def finale(self, characters_dir: Path = CHARACTERS_DIR) -> FinalScene:
        progress = GameProgress()
        for trial_id in TRIALS:
            progress.complete(trial_id)
        return FinalScene(progress, characters_dir=characters_dir)

    def leo_commands(self, scene: FinalScene) -> list[SpriteCommand]:
        layer = HiResLayer()
        scene.draw(self.canvas, layer)
        return [command for command in layer.commands
                if isinstance(command, SpriteCommand) and command.rect.size == (LEO_SIZE, LEO_SIZE)]

    def test_leo_sits_on_the_page_drawn_from_his_manifest(self) -> None:
        scene = self.finale()
        scene.update(10)  # страница проявилась, идёт разговор
        (command,) = self.leo_commands(scene)
        self.assertEqual(command.rect.midbottom, LEO_POSITION)
        frame = load_character_sprites(CHARACTERS_DIR / "leo").frame(final_dialogue.LEO_IDLE_POSE).image
        self.assertEqual(pygame.image.tobytes(command.image, "RGBA"), pygame.image.tobytes(frame, "RGBA"))
        # Без слоя высокого разрешения он на холсте: тот же кадр, уменьшенный ближайшим соседом.
        scene.draw(self.canvas)
        expected = pygame.transform.scale(frame, (LEO_SIZE, LEO_SIZE))
        rect = expected.get_rect(midbottom=LEO_POSITION)
        x, y = next((x, y) for y in range(LEO_SIZE) for x in range(LEO_SIZE) if expected.get_at((x, y)).a == 255)
        self.assertEqual(self.canvas.get_at((rect.x + x, rect.y + y))[:3], expected.get_at((x, y))[:3])

    def test_leo_reacts_to_the_commission_and_stays_still(self) -> None:
        scene = self.finale()
        press(scene, pygame.K_e, pygame.KSCAN_E)
        poses = {}
        rects = set()
        while scene.dialogue is not None:
            poses[scene.dialogue.node.id] = scene.leo_pose
            scene.update(0.05)  # Чучмек говорит и покачивается, а Лео — нет
            rects.update(command.rect.midbottom for command in self.leo_commands(scene))
            press(scene, pygame.K_RETURN)
            if scene.dialogue is not None and not scene.dialogue.is_typing:
                press(scene, pygame.K_RETURN)
        self.assertEqual(poses["f_restored"], "sit_idle")
        self.assertEqual(poses["f_commission"], "surprised")
        self.assertEqual(poses["f_verdict"], "laugh")
        self.assertEqual(rects, {LEO_POSITION})
        self.assertEqual(scene.phase, LETTER)
        self.assertEqual(scene.leo_pose, "sit_idle")  # письмо читают спокойно
        for _ in final_dialogue.LETTER_PAGES:
            press(scene, pygame.K_e, pygame.KSCAN_E)
            press(scene, pygame.K_e, pygame.KSCAN_E)
        self.assertEqual(scene.phase, PAUSE)
        self.assertEqual(scene.leo_pose, final_dialogue.LEO_PAUSE_POSE)
        frames = {frame.id for frame in load_character_sprites(CHARACTERS_DIR / "leo").frames}
        used = {*final_dialogue.LEO_POSES.values(), final_dialogue.LEO_IDLE_POSE, final_dialogue.LEO_PAUSE_POSE}
        self.assertLessEqual(used, frames)

    def test_leo_covers_neither_alice_nor_chuchmek_nor_is_covered_by_the_dialogue(self) -> None:
        sprites = {who: load_character_sprites(CHARACTERS_DIR / who) for who in ("alice", "chuchmek", "leo")}

        def body(who: str, pose: str, feet: tuple[int, int], size: int) -> pygame.Rect:
            image = pygame.transform.scale(sprites[who].frame(pose).image, (size, size))
            return image.get_bounding_rect().move(image.get_rect(midbottom=feet).topleft)

        leo_poses = {*final_dialogue.LEO_POSES.values(), final_dialogue.LEO_IDLE_POSE, final_dialogue.LEO_PAUSE_POSE}
        alice_poses = {*final_dialogue.ALICE_POSES.values(), "idle_right", "idle_down", "happy_down_2"}
        chuchmek_poses = {*final_dialogue.CHUCHMEK_POSES.values(), "idle", "wink"}
        for leo_pose in leo_poses:
            leo = body("leo", leo_pose, LEO_POSITION, LEO_SIZE)
            for pose in alice_poses:
                self.assertFalse(leo.colliderect(body("alice", pose, ALICE_POSITION, FINALE_SPRITE_SIZE)), pose)
            for pose in chuchmek_poses:
                self.assertFalse(leo.colliderect(body("chuchmek", pose, CHUCHMEK_POSITION, FINALE_SPRITE_SIZE)))
        box = DialogueBox()
        lowest_box = min(box.layout(node, hires).area.top for script in final_dialogue.all_scripts()
                         for node in script.nodes.values() for hires in (False, True))
        self.assertLessEqual(LEO_POSITION[1], lowest_box)

    def test_finale_without_sprites_still_shows_everyone(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            scene = self.finale(Path(empty))
        for _ in range(3):
            scene.update(2.0)
            scene.draw(self.canvas)
            self.assertEqual(len(self.leo_commands(scene)), 1)  # временный манекен на месте Лео

    def test_letter_gift_and_credits_are_unchanged(self) -> None:
        text = final_dialogue
        blob = repr((text.LETTER_TITLE, text.LETTER_PAGES, text.LETTER_SIGNATURE, text.GIFT_TITLE, text.GIFT_TEXT,
                     text.CREDITS, text.THE_END_LINES, text.EXIT_HINT,
                     [(node.id, node.speaker, node.text) for node in text.GIFT_REACTION.nodes.values()]))
        self.assertEqual(hashlib.sha256(blob.encode()).hexdigest(), LETTER_SHA256)
        self.assertNotIn("Лео", " ".join(line for _, line in text.CREDITS))  # титры прежние


if __name__ == "__main__":
    unittest.main()
