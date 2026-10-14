"""Сцена вступления: классическая «Алиса в стране чудес», которая ломается и становится «…Чучмека?!».

Сценарий (реплики, паузы, таблица превращения заголовка) — в game/story/intro_dialogue.py;
здесь только показ. Всё неблокирующее: шаги вступления переключаются по накопленному
времени dt и по завершению диалогов, поэтому результат не зависит от частоты кадров.
Сбой сказки — чисто визуальный: рывки, пропущенные кадры, рваные строки и шуточное
сообщение, нарисованное как страница книги. Ни исключений, ни пауз, ни блокировок.

Оформление временное: страница и эффекты нарисованы программно, настоящие локации
появятся отдельно.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import pygame

import config
from game.core.input import Action, actions_for
from game.core.scenes import Scene
from game.dialogue.box import DialogueBox
from game.dialogue.model import DialogueChoice, DialogueController
from game.graphics.animation import AnimationPlayer
from game.graphics.fonts import load_font, render_text
from game.graphics.placeholder import placeholder_animations
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, try_load_character_sprites
from game.story.intro_dialogue import (
    BEATS,
    CHOICE_ID,
    ERROR_LINES,
    ERROR_TITLE,
    POSES,
    SPEAKER_ACTORS,
    TITLE_CLASSIC,
    TITLE_FINAL,
    TITLE_REVEAL_START,
    Beat,
    Cue,
    Lines,
    TitleStep,
    all_scripts,
    title_step_at,
)

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 48  # кадры 64×64 уменьшаются до 48×48 ближайшим соседом

# Расстановка на сцене (x — середина под ногами).
ALICE_X = 160
RABBIT_X = 96
BURROW_X = 268  # нора у правого края
ALICE_BURROW_X = 240  # где Алиса останавливается перед норой
CHUCHMEK_X = 232  # где Чучмек стоит после выхода из норы
CAP_HEIGHT = 17  # сколько пикселей шляпки видно, когда Чучмек только выглядывает
JUMP_HEIGHT = 22  # «слишком высокий» прыжок Чучмека: выше он зашёл бы на заголовок
ACTOR_LAYOUT = {
    "white_rabbit": (RABBIT_X, "idle_front"),
    "alice": (ALICE_X, "idle_down"),
    "chuchmek": (CHUCHMEK_X, "idle"),
}
DRAW_ORDER = ("white_rabbit", "chuchmek", "alice")
BOB_SPEED = 9.0  # покачивание говорящего, радиан в секунду
# Эффекты считаются шагами не длиннее этого, даже если пришёл большой dt: ни один
# короткий момент (ступенька заголовка, кадр сбоя) не пропускается из-за подвисания окна.
MAX_SUBSTEP = 0.05
TITLE_BOTTOM = 30  # ниже этой линии заголовок не опускается: персонажи выше неё не поднимаются

# Сбой: содержимое «подвисает» на GLITCH_LAG секунд, рваные строки меняются каждые GLITCH_SLOT.
GLITCH_SLOT = 0.1
GLITCH_LAG = 0.24
TEAR_BAND = 6
GLITCH_ALICE_POSES = ("walk_left_2", "idle_up", "walk_left_4", "idle_left", "walk_left_1", "idle_down")
GLITCH_RABBIT_POSES = ("panic_gasp", "back_view", "confused_watch", "idle_front")
GLITCH_LINE_COLORS = ((255, 214, 230), (206, 240, 226), (255, 240, 176))

# Сообщение об ошибке: страница книги, а не окно системы.
ERROR_W, ERROR_H = 272, 70
ERROR_SLIDE = 0.35  # секунд, пока оно въезжает
ERROR_LINE_TIMES = (0.8, 1.7)  # когда появляются строки сообщения
ERROR_BREAK_AT = 3.0  # с этого момента сообщение разваливается
ERROR_SEGMENTS = 20

# Палитра временной сказочной страницы и её «сломанной» версии.
PAGE_COLOR = (246, 236, 208)
PAGE_EDGE_COLOR = (196, 160, 112)
INK_COLOR = (120, 84, 52)
SUN_COLOR = (250, 206, 108)
CLOUD_COLOR = (255, 252, 244)
HILL_COLORS = ((178, 206, 146), (154, 188, 126))
PATH_COLOR = (226, 204, 160)
TREE_COLORS = ((106, 150, 96), (132, 98, 70))
FLOWER_COLORS = ((232, 150, 170), (250, 214, 110), (190, 170, 230))
ABSURD_COLOR = (226, 214, 238)
ABSURD_DOT_COLOR = (196, 232, 214)
ABSURD_HILL_COLORS = ((236, 168, 196), (150, 206, 204))
TITLE_COLOR = (112, 70, 56)
TITLE_SHADOW_COLOR = (236, 216, 176)
TITLE_FINAL_COLOR = (190, 54, 66)
TITLE_FINAL_SHADOW_COLOR = (250, 226, 214)
EARTH_COLOR = (150, 112, 72)
HOLE_COLOR = (44, 30, 34)
HOLE_SHADOW_COLOR = (124, 156, 104)
GRASS_COLOR = (98, 142, 84)
PARCHMENT_COLOR = (250, 242, 220)
PLUM_COLOR = (128, 74, 126)
GOLD_COLOR = (222, 176, 84)
CREAM_COLOR = (252, 238, 204)
FLASH_COLOR = (255, 250, 236)
DIM_COLOR = (52, 38, 74)
FINALE_TEXT = "…и сказка пошла совсем не по плану"


def _ease(t: float) -> float:
    """Плавный разгон и торможение: 0 → 1."""
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _walk_progress(p: float) -> float:
    """Доля пути Алисы к норе: ровный шаг, а у самой норы — торможение."""
    if p < 0.75:
        return 0.85 * p / 0.75
    q = (p - 0.75) / 0.25
    return 0.85 + 0.15 * (1 - (1 - q) ** 2)


class StageActor:
    """Персонаж на сцене вступления: поза или анимация из манифеста, позиция и положение тела.

    Если спрайтов нет или нужного кадра нет в манифесте, показывается ближайшая замена,
    а в крайнем случае — временный манекен: вступление не падает из-за ресурса.
    Кадры только масштабируются (ближайший сосед) и, для комических эффектов, наклоняются
    или приседают; отражение по горизонтали не используется.
    """

    def __init__(self, char_id: str, sprites: CharacterSprites | None, home_x: int, pose: str) -> None:
        self.id = char_id
        self.sprites = sprites
        self.home_x = home_x
        self.x = float(home_x)
        self.dx = 0.0  # временное смещение: дрожание, покачивание
        self.lift = 0.0  # насколько персонаж поднят над землёй, пиксели (отрицательно — под землёй)
        self.squash = 1.0  # 1 — стоит прямо, меньше — присел
        self.tilt = 0.0  # наклон в градусах против часовой стрелки
        self.alpha = 255
        self.visible = False
        self.default_pose = pose
        self.pose = pose
        self.player: AnimationPlayer | None = None
        self._scaled: dict[int, pygame.Surface] = {}

    def set_pose(self, frame_id: str) -> None:
        self.pose = frame_id
        self.player = None

    def play(self, group_name: str, loop: bool | None = None) -> bool:
        """Проигрывает группу кадров, только если она есть и не черновая."""
        sprites = self.sprites
        group = sprites.groups.get(group_name) if sprites is not None else None
        if group is None or group.draft:
            return False
        self.player = AnimationPlayer(sprites.animation(group_name, loop))
        return True

    @property
    def is_playing(self) -> bool:
        return self.player is not None and not self.player.is_finished

    def update(self, dt: float) -> None:
        if self.player is not None:
            self.player.update(dt)

    def image(self) -> pygame.Surface:
        source = self.player.frame if self.player is not None else self._pose_image()
        if source.get_size() != (64, 64):
            return source  # временный манекен уже нужного размера
        scaled = self._scaled.get(id(source))
        if scaled is None:
            # Ближайший сосед: новый кадр, исходный не меняется.
            scaled = self._scaled[id(source)] = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
        return scaled

    def _pose_image(self) -> pygame.Surface:
        sprites = self.sprites
        if sprites is not None:
            for frame_id in (self.pose, self.default_pose):
                try:
                    return sprites.frame(frame_id).image
                except KeyError:
                    continue
            return sprites.frames[0].image
        return _fallback_frame()

    def _placed_image(self, ground: int) -> tuple[pygame.Surface, pygame.Rect]:
        """Кадр с учётом приседания и наклона и его место на холсте."""
        image = self.image()
        if self.squash != 1.0:
            image = pygame.transform.scale(image, (image.get_width(), max(1, round(image.get_height() * self.squash))))
        rect = image.get_rect(midbottom=(round(self.x + self.dx), ground - round(self.lift)))
        if self.tilt:
            image = pygame.transform.rotate(image, self.tilt)
            rect = image.get_rect(center=rect.center)
        return image, rect

    def bounds(self, ground: int) -> pygame.Rect:
        """Прямоугольник, который персонаж занимает на холсте сейчас."""
        return self._placed_image(ground)[1]

    def draw(self, surface: pygame.Surface, ground: int, clip_bottom: int | None = None) -> None:
        """Рисует персонажа; clip_bottom — линия, ниже которой его не видно (вход в нору)."""
        if not self.visible or self.alpha <= 0:
            return
        image, rect = self._placed_image(ground)
        if self.alpha < 255:
            image = image.copy()
            image.set_alpha(self.alpha)
        old_clip = surface.get_clip()
        if clip_bottom is not None:
            surface.set_clip(old_clip.clip(pygame.Rect(0, 0, WIDTH, clip_bottom)))
        surface.blit(image, rect)
        surface.set_clip(old_clip)


_FALLBACK: pygame.Surface | None = None


def _fallback_frame() -> pygame.Surface:
    """Временный манекен (16×26), увеличенный вдвое, — если спрайтов персонажа нет."""
    global _FALLBACK
    if _FALLBACK is None:
        frame = placeholder_animations().default.frames[0]
        _FALLBACK = pygame.transform.scale(frame, (frame.get_width() * 2, frame.get_height() * 2))
    return _FALLBACK


class IntroScene(Scene):
    """Вступление. Когда оно сыграно, вызывается on_complete, а затем:
    если задана зарегистрированная сцена next_scene (будущая центральная локация) —
    переход на неё, иначе возврат к предыдущей сцене. Backspace прерывает вступление."""

    def __init__(
        self,
        on_complete: Callable[[IntroScene], None] | None = None,
        next_scene: str | None = None,
        characters_dir: str | Path = CHARACTERS_DIR,
        beats: tuple[Beat, ...] = BEATS,
    ) -> None:
        self.beats = beats
        self.on_complete = on_complete
        self.next_scene = next_scene
        root = Path(characters_dir)
        self.actors = {
            char_id: StageActor(char_id, try_load_character_sprites(root / char_id), x, pose)
            for char_id, (x, pose) in ACTOR_LAYOUT.items()
        }
        self.box = DialogueBox()
        for script in all_scripts():
            self.box.check_fits(script)
        # Персонажи стоят выше самого высокого окна диалога: текст их не закрывает.
        self.ground = min(self._box_top(node) for script in all_scripts() for node in script.nodes.values()) - 3

        self.beat_index = 0
        self.beat_time = 0.0
        self.time = 0.0  # общее время сцены — для покачиваний и дрожания
        self.dialogue: DialogueController | None = None
        self.answers: dict[str, DialogueChoice] = {}
        self.completed = False
        self._shown_node_id: str | None = None

        # Заголовок и всё, что с ним делает превращение.
        self.title = ""
        # Журнал вступления по порядку: ("cue", имя) — началось событие, ("title", текст) —
        # заголовок стал таким, ("node", id) — показана реплика. Нужен прежде всего тестам.
        self.events: list[tuple[str, str]] = []
        self.title_visible = True
        self.title_alpha = 255
        self.title_shake = 0
        self.title_dy = 0
        self.page_blend = 0.0  # 0 — сказочная страница, 1 — абсурдная
        self.flash = 0.0  # белая вспышка, 0..1
        # Состояние эффектов.
        self.hidden: set[str] = set()  # что на миг «пропало» при сбое
        self.glitch_slot = 0
        self.error_text: tuple[str, ...] = ()  # какие строки сообщения об ошибке видны сейчас
        self.burrow_open = 0.0
        self.chuchmek_clipped = False  # Чучмек ещё внутри норы
        self.watch_reversed = False  # Кролик «незаметно» крутит часы наоборот
        self._lag_slot = -1

        self._title_font = load_font(16)
        self._font = load_font(9)
        self._font10 = load_font(10)
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self._pages = {"fairy": _render_fairy_page(), "absurd": _render_absurd_page()}
        self._buffer = pygame.Surface(config.LOGICAL_SIZE)
        self._lag_buffer = pygame.Surface(config.LOGICAL_SIZE)
        self._flash_surface = pygame.Surface(config.LOGICAL_SIZE)
        self._flash_surface.fill(FLASH_COLOR)
        self._dim_surface = pygame.Surface(config.LOGICAL_SIZE)
        self._dim_surface.fill(DIM_COLOR)
        self._dim_surface.set_alpha(120)
        self._start_beat()

    # --- Состояние ---

    @property
    def beat(self) -> Beat | None:
        return self.beats[self.beat_index] if self.beat_index < len(self.beats) else None

    @property
    def cue_log(self) -> list[str]:
        """Имена постановочных событий в порядке начала."""
        return [value for kind, value in self.events if kind == "cue"]

    @property
    def title_history(self) -> list[str]:
        """Каждое новое состояние заголовка по порядку (пустая строка — заголовок убран)."""
        return [value for kind, value in self.events if kind == "title"]

    @property
    def cue_name(self) -> str | None:
        beat = self.beat
        return beat.name if isinstance(beat, Cue) else None

    @property
    def part(self) -> str | None:
        beat = self.beat
        return beat.part if beat is not None else None

    @property
    def choice(self) -> DialogueChoice | None:
        """Ответ Алисы в части E, если он уже выбран."""
        return self.answers.get(CHOICE_ID)

    def _box_top(self, node) -> int:
        layout = self.box.layout(node)
        return (layout.name_tab or layout.box).top

    def _set_title(self, text: str) -> None:
        if text != self.title:
            self.title = text
            self.events.append(("title", text))

    # --- Управление ---

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and Action.CANCEL in actions_for(event):
            self.finish()  # тестовое вступление прервано, итога нет
            return
        if self.dialogue is None:
            return  # во время пауз и эффектов нажатия ничего не пропускают
        actions = actions_for(event) if event.type == pygame.KEYDOWN else frozenset()
        if Action.INTERACT in actions and Action.CONFIRM not in actions:
            self.dialogue.confirm()  # как во всей игре: E продолжает реплику и выбирает ответ
        else:
            self.dialogue.handle_event(event)
        self._sync_dialogue()

    def update(self, dt: float) -> None:
        self.time += dt
        for actor in self.actors.values():
            actor.update(dt)
        remaining = dt
        # Остаток времени переходит в следующий шаг: итог не зависит от разбиения dt на кадры.
        while remaining > 0 and self.beat is not None and not self.completed:
            if self.dialogue is not None:
                self.dialogue.update(remaining)
                self._sync_dialogue()
                break
            beat = self.beat
            step = min(remaining, beat.seconds - self.beat_time, MAX_SUBSTEP)
            self.beat_time += step
            remaining -= step
            self._animate_cue(beat)
            if self.beat_time >= beat.seconds - 1e-9:
                self._next_beat()
        self._animate_speaker()

    def _start_beat(self) -> None:
        self.beat_time = 0.0
        beat = self.beat
        if beat is None:
            self._complete()
        elif isinstance(beat, Lines):
            self.dialogue = DialogueController(beat.script)
            self._sync_dialogue()
        elif isinstance(beat, Cue):
            self.events.append(("cue", beat.name))
            self._call_cue("begin", beat.name)

    def _next_beat(self) -> None:
        beat = self.beat
        if isinstance(beat, Cue):
            self._call_cue("end", beat.name)
            for actor in self.actors.values():
                actor.lift = actor.dx = actor.tilt = 0.0
        self.dialogue = None
        self.watch_reversed = False
        self.beat_index += 1
        self._start_beat()

    def _call_cue(self, stage: str, name: str, *args) -> None:
        handler = getattr(self, f"_{stage}_{name}", None)
        if handler is not None:
            handler(*args)

    def _animate_cue(self, beat: Beat) -> None:
        if isinstance(beat, Cue):
            self._call_cue("do", beat.name, self.beat_time / beat.seconds)

    def _sync_dialogue(self) -> None:
        """Применяет ремарки новой реплики и завершает шаг, когда диалог пройден."""
        dialogue = self.dialogue
        if dialogue is None:
            return
        self.answers.update(dialogue.answers)
        if dialogue.is_finished:
            self._next_beat()
            return
        node = dialogue.node
        if node.id != self._shown_node_id:
            self._shown_node_id = node.id
            self.events.append(("node", node.id))
            self.watch_reversed = node.id == "r_prepared"
            for char_id, frame_id in POSES.get(node.id, {}).items():
                self.actors[char_id].set_pose(frame_id)

    def _animate_speaker(self) -> None:
        """Говорящий покачивается, пока печатается его реплика; Алиса ещё и шевелит губами."""
        dialogue = self.dialogue
        if dialogue is None or dialogue.node is None:
            return
        speaker = SPEAKER_ACTORS.get(dialogue.node.speaker)
        for char_id, actor in self.actors.items():
            talking = char_id == speaker and dialogue.is_typing
            actor.lift = abs(math.sin(self.time * BOB_SPEED)) * 1.5 if talking else 0.0
            if char_id == "alice":
                pinned = char_id in POSES.get(dialogue.node.id, {})
                if talking and not pinned and not actor.is_playing:
                    actor.play("talk_down", loop=True)
                elif not talking and actor.player is not None and actor.player.animation.loop:
                    actor.set_pose(actor.pose)

    def _complete(self) -> None:
        if self.completed:
            return
        self.completed = True
        if self.on_complete is not None:
            self.on_complete(self)
        manager = self.manager
        if manager is not None and self.next_scene is not None and manager.is_registered(self.next_scene):
            manager.replace(self.next_scene)  # сюда подключится центральная локация
        else:
            self.finish()

    # --- Постановочные события: _begin_<имя>, _do_<имя>(p), _end_<имя> ---

    @property
    def _alice(self) -> StageActor:
        return self.actors["alice"]

    @property
    def _rabbit(self) -> StageActor:
        return self.actors["white_rabbit"]

    @property
    def _chuchmek(self) -> StageActor:
        return self.actors["chuchmek"]

    # A. Классическая заставка

    def _begin_title_card(self) -> None:
        self._set_title(TITLE_CLASSIC)
        self.title_alpha = 0
        self._alice.visible, self._alice.alpha = True, 0

    def _do_title_card(self, p: float) -> None:
        self.title_alpha = round(255 * _ease(p / 0.5))
        fade = _ease((p - 0.3) / 0.7)
        self._alice.alpha = round(255 * fade)
        self._alice.lift = 8 * (1 - fade)

    def _end_title_card(self) -> None:
        self.title_alpha = 255
        self._alice.alpha = 255

    def _begin_rabbit_runs_in(self) -> None:
        self._rabbit.visible = True
        self._rabbit.set_pose("run_right_2")
        self._rabbit.x = -SPRITE_SIZE

    def _do_rabbit_runs_in(self, p: float) -> None:
        rabbit = self._rabbit
        rabbit.x = -SPRITE_SIZE + (RABBIT_X + SPRITE_SIZE) * _ease(p)
        rabbit.lift = abs(math.sin(p * math.pi * 5)) * 4 * (1 - p)  # торопливые прыжки
        if p > 0.4 and self._alice.pose != "idle_left":
            self._alice.set_pose("idle_left")  # Алиса оборачивается на шум

    def _end_rabbit_runs_in(self) -> None:
        self._rabbit.x = RABBIT_X
        self._rabbit.set_pose("checks_watch_happy")

    def _begin_rabbit_points(self) -> None:
        self._rabbit.set_pose("hurries_pointing")
        self.burrow_open = 0.0

    def _do_rabbit_points(self, p: float) -> None:
        self.burrow_open = _ease(p)  # нора раскрывается там, куда указывает Кролик

    def _end_rabbit_points(self) -> None:
        self.burrow_open = 1.0

    def _begin_alice_walks(self) -> None:
        self._alice.play("walk_right", loop=True)  # не черновая группа: ходьба вправо
        if not self._alice.is_playing:
            self._alice.set_pose("idle_right")

    def _do_alice_walks(self, p: float) -> None:
        alice = self._alice
        alice.x = ALICE_X + (ALICE_BURROW_X - ALICE_X) * _walk_progress(p)
        if p > 0.93 and alice.player is not None:
            alice.set_pose("idle_right")  # остановилась — ноги больше не шагают

    def _end_alice_walks(self) -> None:
        self._alice.x = ALICE_BURROW_X
        self._alice.set_pose("idle_right")

    def _begin_alice_prepares(self) -> None:
        self._alice.set_pose("idle_right")

    def _do_alice_prepares(self, p: float) -> None:
        self._alice.squash = 1 - 0.12 * _ease(p / 0.5)  # присела, чтобы прыгнуть

    def _end_alice_prepares(self) -> None:
        self._alice.squash = 0.88

    # B. Сбой сказки

    def _begin_glitch(self) -> None:
        self._lag_slot = -1
        self.hidden = set()
        self._alice.squash = 1.0
        self.title_shake = 2

    def _do_glitch(self, p: float) -> None:
        slot = int(self.beat_time / GLITCH_SLOT)
        self.glitch_slot = slot
        alice, rabbit = self._alice, self._rabbit
        if p < 0.12:  # первая лёгкая дрожь: ничего ещё не понятно
            self.hidden = set()
            return
        self.hidden = set()
        if slot % 5 == 2:
            self.hidden.add("white_rabbit")
        if slot % 7 == 3:
            self.hidden.add("burrow")
        if slot % 6 == 4:
            self.hidden.add("title")
        if slot % 9 == 5:
            self.hidden.add("alice")
        # Алиса «прыгает» неправильными фазами движения, рывками.
        alice.set_pose(GLITCH_ALICE_POSES[slot % len(GLITCH_ALICE_POSES)])
        alice.lift = ((slot * 3) % 5 - 2) * 2
        alice.dx = ((slot * 7) % 5 - 2) * 2
        rabbit.set_pose(GLITCH_RABBIT_POSES[slot % len(GLITCH_RABBIT_POSES)])

    def _end_glitch(self) -> None:
        self.hidden = set()
        self.title_shake = 0

    def _begin_error_message(self) -> None:
        self._set_title("")
        self.hidden = {"white_rabbit", "alice", "title"}
        self.error_text = ()

    def _do_error_message(self, p: float) -> None:
        t = self.beat_time
        if t < ERROR_SLIDE or t >= self.beats[self.beat_index].seconds - 0.2:
            self.error_text = ()
            return
        shown = [ERROR_TITLE]
        shown += [line for line, start in zip(ERROR_LINES, ERROR_LINE_TIMES) if t >= start]
        self.error_text = tuple(shown)

    def _end_error_message(self) -> None:
        self.error_text = ()

    def _begin_restart(self) -> None:
        """Сказка «перезапущена»: снова классическая заставка, как в самом начале."""
        self.hidden = set()
        self.flash = 1.0
        self.page_blend = 0.0
        self.title_visible, self.title_alpha, self.title_shake = True, 255, 0
        self._set_title(TITLE_CLASSIC)
        alice = self._alice
        alice.x, alice.squash, alice.alpha, alice.visible = ALICE_X, 1.0, 255, True
        alice.set_pose("idle_down")
        self._rabbit.visible = False
        self._rabbit.x = RABBIT_X
        self._chuchmek.visible = False

    def _do_restart(self, p: float) -> None:
        self.flash = 1 - _ease(p / 0.8)

    def _end_restart(self) -> None:
        self.flash = 0.0

    def _apply_title_step(self, step: TitleStep) -> None:
        self._set_title(step.text)
        self.title_visible = step.visible
        self.title_shake = step.shake

    def _begin_title_rewrite(self) -> None:
        self._apply_title_step(title_step_at(0.0))

    def _do_title_rewrite(self, p: float) -> None:
        seconds = self.beats[self.beat_index].seconds
        t = p * seconds
        self._apply_title_step(title_step_at(t))
        if t >= TITLE_REVEAL_START - 1e-9:  # финальное название: «хлопок», вспышка, страница меняет краски
            local = t - TITLE_REVEAL_START
            self.page_blend = _ease(local / 1.4)
            self.flash = 0.8 * (1 - _ease(local / 0.5))
            self.title_dy = round(5 * math.sin(min(1.0, local / 0.5) * math.pi))

    def _end_title_rewrite(self) -> None:
        self._set_title(TITLE_FINAL)
        self.title_visible, self.title_shake, self.title_dy = True, 0, 0
        self.page_blend = 1.0
        self.flash = 0.0

    # C. Чучмек

    def _begin_chuchmek_emerges(self) -> None:
        chuchmek = self._chuchmek
        chuchmek.visible, chuchmek.alpha = True, 255
        chuchmek.x = BURROW_X
        chuchmek.set_pose("confused")
        self.chuchmek_clipped = True
        self._alice.set_pose("idle_right")  # Алиса смотрит на нору

    def _do_chuchmek_emerges(self, p: float) -> None:
        chuchmek = self._chuchmek
        hidden_part = -(SPRITE_SIZE - CAP_HEIGHT)  # под землёй всё, кроме шляпки
        self.chuchmek_clipped = p < 0.55
        if p < 0.12:  # видна только покосившаяся шляпка
            chuchmek.lift = hidden_part
            chuchmek.tilt = 12 + 2 * math.sin(p * 60)
        elif p < 0.45:  # медленно поднимается и выпрямляется
            q = _ease((p - 0.12) / 0.33)
            chuchmek.lift = hidden_part * (1 - q)
            chuchmek.tilt = 12 * (1 - q)
        elif p < 0.55:  # замер: проверяет, всё ли на месте
            chuchmek.lift, chuchmek.tilt = 0.0, 0.0
            chuchmek.set_pose("curious_glance")
        elif p < 0.72:  # неожиданно подпрыгивает слишком высоко
            q = (p - 0.55) / 0.17
            chuchmek.set_pose("arms_up_panic")
            chuchmek.lift = JUMP_HEIGHT * math.sin(q * math.pi)
            chuchmek.x = BURROW_X - 22 * _ease(q)
        else:  # падает на ноги, шатается и выбирается из норы
            q = (p - 0.72) / 0.28
            chuchmek.set_pose("panicked" if q < 0.6 else "clipboard_confident")
            chuchmek.lift = 0.0
            sway = math.sin(q * 3 * math.pi) * (1 - q)
            chuchmek.tilt = 16 * sway
            chuchmek.dx = 5 * sway
            chuchmek.x = (BURROW_X - 22) + (CHUCHMEK_X - (BURROW_X - 22)) * _ease(q)

    def _end_chuchmek_emerges(self) -> None:
        chuchmek = self._chuchmek
        chuchmek.x = CHUCHMEK_X
        chuchmek.set_pose("clipboard_confident")  # важный вид, будто так и было задумано
        self.chuchmek_clipped = False

    def _begin_alice_reacts(self) -> None:
        self._alice.set_pose("idle_down")
        self._alice.play("react_down")

    def _end_alice_reacts(self) -> None:
        self._alice.set_pose("idle_right")

    # F. Конец

    def _begin_finale(self) -> None:
        self._chuchmek.set_pose("smug_wink")
        self._alice.set_pose("idle_down")
        self._alice.play("happy_down")

    def _do_finale(self, p: float) -> None:
        self._chuchmek.lift = abs(math.sin(p * math.pi * 2)) * 3

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface) -> None:
        name = self.cue_name
        if name == "glitch":
            self._draw_glitch(surface)
        elif name == "error_message":
            self._draw_error(surface)
        else:
            self._compose(surface)
            if name == "finale":
                self._draw_finale_plaque(surface)
        if self.flash > 0:
            self._flash_surface.set_alpha(round(255 * min(1.0, self.flash)))
            surface.blit(self._flash_surface, (0, 0))
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue)

    def _compose(self, surface: pygame.Surface) -> None:
        """Страница, нора, персонажи и заголовок. Персонажи не заходят на заголовок и окно диалога."""
        surface.blit(self._pages["fairy"], (0, 0))
        if self.page_blend > 0:
            absurd = self._pages["absurd"]
            absurd.set_alpha(round(255 * self.page_blend))
            surface.blit(absurd, (0, 0))
        show_burrow = "burrow" not in self.hidden and self.burrow_open > 0
        if show_burrow:
            _draw_burrow_back(surface, self.burrow_open, self.ground)
        for char_id in DRAW_ORDER:
            if char_id in self.hidden:
                continue
            clip = self.ground + 1 if char_id == "chuchmek" and self.chuchmek_clipped else None
            self.actors[char_id].draw(surface, self.ground, clip)
        if show_burrow:
            _draw_burrow_front(surface, self.burrow_open, self.ground)
        if self.watch_reversed and "white_rabbit" not in self.hidden:
            self._draw_reversed_watch(surface)
        self._draw_title(surface)

    def _text(self, font: pygame.font.Font, text: str, color: config.Color) -> pygame.Surface:
        key = (id(font), text, color)
        image = self._text_cache.get(key)
        if image is None:
            image = self._text_cache[key] = render_text(font, text, color)
        return image

    def _title_image(self, text: str) -> pygame.Surface:
        key = ("title", text)
        image = self._text_cache.get(key)
        if image is None:
            final = text == TITLE_FINAL
            color, shadow = (TITLE_FINAL_COLOR, TITLE_FINAL_SHADOW_COLOR) if final else (TITLE_COLOR, TITLE_SHADOW_COLOR)
            front, back = render_text(self._title_font, text, color), render_text(self._title_font, text, shadow)
            image = pygame.Surface((front.get_width() + 1, front.get_height() + 1), pygame.SRCALPHA)
            image.blit(back, (1, 1))
            image.blit(front, (0, 0))
            self._text_cache[key] = image
        return image

    def _draw_title(self, surface: pygame.Surface) -> None:
        if not self.title or not self.title_visible or "title" in self.hidden:
            return
        image = self._title_image(self.title)
        slot = int(self.time * 24)
        dx = ((slot * 5) % 3 - 1) * self.title_shake
        if self.title_alpha < 255:
            image = image.copy()
            image.set_alpha(self.title_alpha)
        surface.blit(image, image.get_rect(midtop=(WIDTH // 2 + dx, 9 - self.title_dy)))

    def _draw_reversed_watch(self, surface: pygame.Surface) -> None:
        """Крошечные часы над Кроликом: стрелки идут против часовой. Заметит только внимательный."""
        cx, cy = round(self._rabbit.x + 22), self.ground - 46
        pygame.draw.circle(surface, CREAM_COLOR, (cx, cy), 5)
        pygame.draw.circle(surface, INK_COLOR, (cx, cy), 5, 1)
        angle = -self.time * 3.0
        for length, speed in ((3.6, 1.0), (2.2, 0.25)):
            a = angle * speed
            pygame.draw.line(surface, INK_COLOR, (cx, cy), (cx + math.sin(a) * length, cy - math.cos(a) * length))

    def _draw_finale_plaque(self, surface: pygame.Surface) -> None:
        beat = self.beat
        image = self._text(self._font10, FINALE_TEXT, INK_COLOR).copy()
        image.set_alpha(round(255 * _ease(self.beat_time / (beat.seconds * 0.4))))
        rect = image.get_rect(center=(WIDTH // 2, 44))
        pygame.draw.rect(surface, PAGE_COLOR, rect.inflate(10, 6))
        pygame.draw.rect(surface, PAGE_EDGE_COLOR, rect.inflate(10, 6), 1)
        surface.blit(image, rect)

    # --- Сбой ---

    def _draw_glitch(self, surface: pygame.Surface) -> None:
        """Содержимое подвисает (пропущенные кадры), а изображение рвётся горизонтальными полосами."""
        lag_slot = int(self.beat_time / GLITCH_LAG)
        if lag_slot != self._lag_slot:
            self._compose(self._lag_buffer)
            self._lag_slot = lag_slot
        p = self.beat_time / self.beats[self.beat_index].seconds
        self._tear(surface, self._lag_buffer, self.glitch_slot, 2 + int(8 * p))
        for k, color in enumerate(GLITCH_LINE_COLORS):
            y = (self.glitch_slot * 37 + k * 61) % HEIGHT
            pygame.draw.line(surface, color, (0, y), (WIDTH, y))

    def _tear(self, surface: pygame.Surface, source: pygame.Surface, slot: int, amplitude: int) -> None:
        """Рисует source, сдвигая отдельные горизонтальные полосы (с заворотом за край)."""
        surface.blit(source, (0, 0))
        for index, y in enumerate(range(0, HEIGHT, TEAR_BAND)):
            if (slot + index) % 3:
                continue
            offset = ((slot * 7 + index * 13) % (2 * amplitude + 1)) - amplitude
            if not offset:
                continue
            area = pygame.Rect(0, y, WIDTH, min(TEAR_BAND, HEIGHT - y))
            surface.blit(source, (offset, y), area)
            surface.blit(source, (offset - WIDTH if offset > 0 else offset + WIDTH, y), area)

    def _draw_error(self, surface: pygame.Surface) -> None:
        """Страница притихла, а поверх неё — сообщение в виде страницы книги, которое потом разваливается."""
        t = self.beat_time
        self._compose(self._buffer)
        self._buffer.blit(self._dim_surface, (0, 0))
        slot = int(t / 0.25)
        self._tear(surface, self._buffer, slot, 3 if slot % 4 == 0 else 0)
        if t < ERROR_SLIDE:
            top = round(-ERROR_H + (self._error_top() + ERROR_H) * _ease(t / ERROR_SLIDE))
        else:
            top = self._error_top()
        left = (WIDTH - ERROR_W) // 2
        box = self._render_error_box(t)
        if t < ERROR_BREAK_AT:
            surface.blit(box, (left, top))
            return
        e = _ease((t - ERROR_BREAK_AT) / 0.8)
        half = ERROR_H // 2
        flicker = t > ERROR_BREAK_AT + 0.6 and int(t * 20) % 3 == 0
        if t >= self.beats[self.beat_index].seconds - 0.2 or flicker:
            return  # обломки мигают и пропадают
        lower = box.subsurface((0, half, ERROR_W, ERROR_H - half))
        surface.blit(box.subsurface((0, 0, ERROR_W, half)), (left - round(e * 24), top - round(e * 8)))
        surface.blit(lower, (left + round(e * 24), top + half + round(e * 14)))
        # Рваный край на месте разлома.
        y = top + half
        points = [(left + x, y + (3 if (x // 8) % 2 else -3) * (1 - e)) for x in range(0, ERROR_W + 1, 8)]
        pygame.draw.lines(surface, PLUM_COLOR, False, points, 1)

    @staticmethod
    def _error_top() -> int:
        return (HEIGHT - ERROR_H) // 2 - 4

    def _render_error_box(self, t: float) -> pygame.Surface:
        box = pygame.Surface((ERROR_W, ERROR_H))
        box.fill(PARCHMENT_COLOR)
        pygame.draw.rect(box, PLUM_COLOR, box.get_rect(), 2)
        pygame.draw.rect(box, GOLD_COLOR, box.get_rect().inflate(-6, -6), 1)
        band = pygame.Rect(4, 4, ERROR_W - 8, 17)
        pygame.draw.rect(box, PLUM_COLOR, band)
        title = self._text(self._font10, ERROR_TITLE, CREAM_COLOR)
        box.blit(title, title.get_rect(center=band.center))
        _draw_star(box, band.left + 9, band.centery, GOLD_COLOR)
        _draw_star(box, band.right - 10, band.centery, GOLD_COLOR)
        y = band.bottom + 8
        for line, start in zip(ERROR_LINES, ERROR_LINE_TIMES):
            if t >= start:
                box.blit(self._text(self._font, line, INK_COLOR), (12, y))
            y += 13
        # Полоска «восстановления» из страничек: доходит до трети и застревает.
        progress = 0.35 * min(1.0, max(0.0, (t - ERROR_LINE_TIMES[1]) / 1.2))
        filled = int(progress * ERROR_SEGMENTS)
        for index in range(ERROR_SEGMENTS):
            color = GOLD_COLOR if index < filled else (232, 218, 188)
            box.fill(color, (14 + index * 12, ERROR_H - 18, 10, 6))
        return box


def _draw_star(surface: pygame.Surface, x: int, y: int, color: config.Color) -> None:
    """Маленькая сказочная звёздочка-плюс 5×5."""
    pygame.draw.line(surface, color, (x - 2, y), (x + 2, y))
    pygame.draw.line(surface, color, (x, y - 2), (x, y + 2))
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        surface.set_at((x + dx, y + dy), color)


def _burrow_rect(open_t: float, ground: int) -> pygame.Rect:
    rect = pygame.Rect(0, 0, max(2, round(38 * open_t)), max(2, round(12 * open_t)))
    rect.center = (BURROW_X, ground)
    return rect


def _draw_burrow_back(surface: pygame.Surface, open_t: float, ground: int) -> None:
    """Тёмный вход в землю с тенью и пучками травы. Задняя половина: за ней появляется Чучмек."""
    rect = _burrow_rect(open_t, ground)
    pygame.draw.ellipse(surface, HOLE_SHADOW_COLOR, rect.inflate(10, 5))
    pygame.draw.ellipse(surface, EARTH_COLOR, rect.inflate(4, 2))
    pygame.draw.ellipse(surface, HOLE_COLOR, rect)
    for dx, height in ((-22, 4), (-18, 6), (-14, 3), (15, 5), (19, 3), (23, 6)):
        x, y = rect.centerx + round(dx * open_t), rect.centery - 1
        pygame.draw.line(surface, GRASS_COLOR, (x, y), (x - 1, y - round(height * open_t)))
        pygame.draw.line(surface, GRASS_COLOR, (x + 1, y), (x + 2, y - round(height * open_t) + 1))


def _draw_burrow_front(surface: pygame.Surface, open_t: float, ground: int) -> None:
    """Передний край норы: поверх него видно, что Чучмек выбирается из-под земли."""
    rect = _burrow_rect(open_t, ground)
    old_clip = surface.get_clip()
    surface.set_clip(old_clip.clip(pygame.Rect(0, ground, WIDTH, HEIGHT)))
    pygame.draw.ellipse(surface, EARTH_COLOR, rect.inflate(4, 2), 2)
    surface.set_clip(old_clip)
    for dx in (-8, 6):
        x, y = rect.centerx + round(dx * open_t), rect.centery + round(5 * open_t)
        pygame.draw.line(surface, GRASS_COLOR, (x, y), (x - 1, y - 3))
        pygame.draw.line(surface, GRASS_COLOR, (x + 1, y), (x + 2, y - 2))


def _render_fairy_page() -> pygame.Surface:
    """Спокойная сказочная страница: рамка, солнце, облака, холмы, дорожка, деревья, цветы."""
    page = pygame.Surface(config.LOGICAL_SIZE)
    page.fill(PAGE_COLOR)
    horizon = 96
    pygame.draw.circle(page, SUN_COLOR, (276, 52), 11)
    for angle in range(0, 360, 45):
        dx, dy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        pygame.draw.line(page, SUN_COLOR, (276 + dx * 15, 52 + dy * 15), (276 + dx * 20, 52 + dy * 20))
    for x, y in ((52, 56), (206, 50)):
        for ox, oy, w, h in ((0, 3, 30, 9), (7, -2, 18, 10), (-8, 4, 14, 7)):
            pygame.draw.ellipse(page, CLOUD_COLOR, (x + ox, y + oy, w, h))
    pygame.draw.ellipse(page, HILL_COLORS[0], (-40, horizon - 22, 220, 70))
    pygame.draw.ellipse(page, HILL_COLORS[1], (130, horizon - 16, 240, 70))
    pygame.draw.rect(page, HILL_COLORS[1], (0, horizon + 10, WIDTH, HEIGHT))
    pygame.draw.polygon(page, PATH_COLOR, [(150, horizon - 6), (160, horizon - 6), (205, HEIGHT), (110, HEIGHT)])
    for x, y in ((34, horizon - 8), (300, horizon - 4), (216, horizon - 14)):
        pygame.draw.rect(page, TREE_COLORS[1], (x - 1, y - 6, 3, 8))
        pygame.draw.circle(page, TREE_COLORS[0], (x, y - 10), 7)
    for index, (x, y) in enumerate(((30, 128), (52, 150), (84, 138), (240, 144), (270, 160), (292, 132), (22, 164))):
        pygame.draw.line(page, GRASS_COLOR, (x, y), (x, y + 4))
        pygame.draw.circle(page, FLOWER_COLORS[index % 3], (x, y - 1), 2)
    _draw_ornament(page, PAGE_EDGE_COLOR)
    _draw_border(page, PAGE_EDGE_COLOR)
    return page


def _render_absurd_page() -> pygame.Surface:
    """Та же страница после «сюжетного поворота»: сиреневая, в горошек, с кривыми холмами."""
    page = pygame.Surface(config.LOGICAL_SIZE)
    page.fill(ABSURD_COLOR)
    for row, y in enumerate(range(10, HEIGHT, 18)):
        for x in range(10 + (row % 2) * 12, WIDTH, 24):
            pygame.draw.circle(page, ABSURD_DOT_COLOR, (x, y), 3)
    horizon = 96
    left_hill = [(0, horizon - 4), (90, horizon - 30), (170, horizon + 4), (0, HEIGHT)]
    right_hill = [(120, horizon + 2), (250, horizon - 26), (WIDTH, horizon - 2), (WIDTH, HEIGHT), (120, HEIGHT)]
    pygame.draw.polygon(page, ABSURD_HILL_COLORS[0], left_hill)
    pygame.draw.polygon(page, ABSURD_HILL_COLORS[1], right_hill)
    pygame.draw.rect(page, ABSURD_HILL_COLORS[1], (0, horizon + 10, WIDTH, HEIGHT))
    # Солнце, которое передумало быть кругом.
    pygame.draw.rect(page, SUN_COLOR, (268, 44, 16, 16))
    pygame.draw.rect(page, PAGE_EDGE_COLOR, (268, 44, 16, 16), 1)
    _draw_ornament(page, (168, 132, 190))
    _draw_border(page, (168, 132, 190))
    return page


def _draw_ornament(page: pygame.Surface, color: config.Color) -> None:
    """Тонкая линия с ромбиком под заголовком."""
    y = 31
    pygame.draw.line(page, color, (60, y), (150, y))
    pygame.draw.line(page, color, (170, y), (260, y))
    pygame.draw.polygon(page, color, [(160, y - 3), (163, y), (160, y + 3), (157, y)])


def _draw_border(page: pygame.Surface, color: config.Color) -> None:
    """Двойная рамка книжной страницы с уголками."""
    pygame.draw.rect(page, color, page.get_rect().inflate(-6, -6), 1)
    pygame.draw.rect(page, color, page.get_rect().inflate(-10, -10), 1)
    for x, y in ((5, 5), (WIDTH - 6, 5), (5, HEIGHT - 6), (WIDTH - 6, HEIGHT - 6)):
        pygame.draw.circle(page, color, (x, y), 2)
