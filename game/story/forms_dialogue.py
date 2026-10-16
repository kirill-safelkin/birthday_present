"""Реплики испытания формуляров: вступление, находки в архиве, подсказки и отказы гуся,
приём документов, разрешение на получение гражданства и само гражданство Лео. Только данные.

Сюжет: Лео уже родился и спит на площади, но сказочный архив его не признаёт — рождение
не зарегистрировано, гражданства нет. Гусь-инспектор не может признать очевидное без документа,
а документ — без разрешения. Это вымышленная бюрократия Страны Чучмека, а не настоящие правила.
Во вступлении и при сдаче документов у Алисы выбор: гусь отвечает по-разному, но задача одна
и та же, и ни один ответ не находит документы и не сдаёт их за игрока.

Показывает их game/trials/forms_scene.py через существующую систему диалогов.
GOOSE_POSES — какую позу (кадр goose_inspector) принимает гусь на реплике;
ISSUE_NODES — на какой реплике гусь выдаёт документ процедуры (сцена его показывает).
"""

from __future__ import annotations

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE
from game.trials.forms_puzzle import DOCUMENTS, SECTIONS, SearchResult

GOOSE = "Гусь-инспектор"
REGISTER_CHOICE_ID = "i_register"  # выбор Алисы во вступлении
OATH_CHOICE_ID = "r_oath"  # выбор Алисы, когда гусь принимает документы


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


