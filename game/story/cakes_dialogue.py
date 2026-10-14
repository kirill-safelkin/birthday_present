"""Реплики испытания тортов: вступление в перевёрнутой кондитерской, отказы и успех рецепта,
побег клубники, находка в кладовой и финал. Только данные.

Показывает их game/trials/cakes_scene.py через существующую систему диалогов.
CHUCHMEK_POSES — какую позу (кадр chuchmek) принимает Чучмек на реплике.
"""

from __future__ import annotations

from game.dialogue.model import DialogueNode, DialogueScript
from game.story.intro_dialogue import ALICE, CHUCHMEK
from game.trials.cakes_puzzle import STEPS


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


INTRO = _script(
    DialogueNode(
        "i_ready", CHUCHMEK, "Всё готово! Я лично проверил рецепт, ингредиенты и саму реальность.", next_id="i_tray"
    ),
    DialogueNode("i_tray", ALICE, "Почему противень висит на потолке?", next_id="i_space"),
    DialogueNode("i_space", CHUCHMEK, "Экономия места. И тесто теперь не падает вниз. Обычно.", next_id="i_reversed"),
    DialogueNode("i_reversed", ALICE, "Подожди… Здесь всё наоборот. Даже рецепт.", next_id="i_backwards"),
    DialogueNode(
        "i_backwards",
        CHUCHMEK,
        "Неправда. Я просто выполнил рецепт в обратном порядке. Очень удобно: сразу знаешь, чем всё закончится.",
        next_id="i_fix",
    ),
    DialogueNode("i_fix", ALICE, "Тогда я расставлю этапы по порядку. А потом проверим."),
)

# Чучмек на неверный порядок — шутки идут по кругу, без случайностей.
WRONG_JOKES = (
    "Хм. Пока это выглядит как задумка торта, а не как торт.",
    "Мне всё ещё нравится. Но духовка смотрит на нас с осуждением.",
    "Почти! Если считать «почти» отдельным этапом рецепта.",
)
# А Алиса сама замечает первую ошибку — по позиции, где стоит не тот этап.
WRONG_HINTS = (
    "Сначала нужно подготовить ингредиенты. Без них и мешать нечего.",
    "После ингредиентов замешивают тесто. Пока его нет, печь нечего.",
    "Тесто готово — значит, теперь коржи отправляются в духовку.",
    "Горячие коржи сначала остужают. Иначе крем просто растает.",
    "Крем и украшения — в самом конце, когда всё остальное готово.",
)

SUCCESS = _script(
    DialogueNode(
        "s_finally",
        CHUCHMEK,
        "Наконец-то кто-то знает, что духовку нельзя включать после украшения кремом.",
        next_id="s_obvious",
    ),
    DialogueNode("s_obvious", ALICE, "Это знает каждый, кто хоть раз ел торт. Осталось положить клубнику…"),
)

ESCAPE = _script(
    DialogueNode("e_escaped", CHUCHMEK, "Клубника сбежала!", next_id="e_strawberry"),
    DialogueNode("e_strawberry", ALICE, "Она же клубника.", next_id="e_reason"),
    DialogueNode("e_reason", CHUCHMEK, "Именно. У неё ни прописки, ни чувства ответственности.", next_id="e_where"),
    DialogueNode(
        "e_where",
        CHUCHMEK,
        "Она укатилась в кладовую, между коробками и противнями. Найди её, пока она не записалась в другой торт!",
    ),
)

FOUND = _script(
    DialogueNode("c_caught", ALICE, "Попалась! Сидела за коробками и делала вид, что она вишня.", next_id="c_planned"),
    DialogueNode("c_planned", CHUCHMEK, "Блестяще! Я её специально отпустил. Проверял лабиринт.", next_id="c_sure"),
    DialogueNode("c_sure", ALICE, "Конечно. Возвращаемся к торту."),
)

FINAL = _script(
    DialogueNode("f_finish", ALICE, "Нашла. Теперь можно наконец закончить торт?", next_id="f_convince"),
    DialogueNode(
        "f_convince",
        CHUCHMEK,
        "Конечно! Осталось только убедить клубнику, что она часть десерта, а не руководитель проекта.",
        next_id="f_boss",
    ),
    DialogueNode("f_boss", ALICE, "По-моему, она уже назначила себя руководителем.", next_id="f_fragment"),
    DialogueNode(
        "f_fragment", CHUCHMEK, "Тогда держи фрагмент праздника. Руководитель проекта одобрил. Кажется, кивнул."
    ),
)

CHUCHMEK_POSES = {
    "i_ready": "clipboard_confident",
    "i_space": "smug_wink",
    "i_backwards": "talk_gesture",
    "wrong_joke": "confused",
    "s_finally": "talk_excited",
    "e_escaped": "arms_up_panic",
    "e_reason": "panicked",
    "e_where": "talk_gesture",
    "c_planned": "smug_wink",
    "f_convince": "talk_excited",
    "f_fragment": "wink",
}
CHUCHMEK_IDLE_POSE = "idle"
CHUCHMEK_PANIC_POSE = "panicked"  # пока клубника убегает


def wrong_order(attempt: int, mistake: int) -> DialogueScript:
    """Неверный рецепт: attempt — номер неудачной проверки с единицы, mistake — первая неверная позиция."""
    return _script(
        DialogueNode("wrong_joke", CHUCHMEK, WRONG_JOKES[(attempt - 1) % len(WRONG_JOKES)], next_id="wrong_hint"),
        DialogueNode("wrong_hint", ALICE, WRONG_HINTS[min(mistake, len(WRONG_HINTS) - 1)]),
    )


def all_scripts() -> list[DialogueScript]:
    """Все сценарии испытания, включая собранные по ходу игры, — для проверки, что они помещаются на экран."""
    scripts = [INTRO, SUCCESS, ESCAPE, FOUND, FINAL]
    scripts += [
        wrong_order(attempt, mistake)
        for attempt in range(1, len(WRONG_JOKES) + 1)
        for mistake in range(len(STEPS))
    ]
    return scripts
