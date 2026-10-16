"""Логика испытания формуляров без Pygame: разделы архива, найденные документы,
стол подачи, проверка порядка и то, что гусь выдаёт после приёма.

Сказочный архив не признаёт Лео, пока его рождение не зарегистрировано, а для этого нужны
три документа. Они лежат в разных разделах архива. Найденный документ архив сам кладёт на стол
подачи — на своё «архивное» место (по алфавиту задом наперёд), поэтому порядок на столе поначалу
всегда неверный. Когда найдены все три, документы на столе можно менять местами: взять один
и положить на место другого. Документ в руках всегда можно вернуть обратно, поэтому застрять
невозможно. Проверка (check) засчитывает только порядок «заявление на выдачу бланка → разрешение
на подачу → заявление о регистрации»; неверный порядок не засчитывается и ничего не портит,
а принятые документы не принимаются повторно.

После приёма гусь по очереди выдаёт ещё два документа (issue): разрешение на получение
гражданства и само свидетельство о гражданстве. Это вымышленная бюрократия Страны Чудес,
а не настоящие правила.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

# Документы в правильном порядке подачи: сначала просят бланк, потом разрешение подать
# заявление, и только потом подают само заявление.
DOCUMENTS = ("form_request", "filing_permit", "leo_application")
CORRECT_ORDER = DOCUMENTS
# Полные названия — в находках и репликах гуся.
DOCUMENT_TITLES = {
    "form_request": "Заявление на выдачу бланка заявления",
    "filing_permit": "Разрешение на подачу заявления",
    "leo_application": "Заявление о регистрации рождения и гражданстве Лео",
}
# Короткие — в строке подсказок и сообщениях, где полное название не помещается (обмен двух
# документов, место на столе): те же слова без сокращений. На листах и в «В руках» — полные.
DOCUMENT_NAMES = {
    "form_request": "Заявление на бланк",
    "filing_permit": "Разрешение на подачу",
    "leo_application": "Заявление о Лео",
}
SLOT_COUNT = len(DOCUMENTS)
# Куда архив кладёт найденный документ: по полным названиям в алфавитном порядке задом наперёд
# (Разрешение…, Заявление о…, Заявление на…) — ни один документ не на своём месте.
ARCHIVE_SLOTS = {
    document: slot for slot, document in enumerate(sorted(DOCUMENTS, key=DOCUMENT_TITLES.get, reverse=True))
}

# Что гусь выдаёт после приёма документов — строго по очереди.
ISSUED = ("citizenship_permit", "citizenship")
ISSUED_TITLES = {
    "citizenship_permit": "Разрешение на получение гражданства Лео",
    "citizenship": "Свидетельство о гражданстве Лео",
}


@dataclass(frozen=True)
class Section:
    """Раздел архива (шкаф). document — что в нём лежит из нужного, None — ничего."""

    id: str
    name: str  # полное название раздела
    label: str  # короткая надпись на шкафу
    document: str | None = None

    def __post_init__(self) -> None:
        if self.document is not None and self.document not in DOCUMENTS:
            raise ValueError(f"в разделе «{self.name}» неизвестный документ {self.document!r}")


SECTIONS = (
    Section("permits", "Разрешения на другие разрешения", "Разрешения", "filing_permit"),
    Section("cakes", "Торты, признанные документами", "Торты"),
    Section("births", "Рождения, ожидающие регистрации", "Рождения", "leo_application"),
    Section("department", "Соответствующий отдел", "Отдел"),
    Section("requests", "Заявки, которые ещё не стали заявлениями", "Заявки", "form_request"),
)


class SearchResult(Enum):
    FOUND = "found"  # нашёлся документ — архив положил его на стол подачи
    NOTHING = "nothing"  # нужного здесь нет и не было
    EMPTIED = "emptied"  # документ отсюда уже забран — больше ничего нужного нет


class SlotResult(Enum):
    TAKEN = "taken"  # документ взят со стола
    PUT_BACK = "put_back"  # документ положен обратно на освободившееся место
    SWAPPED = "swapped"  # документ из рук и документ с этого места поменялись местами
    NOT_READY = "not_ready"  # ещё не все документы найдены — раскладывать рано
    LOCKED = "locked"  # документы уже приняты


class CheckResult(Enum):
    ACCEPTED = "accepted"  # порядок верный — документы приняты
    WRONG_ORDER = "wrong_order"  # не засчитано, можно переложить и сдать снова
    MISSING = "missing"  # найдены не все документы
    HOLDING = "holding"  # один документ в руках, а не на столе
    ALREADY_ACCEPTED = "already_accepted"  # повторная проверка ничего не даёт


class FormsPuzzle:
    """Что найдено в архиве, что лежит на столе подачи, что у Алисы в руках и что гусь уже выдал."""

    def __init__(self, sections: Iterable[Section] = SECTIONS) -> None:
        self.sections = {section.id: section for section in sections}
        hidden = [section.document for section in self.sections.values() if section.document is not None]
        if sorted(hidden) != sorted(DOCUMENTS):
            raise ValueError("каждый документ должен лежать ровно в одном разделе архива")
        self.found: list[str] = []  # в порядке находки
        self.searches = dict.fromkeys(self.sections, 0)  # сколько раз искали в каждом разделе
        self._slots: list[str | None] = [None] * SLOT_COUNT
        self.held: str | None = None
        self.held_from: int | None = None  # место на столе, с которого взят документ
        self.solved = False
        self.failed_checks = 0
        self.issued: list[str] = []  # что гусь выдал после приёма, по порядку

    # --- Состояние ---

    @property
    def order(self) -> tuple[str | None, ...]:
        """Что лежит на местах стола 1, 2, 3 (None — пусто)."""
        return tuple(self._slots)

    @property
    def found_count(self) -> int:
        return len(self.found)

    @property
    def all_found(self) -> bool:
        return len(self.found) == len(DOCUMENTS)

    def is_found(self, document: str) -> bool:
        return document in self.found

    @property
    def citizen(self) -> bool:
        """Процедура закончена: Лео выдано свидетельство о гражданстве."""
        return self.issued == list(ISSUED)

    def first_mistake(self) -> int | None:
        """Первое место стола, где лежит не тот документ (или пусто). None — порядок верный."""
        for index, document in enumerate(CORRECT_ORDER):
            if self._slots[index] != document:
                return index
        return None

    # --- Действия ---

    def search(self, section_id: str) -> SearchResult:
        """Поиск в разделе архива. Повторный поиск не создаёт новых документов."""
        section = self.sections.get(section_id)
        if section is None:
            raise ValueError(f"неизвестный раздел архива {section_id!r}")
        self.searches[section_id] += 1
        document = section.document
        if document is None:
            return SearchResult.NOTHING
        if document in self.found:
            return SearchResult.EMPTIED
        self.found.append(document)
        self._slots[self._free_slot(ARCHIVE_SLOTS[document])] = document
        return SearchResult.FOUND

    def _free_slot(self, preferred: int) -> int:
        # Пока не найдены все документы, раскладывать нельзя, поэтому архивное место свободно.
        # Запасной вариант — первое свободное место: документ никогда не теряется.
        if self._slots[preferred] is None:
            return preferred
        return self._slots.index(None)

    def use_slot(self, index: int) -> SlotResult:
        """Взаимодействие с местом стола: взять документ, положить обратно или поменять местами."""
        if not 0 <= index < SLOT_COUNT:
            raise ValueError(f"на столе нет места {index}")
        if self.solved:
            return SlotResult.LOCKED
        if not self.all_found:
            return SlotResult.NOT_READY
        if self.held is None:
            self.held, self._slots[index] = self._slots[index], None
            self.held_from = index
            return SlotResult.TAKEN
        if index == self.held_from:
            self._slots[index] = self.held
            self.held = self.held_from = None
            return SlotResult.PUT_BACK
        # Документ с этого места переезжает туда, откуда взят документ из рук.
        self._slots[self.held_from] = self._slots[index]
        self._slots[index] = self.held
        self.held = self.held_from = None
        return SlotResult.SWAPPED

    def check(self) -> CheckResult:
        """Сдать документы на проверку."""
        if self.solved:
            return CheckResult.ALREADY_ACCEPTED
        if not self.all_found:
            return CheckResult.MISSING
        if self.held is not None:
            return CheckResult.HOLDING
        if self.first_mistake() is None:
            self.solved = True
            return CheckResult.ACCEPTED
        self.failed_checks += 1
        return CheckResult.WRONG_ORDER

    def issue(self, document: str) -> bool:
        """Гусь выдаёт документ процедуры. Только после приёма и только следующий по очереди:
        сначала разрешение на получение гражданства, потом свидетельство. Повторно не выдаётся."""
        if document not in ISSUED:
            raise ValueError(f"неизвестный выдаваемый документ {document!r}")
        if not self.solved or len(self.issued) == len(ISSUED) or ISSUED[len(self.issued)] != document:
            return False
        self.issued.append(document)
        return True
