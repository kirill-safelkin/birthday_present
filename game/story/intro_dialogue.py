"""Сценарий вступления «Алиса в стране Чучмека?!»: реплики, паузы, постановочные события.

Здесь только данные. Как всё это показывается, решает game/story/intro_scene.py.
Вступление — последовательность шагов (BEATS):
  Lines — реплики по сценарию DialogueScript (существующая система диалогов);
  Pause — пауза без реплик, чтобы шутка успела сработать;
  Cue   — постановочное событие (появление персонажа, сбой, превращение заголовка),
          его рисует сцена;
  Explore — интерактивный шаг: Алиса под управлением игрока, пока он не пройдёт эпизод
          (модель эпизода — game/story/entrance.py).
POSES — ремарки: какую позу принимает персонаж, пока показана реплика.

Части:
  A — классическая «Алиса в стране чудес»: заставка, Белый Кролик; игрок сам ведёт Алису к месту
      норы, сказка начинает сбоить, нора появляется, E — заглянуть внутрь; «Ну, поехали» и прыжок;
  B — сбой сказки: рывки, сообщение об ошибке, перезапуск, превращение заголовка;
  C — Чучмек вылезает из норы и знакомится;
  D — праздничный план: у Алисы день рождения, вся сказка готовит ей праздник, Чучмек сам
      назначил себя организатором, а план после сломанной сказки разлетелся на три фрагмента:
      три испытания, три фрагмента, мозаика на площади; почему их собирает Алиса и кто такой Лео;
  E — последний вопрос к организатору;
  F — конец вступления.
В частях D и E у Алисы по одному выбору ответа: ветки дают свои реплики и сходятся в общей,
так что главное игрок узнаёт при любом ответе.
До части C (до превращения названия) Чучмек, грибы и испытания не упоминаются. Что внутри
испытаний (суши, архив, торты), Чучмек не раскрывает: Алиса узнаёт это, войдя в портал.
"""

from __future__ import annotations

from dataclasses import dataclass

from game.dialogue.model import DialogueChoice, DialogueNode, DialogueScript

ALICE = "Алиса"
RABBIT = "Белый Кролик"
CHUCHMEK = "Чучмек"
# Говорящий → персонаж на сцене (идентификатор из assets/characters).
SPEAKER_ACTORS = {ALICE: "alice", RABBIT: "white_rabbit", CHUCHMEK: "chuchmek"}

# Реплика с выбором Алисы в части E: по ней сцена и экран проверки узнают, какой ответ выбран.
CHOICE_ID = "e_where_to_start"
# Выбор в части D: как Алиса отвечает на новость о самоназначенном организаторе.
ORGANIZER_CHOICE_ID = "d_organizer"

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


@dataclass(frozen=True)
class Explore:
    """Интерактивный шаг без заданной длительности: заканчивается действием игрока."""

    part: str
    name: str


Beat = Lines | Pause | Cue | Explore


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
        "Нора должна быть вон там! Прошу вас первой, Алиса. Я прыгну сразу следом. По расписанию.",
    ),
)
PART_A_GO = _script(DialogueNode("a_go", ALICE, "Ну, поехали."))
# Короткие реплики Кролика над его головой, пока сказка ломается и появляется нора. Это не диалог:
# они не останавливают постановку и не ждут нажатия.
RABBIT_REMARK_BREAKING = "Ой-ой! Этого нет в расписании!"
RABBIT_REMARK_READY = "Вот и нора. Почти по расписанию!"

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

# --- Часть D. Праздничный план ---

