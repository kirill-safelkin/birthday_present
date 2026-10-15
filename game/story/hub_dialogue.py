"""Реплики центральной площади: разговор с Чучмеком, Лео в корзинке и сообщения у неготовых порталов.

Здесь только данные. Показывает их game/world/hub.py через существующую систему диалогов.

С Чучмеком в первый раз — знакомство с площадью, потом сразу вопрос: у Алисы выбор
(совет о порталах или что поручено Лео), ветки сходятся в общей реплике. Повторный разговор
начинается с того же вопроса, без приветствия. Ни один ответ не переводит в испытание.
Лео спит в корзинке и не говорит: у корзинки — по одной короткой реплике по кругу.
"""

from __future__ import annotations

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE, CHUCHMEK

# Вопрос, на который Алиса отвечает выбором, и общая реплика, где ветки сходятся.
HUB_CHOICE_ID = "h_question"
HUB_JOIN_ID = "h_mosaic"
HUB_CHOICES = (
    DialogueChoice("С какого испытания лучше начать?", "h_where"),
    DialogueChoice("А что конкретно ты поручил Лео?", "h_leo"),
)

_TALK_NODES = (
    DialogueNode("h_welcome", CHUCHMEK, "Добро пожаловать на центральную площадь!", next_id="h_why"),
    DialogueNode("h_why", ALICE, "Почему она центральная?", next_id="h_because"),
    DialogueNode(
        "h_because", CHUCHMEK, "Потому что если бы она была боковой, её пришлось бы искать.", next_id=HUB_CHOICE_ID
    ),
    DialogueNode(HUB_CHOICE_ID, CHUCHMEK, "Вопросы к организатору?", choices=HUB_CHOICES),
    DialogueNode("h_again", CHUCHMEK, "Снова к организатору? Слушаю.", choices=HUB_CHOICES),
    # Ветка «с чего начать»: совет, но не приказ.
    DialogueNode(
        "h_where", CHUCHMEK, "С любого. Слева суши, справа торты, документы где-то между ними. Как и в жизни.",
        next_id="h_hungry",
    ),
    DialogueNode(
        "h_hungry", CHUCHMEK, "Порядок не важен. Важно, чтобы именинница не проголодалась: это главная угроза плану.",
        next_id=HUB_JOIN_ID,
    ),
    # Ветка про Лео: его должность и критерий проверки.
    DialogueNode(
        "h_leo", CHUCHMEK, "Контроль качества. Если Лео улыбнётся — пункт плана утверждён.", next_id="h_yawn"
    ),
    DialogueNode("h_yawn", ALICE, "А если зевнёт?", next_id="h_commission"),
    DialogueNode(
        "h_commission", CHUCHMEK, "Значит, пункт на доработку. Или комиссии пора спать. Это мы ещё уточняем.",
        next_id=HUB_JOIN_ID,
    ),
    DialogueNode(
        HUB_JOIN_ID, CHUCHMEK, "Фрагменты собираются в мозаике в центре. Когда будут все три — подойди к ней сама."
    ),
)
CHUCHMEK_TALK = DialogueScript("h_welcome", _TALK_NODES)
CHUCHMEK_TALK_AGAIN = DialogueScript("h_again", _TALK_NODES)

# Лео в корзинке: реплики рассказчика по кругу — каждая следующая встреча со своей.
LEO_LINES = (
    "Лео сладко спит в корзинке. Проверка праздничного настроения идёт полным ходом.",
    "Лео улыбается во сне. Кажется, ещё один пункт плана только что утверждён.",
    "Лео тихонько сопит. Тише: главный инспектор совещается сам с собой.",
)


def leo_script(visit: int) -> DialogueScript:
    """Одна реплика у корзинки Лео. visit — номер подхода с единицы."""
    return DialogueScript("leo", [DialogueNode("leo", "", LEO_LINES[(visit - 1) % len(LEO_LINES)])])


# Порталы пока не подключены к испытаниям: Чучмек объясняет, что они не готовы.
PORTAL_NOT_READY = {
    "sushi": DialogueScript(
        "p_sushi",
        [DialogueNode("p_sushi", CHUCHMEK, "Портал пока не готов. Кот-повар точит нож. Надеюсь, для суши.")],
    ),
    "forms": DialogueScript(
        "p_forms",
        [
            DialogueNode(
                "p_forms", CHUCHMEK, "Портал пока не готов. Для входа необходимо заполнить форму на разрешение входа."
            )
        ],
    ),
    "cakes": DialogueScript(
        "p_cakes",
        [
            DialogueNode(
                "p_cakes",
                CHUCHMEK,
                "Портал пока не готов. Чучмек утверждает, что с тортами всё под контролем. Это тревожный знак.",
            )
        ],
    ),
}


def all_scripts() -> list[DialogueScript]:
    leo = [leo_script(visit) for visit in range(1, len(LEO_LINES) + 1)]
    return [CHUCHMEK_TALK, CHUCHMEK_TALK_AGAIN, *leo, *PORTAL_NOT_READY.values()]
