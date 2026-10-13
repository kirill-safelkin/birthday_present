"""Демонстрационный диалог для проверки системы диалогов. Это не часть сюжета игры."""

from game.dialogue import DialogueChoice, DialogueNode, DialogueScript

CHUCHMEK = "Чучмек"
# Реплика с вопросом: по ней экран проверки показывает, какой ответ выбран.
QUESTION_ID = "decision"

DEMO_SCRIPT = DialogueScript(
    start_id="start",
    nodes=[
        DialogueNode("start", CHUCHMEK, "Так. Я проверил систему. Она работает.", next_id="rumour"),
        DialogueNode("rumour", CHUCHMEK, "По крайней мере, мне так сказали.", next_id=QUESTION_ID),
        DialogueNode(
            QUESTION_ID,
            CHUCHMEK,
            "Теперь необходимо принять одно крайне важное решение.",
            choices=[
                DialogueChoice("Продолжай.", "go_on"),
                DialogueChoice("Почему у тебя на шляпе крошки?", "crumbs"),
                DialogueChoice("Ты вообще знаешь, что делаешь?", "competence"),
            ],
        ),
        DialogueNode(
            "go_on",
            CHUCHMEK,
            "Отлично. Тогда фиксирую: система работает, решение принято, "
            "а все претензии принимаются в письменном виде, на бумаге, в трёх экземплярах.",
        ),
        DialogueNode(
            "crumbs",
            CHUCHMEK,
            "Это не крошки. Это стратегический запас на случай долгой загрузки.",
            next_id="forgot",
        ),
        # Ветка, в которой Чучмек забывает, о чём говорил, и возвращается к вопросу.
        DialogueNode("forgot", CHUCHMEK, "…Так. О чём это я? Ах да. Решение.", next_id=QUESTION_ID),
        DialogueNode(
            "competence",
            CHUCHMEK,
            "Разумеется. Я прочитал инструкцию. Ну, её обложку. Обложка была очень уверенная.",
        ),
    ],
)
