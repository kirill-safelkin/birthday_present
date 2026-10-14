"""Сценарий вступления «Алиса и Чучмек»: реплики, паузы и постановочные события.

Здесь только данные. Как всё это показывается, решает game/story/intro_scene.py.
Вступление — последовательность шагов (BEATS):
  Lines — реплики по сценарию DialogueScript (существующая система диалогов);
  Pause — пауза без реплик, чтобы шутка успела сработать;
  Cue   — постановочное событие (появление персонажа, сгиб страницы), его рисует сцена.
POSES — ремарки: какую позу принимает персонаж, пока показана реплика.
"""

from __future__ import annotations

from dataclasses import dataclass

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript

NARRATOR = "Рассказчик"
ALICE = "Алиса"
RABBIT = "Белый Кролик"
CHUCHMEK = "Чучмек"
# Говорящий → персонаж на сцене (идентификатор из assets/characters). У рассказчика персонажа нет.
SPEAKER_ACTORS = {ALICE: "alice", RABBIT: "white_rabbit", CHUCHMEK: "chuchmek"}

# Реплика с выбором Алисы: по ней сцена и экран проверки узнают, какой ответ выбран.
CHOICE_ID = "e_where_to_start"


@dataclass(frozen=True)
class Lines:
    part: str
    script: DialogueScript


@dataclass(frozen=True)
class Pause:
    part: str
    seconds: float


@dataclass(frozen=True)
class Cue:
    """Постановочное событие длительностью seconds. Имя понимает сцена вступления."""

    part: str
    name: str
    seconds: float


Beat = Lines | Pause | Cue


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


# --- Часть A. Начало сказки ---

PART_A_OPENING = _script(
    DialogueNode("a_once", NARRATOR, "В одной совершенно чудесной стране жила Алиса.", next_id="a_land"),
    DialogueNode(
        "a_land",
        NARRATOR,
        "В этой стране происходили загадочные события, случались невероятные приключения, "
        "а каждый поворот дорожки обещал нечто необыкновенное.",
        next_id="a_sushi",
    ),
    DialogueNode("a_sushi", ALICE, "Звучит неплохо. А где здесь суши?", next_id="a_no_sushi"),
    DialogueNode("a_no_sushi", NARRATOR, "Суши не предусмотрены классическими сказками."),
)
PART_A_PUNCHLINE = _script(
    DialogueNode("a_upgrade", ALICE, "Тогда классические сказки нуждаются в доработке."),
)

# --- Часть B. Появление Белого Кролика ---

PART_B_RABBIT = _script(
    DialogueNode(
        "b_late", RABBIT, "Я опаздываю! По расписанию я должен был появиться три абзаца назад!", next_id="b_who"
    ),
    DialogueNode("b_who", ALICE, "Ты же Белый Кролик из Страны чудес?", next_id="b_consent"),
    DialogueNode(
        "b_consent",
        RABBIT,
        "Да. Но мне сказали, что дальше будет сюжетный поворот, и я не подписывал согласие.",
        next_id="b_schedule",
    ),
    DialogueNode(
        "b_schedule",
        RABBIT,
        "У меня всё по расписанию! С 9:00 до 9:05 — паника. С 9:05 до 9:10 — организованная паника. "
        "Сюжетных поворотов в графике нет!",
    ),
)

# --- Часть C. Поломка сказки ---

PART_C_ARRIVAL = _script(
    DialogueNode("c_control", CHUCHMEK, "Так. Не паникуем. Я всё контролирую. Кажется.", next_id="c_mushroom"),
    DialogueNode("c_mushroom", ALICE, "Ты гриб."),
)
PART_C_POSITION = _script(
    DialogueNode("c_position", CHUCHMEK, "Это должность.", next_id="c_which"),
    DialogueNode("c_which", ALICE, "Какая должность?", next_id="c_salary"),
    DialogueNode(
        "c_salary", CHUCHMEK, "Временно ответственный по непредсказуемости. Зарплату выдают в компосте."
    ),
)

# --- Часть D. Объяснение приключения ---

PART_D_EXPLANATION = _script(
    DialogueNode(
        "d_fragments",
        CHUCHMEK,
        "Нам нужны три сюжетных фрагмента. Без них финальная дверь не откроется.",
        next_id="d_door",
    ),
    DialogueNode("d_door", ALICE, "Что за дверью?", next_id="d_guide"),
    DialogueNode("d_guide", CHUCHMEK, "Не знаю. Я гриб, а не экскурсовод.", next_id="d_where"),
    DialogueNode("d_where", ALICE, "Хорошо. А где берут эти фрагменты?", next_id="d_trials"),
    DialogueNode("d_trials", CHUCHMEK, "Три испытания. Суши, формуляры и торты.", next_id="d_why_forms"),
    DialogueNode("d_why_forms", ALICE, "Почему формуляры?", next_id="d_evil"),
    DialogueNode("d_evil", CHUCHMEK, "Потому что зло бывает разным.", next_id="d_cat"),
    DialogueNode(
        "d_cat", CHUCHMEK, "Суши охраняет кот-повар. Строгий, но справедливый. В основном строгий.", next_id="d_goose"
    ),
    DialogueNode(
        "d_goose",
        CHUCHMEK,
        "Формуляры принимает гусь-инспектор. А про торты я пока говорить не готов. Эмоционально.",
    ),
)

