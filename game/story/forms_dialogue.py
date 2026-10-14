"""Реплики испытания формуляров: вступление, находки в архиве, подсказки и отказы гуся,
реакция на правильный порядок и финальная проверка. Только данные.

Показывает их game/trials/forms_scene.py через существующую систему диалогов.
GOOSE_POSES — какую позу (кадр goose_inspector) принимает гусь на реплике.
"""

from __future__ import annotations

from game.dialogue.model import DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE
from game.trials.forms_puzzle import DOCUMENTS, SECTIONS, SearchResult

GOOSE = "Гусь-инспектор"


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


INTRO = _script(
    DialogueNode(
        "i_stop", GOOSE, "Стоять. Вход в архив разрешён при наличии разрешения на вход в архив.", next_id="i_need"
    ),
    DialogueNode("i_need", ALICE, "Мне нужно разрешение на праздник.", next_id="i_address"),
    DialogueNode(
        "i_address",
        GOOSE,
        "Тогда вы пришли по адресу. Здесь хранятся все разрешения, кроме тех, которые мы ещё не разрешили хранить.",
        next_id="i_where",
    ),
    DialogueNode("i_where", ALICE, "И где искать моё?", next_id="i_department"),
    DialogueNode(
        "i_department",
        GOOSE,
        "В соответствующем отделе. Если бы я знал, где он, я бы уже давно его закрыл.",
        next_id="i_three",
    ),
    DialogueNode(
        "i_three",
        GOOSE,
        "Для праздника нужны три бумаги: заявление, согласование и разрешение. Ищите в шкафах.",
        next_id="i_table",
    ),
    DialogueNode(
        "i_table",
        GOOSE,
        "Найденное архив сам кладёт на стол подачи. По алфавиту, задом наперёд — так труднее найти.",
        next_id="i_order",
    ),
    DialogueNode("i_order", GOOSE, "А сдавать — мне. В установленном порядке. Установлен он давно, но держится."),
)

# Находки по разделам: документ (FOUND), повторный поиск там же (EMPTIED) и шутки
# пустых разделов (NOTHING) — они идут по кругу, без случайностей.
SEARCH_TEXTS = {
    "permits": {
        SearchResult.FOUND: (
            "«Разрешение на праздник»! Лежало между разрешением на разрешение и разрешением на отказ.",
        ),
        SearchResult.EMPTIED: ("«Разрешение на чихание в архиве». Срок действия истёк. Лучше не чихать.",),
    },
    "cakes": {
        SearchResult.NOTHING: (
            "«Торт „Наполеон“. Признан документом в 1812 году». Подпись сделана кремом.",
            "«Медовик». Срок хранения — бессрочно. Пахнет архивом. Не тот документ.",
            "Опись тортов, признанных недействительными. Пустая: их съели до признания.",
        ),
    },
    "holidays": {
        SearchResult.FOUND: (
            "«Заявление на проведение праздника»! Лежало среди несостоявшихся. Мой праздник тоже пока не состоялся.",
        ),
        SearchResult.EMPTIED: ("Остались только несостоявшиеся. «День без бумаг» — его даже не планировали.",),
    },
    "department": {
        SearchResult.NOTHING: (
            "Тот самый соответствующий отдел! Внутри записка: «Отдел закрыт. Где — не сообщается».",
            "Под запиской ещё одна: «Если вы это читаете, отдел снова переехал».",
        ),
    },
    "requests": {
        SearchResult.FOUND: (
            "«Согласование ответственного лица». Ответственное лицо — гусь. Согласовал сам с собой. Удобно.",
        ),
        SearchResult.EMPTIED: ("Ещё заявки. «Заявка на отзыв заявки на подачу заявки». Хватит с меня заявок.",),
    },
}

# Подсказка гуся о первом ненайденном документе.
MISSING_HINTS = {
    "application": "Не хватает заявления. Ищите среди праздников, которые не состоялись. Ваш пока там же.",
    "approval": "Не хватает согласования. Оно с заявками — единственное, что у нас лежит на своём месте.",
    "permission": "Не хватает разрешения. Разрешения хранятся среди других разрешений. Логично, но подозрительно.",
}
HOLDING_TEXT = "Документ в руках — не документ, а намерение. Положите его на стол, потом сдавайте."

