"""Сценарий вступления «Алиса в стране Чучмека?!»: реплики, паузы, постановочные события.

Здесь только данные. Как всё это показывается, решает game/story/intro_scene.py.
Вступление — последовательность шагов (BEATS):
  Lines — реплики по сценарию DialogueScript (существующая система диалогов);
  Pause — пауза без реплик, чтобы шутка успела сработать;
  Cue   — постановочное событие (появление персонажа, сбой, превращение заголовка),
          его рисует сцена.
POSES — ремарки: какую позу принимает персонаж, пока показана реплика.

Части:
  A — классическая «Алиса в стране чудес»: заставка, Белый Кролик, нора, «Ну, поехали»;
  B — сбой сказки: рывки, сообщение об ошибке, перезапуск, превращение заголовка;
  C — Чучмек вылезает из норы и знакомится;
  D — объяснение приключения и три испытания;
  E — выбор Алисы (обе ветки сходятся);
  F — конец вступления.
До части C (до превращения названия) Чучмек, грибы и испытания не упоминаются.
"""

from __future__ import annotations

from dataclasses import dataclass

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript

ALICE = "Алиса"
RABBIT = "Белый Кролик"
CHUCHMEK = "Чучмек"
# Говорящий → персонаж на сцене (идентификатор из assets/characters).
SPEAKER_ACTORS = {ALICE: "alice", RABBIT: "white_rabbit", CHUCHMEK: "chuchmek"}

# Реплика с выбором Алисы: по ней сцена и экран проверки узнают, какой ответ выбран.
CHOICE_ID = "e_where_to_start"

TITLE_CLASSIC = "Алиса в стране чудес"
TITLE_FINAL = "Алиса в стране Чучмека?!"
ERROR_TITLE = "ОШИБКА СКАЗОЧНОГО ДВИЖКА"
ERROR_LINES = ("Обнаружено слишком много чудес.", "Попытка восстановить предыдущую версию истории…")


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


@dataclass(frozen=True)
class TitleStep:
    """Одно состояние заголовка при превращении: сколько оно длится и как выглядит."""

    seconds: float
    text: str
    shake: int = 0  # дрожание заголовка, пиксели
    visible: bool = True  # False — заголовок «моргнул»


# Превращение заголовка. Три главных состояния написаны точно: «Алиса в стране чудес»,
# «Алиса в стране чу…», «Алиса в стране Чучмека?!». Остальное — короткие ступеньки между
# ними: буквы пропадают по одной, потом на миг меняются местами и заголовок моргает.
TITLE_REWRITE: tuple[TitleStep, ...] = (
    TitleStep(1.4, TITLE_CLASSIC),
    TitleStep(0.5, TITLE_CLASSIC, shake=1),
    TitleStep(0.5, "Алиса в стране чуде", shake=1),
    TitleStep(0.5, "Алиса в стране чуд", shake=1),
    TitleStep(0.5, "Алиса в стране чу", shake=1),
    TitleStep(1.6, "Алиса в стране чу…", shake=1),
    TitleStep(0.3, "Алиса в сртане чу…", shake=2),
    TitleStep(0.3, "Алиса в стране уч…", shake=2),
    TitleStep(0.3, "Алиса в стране чу…", shake=1),
    TitleStep(0.15, "Алиса в стране чу…", visible=False),
    TitleStep(0.15, "Алиса в стране чу…"),
    TitleStep(0.15, "Алиса в стране чу…", visible=False),
    TitleStep(0.15, "Алиса в стране чу…"),
    TitleStep(0.5, "Алиса в стране чу…", visible=False),
    TitleStep(2.6, TITLE_FINAL),  # финальное название и его «хлопок»; страница меняет краски
)
TITLE_REWRITE_SECONDS = sum(step.seconds for step in TITLE_REWRITE)
TITLE_REVEAL_START = TITLE_REWRITE_SECONDS - TITLE_REWRITE[-1].seconds


def title_step_at(seconds: float) -> TitleStep:
    """Состояние заголовка в момент seconds от начала превращения."""
    elapsed = 0.0
    for step in TITLE_REWRITE:
        elapsed += step.seconds
        if seconds < elapsed - 1e-9:
            return step
    return TITLE_REWRITE[-1]


def _script(*nodes: DialogueNode) -> DialogueScript:
    return DialogueScript(nodes[0].id, nodes)


# --- Часть A. Классическая сказка: Белый Кролик и нора ---

PART_A_RABBIT = _script(
    DialogueNode("r_hello", RABBIT, "Алиса! Наконец-то! Мы уже начинаем опаздывать!", next_id="r_where"),
    DialogueNode("r_where", ALICE, "Куда?", next_id="r_burrow"),
    DialogueNode(
        "r_burrow",
        RABBIT,
        "В нору. По расписанию мы должны были прыгнуть туда ещё четырнадцать секунд назад!",
        next_id="r_why",
    ),
    DialogueNode("r_why", ALICE, "А почему я должна прыгать в незнакомую нору?", next_id="r_wonderland"),
    DialogueNode(
        "r_wonderland",
        RABBIT,
        "Потому что это Страна чудес. Здесь сначала прыгают, а потом заполняют документы.",
        next_id="r_docs",
    ),
    DialogueNode("r_docs", ALICE, "Документы?", next_id="r_form"),
    DialogueNode(
        "r_form",
        RABBIT,
        "Не волнуйтесь. Форму 27-Б заполнять необязательно. Если у вас есть форма 27-А.",
        next_id="r_below",
    ),
    DialogueNode("r_below", ALICE, "И что там внизу?", next_id="r_unknown"),
    DialogueNode(
        "r_unknown", RABBIT, "Неизвестно. Но по расписанию там должно быть приключение.", next_id="r_ok"
    ),
    DialogueNode(
        "r_ok", ALICE, "Ладно. Только если там нет приключения, мы вернёмся.", next_id="r_prepared"
    ),
    DialogueNode("r_prepared", RABBIT, "Конечно! Я предусмотрел даже такую возможность."),
)
PART_A_INVITE = _script(
    DialogueNode(
        "r_invite",
        RABBIT,
        "Нора вон там! Прошу вас первой, Алиса. Я прыгну сразу следом. По расписанию.",
    ),
)
PART_A_GO = _script(DialogueNode("a_go", ALICE, "Ну, поехали."))

