"""Реплики испытания суши: вступление, реакции на заказы, финал. Только данные.

Суши — вкусная часть праздничного плана. Во вступлении у Алисы выбор (чему она доверяет
на кухне): повар отвечает по-разному, а правила и заказы одни и те же при любом ответе.
Показывает их game/trials/sushi_scene.py через существующую систему диалогов.
CHEF_POSES — какую позу (кадр cat_chef) принимает кот-повар на реплике.
"""

from __future__ import annotations

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE

CHEF = "Кот-повар"
TRUST_CHOICE_ID = "s_trust"  # выбор Алисы во вступлении


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


INTRO = _script(
    DialogueNode(
        "s_welcome", CHEF, "Добро пожаловать. На моей кухне всё подчиняется точности, чистоте и рису.", next_id="s_just"
    ),
    DialogueNode("s_just", ALICE, "А если я просто хочу приготовить суши?", next_id="s_suspicious"),
    DialogueNode("s_suspicious", CHEF, "Это и есть самое подозрительное, что ты могла сказать.", next_id="s_tasty"),
    DialogueNode(
        "s_tasty",
        CHEF,
        "Чучмек предупредил: тебе нужна вкусная часть праздника. Её здесь не выдают, а заслуживают.",
        next_id=TRUST_CHOICE_ID,
    ),
    DialogueNode(
        TRUST_CHOICE_ID,
        CHEF,
        "Скажи честно: чему ты доверяешь на кухне?",
        choices=[
            DialogueChoice("Я доверяю рецепту.", "s_recipe"),
            DialogueChoice("Я доверяю своему аппетиту.", "s_appetite"),
        ],
    ),
    DialogueNode(
        "s_recipe", CHEF, "Разумно. Рецепт не спорит, не опаздывает и не просит попробовать.", next_id="s_law"
    ),
    DialogueNode("s_law", CHEF, "Но помни: рецепт — это закон. А я — его суд.", next_id="s_rules"),
    DialogueNode("s_appetite", CHEF, "Смело. Аппетит — плохой повар, но честный критик.", next_id="s_critic"),
    DialogueNode("s_critic", ALICE, "Значит, он проследит за качеством.", next_id="s_rice_speaks"),
    DialogueNode("s_rice_speaks", CHEF, "Пусть следит молча. На моей кухне говорит только рис.", next_id="s_rules"),
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
        "Это значит, ты получаешь вкусную часть праздника. И совет: не говори Чучмеку, где лежит соевый соус.",
    ),
)

CHEF_POSES = {
    "s_welcome": "stern_arms_crossed",
    "s_suspicious": "stern_side_pose",
    "s_tasty": "idle_grumpy",
    TRUST_CHOICE_ID: "stern_arms_crossed",
    "s_recipe": "present_sushi",
    "s_law": "stern_arms_crossed",
    "s_appetite": "taste_sushi",
    "s_rice_speaks": "stern_side_pose",
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