REJECTION_JOKES = (
    "Отказано. Документы поданы в художественном порядке, а нужен — в установленном.",
    "Снова отказано. Я бы подсказал, но подсказка требует согласования.",
    "Отказано. Не расстраивайтесь: отказ — тоже документ. Подошьём к остальным.",
)
# Неофициальная подсказка о первом месте на столе, где лежит не тот документ.
REJECTION_HINTS = (
    "Неофициально: первым подают заявление. Без него никто не знает, о чём вы вообще просите.",
    "Неофициально: заявление на месте. Но разрешают только согласованное — согласование идёт раньше разрешения.",
    "Неофициально: разрешение всегда приходит последним. Как и я на работу.",
)

INSPECTION = _script(  # реакция гуся на правильный порядок
    DialogueNode(
        "r_inspect",
        GOOSE,
        "Так. Заявление. Согласование. Разрешение. Всё по порядку. Подозрительно по порядку.",
        next_id="r_stamp",
    ),
    DialogueNode(
        "r_stamp", "", "Гусь ставит три печати: одну на документы и две — для настроения.", next_id="r_approve"
    ),
    DialogueNode("r_approve", GOOSE, "Принято. Обычно до этой печати никто не доходит. Я даже чернила не менял."),
)

FINAL = _script(
    DialogueNode(
        "f_exists",
        GOOSE,
        "Заявление подано, согласование получено, разрешение разрешено. Формально праздник существует.",
        next_id="f_can",
    ),
    DialogueNode("f_can", ALICE, "А праздновать уже можно?", next_id="f_separate"),
    DialogueNode("f_separate", GOOSE, "Не торопитесь. На это потребуется отдельное разрешение.", next_id="f_fragment"),
    DialogueNode(
        "f_fragment", GOOSE, "Но фрагмент праздника выдам сейчас. Без очереди. Никому не говорите — это не по форме."
    ),
)

GOOSE_POSES = {
    "i_stop": "reject",
    "i_address": "talk",
    "i_department": "question",
    "i_three": "talk",
    "i_table": "read",
    "i_order": "inspect",
    "hint": "question",
    "holding": "inspect",
    "reject_joke": "reject",
    "reject_hint": "talk",
    "r_inspect": "inspect",
    "r_stamp": "stamp",
    "r_approve": "approve",
    "f_exists": "read",
    "f_separate": "write",
    "f_fragment": "celebrate",
}
GOOSE_IDLE_POSE = "idle"


def search_script(section_id: str, result: SearchResult, visit: int) -> DialogueScript:
    """Что Алиса нашла в разделе архива. visit — номер поиска в этом разделе, с единицы."""
    texts = SEARCH_TEXTS[section_id][result]
    return _script(DialogueNode("search", ALICE, texts[(visit - 1) % len(texts)]))


def goose_hint(missing: str | None) -> DialogueScript:
    """Гусь подсказывает, какого документа не хватает (missing — первый ненайденный)."""
    return _script(DialogueNode("hint", GOOSE, MISSING_HINTS[missing]))


def goose_holding() -> DialogueScript:
    """Алиса хочет сдать документы, а один из них у неё в руках."""
    return _script(DialogueNode("holding", GOOSE, HOLDING_TEXT))


def goose_rejection(attempt: int, mistake: int) -> DialogueScript:
    """Отказ гуся: attempt — номер неудачной проверки с единицы, mistake — первое неверное место."""
    return _script(
        DialogueNode(
            "reject_joke", GOOSE, REJECTION_JOKES[(attempt - 1) % len(REJECTION_JOKES)], next_id="reject_hint"
        ),
        DialogueNode("reject_hint", GOOSE, REJECTION_HINTS[mistake]),
    )


def all_scripts() -> list[DialogueScript]:
    """Все сценарии испытания, включая собранные по ходу игры, — для проверки, что они помещаются на экран."""
    scripts = [INTRO, INSPECTION, FINAL, goose_holding()]
    for section in SECTIONS:
        for result, texts in SEARCH_TEXTS[section.id].items():
            scripts += [search_script(section.id, result, visit) for visit in range(1, len(texts) + 1)]
    scripts += [goose_hint(document) for document in DOCUMENTS]
    scripts += [
        goose_rejection(attempt, mistake)
        for attempt in range(1, len(REJECTION_JOKES) + 1)
        for mistake in range(len(REJECTION_HINTS))
    ]
    return scripts