# --- Часть C. Чучмек вылезает из норы ---

PART_C_WAKING = _script(
    DialogueNode(
        "c_who", CHUCHMEK, "Так. Кто перезапустил сказку? Я ещё даже не проснулся.", next_id="c_you"
    ),
    DialogueNode("c_you", ALICE, "Ты кто?", next_id="c_name"),
    DialogueNode("c_name", CHUCHMEK, "Чучмек. Временно ответственный по непредсказуемости.", next_id="c_post"),
    DialogueNode("c_post", ALICE, "Это должность?", next_id="c_now"),
    DialogueNode("c_now", CHUCHMEK, "Теперь да."),
)
PART_C_TITLE = _script(
    DialogueNode(
        "c_title",
        CHUCHMEK,
        "Я, кстати, не знаю, почему оказался в заголовке книги. Но считаю это повышением.",
        next_id="c_mushroom",
    ),
    DialogueNode("c_mushroom", ALICE, "Ты гриб.", next_id="c_career"),
    DialogueNode(
        "c_career", CHUCHMEK, "Это не мешает карьерному росту. Зарплату, правда, выдают в компосте."
    ),
)

# --- Часть D. Объяснение приключения ---

PART_D_EXPLANATION = _script(
    DialogueNode(
        "d_fragments",
        CHUCHMEK,
        "Так. К делу. Нам нужны три сюжетных фрагмента. Без них финальная дверь не откроется.",
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
    # A. Классическая сказка
    Cue("A", "title_card", 2.6),  # заголовок «Алиса в стране чудес» и Алиса на спокойной странице
    Pause("A", 1.2),  # короткая вступительная пауза
    Cue("A", "rabbit_runs_in", 1.6),
    Lines("A", PART_A_RABBIT),
    Cue("A", "rabbit_points", 1.2),  # Кролик показывает на нору
    Lines("A", PART_A_INVITE),
    Cue("A", "alice_walks", 2.6),  # Алиса идёт к норе и притормаживает перед ней
    Cue("A", "alice_prepares", 1.0),  # присела, готовится прыгнуть
    Lines("A", PART_A_GO),
    # B. Сбой сказки
    Cue("B", "glitch", 1.8),  # рывки, пропущенные кадры, рваные строки
    Cue("B", "error_message", 4.0),  # шуточное сообщение «ОШИБКА СКАЗОЧНОГО ДВИЖКА»
    Cue("B", "restart", 1.2),  # вспышка и возврат к классической заставке
    Cue("B", "title_rewrite", TITLE_REWRITE_SECONDS),  # …чудес → …чу… → …Чучмека?!
    # C. Чучмек
    Cue("C", "chuchmek_emerges", 4.6),
    Lines("C", PART_C_WAKING),
    Pause("C", 1.0),
    Lines("C", PART_C_TITLE),
    Cue("C", "alice_reacts", 0.8),
    # D–F. Прежнее продолжение: три испытания, выбор, конец
    Lines("D", PART_D_EXPLANATION),
    Lines("E", PART_E_CHOICE),
    Lines("F", PART_F_ENDING),
    Cue("F", "finale", 2.0),
)

# Ремарки: поза персонажа (кадр из его манифеста), пока показана реплика. Если нужного
# кадра нет, сцена берёт ближайший доступный или временный спрайт. Алиса, которой нет
# в ремарке, говорит анимацией talk_down.
FACING_RABBIT = {"alice": "idle_left"}
FACING_CHUCHMEK = {"alice": "idle_right"}
POSES: dict[str, dict[str, str]] = {
    "r_hello": {"white_rabbit": "checks_watch_happy", **FACING_RABBIT},
    "r_where": {"white_rabbit": "idle_front"},
    "r_burrow": {"white_rabbit": "hurries_pointing", **FACING_RABBIT},
    "r_why": {"white_rabbit": "idle_front"},
    "r_wonderland": {"white_rabbit": "confident_point", **FACING_RABBIT},
    "r_docs": {"white_rabbit": "confused_watch"},
    "r_form": {"white_rabbit": "reads_schedule", **FACING_RABBIT},
    "r_below": {"white_rabbit": "idle_front"},
    "r_unknown": {"white_rabbit": "checks_watch_happy", **FACING_RABBIT},
    "r_ok": {"white_rabbit": "idle_front"},
    "r_prepared": {"white_rabbit": "checks_watch_happy", **FACING_RABBIT},
    "r_invite": {"white_rabbit": "hurries_pointing", **FACING_RABBIT},
    "a_go": {"white_rabbit": "hurries_pointing"},
    "c_who": {"chuchmek": "confused", **FACING_CHUCHMEK},
    "c_you": {"chuchmek": "curious_glance"},
    "c_name": {"chuchmek": "clipboard_confident", **FACING_CHUCHMEK},
    "c_post": {"chuchmek": "idle"},
    "c_now": {"chuchmek": "smug_wink", **FACING_CHUCHMEK},
    "c_title": {"chuchmek": "talk_gesture", **FACING_CHUCHMEK},
    "c_mushroom": {"chuchmek": "curious_glance"},
    "c_career": {"chuchmek": "talk_01", **FACING_CHUCHMEK},
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