INTRO = _script(
    DialogueNode(
        "i_stop", GOOSE, "Стойте. Для подготовки праздника необходимо проверить реестр участников.", next_id="i_here"
    ),
    DialogueNode("i_here", ALICE, "Проверяйте. Лео уже здесь — спит в корзинке на площади.", next_id="i_registry"),
    DialogueNode(
        "i_registry",
        GOOSE,
        "В реестре Страны Чучмека Лео не значится: ни рождения, ни гражданства. Есть только отметка «сопит».",
        next_id="i_presence",
    ),
    DialogueNode(
        "i_presence",
        GOOSE,
        "Присутствие не заменяет регистрацию. Регистрация не заменяет разрешение. "
        "А разрешение не заменяет разрешение на получение разрешения.",
        next_id=REGISTER_CHOICE_ID,
    ),
    DialogueNode(
        REGISTER_CHOICE_ID,
        GOOSE,
        "Итак. С чем пожаловали?",
        choices=[
            DialogueChoice("Мы просто хотим зарегистрировать Лео.", "i_simply"),
            DialogueChoice("А есть заявление на разрешение заявления?", "i_expert"),
        ],
    ),
    DialogueNode(
        "i_simply",
        GOOSE,
        "Просто? Младенец, который просто присутствует, для архива — слух. А слухи не подшивают.",
        next_id="i_not_rumour",
    ),
    DialogueNode("i_not_rumour", ALICE, "Лео не слух. Он сопит.", next_id="i_first"),
    DialogueNode(
        "i_expert", GOOSE, "Наконец-то специалист! Именно такая бумага нам и нужна. Ну, почти такая.", next_id="i_first"
    ),
    DialogueNode(
        "i_first",
        GOOSE,
        "Тогда действуем по порядку. Сначала найдём заявление на выдачу бланка заявления.",
        next_id="i_then",
    ),
    DialogueNode("i_then", ALICE, "А потом?", next_id="i_procedure"),
    DialogueNode(
        "i_procedure",
        GOOSE,
        "Потом — разрешение на подачу заявления. Потом — само заявление о регистрации рождения и гражданстве Лео.",
        next_id="i_known",
    ),
    DialogueNode(
        "i_known",
        GOOSE,
        "А дальше моя часть: печати, разрешения и официальное признание того, что всем и так известно.",
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
            "«Разрешение на подачу заявления»! Лежало между разрешением на разрешение и разрешением на отказ.",
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
    "births": {
        SearchResult.FOUND: (
            "«Заявление о регистрации рождения и гражданстве Лео»! В папке «Срочно». "
            "Судя по пыли, срочно с прошлого века.",
        ),
        SearchResult.EMPTIED: (
            "Остальные рождения ждут дальше. Один дракон ждёт регистрации с 1302 года. Терпеливый.",
        ),
    },
    "department": {
        SearchResult.NOTHING: (
            "Тот самый соответствующий отдел! Внутри записка: «Отдел закрыт. Где — не сообщается».",
            "Под запиской ещё одна: «Если вы это читаете, отдел снова переехал».",
        ),
    },
    "requests": {
        SearchResult.FOUND: (
            "«Заявление на выдачу бланка заявления»! Без него не дают бланк, а без бланка его не напишешь. "
            "Хорошо, что оно уже есть.",
        ),
        SearchResult.EMPTIED: ("Ещё заявки. «Заявка на отзыв заявки на подачу заявки». Хватит с меня заявок.",),
    },
}

# Подсказка гуся о первом ненайденном документе: только где искать его, без всего порядка.
MISSING_HINTS = {
    "form_request": "Не хватает заявления на выдачу бланка. Ищите среди заявок, которые ещё не стали заявлениями.",
    "filing_permit": "Не хватает разрешения на подачу. Разрешения хранятся среди других разрешений. "
                     "Логично, но подозрительно.",
    "leo_application": "Не хватает заявления о Лео. Оно среди рождений, ожидающих регистрации. Ждёт, как и он.",
}
HOLDING_TEXT = "Документ в руках — не документ, а намерение. Положите его на стол, потом сдавайте."

REJECTION_JOKES = (
    "Отказано. Документы поданы в художественном порядке, а нужен — в установленном.",
    "Снова отказано. Я бы подсказал, но подсказка требует согласования.",
    "Отказано. Не расстраивайтесь: отказ — тоже документ. Подошьём к остальным.",
)
# Неофициальная подсказка о первом месте на столе, где лежит не тот документ.
REJECTION_HINTS = (
    "Неофициально: первым подают заявление на выдачу бланка. Без бланка не на чем просить остальное.",
    "Неофициально: бланк на месте. Но подать заявление можно только с разрешением на подачу — оно второе.",
    "Неофициально: заявление о Лео подают последним. Как и я прихожу на работу.",
)

# Гусь принимает документы: присяга заявителя (выбор), проверка пакета и разрешение на получение
# гражданства. Документы уже приняты — ответ на присягу меняет только реплику гуся.
INSPECTION = _script(
    DialogueNode("r_oath_intro", GOOSE, "Стоп. Перед приёмом — устная присяга заявителя.", next_id=OATH_CHOICE_ID),
    DialogueNode(
        OATH_CHOICE_ID,
        GOOSE,
        "Клянётесь, что Лео существует?",
        choices=[
            DialogueChoice("Клянусь. Он сопит на площади.", "r_snore"),
            DialogueChoice("А на присягу нужно разрешение?", "r_oath_permit"),
        ],
    ),
    DialogueNode(
        "r_snore", GOOSE, "Сопение принимается вместо подписи. Неразборчиво, но искренне.", next_id="r_inspect"
    ),
    DialogueNode(
        "r_oath_permit", GOOSE, "Нужно. Выдаю его себе устно. Готово: вы приведены к присяге.", next_id="r_inspect"
    ),
    DialogueNode(
        "r_inspect",
        GOOSE,
        "Заявление принято. Все три документа в правильном порядке. Это подозрительно, но я обязан продолжить.",
        next_id="r_registered",
    ),
    DialogueNode("r_registered", ALICE, "Теперь Лео зарегистрирован?", next_id="r_almost"),
    DialogueNode(
        "r_almost",
        GOOSE,
        "Почти. Сначала необходимо получить разрешение на получение гражданства.",
        next_id="r_already",
    ),
    DialogueNode("r_already", ALICE, "Но мы ведь уже получили разрешение на подачу заявления.", next_id="r_different"),
    DialogueNode(
        "r_different",
        GOOSE,
        "То было разрешение на подачу. А это — на получение. Разница очевидна: у них разные печати.",
        next_id="r_stamp",
    ),
    DialogueNode(
        "r_stamp",
        "",
        "Гусь ставит печать, потом ещё одну — на печать. Готово «Разрешение на получение гражданства Лео».",
        next_id="r_approve",
    ),
    DialogueNode("r_approve", GOOSE, "Выдано. Обычно до этой печати никто не доходит. Я даже чернила не менял."),
)

# Гражданство и финал испытания: свидетельство, затем фрагмент праздничного плана.
FINAL = _script(
    DialogueNode(
        "f_decree",
        GOOSE,
        "На основании разрешения на получение гражданства постановляю: Лео признан гражданином Страны Чучмека.",
        next_id="f_certificate",
    ),
    DialogueNode(
        "f_certificate",
        "",
        "Гусь вручает свидетельство: «Рождение Лео зарегистрировано. Лео — гражданин Страны Чучмека». "
        "Печатей на нём больше, чем букв.",
        next_id="f_sneeze",
    ),
    DialogueNode(
        "f_sneeze", "", "Где-то на площади Лео чихает во сне. Гусь вносит это в протокол как ответную речь.",
        next_id="f_congrats",
    ),
    DialogueNode("f_congrats", ALICE, "Поздравляю Лео! Теперь можно отмечать день рождения?", next_id="f_sleep"),
    DialogueNode(
        "f_sleep",
        GOOSE,
        "Можно. Но гражданство не освобождает от ответственности за сон во время официальных мероприятий.",
        next_id="f_fragment",
    ),
    DialogueNode(
        "f_fragment",
        GOOSE,
        "И вот что было подшито к делу Лео: фрагмент праздничного плана. Выдаю без очереди. "
        "Никому не говорите — это не по форме.",
    ),
)

# На какой реплике гусь выдаёт документ процедуры (по порядку, см. FormsPuzzle.issue).
ISSUE_NODES = {"r_stamp": "citizenship_permit", "f_certificate": "citizenship"}

GOOSE_POSES = {
    "i_stop": "reject",
    "i_registry": "read",
    "i_presence": "talk",
    REGISTER_CHOICE_ID: "inspect",
    "i_simply": "question",
    "i_expert": "approve",
    "i_first": "talk",
    "i_procedure": "write",
    "i_known": "inspect",
    "i_table": "read",
    "i_order": "inspect",
    "hint": "question",
    "holding": "inspect",
    "reject_joke": "reject",
    "reject_hint": "talk",
    "r_oath_intro": "inspect",
    OATH_CHOICE_ID: "question",
    "r_snore": "approve",
    "r_oath_permit": "write",
    "r_inspect": "inspect",
    "r_almost": "question",
    "r_different": "talk",
    "r_stamp": "stamp",
    "r_approve": "approve",
    "f_decree": "read",
    "f_certificate": "celebrate",
    "f_sneeze": "write",
    "f_sleep": "talk",
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
