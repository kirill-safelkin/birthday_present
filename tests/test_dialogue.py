"""Проверки системы диалогов: сценарий, контроллер, перенос строк и окно диалога."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import unittest  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.debug.demo_dialogue import DEMO_SCRIPT, QUESTION_ID  # noqa: E402
from game.dialogue.model import (  # noqa: E402
    DialogueChoice,
    DialogueController,
    DialogueError,
    DialogueNode,
    DialogueScript,
)
from game.dialogue.box import CHOICES_GAP, PADDING_Y, DialogueBox, wrap_spans, wrap_text  # noqa: E402
from game.graphics.hires import HiResLayer, TextCommand  # noqa: E402
from game.graphics.fonts import load_font  # noqa: E402

LONG_RUSSIAN_TEXT = (
    "Когда Алиса наконец открыла старый сундук, оттуда выпорхнула стая бумажных "
    "журавликов, и каждый был исписан мелким почерком: списки покупок, забытые "
    "обещания и одна очень подробная инструкция по приготовлению пельменей."
)


def key(key_code: int, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key_code, mod=0, unicode="", scancode=0)


def linear_script() -> DialogueScript:
    return DialogueScript(
        "first",
        [
            DialogueNode("first", "Алиса", "Привет.", next_id="second"),
            DialogueNode("second", "Лео", "Пока."),
        ],
    )


def branching_script() -> DialogueScript:
    return DialogueScript(
        "question",
        [
            DialogueNode(
                "question",
                "Чучмек",
                "Выбирай.",
                choices=[
                    DialogueChoice("Да", "yes"),
                    DialogueChoice("Нет", "no"),
                    DialogueChoice("Повтори вопрос", "question"),
                ],
            ),
            DialogueNode("yes", "Чучмек", "Хорошо."),
            DialogueNode("no", "Чучмек", "Жаль."),
        ],
    )


class ScriptValidationTest(unittest.TestCase):
    def test_valid_script_is_created(self) -> None:
        script = branching_script()
        self.assertEqual(script.start_id, "question")
        self.assertEqual(set(script.nodes), {"question", "yes", "no"})
        self.assertIsInstance(script.nodes["question"].choices, tuple)

    def test_missing_start_node_is_rejected(self) -> None:
        with self.assertRaisesRegex(DialogueError, "начальная реплика «nowhere» не найдена"):
            DialogueScript("nowhere", [DialogueNode("a", "Чучмек", "Текст.")])

    def test_empty_script_is_rejected(self) -> None:
        with self.assertRaisesRegex(DialogueError, "нет ни одной реплики"):
            DialogueScript("a", [])

    def test_reference_to_missing_node_is_rejected(self) -> None:
        cases = {
            "next_id": [DialogueNode("a", "Чучмек", "Текст.", next_id="ghost")],
            "вариант ответа": [DialogueNode("a", "Чучмек", "Вопрос?", choices=[DialogueChoice("Ответ", "ghost")])],
        }
        for case, nodes in cases.items():
            with self.subTest(case), self.assertRaisesRegex(DialogueError, "несуществующую реплику «ghost»"):
                DialogueScript("a", nodes)

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(DialogueError, "«a» повторяется"):
            DialogueScript("a", [DialogueNode("a", "Чучмек", "Раз."), DialogueNode("a", "Чучмек", "Два.")])

    def test_empty_ids_and_texts_are_rejected(self) -> None:
        cases = {
            "идентификатор реплики": lambda: DialogueNode(" ", "Чучмек", "Текст."),
            "текст реплики": lambda: DialogueNode("a", "Чучмек", "   "),
            "текст варианта": lambda: DialogueChoice("", "a"),
            "цель варианта": lambda: DialogueChoice("Ответ", ""),
        }
        for case, make in cases.items():
            with self.subTest(case), self.assertRaises(DialogueError):
                make()

    def test_empty_choice_list_is_rejected(self) -> None:
        with self.assertRaisesRegex(DialogueError, "пустой список вариантов"):
            DialogueNode("a", "Чучмек", "Вопрос?", choices=[])

    def test_choices_together_with_next_id_are_rejected(self) -> None:
        with self.assertRaisesRegex(DialogueError, "и next_id, и варианты ответа"):
            DialogueNode("a", "Чучмек", "Вопрос?", next_id="b", choices=[DialogueChoice("Да", "b")])

    def test_dialogue_without_way_to_finish_is_rejected(self) -> None:
        loop = [
            DialogueNode("a", "Чучмек", "Раз.", next_id="b"),
            DialogueNode("b", "Чучмек", "Два.", next_id="a"),
        ]
        with self.assertRaisesRegex(DialogueError, "нельзя дойти до конца"):
            DialogueScript("a", loop)

    def test_narrator_line_without_speaker_is_allowed(self) -> None:
        script = DialogueScript("a", [DialogueNode("a", "", "Наступила тишина.")])
        self.assertEqual(script.nodes["a"].speaker, "")


class ControllerTest(unittest.TestCase):
    def test_linear_lines_follow_each_other(self) -> None:
        dialogue = DialogueController(linear_script())
        self.assertEqual(dialogue.node.id, "first")
        dialogue.confirm()  # дописать текст
        dialogue.confirm()  # перейти дальше
        self.assertEqual(dialogue.node.id, "second")
        self.assertEqual(dialogue.visible_text, "")

    def test_text_appears_gradually_with_dt(self) -> None:
        dialogue = DialogueController(linear_script(), chars_per_second=20)
        self.assertEqual(dialogue.visible_text, "")
        dialogue.update(0.1)
        self.assertEqual(dialogue.visible_text, "Пр")
        dialogue.update(0.05)
        self.assertEqual(dialogue.visible_text, "При")
        self.assertTrue(dialogue.is_typing)
        dialogue.update(10)  # с запасом: текст не выходит за конец реплики
        self.assertEqual(dialogue.visible_text, "Привет.")
        self.assertFalse(dialogue.is_typing)

    def test_many_small_dt_add_up_exactly(self) -> None:
        dialogue = DialogueController(linear_script(), chars_per_second=40)
        for _ in range(10):
            dialogue.update(0.01)  # 10 кадров по 0,01 с при 40 символах в секунду
        self.assertEqual(dialogue.visible_chars, 4)

    def test_enter_reveals_text_instantly(self) -> None:
        for confirm_key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            with self.subTest(key=confirm_key):
                dialogue = DialogueController(linear_script())
                dialogue.update(0.05)
                self.assertTrue(dialogue.handle_event(key(confirm_key)))
                self.assertEqual(dialogue.node.id, "first")
                self.assertEqual(dialogue.visible_text, "Привет.")

    def test_enter_after_typing_goes_to_next_line(self) -> None:
        dialogue = DialogueController(linear_script())
        dialogue.update(10)
        dialogue.handle_event(key(pygame.K_RETURN))
        self.assertEqual(dialogue.node.id, "second")
        self.assertEqual(dialogue.visible_text, "")  # новая реплика печатается заново

    def test_each_press_makes_exactly_one_step(self) -> None:
        dialogue = DialogueController(linear_script())
        steps = []
        for _ in range(4):
            dialogue.handle_event(key(pygame.K_RETURN))
            steps.append((dialogue.node.id if dialogue.node else None, dialogue.visible_text))
        self.assertEqual(steps, [("first", "Привет."), ("second", ""), ("second", "Пока."), (None, "")])

    def test_arrows_move_selection_with_wraparound(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        self.assertEqual(dialogue.selected_index, 0)
        indexes = []
        for arrow in (pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_UP):
            self.assertTrue(dialogue.handle_event(key(arrow)))
            indexes.append(dialogue.selected_index)
        self.assertEqual(indexes, [1, 2, 0, 2])

    def test_choices_are_hidden_while_typing(self) -> None:
        dialogue = DialogueController(branching_script())
        self.assertEqual(dialogue.choices, ())
        dialogue.handle_event(key(pygame.K_DOWN))
        self.assertEqual(dialogue.selected_index, 0)
        dialogue.update(10)
        self.assertEqual([choice.text for choice in dialogue.choices], ["Да", "Нет", "Повтори вопрос"])

    def test_question_waits_for_answer(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        dialogue.update(100)
        self.assertEqual(dialogue.node.id, "question")
        self.assertEqual(dialogue.visible_text, "Выбирай.")

    def test_choosing_answer_follows_its_branch(self) -> None:
        for presses, expected in ((0, "yes"), (1, "no")):
            with self.subTest(expected):
                dialogue = DialogueController(branching_script())
                dialogue.update(10)
                for _ in range(presses):
                    dialogue.handle_event(key(pygame.K_DOWN))
                dialogue.handle_event(key(pygame.K_RETURN))
                self.assertEqual(dialogue.node.id, expected)
                self.assertEqual(dialogue.answers["question"].next_id, expected)

    def test_returning_to_question_keeps_latest_answer(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        dialogue.move_selection(2)
        dialogue.confirm()  # «Повтори вопрос» ведёт обратно к вопросу
        self.assertEqual(dialogue.node.id, "question")
        self.assertEqual(dialogue.selected_index, 0)
        dialogue.update(10)
        dialogue.confirm()  # «Да»
        self.assertEqual(dialogue.answers, {"question": DialogueChoice("Да", "yes")})

    def test_last_line_finishes_dialogue(self) -> None:
        dialogue = DialogueController(linear_script())
        for _ in range(4):
            dialogue.confirm()
        self.assertTrue(dialogue.is_finished)
        self.assertIsNone(dialogue.node)
        self.assertEqual(dialogue.visible_text, "")
        self.assertEqual(dialogue.choices, ())
        # После конца диалог больше не реагирует на ввод и не падает.
        self.assertFalse(dialogue.handle_event(key(pygame.K_RETURN)))
        dialogue.update(1)
        dialogue.confirm()
        dialogue.move_selection(1)
        self.assertTrue(dialogue.is_finished)

    def test_other_keys_and_key_release_are_ignored(self) -> None:
        dialogue = DialogueController(linear_script())
        self.assertFalse(dialogue.handle_event(key(pygame.K_a)))
        self.assertFalse(dialogue.handle_event(key(pygame.K_RETURN, pygame.KEYUP)))
        self.assertEqual(dialogue.visible_text, "")

    def test_space_types_and_continues_but_never_answers(self) -> None:
        dialogue = DialogueController(branching_script())
        self.assertTrue(dialogue.handle_event(key(pygame.K_SPACE)))  # дописал вопрос
        self.assertFalse(dialogue.is_typing)
        for _ in range(3):
            self.assertTrue(dialogue.handle_event(key(pygame.K_SPACE)))  # нажатие диалоговое, но ответа нет
        self.assertEqual(dialogue.node.id, "question")
        self.assertEqual(dialogue.answers, {})
        dialogue.handle_event(key(pygame.K_DOWN))
        dialogue.handle_event(key(pygame.K_KP_ENTER))  # Enter на цифровом блоке — тоже ответ
        self.assertEqual(dialogue.node.id, "no")
        dialogue.update(10)
        dialogue.handle_event(key(pygame.K_SPACE))  # а обычные реплики пробел по-прежнему листает
        self.assertTrue(dialogue.is_finished)

    def test_e_answers_through_confirm_like_enter(self) -> None:
        # Сцены передают E в confirm(): так E выбирает выделенный ответ, как Enter.
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        dialogue.handle_event(key(pygame.K_DOWN))
        dialogue.confirm()
        self.assertEqual(dialogue.answers["question"], DialogueChoice("Нет", "no"))

    def test_one_press_on_a_question_makes_one_step(self) -> None:
        # Нажатие, которое дописывает вопрос, ответ не выбирает: его выбирает только следующее.
        dialogue = DialogueController(branching_script())
        dialogue.handle_event(key(pygame.K_RETURN))
        self.assertEqual(dialogue.node.id, "question")
        self.assertEqual(dialogue.answers, {})
        dialogue.handle_event(key(pygame.K_RETURN))
        self.assertEqual(dialogue.node.id, "yes")
        self.assertTrue(dialogue.is_typing)  # новая реплика начата с нуля

    def test_typing_speed_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            DialogueController(linear_script(), chars_per_second=0)


def three_lines_script() -> DialogueScript:
    return DialogueScript(
        "one",
        [
            DialogueNode("one", "Алиса", "Раз.", next_id="two"),
            DialogueNode("two", "Лео", "Два.", next_id="three"),
            DialogueNode("three", "Чучмек", "Три."),
        ],
    )


def arrow(code: int) -> pygame.event.Event:
    """Стрелка со скан-кодом, как от настоящей клавиатуры."""
    scancode = {pygame.K_LEFT: pygame.KSCAN_LEFT, pygame.K_RIGHT: pygame.KSCAN_RIGHT}[code]
    return pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode="", scancode=scancode)


class HistoryNavigationTest(unittest.TestCase):
    """← — к прежней реплике, → — как пробел; история не меняет ответов и не повторяет переходов."""

    def steps(self, code: int) -> list[tuple[str | None, str]]:
        dialogue = DialogueController(three_lines_script())
        event = arrow(code) if code == pygame.K_RIGHT else key(code)
        steps = []
        for _ in range(6):
            self.assertTrue(dialogue.handle_event(event))
            steps.append((dialogue.node.id if dialogue.node else None, dialogue.visible_text))
        return steps

    def test_space_and_right_arrow_continue_the_same_way(self) -> None:
        expected = [("one", "Раз."), ("two", ""), ("two", "Два."), ("three", ""), ("three", "Три."), (None, "")]
        self.assertEqual(self.steps(pygame.K_SPACE), expected)
        self.assertEqual(self.steps(pygame.K_RIGHT), expected)

    def test_left_arrow_shows_previous_line_in_full(self) -> None:
        dialogue = DialogueController(three_lines_script())
        dialogue.confirm()
        dialogue.confirm()  # на «two», печать с нуля
        dialogue.update(0.01)
        self.assertTrue(dialogue.handle_event(arrow(pygame.K_LEFT)))
        self.assertEqual(dialogue.node.id, "one")
        self.assertEqual(dialogue.visible_text, "Раз.")  # прежняя реплика видна сразу целиком
        self.assertFalse(dialogue.is_typing)
        self.assertTrue(dialogue.is_reviewing)
        dialogue.update(10)  # пока листают историю, текущая реплика не допечатывается
        dialogue.handle_event(arrow(pygame.K_RIGHT))
        self.assertEqual(dialogue.node.id, "two")
        self.assertFalse(dialogue.is_reviewing)
        self.assertTrue(dialogue.is_typing)  # текущая реплика вернулась такой, какой была
        self.assertEqual(dialogue.visible_chars, int(0.01 * dialogue.chars_per_second))

    def test_right_arrow_restores_next_seen_line_then_continues_normally(self) -> None:
        dialogue = DialogueController(three_lines_script())
        for _ in range(4):
            dialogue.confirm()  # «one» и «two» прочитаны, «three» печатается
        for _ in range(2):
            dialogue.handle_event(arrow(pygame.K_LEFT))
        self.assertEqual(dialogue.node.id, "one")
        shown = []
        for _ in range(2):
            dialogue.handle_event(arrow(pygame.K_RIGHT))
            shown.append((dialogue.node.id, dialogue.is_reviewing))
        self.assertEqual(shown, [("two", True), ("three", False)])
        dialogue.handle_event(arrow(pygame.K_RIGHT))  # дальше — по обычным правилам: дописать…
        self.assertEqual(dialogue.visible_text, "Три.")
        dialogue.handle_event(arrow(pygame.K_RIGHT))  # …и закончить
        self.assertTrue(dialogue.is_finished)

    def test_cannot_go_back_before_the_first_line(self) -> None:
        dialogue = DialogueController(three_lines_script())
        self.assertFalse(dialogue.can_go_back)
        self.assertTrue(dialogue.handle_event(arrow(pygame.K_LEFT)))  # клавиша диалога, но шага нет
        self.assertEqual(dialogue.node.id, "one")
        self.assertFalse(dialogue.is_reviewing)
        dialogue.confirm()
        dialogue.confirm()
        for _ in range(3):
            dialogue.back()
        self.assertEqual(dialogue.node.id, "one")
        self.assertFalse(dialogue.back())

    def test_one_press_moves_exactly_one_line(self) -> None:
        dialogue = DialogueController(three_lines_script())
        for _ in range(4):
            dialogue.confirm()
        dialogue.handle_event(arrow(pygame.K_LEFT))
        self.assertEqual(dialogue.node.id, "two")
        dialogue.handle_event(arrow(pygame.K_LEFT))
        self.assertEqual(dialogue.node.id, "one")
        dialogue.handle_event(arrow(pygame.K_RIGHT))
        self.assertEqual(dialogue.node.id, "two")  # не сразу к текущей

    def test_enter_and_e_in_history_also_step_forward(self) -> None:
        dialogue = DialogueController(three_lines_script())
        dialogue.confirm()
        dialogue.confirm()
        dialogue.back()
        dialogue.handle_event(key(pygame.K_RETURN))
        self.assertEqual((dialogue.node.id, dialogue.is_reviewing), ("two", False))
        dialogue.back()
        dialogue.confirm()  # так сцены передают E
        self.assertEqual((dialogue.node.id, dialogue.is_reviewing), ("two", False))
        self.assertTrue(dialogue.is_typing)

    def test_last_line_still_finishes_after_going_back(self) -> None:
        dialogue = DialogueController(linear_script())
        dialogue.confirm()
        dialogue.confirm()
        dialogue.update(10)  # «Пока.» видна целиком
        dialogue.back()
        dialogue.handle_event(key(pygame.K_SPACE))  # к последней реплике, она уже дописана
        self.assertEqual(dialogue.node.id, "second")
        self.assertFalse(dialogue.is_finished)
        dialogue.handle_event(key(pygame.K_SPACE))
        self.assertTrue(dialogue.is_finished)
        self.assertFalse(dialogue.can_go_back)  # после конца диалог больше ничего не листает
        self.assertFalse(dialogue.handle_event(arrow(pygame.K_LEFT)))
        self.assertIsNone(dialogue.node)

    def test_answered_question_in_history_shows_its_answer_read_only(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        dialogue.move_selection(1)
        dialogue.confirm()  # «Нет»
        self.assertEqual(dialogue.node.id, "no")
        dialogue.handle_event(arrow(pygame.K_LEFT))
        self.assertEqual(dialogue.node.id, "question")
        self.assertEqual([choice.text for choice in dialogue.choices], ["Да", "Нет", "Повтори вопрос"])
        self.assertEqual(dialogue.selected_index, 1)  # выделен ответ, который тогда выбрали
        for code in (pygame.K_UP, pygame.K_DOWN, pygame.K_DOWN):
            dialogue.handle_event(key(code))
        self.assertEqual(dialogue.selected_index, 1)  # прежний ответ не меняется
        dialogue.handle_event(key(pygame.K_RETURN))  # Enter — снова к ветке этого ответа
        self.assertEqual(dialogue.node.id, "no")
        self.assertEqual(dialogue.answers, {"question": DialogueChoice("Нет", "no")})

    def test_space_and_right_arrow_step_out_of_answered_question_in_history(self) -> None:
        for code in (pygame.K_SPACE, pygame.K_RIGHT):
            with self.subTest(key=code):
                dialogue = DialogueController(branching_script())
                dialogue.update(10)
                dialogue.confirm()  # «Да»
                dialogue.back()
                dialogue.handle_event(arrow(code) if code == pygame.K_RIGHT else key(code))
                self.assertEqual(dialogue.node.id, "yes")  # ответ уже был, вслепую ничего не выбрано
                self.assertEqual(dialogue.answers, {"question": DialogueChoice("Да", "yes")})

    def test_live_question_still_needs_e_or_enter(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        for _ in range(3):
            dialogue.handle_event(arrow(pygame.K_RIGHT))
            dialogue.handle_event(key(pygame.K_SPACE))
        self.assertEqual(dialogue.node.id, "question")
        self.assertEqual(dialogue.answers, {})
        dialogue.handle_event(key(pygame.K_DOWN))
        dialogue.handle_event(arrow(pygame.K_LEFT))  # назад некуда: выделение на месте
        self.assertEqual(dialogue.selected_index, 1)
        dialogue.handle_event(key(pygame.K_RETURN))
        self.assertEqual(dialogue.node.id, "no")

    def test_repeated_question_remembers_each_answer_in_history(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        dialogue.move_selection(2)
        dialogue.confirm()  # «Повтори вопрос»
        dialogue.update(10)
        dialogue.confirm()  # «Да»
        seen = []
        while dialogue.back():
            seen.append((dialogue.node.id, dialogue.selected_index))
        self.assertEqual(seen, [("question", 0), ("question", 2)])
        self.assertEqual(dialogue.answers, {"question": DialogueChoice("Да", "yes")})

    def test_live_selection_survives_a_look_back(self) -> None:
        script = DialogueScript("intro", [
            DialogueNode("intro", "Чучмек", "Внимание.", next_id="question"),
            *branching_script().nodes.values(),
        ])
        dialogue = DialogueController(script)
        dialogue.confirm()
        dialogue.confirm()
        dialogue.update(10)
        dialogue.move_selection(1)
        dialogue.back()
        self.assertEqual(dialogue.node.id, "intro")
        dialogue.handle_event(arrow(pygame.K_RIGHT))
        self.assertEqual((dialogue.node.id, dialogue.selected_index), ("question", 1))
        dialogue.confirm()
        self.assertEqual(dialogue.node.id, "no")

    def test_letters_a_and_d_do_not_page(self) -> None:
        dialogue = DialogueController(three_lines_script())
        dialogue.confirm()
        dialogue.confirm()
        for code, scancode in ((pygame.K_a, pygame.KSCAN_A), (pygame.K_d, pygame.KSCAN_D)):
            event = pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode="", scancode=scancode)
            self.assertFalse(dialogue.handle_event(event))
        self.assertEqual((dialogue.node.id, dialogue.is_reviewing), ("two", False))

    def test_new_dialogue_starts_with_empty_history(self) -> None:
        first = DialogueController(three_lines_script())
        for _ in range(4):
            first.confirm()
        second = DialogueController(three_lines_script())
        self.assertFalse(second.can_go_back)
        second.back()
        self.assertEqual(second.node.id, "one")


class LongTextTest(unittest.TestCase):
    font: pygame.font.Font

    @classmethod
    def setUpClass(cls) -> None:
        pygame.font.init()
        cls.font = load_font(10)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.font.quit()

    def test_long_russian_text_wraps_within_width(self) -> None:
        lines = wrap_text(LONG_RUSSIAN_TEXT, self.font, 200)
        self.assertGreater(len(lines), 3)
        for line in lines:
            self.assertLessEqual(self.font.size(line)[0], 200, line)
        # Переносы только по пробелам: слова не потеряны и не разрезаны.
        self.assertEqual(" ".join(lines), LONG_RUSSIAN_TEXT)

    def test_word_longer_than_line_is_cut_by_letters(self) -> None:
        word = "Рентгеноэлектрокардиографический" * 2
        lines = wrap_text(word, self.font, 100)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(self.font.size(line)[0], 100, line)
        self.assertEqual("".join(lines), word)

    def test_dash_inside_a_phrase_never_starts_a_line(self) -> None:
        text = "Что это — пока секрет. Скоро — узнаешь — правда."
        for width in range(70, 320, 7):  # уже — пара «слово + тире» сама не помещается и режется по буквам
            lines = wrap_text(text, self.font, width)
            with self.subTest(width=width):
                self.assertFalse(any(line.startswith("—") for line in lines), lines)
                self.assertEqual(" ".join(lines).split(), text.split())
        self.assertEqual(wrap_text("— Привет!", self.font, 300), ["— Привет!"])  # тире прямой речи — на месте

    def test_newline_starts_new_line(self) -> None:
        self.assertEqual(wrap_text("Раз.\nДва три.", self.font, 300), ["Раз.", "Два три."])

    def test_spans_cover_text_in_order(self) -> None:
        spans = wrap_spans(LONG_RUSSIAN_TEXT, self.font, 150)
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], len(LONG_RUSSIAN_TEXT))
        # Между соседними строками в исходном тексте только пробел переноса.
        for (_, end), (next_start, _) in zip(spans, spans[1:]):
            self.assertEqual(LONG_RUSSIAN_TEXT[end:next_start], " ")

    def test_long_line_types_out_by_dt(self) -> None:
        script = DialogueScript("a", [DialogueNode("a", "Алиса", LONG_RUSSIAN_TEXT)])
        dialogue = DialogueController(script, chars_per_second=50)
        total_seconds = len(LONG_RUSSIAN_TEXT) / 50
        dialogue.update(total_seconds / 2)
        self.assertTrue(dialogue.is_typing)
        self.assertAlmostEqual(dialogue.visible_chars, len(LONG_RUSSIAN_TEXT) / 2, delta=1)
        for _ in range(math.ceil(total_seconds / 2 * 60) + 1):
            dialogue.update(1 / 60)
        self.assertEqual(dialogue.visible_text, LONG_RUSSIAN_TEXT)


class DialogueBoxTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.box = DialogueBox()
        self.screen_rect = pygame.Rect((0, 0), config.LOGICAL_SIZE)
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def tearDown(self) -> None:
        pygame.quit()

    def assert_on_screen(self, node: DialogueNode) -> None:
        layout = self.box.layout(node)
        self.assertTrue(self.screen_rect.contains(layout.box), node.id)
        if layout.name_tab is not None:
            self.assertTrue(self.screen_rect.contains(layout.name_tab), node.id)
        if layout.hint_tab is not None:
            self.assertTrue(self.screen_rect.contains(layout.hint_tab), node.id)
        choice_rows = sum(len(lines) for lines in layout.choice_lines)
        self.assertLessEqual(layout.choices_top + choice_rows * self.box.line_height, layout.box.bottom, node.id)

    def test_demo_script_fits_on_screen(self) -> None:
        self.box.check_fits(DEMO_SCRIPT)
        for node in DEMO_SCRIPT.nodes.values():
            self.assert_on_screen(node)

    def test_long_russian_line_is_wrapped_inside_box(self) -> None:
        node = DialogueNode("long", "Алиса", LONG_RUSSIAN_TEXT)
        self.assertGreater(len(self.box.layout(node).text_spans), 3)
        self.assert_on_screen(node)

    def test_long_choices_are_wrapped_inside_box(self) -> None:
        long_choice = "Сначала объясни, почему чайник стоит на крыше, а потом уже про решения."
        node = DialogueNode("q", "Чучмек", "Ну?", choices=[DialogueChoice(long_choice, "q"), DialogueChoice("Нет", "q")])
        self.assertGreater(len(self.box.layout(node).choice_lines[0]), 1)
        self.assert_on_screen(node)

    def test_too_long_line_is_reported_before_the_game(self) -> None:
        script = DialogueScript("a", [DialogueNode("a", "Алиса", LONG_RUSSIAN_TEXT * 5)])
        with self.assertRaisesRegex(DialogueError, "не помещается на экран"):
            self.box.check_fits(script)

    def test_selected_choice_is_highlighted(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        layout = self.box.layout(dialogue.node)

        def row_color(index: int) -> tuple[int, ...]:
            self.canvas.fill(config.BACKGROUND_COLOR)
            self.box.draw(self.canvas, dialogue)
            point = (layout.box.right - 5, layout.choices_top + index * self.box.line_height + 1)
            return tuple(self.canvas.get_at(point))[:3]

        self.assertEqual(row_color(0), config.DIALOGUE_SELECTED_BG_COLOR)
        self.assertEqual(row_color(1), config.DIALOGUE_BOX_COLOR)
        dialogue.move_selection(1)
        self.assertEqual(row_color(0), config.DIALOGUE_BOX_COLOR)
        self.assertEqual(row_color(1), config.DIALOGUE_SELECTED_BG_COLOR)

    def test_drawing_uses_only_palette_colors(self) -> None:
        # Текст рисуется без сглаживания: на холсте нет промежуточных оттенков,
        # и при увеличении края остаются чёткими.
        dialogue = DialogueController(DEMO_SCRIPT)
        while dialogue.node is not None and dialogue.node.id != QUESTION_ID:
            dialogue.confirm()
        dialogue.update(10)
        self.canvas.fill(config.BACKGROUND_COLOR)
        self.box.draw(self.canvas, dialogue)
        palette = {
            config.BACKGROUND_COLOR,
            config.DIALOGUE_BOX_COLOR,
            config.DIALOGUE_BORDER_COLOR,
            config.DIALOGUE_NAME_COLOR,
            config.DIALOGUE_TEXT_COLOR,
            config.DIALOGUE_CHOICE_COLOR,
            config.DIALOGUE_SELECTED_COLOR,
            config.DIALOGUE_SELECTED_BG_COLOR,
        }
        width, height = config.LOGICAL_SIZE
        used = {tuple(self.canvas.get_at((x, y)))[:3] for x in range(width) for y in range(height)}
        self.assertLessEqual(used, palette)
        self.assertIn(config.DIALOGUE_SELECTED_COLOR, used)

    def test_answer_hint_appears_with_the_choices(self) -> None:
        dialogue = DialogueController(branching_script())
        layout = self.box.layout(dialogue.node)
        tab = layout.hint_tab
        self.assertIsNotNone(tab)
        self.assertIsNone(self.box.layout(linear_script().nodes["first"]).hint_tab)  # без вопроса — без подсказки
        # Справа на верхней рамке, той же высоты, что табличка имени, и не наезжает на неё.
        self.assertEqual((tab.top, tab.height), (layout.name_tab.top, layout.name_tab.height))
        self.assertEqual(tab.bottom, layout.box.top + 1)
        self.assertGreater(tab.left, layout.name_tab.right)
        self.assertEqual(layout.area, layout.box.union(layout.name_tab).union(tab))

        def tab_border() -> tuple[int, ...]:
            self.canvas.fill(config.BACKGROUND_COLOR)
            self.box.draw(self.canvas, dialogue)
            return tuple(self.canvas.get_at((tab.centerx, tab.top)))[:3]

        self.assertEqual(tab_border(), config.BACKGROUND_COLOR)  # пока вопрос печатается — подсказки нет
        dialogue.update(10)
        self.assertEqual(tab_border(), config.DIALOGUE_BORDER_COLOR)

    def test_answer_hint_is_drawn_at_window_resolution(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        layer = HiResLayer()
        self.box.draw(self.canvas, dialogue, layer)
        texts = [command.text for command in layer.commands if isinstance(command, TextCommand)]
        self.assertIn("E — ответить", texts)
        self.assertEqual(texts[0], "Чучмек")
        self.assertIn("Выбирай.", texts)

    def test_answered_question_in_history_has_no_answer_hint(self) -> None:
        dialogue = DialogueController(branching_script())
        dialogue.update(10)
        dialogue.confirm()
        dialogue.back()
        tab = self.box.layout(dialogue.node).hint_tab
        self.canvas.fill(config.BACKGROUND_COLOR)
        self.box.draw(self.canvas, dialogue)
        self.assertEqual(tuple(self.canvas.get_at((tab.centerx, tab.top)))[:3], config.BACKGROUND_COLOR)
        layer = HiResLayer()
        self.box.draw(self.canvas, dialogue, layer)
        texts = [command.text for command in layer.commands if isinstance(command, TextCommand)]
        self.assertNotIn("E — ответить", texts)
        self.assertIn("Выбирай.", texts)  # прежний вопрос — целиком, с вариантами
        self.assertIn("Да", texts)

    def test_short_question_box_is_as_tall_as_a_plain_line(self) -> None:
        # Вопрос в строку и два ответа в строку: окно не подпрыгивает, когда появляется вопрос.
        question = DialogueNode("q", "Чучмек", "Ну?", choices=[DialogueChoice("Да", "a"), DialogueChoice("Нет", "a")])
        plain = DialogueNode("a", "Чучмек", "Ну.")
        for hires in (False, True):
            with self.subTest(hires=hires):
                layout = self.box.layout(question, hires)
                self.assertEqual(layout.box, self.box.layout(plain, hires).box)
                # Отступ перед ответами сохранён, а ответы не вылезают за нижний край окна.
                self.assertEqual(layout.choices_top, layout.text_top + layout.line_height + CHOICES_GAP)
                self.assertLessEqual(layout.choices_top + 2 * layout.line_height, layout.box.bottom - 2)
                self.assertGreaterEqual(layout.text_top, layout.box.top + 2)

    def test_long_question_box_grows_and_keeps_the_usual_padding(self) -> None:
        question = DialogueNode("q", "Чучмек", LONG_RUSSIAN_TEXT[:150],
                                choices=[DialogueChoice("Да", "a"), DialogueChoice("Нет", "a")])
        layout = self.box.layout(question)
        rows = len(layout.text_spans)
        self.assertGreater(rows, 1)
        self.assertEqual(layout.text_top, layout.box.top + PADDING_Y)
        self.assertEqual(layout.box.height, (rows + 2) * layout.line_height + CHOICES_GAP + 2 * PADDING_Y)

    def test_finished_dialogue_draws_nothing(self) -> None:
        dialogue = DialogueController(linear_script())
        for _ in range(4):
            dialogue.confirm()
        self.canvas.fill(config.BACKGROUND_COLOR)
        before = pygame.image.tobytes(self.canvas, "RGB")
        self.box.draw(self.canvas, dialogue)
        self.assertEqual(pygame.image.tobytes(self.canvas, "RGB"), before)


class DemoScriptTest(unittest.TestCase):
    def play(self, answers: list[int]) -> tuple[DialogueController, list[str]]:
        """Проходит демонстрацию нажатиями: на вопросах — нужное число стрелок вниз."""
        dialogue = DialogueController(DEMO_SCRIPT)
        remaining_answers = iter(answers)
        visited: list[str] = []
        while dialogue.node is not None and len(visited) < 50:
            visited.append(dialogue.node.id)
            dialogue.handle_event(key(pygame.K_RETURN))  # дописать текст
            if dialogue.choices:
                for _ in range(next(remaining_answers)):
                    dialogue.handle_event(key(pygame.K_DOWN))
            dialogue.handle_event(key(pygame.K_RETURN))  # продолжить или выбрать ответ
        return dialogue, visited

    def test_each_answer_leads_to_its_own_reply(self) -> None:
        expected = {0: "go_on", 1: "crumbs", 2: "competence"}
        for answer, reply in expected.items():
            with self.subTest(answer=answer):
                _, visited = self.play([answer, 0])
                self.assertEqual(visited[:4], ["start", "rumour", QUESTION_ID, reply])

    def test_crumbs_branch_returns_to_question_and_ends(self) -> None:
        dialogue, visited = self.play([1, 0])
        self.assertEqual(visited, ["start", "rumour", QUESTION_ID, "crumbs", "forgot", QUESTION_ID, "go_on"])
        self.assertTrue(dialogue.is_finished)
        self.assertEqual(dialogue.answers[QUESTION_ID].text, "Продолжай.")

    def test_other_branches_end_dialogue(self) -> None:
        for answer, last in ((0, "go_on"), (2, "competence")):
            with self.subTest(answer=answer):
                dialogue, visited = self.play([answer])
                self.assertEqual(visited[-1], last)
                self.assertTrue(dialogue.is_finished)


if __name__ == "__main__":
    unittest.main()
