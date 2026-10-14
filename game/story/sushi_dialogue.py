"""Реплики испытания суши: вступление, реакции на заказы, финал. Только данные.

Показывает их game/trials/sushi_scene.py через существующую систему диалогов.
CHEF_POSES — какую позу (кадр cat_chef) принимает кот-повар на реплике.
"""

from __future__ import annotations

from game.dialogue.model import DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE

CHEF = "Кот-повар"


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


INTRO = _script(
    DialogueNode(
        "s_welcome", CHEF, "Добро пожаловать. На моей кухне всё подчиняется точности, чистоте и рису.", next_id="s_just"
    ),
    DialogueNode("s_just", ALICE, "А если я просто хочу приготовить суши?", next_id="s_suspicious"),
    DialogueNode("s_suspicious", CHEF, "Это и есть самое подозрительное, что ты могла сказать.", next_id="s_rules"),
    DialogueNode(
        "s_rules",
        CHEF,
        "Три заказа. Ингредиенты — на стойке, тарелка — на столе. Носишь по одному. Это не обсуждается.",
        next_id="s_mistake",
    ),
    DialogueNode("s_mistake", ALICE, "А если я перепутаю?", next_id="s_forgives"),
    DialogueNode("s_forgives", CHEF, "Вернёшь на место. Рис прощает. Я — запоминаю."),
)

# Реакция повара на каждый собранный заказ — своя.
REACTIONS = (
    _script(
        DialogueNode("r1_rice", CHEF, "Приемлемо. Рис не пытался сбежать. Уже хорошее начало."),
    ),
    _script(
        DialogueNode(
            "r2_cucumber", CHEF, "Огурец завёрнут без драмы. Запишу это в достижения кухни.", next_id="r2_taste"
        ),
        DialogueNode("r2_taste", ALICE, "А можно я хотя бы один попробую?", next_id="r2_after"),
        DialogueNode("r2_after", CHEF, "После смены. И только если рис разрешит."),
    ),
    _script(
        DialogueNode("r3_bold", CHEF, "Лосось и авокадо в одном ролле. Смело. Смело и правильно."),
    ),
)

FINAL = _script(
    DialogueNode(
        "f_disappointed", CHEF, "Три заказа. Ни одной кулинарной катастрофы. Я почти разочарован.", next_id="f_did_i"
    ),
    DialogueNode("f_did_i", ALICE, "Это значит, я справилась?", next_id="f_fragment"),
    DialogueNode(
        "f_fragment",
        CHEF,
        "Это значит, ты получаешь фрагмент праздника. И совет: не говори Чучмеку, где лежит соевый соус.",
    ),
)

CHEF_POSES = {
    "s_welcome": "stern_arms_crossed",
    "s_suspicious": "stern_side_pose",
    "s_rules": "idle_grumpy",
    "s_forgives": "stern_arms_crossed",
    "r1_rice": "idle_grumpy",
    "r2_cucumber": "arrange_sushi",
    "r2_after": "taste_sushi",
    "r3_bold": "present_sushi",
    "f_disappointed": "stern_arms_crossed",
    "f_fragment": "happy_sushi_tray",
}
CHEF_IDLE_POSE = "idle_grumpy"
CHEF_DISAPPROVING_POSE = "stern_side_pose"  # на миг, когда ингредиент не подошёл


def chef_tip(recipe_name: str, missing: list[str]) -> DialogueScript:
    """Подсказка повара по текущему заказу (Алиса подошла и спросила)."""
    if missing:
        text = f"Сейчас — «{recipe_name}». На тарелке не хватает: {', '.join(missing)}."
    else:
        text = f"«{recipe_name}» собран. Не трогай. Любуйся."
    return _script(DialogueNode("tip", CHEF, text))


def all_scripts() -> list[DialogueScript]:
    return [INTRO, *REACTIONS, FINAL]
