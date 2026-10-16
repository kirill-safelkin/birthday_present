"""Проверки логики испытания формуляров — без Pygame и без окна."""

import itertools
import subprocess
import sys
import unittest
from pathlib import Path

from game.trials.forms_puzzle import (
    ARCHIVE_SLOTS,
    CORRECT_ORDER,
    DOCUMENT_NAMES,
    DOCUMENT_TITLES,
    DOCUMENTS,
    ISSUED,
    ISSUED_TITLES,
    SECTIONS,
    CheckResult,
    FormsPuzzle,
    SearchResult,
    Section,
    SlotResult,
)

ROOT = Path(__file__).resolve().parent.parent
SECTION_OF = {section.document: section.id for section in SECTIONS if section.document}
EMPTY_SECTIONS = [section.id for section in SECTIONS if section.document is None]


def find_all(puzzle: FormsPuzzle, order=DOCUMENTS) -> None:
    for document in order:
        puzzle.search(SECTION_OF[document])


def arrange(puzzle: FormsPuzzle) -> None:
    """Раскладывает стол в правильном порядке из любого состояния — только обычными действиями."""
    if puzzle.held is not None:
        puzzle.use_slot(puzzle.held_from)
    for index, document in enumerate(CORRECT_ORDER):
        if puzzle.order[index] != document:
            puzzle.use_slot(puzzle.order.index(document))
            puzzle.use_slot(index)


class DataTest(unittest.TestCase):
    def test_three_documents_in_the_correct_order(self) -> None:
        self.assertEqual(CORRECT_ORDER, ("form_request", "filing_permit", "leo_application"))
        self.assertEqual([DOCUMENT_TITLES[document] for document in CORRECT_ORDER], [
            "Заявление на выдачу бланка заявления",
            "Разрешение на подачу заявления",
            "Заявление о регистрации рождения и гражданстве Лео",
        ])
        self.assertEqual([DOCUMENT_NAMES[document] for document in CORRECT_ORDER],
                         ["Заявление на бланк", "Разрешение на подачу", "Заявление о Лео"])
        self.assertEqual(len(set(DOCUMENT_NAMES.values())), 3)  # короткие названия не путаются между собой

    def test_required_sections_exist_and_each_document_is_hidden_once(self) -> None:
        names = {section.name for section in SECTIONS}
        for name in ("Заявки, которые ещё не стали заявлениями", "Разрешения на другие разрешения",
                     "Рождения, ожидающие регистрации", "Торты, признанные документами", "Соответствующий отдел"):
            self.assertIn(name, names)
        # Каждый документ Лео — в разделе, который ему по смыслу подходит; торты и отдел — только шутки.
        where = {section.document: section.name for section in SECTIONS if section.document}
        self.assertEqual(where, {
            "form_request": "Заявки, которые ещё не стали заявлениями",
            "filing_permit": "Разрешения на другие разрешения",
            "leo_application": "Рождения, ожидающие регистрации",
        })
        self.assertEqual(sorted(EMPTY_SECTIONS), ["cakes", "department"])
        self.assertEqual(len({section.id for section in SECTIONS}), len(SECTIONS))
        hidden = [section.document for section in SECTIONS if section.document]
        self.assertEqual(sorted(hidden), sorted(DOCUMENTS))
        self.assertTrue(EMPTY_SECTIONS)  # есть разделы-шутки без нужных бумаг
        for section in SECTIONS:
            self.assertTrue(section.label.strip())

    def test_archive_lays_documents_out_in_a_wrong_order(self) -> None:
        self.assertEqual(sorted(ARCHIVE_SLOTS.values()), [0, 1, 2])
        # «По алфавиту задом наперёд», как говорит гусь: по полным названиям.
        by_title = sorted(DOCUMENTS, key=DOCUMENT_TITLES.get, reverse=True)
        self.assertEqual(by_title, ["filing_permit", "leo_application", "form_request"])
        self.assertEqual([document for document, _ in sorted(ARCHIVE_SLOTS.items(), key=lambda item: item[1])],
                         by_title)
        for document, slot in ARCHIVE_SLOTS.items():
            self.assertNotEqual(CORRECT_ORDER[slot], document)  # ни один не на своём месте

    def test_invalid_archive_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Section("x", "Пиццы", "Пиццы", "pizza")
        without_leo_application = [section for section in SECTIONS if section.document != "leo_application"]
        with self.assertRaises(ValueError):
            FormsPuzzle(without_leo_application)
        with self.assertRaises(ValueError):
            FormsPuzzle([*SECTIONS, Section("copy", "Копии", "Копии", "filing_permit")])


class SearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.puzzle = FormsPuzzle()

    def test_documents_are_not_usable_before_they_are_found(self) -> None:
        self.assertEqual(self.puzzle.order, (None, None, None))
        for index in range(3):
            self.assertIs(self.puzzle.use_slot(index), SlotResult.NOT_READY)
        self.assertIs(self.puzzle.check(), CheckResult.MISSING)
        find_all(self.puzzle, ("form_request", "filing_permit"))
        for index in range(3):
            self.assertIs(self.puzzle.use_slot(index), SlotResult.NOT_READY)  # два из трёх — ещё рано
        self.assertIsNone(self.puzzle.held)
        self.assertIs(self.puzzle.check(), CheckResult.MISSING)
        self.assertNotIn("leo_application", self.puzzle.order)
        self.assertFalse(self.puzzle.is_found("leo_application"))
        self.assertFalse(self.puzzle.solved)
        self.assertEqual(self.puzzle.failed_checks, 0)

    def test_found_documents_land_on_their_archive_places(self) -> None:
        self.assertIs(self.puzzle.search("requests"), SearchResult.FOUND)
        self.assertEqual(self.puzzle.order, (None, None, "form_request"))
        self.assertEqual(self.puzzle.found, ["form_request"])
        for order in itertools.permutations(DOCUMENTS):
            with self.subTest(order=order):
                puzzle = FormsPuzzle()
                find_all(puzzle, order)
                self.assertTrue(puzzle.all_found)
                # Раскладка архива не зависит от порядка поиска.
                self.assertEqual(puzzle.order, ("filing_permit", "leo_application", "form_request"))
                self.assertEqual(puzzle.first_mistake(), 0)

    def test_wrong_section_does_not_break_anything(self) -> None:
        self.puzzle.search("requests")
        before = (self.puzzle.order, list(self.puzzle.found))
        for section_id in EMPTY_SECTIONS * 3:
            self.assertIs(self.puzzle.search(section_id), SearchResult.NOTHING)
        self.assertEqual((self.puzzle.order, self.puzzle.found), before)
        self.assertEqual(self.puzzle.searches["cakes"], 3)
        find_all(self.puzzle, ("filing_permit", "leo_application"))
        self.assertTrue(self.puzzle.all_found)

    def test_repeated_search_creates_no_extra_documents(self) -> None:
        self.assertIs(self.puzzle.search("births"), SearchResult.FOUND)
        for _ in range(3):
            self.assertIs(self.puzzle.search("births"), SearchResult.EMPTIED)
        self.assertEqual(self.puzzle.found, ["leo_application"])
        self.assertEqual(self.puzzle.order.count("leo_application"), 1)
        self.assertEqual(self.puzzle.found_count, 1)
        self.assertEqual(self.puzzle.searches["births"], 4)

    def test_unknown_section_and_slot_are_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.puzzle.search("basement")
        with self.assertRaises(ValueError):
            self.puzzle.use_slot(3)
        with self.assertRaises(ValueError):
            self.puzzle.use_slot(-1)


class TableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.puzzle = FormsPuzzle()
        find_all(self.puzzle)  # на столе: Согласование, Разрешение, Заявление

    def test_take_and_put_back(self) -> None:
        self.assertIs(self.puzzle.use_slot(0), SlotResult.TAKEN)
        self.assertEqual(self.puzzle.held, "filing_permit")
        self.assertEqual(self.puzzle.order, (None, "leo_application", "form_request"))
        self.assertIs(self.puzzle.use_slot(0), SlotResult.PUT_BACK)
        self.assertIsNone(self.puzzle.held)
        self.assertEqual(self.puzzle.order, ("filing_permit", "leo_application", "form_request"))

    def test_swap_places(self) -> None:
        self.puzzle.use_slot(2)
        self.assertIs(self.puzzle.use_slot(0), SlotResult.SWAPPED)
        self.assertEqual(self.puzzle.order, ("form_request", "leo_application", "filing_permit"))
        self.assertIsNone(self.puzzle.held)
        self.puzzle.use_slot(2)
        self.puzzle.use_slot(1)
        self.assertEqual(self.puzzle.order, CORRECT_ORDER)

    def test_wrong_order_is_not_accepted_but_can_be_retried(self) -> None:
        self.assertIs(self.puzzle.check(), CheckResult.WRONG_ORDER)
        self.assertFalse(self.puzzle.solved)
        self.assertEqual(self.puzzle.failed_checks, 1)
        self.assertEqual(self.puzzle.order, ("filing_permit", "leo_application", "form_request"))  # стол не перемешан
        self.puzzle.use_slot(2)
        self.puzzle.use_slot(0)  # заявление первым, но согласование и разрешение перепутаны
        self.assertEqual(self.puzzle.first_mistake(), 1)
        self.assertIs(self.puzzle.check(), CheckResult.WRONG_ORDER)
        self.assertEqual(self.puzzle.failed_checks, 2)
        arrange(self.puzzle)
        self.assertIsNone(self.puzzle.first_mistake())
        self.assertIs(self.puzzle.check(), CheckResult.ACCEPTED)
        self.assertTrue(self.puzzle.solved)

    def test_cannot_submit_with_a_document_in_hands(self) -> None:
        arrange(self.puzzle)
        self.puzzle.use_slot(1)
        self.assertIs(self.puzzle.check(), CheckResult.HOLDING)
        self.assertFalse(self.puzzle.solved)
        self.assertEqual(self.puzzle.failed_checks, 0)  # это не ошибка порядка
        self.puzzle.use_slot(1)
        self.assertIs(self.puzzle.check(), CheckResult.ACCEPTED)

    def test_accepted_documents_are_locked_and_not_accepted_twice(self) -> None:
        arrange(self.puzzle)
        self.assertIs(self.puzzle.check(), CheckResult.ACCEPTED)
        for _ in range(2):
            self.assertIs(self.puzzle.check(), CheckResult.ALREADY_ACCEPTED)
        for index in range(3):
            self.assertIs(self.puzzle.use_slot(index), SlotResult.LOCKED)
        self.assertEqual(self.puzzle.order, CORRECT_ORDER)
        self.assertIsNone(self.puzzle.held)
        self.assertIs(self.puzzle.search("requests"), SearchResult.EMPTIED)  # и новых документов не появилось
        self.assertEqual(self.puzzle.found_count, 3)

    def test_game_cannot_be_blocked(self) -> None:
        # Любая последовательность действий со столом и проверок оставляет путь к решению.
        actions = [0, 1, 2, "check"]
        for length in range(5):
            for sequence in itertools.product(actions, repeat=length):
                puzzle = FormsPuzzle()
                find_all(puzzle)
                for action in sequence:
                    puzzle.check() if action == "check" else puzzle.use_slot(action)
                documents = [document for document in (*puzzle.order, puzzle.held) if document]
                self.assertEqual(sorted(documents), sorted(DOCUMENTS), sequence)  # ничего не потеряно и не удвоено
                arrange(puzzle)
                result = puzzle.check()
                self.assertIn(result, (CheckResult.ACCEPTED, CheckResult.ALREADY_ACCEPTED), sequence)

    def test_same_actions_give_same_result(self) -> None:
        runs = []
        for _ in range(2):
            puzzle = FormsPuzzle()
            log = [puzzle.search(section.id) for section in SECTIONS]
            log += [puzzle.use_slot(index) for index in (0, 2, 1, 1)] + [puzzle.check()]
            runs.append((log, puzzle.order))
        self.assertEqual(runs[0], runs[1])  # ни капли случайности

    def test_logic_does_not_need_pygame(self) -> None:
        # Отдельный процесс: в этом Pygame уже мог загрузить другой модуль тестов.
        code = "import sys, game.trials.forms_puzzle; print('pygame' in sys.modules)"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "False")


class ProcedureTest(unittest.TestCase):
    """После приёма гусь выдаёт разрешение на получение гражданства, затем свидетельство — строго по очереди."""

    def accepted(self) -> FormsPuzzle:
        puzzle = FormsPuzzle()
        find_all(puzzle)
        arrange(puzzle)
        self.assertIs(puzzle.check(), CheckResult.ACCEPTED)
        return puzzle

    def test_titles_of_what_the_goose_issues(self) -> None:
        self.assertEqual(ISSUED, ("citizenship_permit", "citizenship"))
        self.assertEqual(ISSUED_TITLES["citizenship_permit"], "Разрешение на получение гражданства Лео")
        self.assertIn("гражданстве Лео", ISSUED_TITLES["citizenship"])

    def test_nothing_is_issued_before_the_documents_are_accepted(self) -> None:
        puzzle = FormsPuzzle()
        for document in ISSUED:
            self.assertFalse(puzzle.issue(document))
        find_all(puzzle)
        self.assertFalse(puzzle.issue("citizenship_permit"))  # найдено, но не сдано
        self.assertIs(puzzle.check(), CheckResult.WRONG_ORDER)
        self.assertFalse(puzzle.issue("citizenship_permit"))  # и неверный порядок ничего не даёт
        self.assertEqual(puzzle.issued, [])
        self.assertFalse(puzzle.citizen)

    def test_permit_first_then_citizenship_and_never_twice(self) -> None:
        puzzle = self.accepted()
        self.assertFalse(puzzle.issue("citizenship"))  # гражданство без разрешения на получение — нельзя
        self.assertEqual(puzzle.issued, [])
        self.assertTrue(puzzle.issue("citizenship_permit"))
        self.assertFalse(puzzle.issue("citizenship_permit"))  # второе такое же разрешение не выдают
        self.assertFalse(puzzle.citizen)
        self.assertTrue(puzzle.issue("citizenship"))
        self.assertTrue(puzzle.citizen)
        for document in ISSUED:
            self.assertFalse(puzzle.issue(document))
        self.assertEqual(puzzle.issued, ["citizenship_permit", "citizenship"])
        self.assertEqual(puzzle.order, CORRECT_ORDER)  # стол не тронут

    def test_unknown_issued_document_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            self.accepted().issue("passport")


if __name__ == "__main__":
    unittest.main()