PART_D_PLAN = _script(
    DialogueNode("d_wait", CHUCHMEK, "Так. Карьера подождёт. У меня тут праздник.", next_id="d_whose"),
    DialogueNode("d_whose", ALICE, "Чей?", next_id="d_yours"),
    DialogueNode(
        "d_yours",
        CHUCHMEK,
        "Твой, конечно! Сегодня твой день рождения. Вся сказка готовит тебе праздник.",
        next_id=ORGANIZER_CHOICE_ID,
    ),
    DialogueNode(
        ORGANIZER_CHOICE_ID,
        CHUCHMEK,
        "А я — временно главный организатор праздника.",
        choices=[
            DialogueChoice("И кто тебя назначил?", "d_self_appointed"),
            DialogueChoice("Ладно. Что нам нужно сделать?", "d_down_to_business"),
        ],
    ),
    DialogueNode(
        "d_self_appointed",
        CHUCHMEK,
        "Я сам. Остальные кандидаты почему-то спрятались. Кролик, например, очень срочно опоздал.",
        next_id="d_democratic",
    ),
    DialogueNode("d_democratic", ALICE, "Очень демократично.", next_id="d_plan"),
    DialogueNode(
        "d_down_to_business",
        CHUCHMEK,
        "Деловой подход! Мне бы такой: я сначала назначил себя, а потом уже начал думать.",
        next_id="d_thought_of",
    ),
    DialogueNode("d_thought_of", ALICE, "И до чего додумался?", next_id="d_plan"),
    # Ветки сошлись: дальше одно и то же при любом ответе.
    DialogueNode(
        "d_plan",
        CHUCHMEK,
        "Я подготовил праздничный план. Потом немного его улучшил. Потом сказка сломалась.",
        next_id="d_disaster",
    ),
    DialogueNode("d_disaster", ALICE, "Это звучит как катастрофа.", next_id="d_pieces"),
    DialogueNode(
        "d_pieces",
        CHUCHMEK,
        "Не спеши с выводами. Катастрофа уже произошла: мой праздничный план разлетелся на три фрагмента.",
        next_id="d_now",
    ),
    DialogueNode("d_now", ALICE, "И что теперь?", next_id="d_trials"),
    DialogueNode(
        "d_trials",
        CHUCHMEK,
        "Три испытания — три фрагмента. Соберём их, восстановим план и наконец устроим твой праздник.",
        next_id="d_mosaic",
    ),
    DialogueNode(
        "d_mosaic",
        CHUCHMEK,
        "Фрагменты сложатся на мозаике посреди площади в последнюю страницу плана. Открыть её сможешь только ты.",
        next_id="d_inside",
    ),
    DialogueNode("d_inside", ALICE, "А ты хотя бы знаешь, что в этих испытаниях?", next_id="d_intrigue"),
    DialogueNode(
        "d_intrigue",
        CHUCHMEK,
        "Конечно. То есть примерно. В общих чертах. Не мешай мне сохранять интригу.",
        next_id="d_why_me",
    ),
    DialogueNode("d_why_me", ALICE, "Подожди. Организатор — ты, а испытания проходить мне?", next_id="d_tried"),
    DialogueNode(
        "d_tried",
        CHUCHMEK,
        "Я пробовал сам. Меня вежливо выставили. Отовсюду. Одновременно.",
        next_id="d_only_you",
    ),
    DialogueNode(
        "d_only_you",
        CHUCHMEK,
        "И потом, только именинница знает, каким должен быть её праздник. Я знаю только, каким не должен.",
        next_id="d_leo",
    ),
    DialogueNode(
        "d_leo",
        CHUCHMEK,
        "Но ты не одна. На площади ждёт Лео: я назначил его главным инспектором праздничного настроения.",
        next_id="d_leo_job",
    ),
    DialogueNode("d_leo_job", ALICE, "Лео? И что же он инспектирует?", next_id="d_leo_smile"),
    DialogueNode(
        "d_leo_smile",
        CHUCHMEK,
        "Самое важное: достаточно ли в плане поводов улыбнуться. Пока проверяет во сне. Очень тщательно.",
    ),
)

# --- Часть E. Последний вопрос к организатору: обе ветки сходятся в e_ready ---

PART_E_CHOICE = _script(
    DialogueNode(
        CHOICE_ID,
        CHUCHMEK,
        "Итак, план ясен. Вопросы к организатору?",
        choices=[
            DialogueChoice("Давай уже спасать праздник.", "e_rescue"),
            DialogueChoice("Почему за праздник отвечает именно гриб?", "e_mushroom"),
        ],
    ),
    DialogueNode(
        "e_rescue",
        CHUCHMEK,
        "Вот это настрой! Я бы тоже спасал, но кто-то же должен руководить спасением.",
        next_id="e_ready",
    ),
    DialogueNode(
        "e_mushroom",
        CHUCHMEK,
        "Больше никто не вызвался. И я вырос у стены библиотеки: прочитал все книги о праздниках. Обложки.",
        next_id="e_explains",
    ),
    DialogueNode("e_explains", ALICE, "Это многое объясняет.", next_id="e_ready"),
    DialogueNode(
        "e_ready",
        CHUCHMEK,
        "В любом случае все три портала открыты. Порядок — на твой вкус. Ты же именинница.",
    ),
)