# --- Часть E. Выбор направления: обе ветки сходятся в e_ready ---

PART_E_CHOICE = _script(
    DialogueNode(
        CHOICE_ID,
        CHUCHMEK,
        "Итак. С чего начнём?",
        choices=[
            DialogueChoice("Начинаем с суши. У истории должен быть вкус.", "e_sushi"),
            DialogueChoice("Сначала объясни, почему гриб разговаривает.", "e_talking"),
        ],
    ),
    DialogueNode("e_sushi", CHUCHMEK, "Смело. Кот-повар как раз точит ножи. Надеюсь, для суши.", next_id="e_ready"),
    DialogueNode(
        "e_talking",
        CHUCHMEK,
        "Долгая история. Если коротко: я вырос у стены библиотеки. Остальное — сплетни.",
        next_id="e_ready",
    ),
    DialogueNode(
        "e_ready", CHUCHMEK, "В любом случае все три испытания открыты. Порядок — на твой вкус.", next_id="e_alice"
    ),
    DialogueNode("e_alice", ALICE, "Отлично. Значит, пора выяснить, что здесь вообще происходит."),
)

# --- Часть F. Конец вступления ---

PART_F_ENDING = _script(
    DialogueNode("f_go", ALICE, "Ладно. Показывай, куда идти.", next_id="f_questions"),
    DialogueNode(
        "f_questions",
        ALICE,
        "Но если следующее испытание окажется про заполнение двенадцати формуляров "
        "на один суши, я буду задавать вопросы.",
        next_id="f_form_12b",
    ),
    DialogueNode("f_form_12b", CHUCHMEK, "Разумно. Хотя формуляр № 12-Б нужен именно для разрешения на вопросы."),
)

BEATS: tuple[Beat, ...] = (
    Cue("A", "alice_appears", 1.2),
    Lines("A", PART_A_OPENING),
    Pause("A", 1.0),  # шутке нужна тишина
    Lines("A", PART_A_PUNCHLINE),
    Pause("A", 0.6),
    Cue("B", "rabbit_runs_in", 1.4),
    Lines("B", PART_B_RABBIT),
    Cue("C", "page_folds", 2.4),  # сказка сгибается, Кролик сбегает
    Cue("C", "chuchmek_appears", 1.0),
    Pause("C", 0.5),
    Lines("C", PART_C_ARRIVAL),
    Pause("C", 0.9),  # «Ты гриб.» — и тишина
    Lines("C", PART_C_POSITION),
    Cue("C", "alice_reacts", 0.8),
    Lines("D", PART_D_EXPLANATION),
    Lines("E", PART_E_CHOICE),
    Lines("F", PART_F_ENDING),
    Cue("F", "finale", 2.0),
)

# Ремарки: поза персонажа (кадр из его манифеста), пока показана реплика. Если нужного
# кадра нет, сцена берёт ближайший доступный или временный спрайт.
POSES: dict[str, dict[str, str]] = {
    "b_late": {"white_rabbit": "panics_watch", "alice": "idle_left"},
    "b_who": {"white_rabbit": "checks_watch_happy"},
    "b_consent": {"white_rabbit": "confused_watch"},
    "b_schedule": {"white_rabbit": "reads_schedule", "alice": "idle_left"},
    "c_control": {"chuchmek": "clipboard_confident"},
    "c_mushroom": {"chuchmek": "curious_glance"},
    "c_position": {"chuchmek": "smug_wink"},
    "c_which": {"chuchmek": "idle"},
    "c_salary": {"chuchmek": "talk_gesture"},
    "d_fragments": {"chuchmek": "talk_01"},
    "d_guide": {"chuchmek": "confused"},
    "d_trials": {"chuchmek": "talk_excited"},
    "d_evil": {"chuchmek": "wink"},
    "d_cat": {"chuchmek": "talk_02"},
    "d_goose": {"chuchmek": "confused"},
    CHOICE_ID: {"chuchmek": "clipboard_confident"},
    "e_sushi": {"chuchmek": "talk_excited"},
    "e_talking": {"chuchmek": "smug_wink"},
    "e_ready": {"chuchmek": "talk_gesture"},
    "f_form_12b": {"chuchmek": "clipboard_confident"},
}


def all_scripts() -> list[DialogueScript]:
    return [beat.script for beat in BEATS if isinstance(beat, Lines)]
