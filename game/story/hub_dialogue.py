"""Реплики центральной площади: разговор с Чучмеком и сообщения у неготовых порталов.

Здесь только данные. Показывает их game/world/hub.py через существующую систему диалогов.
"""

from __future__ import annotations

from game.dialogue.model import DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE, CHUCHMEK

CHUCHMEK_TALK = DialogueScript(
    "h_welcome",
    [
        DialogueNode("h_welcome", CHUCHMEK, "Добро пожаловать на центральную площадь!", next_id="h_why"),
        DialogueNode("h_why", ALICE, "Почему она центральная?", next_id="h_because"),
        DialogueNode(
            "h_because", CHUCHMEK, "Потому что если бы она была боковой, её пришлось бы искать.", next_id="h_where"
        ),
        DialogueNode("h_where", ALICE, "А где три испытания?", next_id="h_directions"),
        DialogueNode(
            "h_directions", CHUCHMEK, "Слева суши, справа торты, документы где-то между ними. Как и в жизни."
        ),
    ],
)

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
    return [CHUCHMEK_TALK, *PORTAL_NOT_READY.values()]