# --- Часть F. Конец вступления ---

PART_F_ENDING = _script(
    DialogueNode("f_go", ALICE, "Ладно. Показывай, куда идти.", next_id="f_questions"),
    DialogueNode(
        "f_questions",
        ALICE,
        "Но если мне понадобится справка о том, что у меня день рождения, я буду задавать вопросы.",
        next_id="f_form_12b",
    ),
    DialogueNode(
        "f_form_12b",
        CHUCHMEK,
        "Разумно. Хотя для вопросов нужна форма № 12-Б. Бумажная волокита не щадит даже праздники.",
    ),
)

BEATS: tuple[Beat, ...] = (
    # A. Классическая сказка
    Cue("A", "title_card", 2.6),  # заголовок «Алиса в стране чудес» и Алиса на спокойной странице
    Pause("A", 1.2),  # короткая вступительная пауза
    Cue("A", "rabbit_runs_in", 1.6),
    Lines("A", PART_A_RABBIT),
    Cue("A", "rabbit_points", 1.2),  # Кролик показывает, где по расписанию должна быть нора; её ещё нет
    Lines("A", PART_A_INVITE),
    # Игрок ведёт Алису сам: у места норы сказка сбоит, нора появляется, E у норы — дальше.
    Explore("A", "find_burrow"),
    Cue("A", "alice_prepares", 1.0),  # подошла к самому краю и присела
    Lines("A", PART_A_GO),
    Cue("A", "alice_jumps", 0.4),  # прыжок — и сказка зависает прямо в воздухе
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
    # D–F. Праздничный план, выбор, конец
    Lines("D", PART_D_PLAN),
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
    "d_wait": {"chuchmek": "talk_gesture"},
    "d_whose": {"chuchmek": "idle"},
    "d_yours": {"chuchmek": "talk_excited"},
    ORGANIZER_CHOICE_ID: {"chuchmek": "clipboard_confident"},
    "d_self_appointed": {"chuchmek": "smug_wink"},
    "d_democratic": {"chuchmek": "idle", "alice": "react_down_1"},
    "d_down_to_business": {"chuchmek": "talk_excited"},
    "d_thought_of": {"chuchmek": "curious_glance"},
    "d_plan": {"chuchmek": "talk_01", **FACING_CHUCHMEK},
    "d_disaster": {"chuchmek": "curious_glance", "alice": "react_down_2"},
    "d_pieces": {"chuchmek": "confused"},
    "d_now": {"chuchmek": "idle"},
    "d_trials": {"chuchmek": "talk_gesture"},
    "d_mosaic": {"chuchmek": "talk_excited"},
    "d_inside": {"chuchmek": "curious_glance"},
    "d_intrigue": {"chuchmek": "wink", **FACING_CHUCHMEK},
    "d_why_me": {"chuchmek": "curious_glance"},
    "d_tried": {"chuchmek": "panicked"},
    "d_only_you": {"chuchmek": "talk_01"},
    "d_leo": {"chuchmek": "clipboard_confident"},
    "d_leo_job": {"chuchmek": "idle"},
    "d_leo_smile": {"chuchmek": "smug_wink"},
    CHOICE_ID: {"chuchmek": "clipboard_confident"},
    "e_rescue": {"chuchmek": "talk_excited"},
    "e_mushroom": {"chuchmek": "smug_wink"},
    "e_explains": {"chuchmek": "idle"},
    "e_ready": {"chuchmek": "talk_gesture"},
    "f_form_12b": {"chuchmek": "clipboard_confident"},
}


def all_scripts() -> list[DialogueScript]:
    return [beat.script for beat in BEATS if isinstance(beat, Lines)]
