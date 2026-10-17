"""Реплики центральной площади: разговор с Чучмеком, Лео в корзинке и сообщения у неготовых порталов.

Здесь только данные. Показывает их game/world/hub.py через существующую систему диалогов.

С Чучмеком в первый раз — знакомство с площадью, потом сразу вопрос: у Алисы выбор
(что за порталами или что поручено Лео), ветки сходятся в общем напоминании: праздник ещё
не собран, три испытания — по фрагменту за каждое, все три откроют мозаику. Повторный
разговор начинается с того же вопроса, без приветствия, и заканчивается тем же напоминанием.
Что внутри испытаний, Чучмек не рассказывает и порядок не подсказывает: это игрок узнаёт
в самих порталах. Ни один ответ не переводит в испытание.
Лео — младенец в корзинке: он то спит, то смеётся, то просто сидит и смотрит по сторонам
(позы и их смена — game/world/leo.py). Если к нему подойти, он отвечает одним коротким звуком
по своему настроению: спящий только сопит, смеющийся хихикает, проснувшийся агукает.
Взрослых фраз у Лео нет.
"""

from __future__ import annotations

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE, CHUCHMEK
from game.world.leo import AWAKE, LAUGH, SLEEP

LEO = "Лео"

# Вопрос, на который Алиса отвечает выбором, и общая реплика, где ветки сходятся.
HUB_CHOICE_ID = "h_question"
HUB_JOIN_ID = "h_rules"
HUB_CHOICES = (
    DialogueChoice("А что там, за порталами?", "h_secret"),
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
    # Ветка «что за порталами»: Чучмек бережёт интригу.
    DialogueNode(
        "h_secret", CHUCHMEK, "Сюрприз. Если я расскажу, это будет уже не сюрприз, а инструктаж.", next_id="h_fair"
    ),
    DialogueNode("h_fair", ALICE, "Справедливо. Но подозрительно.", next_id=HUB_JOIN_ID),
    # Ветка про Лео: его должность и критерий проверки.
    DialogueNode(
        "h_leo",
        CHUCHMEK,
        "Он главный инспектор праздничного настроения. Если Лео улыбнётся — пункт плана утверждён.",
        next_id="h_yawn",
    ),
    DialogueNode("h_yawn", ALICE, "А если зевнёт?", next_id="h_commission"),
    DialogueNode(
        "h_commission", CHUCHMEK, "Значит, пункт на доработку. Или комиссии пора спать. Это мы ещё уточняем.",
        next_id=HUB_JOIN_ID,
    ),
    # Общее напоминание — при любом ответе и при каждом разговоре.
    DialogueNode(
        HUB_JOIN_ID,
        CHUCHMEK,
        "Праздник пока не собран. Правило простое: три испытания, за каждое — фрагмент плана.",
        next_id="h_mosaic",
    ),
    DialogueNode(
        "h_mosaic", CHUCHMEK, "Фрагменты собираются в мозаике в центре. Когда будут все три — подойди к ней сама."
    ),
)
CHUCHMEK_TALK = DialogueScript("h_welcome", _TALK_NODES)
CHUCHMEK_TALK_AGAIN = DialogueScript("h_again", _TALK_NODES)

# Что Лео «говорит», когда к нему подходят, — по настроению. Сон — подпись в звёздочках.
LEO_SOUNDS = {
    SLEEP: ("*сопит*", "*сладко посапывает*", "*причмокивает во сне*"),
    LAUGH: ("Хи-хи!", "Хи-хи-хи!", "Ха-ха!"),
    AWAKE: ("Агу-агу!", "Угу!", "А-а?", "Агу?", "Гу-гу!"),
}


def leo_script(text: str) -> DialogueScript:
    """Одна короткая реплика Лео у корзинки, без выбора."""
    return DialogueScript("leo", [DialogueNode("leo", LEO, text)])


# Порталы пока не подключены к испытаниям: Чучмек объясняет, что они не готовы.
PORTAL_NOT_READY = {
    "sushi": DialogueScript(
        "p_sushi",
        [DialogueNode("p_sushi", CHUCHMEK, "Портал пока не готов. Майкл-повар точит нож. Надеюсь, для суши.")],
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
    leo = [leo_script(text) for sounds in LEO_SOUNDS.values() for text in sounds]
    return [CHUCHMEK_TALK, CHUCHMEK_TALK_AGAIN, *leo, *PORTAL_NOT_READY.values()]
