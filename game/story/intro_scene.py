"""Сцена вступления: классическая «Алиса в стране чудес», которая ломается и становится «…Чучмека?!».

Сценарий (реплики, паузы, таблица превращения заголовка) — в game/story/intro_dialogue.py;
здесь только показ. Всё неблокирующее: шаги вступления переключаются по накопленному
времени dt и по завершению диалогов, поэтому результат не зависит от частоты кадров.
Сбой сказки — чисто визуальный: рывки, пропущенные кадры, рваные строки и шуточное
сообщение, нарисованное как страница книги. Ни исключений, ни пауз, ни блокировок.

После разговора с Кроликом Алисой управляет игрок (шаг Explore): она ходит влево и вправо
как Character — тем же вводом и анимациями, что и на площади. Ход эпизода — стадии сбоя,
появление норы, вход в неё — ведёт модель game/story/entrance.py, а сцена рисует её эффекты:
всё, что лежит на земле, — на холсте под персонажами, искры — поверх них (logical_target),
а сдвиги и полосы — только у страницы, не у персонажей.

Оформление временное: страница и эффекты нарисованы программно, настоящие локации
появятся отдельно.

Со слоем высокого разрешения (game/graphics/hires.py) персонажи рисуются из исходных кадров
64×64, а заголовок, реплики, сообщение об ошибке и табличка финала — шрифтом размера окна.
При сбое «подвисший» кадр записывается вместе с командами слоя и рвётся полосами уже
в разрешении окна (HiResLayer.torn): персонажи и заголовок рвутся вместе со страницей.
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
from game.graphics.animation import Animation, AnimationPlayer, AnimationSet, Direction
from game.graphics.fonts import TextFonts, TextStyle, load_font, render_text
from game.graphics.hires import HiResLayer, logical_target
from game.graphics.placeholder import placeholder_animations
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, try_load_character_sprites
from game.story.entrance import HOLE_X, Effects, Entrance, Spark, Stage
from game.story.intro_dialogue import (
    BEATS,
    CHOICE_ID,
    ERROR_LINES,
    ERROR_TITLE,
    POSES,
    RABBIT_REMARK_BREAKING,
    RABBIT_REMARK_READY,
    SPEAKER_ACTORS,
    TITLE_CLASSIC,
    TITLE_FINAL,
    TITLE_REVEAL_START,
    Beat,
    Cue,
    Explore,
    Lines,
    TitleStep,
    all_scripts,
    title_step_at,
)
from game.world.character import Character

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 48  # кадры 64×64 уменьшаются до 48×48 ближайшим соседом

# Расстановка на сцене (x — середина под ногами).
ALICE_START_X = 120  # в начале Алиса левее середины: справа — место, которое ей предстоит найти
RABBIT_X = 64
ALICE_X = 160  # после перезапуска сказки Алиса стоит посреди страницы
BURROW_X = HOLE_X  # нора у правого края — там, где её найдёт Алиса
ALICE_BURROW_X = 240  # где Алиса приседает на краю норы
ALICE_LEAP_X = 256  # куда она прыгает: уже над норой
ALICE_LEAP = 13  # на какой высоте прыжок «зависает», когда сказка сбоит
CHUCHMEK_X = 232  # где Чучмек стоит после выхода из норы
WALK_SPEED = 56  # скорость Алисы под управлением игрока, логических пикселей в секунду
RECOIL = 12  # на сколько Алиса отшатывается, когда мир начинает ломаться
RECOIL_SECONDS = 0.3
REMARK_SECONDS = {Stage.HOLE_OPENING: 1.0, Stage.HOLE_READY: 2.4}  # сколько видна реплика Кролика
CAP_HEIGHT = 17  # сколько пикселей шляпки видно, когда Чучмек только выглядывает
JUMP_HEIGHT = 22  # «слишком высокий» прыжок Чучмека: выше он зашёл бы на заголовок
ACTOR_LAYOUT = {
    "white_rabbit": (RABBIT_X, "idle_front"),
    "alice": (ALICE_START_X, "idle_down"),
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

# Текст в разрешении окна (слой высокого разрешения); размеры — в логических пикселях.
TITLE_STYLE = TextStyle(15, TITLE_COLOR, bold=True, shadow=TITLE_SHADOW_COLOR)
TITLE_FINAL_STYLE = TextStyle(15, TITLE_FINAL_COLOR, bold=True, shadow=TITLE_FINAL_SHADOW_COLOR)
ERROR_TITLE_STYLE = TextStyle(9, CREAM_COLOR, bold=True, background=PLUM_COLOR)  # на полосе заголовка
ERROR_LINE_STYLE = TextStyle(8, INK_COLOR)
ERROR_LINE_STEP = 13  # строки сообщения об ошибке — через столько пикселей
FINALE_STYLE = TextStyle(9, INK_COLOR)
LABEL_STYLE = TextStyle(8, INK_COLOR)  # подсказка управления и реплики Кролика над головой

# Свободная ходьба и появление норы.
WALK_HINT = "Стрелки или A/D — идти"
APPROACH_HINT = "Нора открылась. Подойди поближе"
ENTER_HINT = "Нора открылась. E — заглянуть внутрь"
HINT_CENTER = (WIDTH // 2, HEIGHT - 17)
SPARK_COLORS = (GOLD_COLOR, CREAM_COLOR, (255, 196, 222), (196, 240, 226))
MAGIC_COLOR = (255, 226, 150)  # магический круг и волны
ROOT_COLOR = (112, 78, 50)
RIM_LIGHT_COLOR = (186, 146, 98)
# Мелочи страницы, которые при первых признаках сбоя на миг сдвигаются: дерево, солнце, облако, цветы.
SHIFT_AREAS = (
    pygame.Rect(290, 70, 20, 30),
    pygame.Rect(254, 30, 44, 44),
    pygame.Rect(196, 46, 40, 18),
    pygame.Rect(234, 138, 14, 10),
    pygame.Rect(264, 154, 14, 10),
)


def _ease(t: float) -> float:
    """Плавный разгон и торможение: 0 → 1."""
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


class StageActor:
    """Персонаж на сцене вступления: поза или анимация из манифеста, позиция и положение тела.

    Если спрайтов нет или нужного кадра нет в манифесте, показывается ближайшая замена,
    а в крайнем случае — временный манекен: вступление не падает из-за ресурса.
    Кадры только масштабируются (ближайший сосед) и, для комических эффектов, наклоняются
    или приседают; отражение по горизонтали не используется.

    Пока к актёру прикреплён body (Character под управлением игрока), кадр — текущий кадр
    его анимации ходьбы или ожидания, а место по горизонтали сцена берёт у него.
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
        self.body: Character | None = None
        self._scaled: dict[int, pygame.Surface] = {}

    def attach(self, body: Character) -> None:
        """Отдаёт персонажа игроку: дальше кадр и место — у body."""
        self.body = body
        self.player = None
        self.x = body.x

    def detach(self, pose: str) -> None:
        """Забирает персонажа у игрока: он остаётся там, где стоял, в позе pose."""
        if self.body is not None:
            self.x = self.body.x
        self.body = None
        self.set_pose(pose)

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
        if self.player is not None and self.body is None:
            self.player.update(dt)  # анимацию body двигает сам Character

    def source_image(self) -> pygame.Surface:
        """Текущий кадр без масштабирования: 64×64 из манифеста или временный манекен."""
        if self.body is not None:
            return self.body.player.source
        return self.player.frame if self.player is not None else self._pose_image()

    def image(self) -> pygame.Surface:
        if self.body is not None:
            return self.body.player.frame  # набор анимаций body уже сделан под размер вступления
        source = self.source_image()
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

    def draw(
        self, surface: pygame.Surface, ground: int, clip_bottom: int | None = None, hires: HiResLayer | None = None
    ) -> None:
        """Рисует персонажа; clip_bottom — линия, ниже которой его не видно (вход в нору).

        Со слоем hires — исходный кадр на том же месте холста и того же размера (с приседанием,
        наклоном и прозрачностью), но в разрешении окна.
        """
        if not self.visible or self.alpha <= 0:
            return
        if hires is not None:
            width, height = self.image().get_size()
            rect = pygame.Rect(0, 0, width, max(1, round(height * self.squash)) if self.squash != 1.0 else height)
            rect.midbottom = (round(self.x + self.dx), ground - round(self.lift))
            clip = pygame.Rect(0, 0, WIDTH, clip_bottom) if clip_bottom is not None else None
            hires.sprite(self.source_image(), rect, alpha=self.alpha, angle=self.tilt, clip=clip)
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


def _walker_animations(sprites: CharacterSprites | None) -> AnimationSet:
    """Анимации Алисы для ходьбы во вступлении: кадры 48×48 из манифеста (исходники 64×64 остаются
    для слоя высокого разрешения), а без спрайтов — тот же манекен, что и в остальном вступлении."""
    if sprites is not None:
        return sprites.animation_set(SPRITE_SIZE)
    return AnimationSet(Animation([_fallback_frame()], 1))


class IntroScene(Scene):
    """Вступление. Когда оно сыграно, вызывается on_complete, а затем:
    если задана зарегистрированная сцена next_scene (будущая центральная локация) —
    переход на неё, иначе возврат к предыдущей сцене. Backspace прерывает вступление.

    На шаге Explore Алисой управляет игрок: walker — её Character (←/→, A/D), entrance — модель
    эпизода (стадии сбоя и появления норы). E или Enter у готовой норы продолжают вступление."""

    supports_hires = True

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
        # Персонажи стоят выше самого высокого окна диалога (при любом способе вывода текста):
        # текст их не закрывает.
        nodes = [node for script in all_scripts() for node in script.nodes.values()]
        self.ground = min(self._box_top(node, hires) for node in nodes for hires in (False, True)) - 3

        # Алиса под управлением игрока: тот же Character, что ходит по площади, но с кадрами вступления.
        # Ходит только по линии земли: вертикальное движение сюда не передаётся, collider держит её
        # между рамкой страницы и краем норы.
        alice = self.actors["alice"]
        self.walker = Character(
            "Алиса", _walker_animations(alice.sprites), position=(alice.x, 0), speed=WALK_SPEED,
            direction=Direction.LEFT,
        )
        self.walker.collider = lambda x, y, dx, dy: (Entrance.clamp(x + dx), y)
        self.entrance: Entrance | None = None  # появляется на шаге Explore и остаётся до конца
        self._stages_seen = 0  # сколько стадий эпизода сцена уже встретила
        self._lock_x = 0.0  # где Алиса стояла, когда сказка начала ломаться
        self._prepare_from = self._jump_from = 0.0  # откуда она шагает к краю норы и откуда прыгает

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
        self.burrow_rim = 0.0  # окантовка норы: земля, корни, трава
        self.chuchmek_clipped = False  # Чучмек ещё внутри норы
        self.watch_reversed = False  # Кролик «незаметно» крутит часы наоборот
        self._lag_slot = -1

        self._title_font = load_font(16)
        self._font = load_font(9)
        self._font10 = load_font(10)
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self._fonts = TextFonts()
        self.finale_metrics = self._fonts.metrics(FINALE_STYLE)
        self._pages = {"fairy": _render_fairy_page(), "absurd": _render_absurd_page()}
        self._buffer = pygame.Surface(config.LOGICAL_SIZE)
        self._lag_buffer = pygame.Surface(config.LOGICAL_SIZE)
        # «Подвисший» кадр сбоя для слоя высокого разрешения: страница и команды персонажей и заголовка.
        self._lag_page = pygame.Surface(config.LOGICAL_SIZE)
        self._lag_commands: tuple = ()
        self._lag_hires_slot = -1
        self._flash_surface = pygame.Surface(config.LOGICAL_SIZE)
        self._flash_surface.fill(FLASH_COLOR)
        self._dim_surface = pygame.Surface(config.LOGICAL_SIZE)
        self._dim_surface.fill(DIM_COLOR)
        self._dim_surface.set_alpha(120)
        # Эффекты у места норы: круг, волны, свечение — на прозрачной поверхности этой области.
        self.magic_area = pygame.Rect(BURROW_X - 64, self.ground - 26, 128, 44)
        spark_area = pygame.Rect(BURROW_X - 64, self.ground - 66, 128, 86)
        self.spark_area = spark_area.clip(pygame.Rect((0, 0), config.LOGICAL_SIZE))
        self._magic = pygame.Surface(self.magic_area.size, pygame.SRCALPHA)
        self._ground_band = pygame.Surface((WIDTH, 22))
        self._ground_band.fill(FLASH_COLOR)
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

    @property
    def exploring(self) -> bool:
        """Идёт шаг Explore: Алиса ищет место норы или стоит у готовой норы."""
        return isinstance(self.beat, Explore)

    @property
    def stage(self) -> Stage | None:
        """Стадия эпизода с норой (None, пока до него не дошло)."""
        return self.entrance.stage if self.entrance is not None else None

    def entrance_effects(self) -> Effects | None:
        """Эффекты эпизода с норой, пока он идёт; иначе None."""
        if not self.exploring:
            return None
        return self.entrance.effects(self.walker.x if self.entrance.can_walk else self._alice.x)

    @property
    def hint_text(self) -> str:
        """Подсказка внизу страницы: как ходить, а у готовой норы — как в неё заглянуть."""
        if not self.exploring:
            return ""
        if self.entrance.stage is Stage.FREE_WALK:
            return WALK_HINT
        if self.entrance.stage is Stage.HOLE_READY:
            return ENTER_HINT if self.entrance.can_enter(self.walker.x) else APPROACH_HINT
        return ""

    @property
    def rabbit_remark(self) -> str:
        """Короткая реплика Кролика над головой, пока сказка ломается и когда нора готова."""
        if not self.exploring:
            return ""
        stage, t = self.entrance.stage, self.entrance.stage_time
        if stage is Stage.WORLD_BREAKING or (stage is Stage.HOLE_OPENING and t < REMARK_SECONDS[stage]):
            return RABBIT_REMARK_BREAKING
        if stage is Stage.HOLE_READY and t < REMARK_SECONDS[stage]:
            return RABBIT_REMARK_READY
        return ""

    def _box_top(self, node, hires: bool = False) -> int:
        layout = self.box.layout(node, hires)
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
        if self.exploring:
            self._explore_event(event)
            return
        if self.dialogue is None:
            return  # во время пауз и эффектов нажатия ничего не пропускают
        actions = actions_for(event) if event.type == pygame.KEYDOWN else frozenset()
        if Action.INTERACT in actions and Action.CONFIRM not in actions:
            self.dialogue.confirm()  # как во всей игре: E продолжает реплику и выбирает ответ
        else:
            self.dialogue.handle_event(event)
        self._sync_dialogue()

    def _explore_event(self, event: pygame.event.Event) -> None:
        """Свободная ходьба: ←/→ (A/D) ведут Алису, E или Enter у готовой норы — заглянуть внутрь.

        Пока идёт постановка (сбой, появление норы), нажатия ничего не меняют и не копятся.
        ↑/↓ (W/S) сюда не передаются: Алиса ходит только по линии земли."""
        if event.type == pygame.WINDOWFOCUSLOST:
            self.walker.handle_event(event)  # отпущенные вне окна клавиши не залипают
            return
        if not self.entrance.can_walk:
            return
        actions = actions_for(event)
        if event.type == pygame.KEYUP or actions & {Action.MOVE_LEFT, Action.MOVE_RIGHT}:
            self.walker.handle_event(event)
        if event.type == pygame.KEYDOWN and Action.INTERACT in actions and self.entrance.enter(self.walker.x):
            self._begin_entering()

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
            if isinstance(beat, Explore):  # длится, пока игрок не заглянет в нору
                step = min(remaining, MAX_SUBSTEP)
                remaining -= step
                self.beat_time += step
                self._explore(step)
                continue
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
        elif isinstance(beat, Explore):
            self._begin_explore()

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

    # --- Свободная ходьба: Алиса сама находит место норы ---

    def _begin_explore(self) -> None:
        """Разговор с Кроликом закончен: Алиса у игрока. Смотрит туда же, куда смотрела."""
        self.entrance = Entrance()
        self._stages_seen = 0
        alice = self._alice
        self.walker.set_position(alice.x, 0)
        self.walker.release_controls()
        self.walker.face(Direction.LEFT if alice.pose == "idle_left" else Direction.RIGHT)
        alice.attach(self.walker)
        self._log_new_stages()

    def _explore(self, step: float) -> None:
        """Один шаг эпизода: Алиса идёт (если управление у игрока), модель решает, что дальше."""
        entrance = self.entrance
        if entrance.can_walk:
            self.walker.update(step)
            self._alice.x = self.walker.x
        entrance.update(step, self._alice.x)
        self._log_new_stages()
        stage, t = entrance.stage, entrance.stage_time
        rabbit = self._rabbit
        if stage is Stage.FREE_WALK:
            # Кролик показывает, куда идти; а когда Алиса уходит в другую сторону — нервно смотрит на часы.
            walking_away = self.walker.is_moving and self.walker.direction is Direction.LEFT
            pose = "annoyed_watch" if walking_away else "hurries_pointing"
            if rabbit.pose != pose:
                rabbit.set_pose(pose)
        elif stage is Stage.WORLD_BREAKING:
            # Алиса отшатывается от места, где ломается земля.
            self._alice.x = Entrance.clamp(self._lock_x - RECOIL * _ease(t / RECOIL_SECONDS))
        fx = entrance.effects(self.walker.x if entrance.can_walk else self._alice.x)
        self.burrow_open, self.burrow_rim, self.flash = fx.depth, fx.rim, fx.flash

    def _log_new_stages(self) -> None:
        """Записывает в журнал каждую новую стадию эпизода и ставит персонажей для неё."""
        log = self.entrance.stage_log
        while self._stages_seen < len(log):
            stage = log[self._stages_seen]
            self._stages_seen += 1
            self.events.append(("stage", stage.value))
            self._call_cue("begin", stage.value)

    def _begin_glitch_warning(self) -> None:
        """Сказка начинает ломаться: управление у постановки, Алиса останавливается и смотрит."""
        self.walker.release_controls()
        alice = self._alice
        alice.detach("idle_right")
        self._lock_x = alice.x
        self._rabbit.set_pose("confused_watch")

    def _begin_world_breaking(self) -> None:
        alice = self._alice
        if not alice.play("react_down"):
            alice.set_pose("react_down_2")
        self._rabbit.set_pose("panics_watch")

    def _begin_hole_opening(self) -> None:
        self._alice.set_pose("idle_right")  # смотрит, как появляется нора
        self._rabbit.set_pose("confused_watch")

    def _begin_hole_ready(self) -> None:
        """Нора готова: управление снова у игрока — с того места, где Алиса стоит."""
        alice = self._alice
        self.walker.set_position(alice.x, 0)
        self.walker.release_controls()
        self.walker.face(Direction.RIGHT)
        alice.attach(self.walker)
        self._rabbit.set_pose("confident_point")

    def _begin_entering(self) -> None:
        """E у готовой норы: дальше Алису ведёт сценарий — край норы, «Ну, поехали», прыжок."""
        self.walker.release_controls()
        self._alice.detach("idle_right")
        self._log_new_stages()
        self.flash = 0.0
        self._next_beat()

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
        # Кролик показывает, где по расписанию должна быть нора. Её там пока нет.
        self._rabbit.set_pose("hurries_pointing")

    def _begin_alice_prepares(self) -> None:
        self._alice.set_pose("idle_right")
        self._prepare_from = self._alice.x

    def _do_alice_prepares(self, p: float) -> None:
        alice = self._alice
        alice.x = self._prepare_from + (ALICE_BURROW_X - self._prepare_from) * _ease(p / 0.3)  # шаг к самому краю
        alice.squash = 1 - 0.12 * _ease((p - 0.2) / 0.5)  # присела, чтобы прыгнуть

    def _end_alice_prepares(self) -> None:
        self._alice.x = ALICE_BURROW_X
        self._alice.squash = 0.88

    def _begin_alice_jumps(self) -> None:
        alice = self._alice
        alice.squash = 1.0
        alice.set_pose("walk_right_3")  # шаг-прыжок: ноги врозь
        self._jump_from = alice.x

    def _do_alice_jumps(self, p: float) -> None:
        alice = self._alice
        alice.x = self._jump_from + (ALICE_LEAP_X - self._jump_from) * _ease(p)
        alice.lift = ALICE_LEAP * math.sin(p * math.pi / 2)  # к концу — в высшей точке, над норой

    def _end_alice_jumps(self) -> None:
        self._alice.x = ALICE_LEAP_X

    # B. Сбой сказки

    def _begin_glitch(self) -> None:
        self._lag_slot = self._lag_hires_slot = -1
        self.hidden = set()
        self._alice.squash = 1.0
        self._alice.lift = ALICE_LEAP  # сказка зависла прямо посреди прыжка
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
        # Алиса «прыгает» неправильными фазами движения, рывками — так и не долетев до норы.
        alice.set_pose(GLITCH_ALICE_POSES[slot % len(GLITCH_ALICE_POSES)])
        alice.lift = ALICE_LEAP + ((slot * 3) % 5 - 2) * 2
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

    def draw(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рисует вступление на холсте; со слоем hires персонажи и текст уходят в него
        (см. описание модуля), а порядок слоёв остаётся тем же."""
        name = self.cue_name
        if name == "glitch":
            self._draw_glitch(surface, hires)
        elif name == "error_message":
            self._draw_error(surface, hires)
        else:
            self._compose(surface, hires)
            if name == "finale":
                self._draw_finale_plaque(surface, hires)
            if self.exploring:
                self._draw_explore_labels(surface, hires)
        if self.flash > 0:
            alpha = round(255 * min(1.0, self.flash))
            if hires is not None:
                hires.fill(FLASH_COLOR, alpha=alpha)  # вспышка закрывает и персонажей, и заголовок
            else:
                self._flash_surface.set_alpha(alpha)
                surface.blit(self._flash_surface, (0, 0))
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue, hires)

    def _compose(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Страница, нора, персонажи и заголовок. Персонажи не заходят на заголовок и окно диалога.

        Пока Алиса ищет нору, сюда же добавляются эффекты эпизода: сдвиги и полосы страницы
        и всё, что на земле, — под персонажами, искры — поверх них."""
        fx = self.entrance_effects()
        self._draw_page(surface, fx)
        if self.page_blend > 0:
            absurd = self._pages["absurd"]
            absurd.set_alpha(round(255 * self.page_blend))
            surface.blit(absurd, (0, 0))
        if fx is not None:
            self._draw_magic_ground(surface, fx)
        show_burrow = "burrow" not in self.hidden and self.burrow_open > 0
        if show_burrow:
            _draw_burrow_back(surface, self.burrow_open, self.ground, self.burrow_rim)
        for char_id in DRAW_ORDER:
            if char_id in self.hidden:
                continue
            clip = self.ground + 1 if char_id == "chuchmek" and self.chuchmek_clipped else None
            self.actors[char_id].draw(surface, self.ground, clip, hires)
        # Передний край норы, искры и часы Кролика — поверх персонажей.
        if show_burrow:
            area = pygame.Rect(0, 0, 52, 26)
            area.center = (BURROW_X, self.ground)
            with logical_target(surface, hires, area) as front:
                _draw_burrow_front(front, self.burrow_open, self.ground)
        if fx is not None and fx.sparks:
            with logical_target(surface, hires, self.spark_area) as front:
                self._draw_sparks(front, fx.sparks)
        if self.watch_reversed and "white_rabbit" not in self.hidden:
            cx, cy = self._watch_center()
            with logical_target(surface, hires, pygame.Rect(cx - 6, cy - 6, 13, 13)) as front:
                self._draw_reversed_watch(front)
        self._draw_title(surface, hires)

    def _draw_page(self, surface: pygame.Surface, fx: Effects | None) -> None:
        """Сказочная страница. Когда сказка ломается, съезжают полосы и сдвигаются мелочи —
        только у страницы: персонажи рисуются поверх, целыми и без двойных силуэтов."""
        page = self._pages["fairy"]
        if fx is not None and fx.tear:
            self._tear(surface, page, fx.slot, fx.tear)
        else:
            surface.blit(page, (0, 0))
        if fx is not None and fx.shift:
            for index, area in enumerate(SHIFT_AREAS):
                offset = fx.shift if index % 2 == 0 else -fx.shift
                surface.blit(page, area.move(offset, (index % 3) - 1), area)

    def _draw_magic_ground(self, surface: pygame.Surface, fx: Effects) -> None:
        """Всё, что происходит на земле у места норы: намёки, мерцание, свечение, магический круг,
        волны и сворачивающаяся внутрь земля. Рисуется на холсте под персонажами."""
        cx, cy = BURROW_X, self.ground
        if fx.hint:
            # Трава на месте будущей норы шевелится, хотя ветра нет.
            for k, (dx, dy, height) in enumerate(((-7, 2, 4), (2, 1, 5), (9, 3, 3))):
                sway = round(math.sin(self.time * 5 + k * 2.1) * (1 + fx.hint))
                x, y = cx + dx, cy + dy
                pygame.draw.line(surface, GRASS_COLOR, (x, y), (x + sway, y - height))
        if fx.flicker >= 0.7:  # первое мерцание задевает всю землю
            self._ground_band.set_alpha(round(70 * fx.flicker))
            surface.blit(self._ground_band, (0, cy - 10))
        if fx.scanlines:
            for k in range(fx.scanlines):
                y = 40 + (fx.slot * 37 + k * 53) % (cy + 30 - 40)
                pygame.draw.line(surface, GLITCH_LINE_COLORS[k % len(GLITCH_LINE_COLORS)], (8, y), (WIDTH - 9, y))
        magic = self._magic
        magic.fill((0, 0, 0, 0))
        mx, my = cx - self.magic_area.x, cy - self.magic_area.y
        if fx.glow:
            _ellipse(magic, (*CREAM_COLOR, round(120 * fx.glow)), (mx, my), 32, 10)
        if fx.flicker:
            _ellipse(magic, (*FLASH_COLOR, round(190 * fx.flicker)), (mx, my), 36, 11)
        if fx.fold:
            # Земля сворачивается внутрь круга: середина темнеет, клочки травы и дорожки закручиваются к центру.
            _ellipse(magic, (*EARTH_COLOR, round(220 * fx.fold)), (mx, my), 6 + 18 * fx.fold, 2 + 6 * fx.fold)
            colors = (HILL_COLORS[1], PATH_COLOR, GRASS_COLOR, HILL_COLORS[0])
            for k in range(16):
                angle = k * 2.4 + fx.fold * 3.2
                radius = (14 + (k * 7) % 17) * (1 - 0.85 * fx.fold)
                size = 2 if fx.fold < 0.6 else 1
                x, y = mx + math.cos(angle) * radius, my + math.sin(angle) * radius / 3
                magic.fill((*colors[k % len(colors)], 255), (round(x), round(y), size, size))
        if fx.ring:
            # Магический круг: пунктир из золотых и светлых точек вращается и чуть пульсирует.
            rx = 27 * (1 + 0.05 * math.sin(self.time * 14))
            alpha = round(255 * fx.ring)
            for k in range(28):
                if k % 4 == 3:
                    continue
                angle = fx.spin + k * math.tau / 28
                x, y = mx + math.cos(angle) * rx, my + math.sin(angle) * rx / 3
                color = MAGIC_COLOR if k % 2 else CREAM_COLOR
                magic.fill((*color, alpha), (round(x), round(y), 2, 1))
            for k in range(4):  # «руны» — звёздочки по сторонам круга
                angle = -fx.spin * 0.5 + k * math.pi / 2
                _draw_star(magic, round(mx + math.cos(angle) * rx * 1.18), round(my + math.sin(angle) * rx * 0.4),
                           (*GOLD_COLOR, alpha))
        for wave in fx.waves:
            rx = 12 + 46 * wave
            _ellipse(magic, (*MAGIC_COLOR, round(210 * (1 - wave))), (mx, my), rx, rx / 3, 1)
        surface.blit(magic, self.magic_area)

    def _draw_sparks(self, surface: pygame.Surface, sparks: tuple[Spark, ...]) -> None:
        """Искры поверх персонажей: точка, плюсик или звёздочка. Бледные — мельче."""
        old_clip = surface.get_clip()
        surface.set_clip(old_clip.clip(self.spark_area))
        for spark in sparks:
            if spark.alpha < 0.25:
                continue
            size = spark.size if spark.alpha >= 0.5 else max(1, spark.size - 1)
            x, y = round(BURROW_X + spark.dx), round(self.ground + spark.dy)
            color = SPARK_COLORS[spark.color % len(SPARK_COLORS)]
            if size == 1:
                surface.fill(color, (x, y, 1, 1))
            elif size == 2:
                surface.fill(color, (x - 1, y, 3, 1))
                surface.fill(color, (x, y - 1, 1, 3))
            else:
                _draw_star(surface, x, y, color)
        surface.set_clip(old_clip)

    def label_rect(self, text: str, center: tuple[int, int], hires: bool = False) -> pygame.Rect:
        """Табличка с надписью (подсказка, реплика Кролика) — по размеру надписи выбранным шрифтом."""
        if hires:
            width, height = self._fonts.metrics(LABEL_STYLE).size(text)
            rect = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        else:
            rect = self._text(self._font, text, INK_COLOR).get_rect()
        rect.center = center
        return rect.inflate(10, 6)

    def remark_rect(self, text: str, hires: bool = False) -> pygame.Rect:
        """Где реплика Кролика: над его головой, но не за краем страницы и не на заголовке."""
        rect = self.label_rect(text, (round(self._rabbit.x), self.ground - 58), hires)
        rect.clamp_ip(pygame.Rect(10, 0, WIDTH - 20, HEIGHT))
        return rect

    def _draw_explore_labels(self, canvas: pygame.Surface, hires: HiResLayer | None) -> None:
        """Реплика Кролика над головой и подсказка внизу страницы."""
        remark = self.rabbit_remark
        if remark and "white_rabbit" not in self.hidden:
            rect = self.remark_rect(remark, hires is not None)
            tip = (min(rect.right - 6, max(rect.left + 6, round(self._rabbit.x) + 6)), rect.bottom + 3)
            with logical_target(canvas, hires, rect.inflate(0, 8)) as surface:
                tail = [(tip[0] - 4, rect.bottom - 1), (tip[0] + 2, rect.bottom - 1), tip]
                pygame.draw.polygon(surface, PAGE_EDGE_COLOR, tail)
                pygame.draw.rect(surface, PAGE_COLOR, rect)
                pygame.draw.rect(surface, PAGE_EDGE_COLOR, rect, 1)
            self._label_text(canvas, hires, remark, rect)
        hint = self.hint_text
        if hint:
            rect = self.label_rect(hint, HINT_CENTER, hires is not None)
            with logical_target(canvas, hires, rect) as surface:
                pygame.draw.rect(surface, PAGE_COLOR, rect)
                pygame.draw.rect(surface, PAGE_EDGE_COLOR, rect, 1)
            self._label_text(canvas, hires, hint, rect)

    def _label_text(self, canvas: pygame.Surface, hires: HiResLayer | None, text: str, rect: pygame.Rect) -> None:
        if hires is not None:
            hires.text(text, LABEL_STYLE, rect.center, anchor="center")
            return
        image = self._text(self._font, text, INK_COLOR)
        canvas.blit(image, image.get_rect(center=rect.center))

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

    def _draw_title(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        if not self.title or not self.title_visible or "title" in self.hidden:
            return
        slot = int(self.time * 24)
        dx = ((slot * 5) % 3 - 1) * self.title_shake
        if hires is not None:
            style = TITLE_FINAL_STYLE if self.title == TITLE_FINAL else TITLE_STYLE
            hires.text(self.title, style, (WIDTH // 2 + dx, 9 - self.title_dy), anchor="midtop", alpha=self.title_alpha)
            return
        image = self._title_image(self.title)
        if self.title_alpha < 255:
            image = image.copy()
            image.set_alpha(self.title_alpha)
        surface.blit(image, image.get_rect(midtop=(WIDTH // 2 + dx, 9 - self.title_dy)))

    def _watch_center(self) -> tuple[int, int]:
        return round(self._rabbit.x + 22), self.ground - 46

    def _draw_reversed_watch(self, surface: pygame.Surface) -> None:
        """Крошечные часы над Кроликом: стрелки идут против часовой. Заметит только внимательный."""
        cx, cy = self._watch_center()
        pygame.draw.circle(surface, CREAM_COLOR, (cx, cy), 5)
        pygame.draw.circle(surface, INK_COLOR, (cx, cy), 5, 1)
        angle = -self.time * 3.0
        for length, speed in ((3.6, 1.0), (2.2, 0.25)):
            a = angle * speed
            pygame.draw.line(surface, INK_COLOR, (cx, cy), (cx + math.sin(a) * length, cy - math.cos(a) * length))

    def finale_plaque_rect(self, hires: bool = False) -> pygame.Rect:
        """Табличка «…и сказка пошла совсем не по плану» — по размеру надписи выбранным шрифтом."""
        if hires:
            width, height = self.finale_metrics.size(FINALE_TEXT)
            rect = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        else:
            rect = self._text(self._font10, FINALE_TEXT, INK_COLOR).get_rect()
        rect.center = (WIDTH // 2, 44)
        return rect.inflate(10, 6)

    def _draw_finale_plaque(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        beat = self.beat
        alpha = round(255 * _ease(self.beat_time / (beat.seconds * 0.4)))
        plaque = self.finale_plaque_rect(hires is not None)
        with logical_target(canvas, hires, plaque) as surface:
            pygame.draw.rect(surface, PAGE_COLOR, plaque)
            pygame.draw.rect(surface, PAGE_EDGE_COLOR, plaque, 1)
        if hires is not None:
            hires.text(FINALE_TEXT, FINALE_STYLE, plaque.center, anchor="center", alpha=alpha)
            return
        image = self._text(self._font10, FINALE_TEXT, INK_COLOR).copy()
        image.set_alpha(alpha)
        canvas.blit(image, image.get_rect(center=plaque.center))

    # --- Сбой ---

    def _draw_glitch(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Содержимое подвисает (пропущенные кадры), а изображение рвётся горизонтальными полосами."""
        lag_slot = int(self.beat_time / GLITCH_LAG)
        if lag_slot != self._lag_slot:
            self._compose(self._lag_buffer)
            self._lag_slot = lag_slot
        p = self.beat_time / self.beats[self.beat_index].seconds
        amplitude = 2 + int(8 * p)
        self._tear(surface, self._lag_buffer, self.glitch_slot, amplitude)
        if hires is not None:
            # Тот же подвисший кадр, но персонажи и заголовок — в разрешении окна; рвётся так же.
            if lag_slot != self._lag_hires_slot:
                recorder = HiResLayer(self._fonts)
                self._compose(self._lag_page, recorder)
                self._lag_commands = tuple(recorder.commands)
                self._lag_hires_slot = lag_slot
            hires.torn(self._lag_page, self._lag_commands, _tear_bands(self.glitch_slot, amplitude))
        for k, color in enumerate(GLITCH_LINE_COLORS):
            y = (self.glitch_slot * 37 + k * 61) % HEIGHT
            with logical_target(surface, hires, pygame.Rect(0, y, WIDTH, 1)) as front:
                pygame.draw.line(front, color, (0, y), (WIDTH, y))

    def _tear(self, surface: pygame.Surface, source: pygame.Surface, slot: int, amplitude: int) -> None:
        """Рисует source, сдвигая отдельные горизонтальные полосы (с заворотом за край)."""
        surface.blit(source, (0, 0))
        for y, height, offset in _tear_bands(slot, amplitude):
            area = pygame.Rect(0, y, WIDTH, height)
            surface.blit(source, (offset, y), area)
            surface.blit(source, (offset - WIDTH if offset > 0 else offset + WIDTH, y), area)

    def _draw_error(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Страница притихла, а поверх неё — сообщение в виде страницы книги, которое потом разваливается.

        Со слоем hires надписи сообщения рисуются шрифтом окна: каждая половина разломанной
        страницы уносит свою часть текста (по своей области отсечения)."""
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
        box = self._render_error_box(t, with_text=hires is None)
        if t < ERROR_BREAK_AT:
            surface.blit(box, (left, top))
            self._error_texts(hires, t, (left, top), pygame.Rect(left, top, ERROR_W, ERROR_H))
            return
        e = _ease((t - ERROR_BREAK_AT) / 0.8)
        half = ERROR_H // 2
        flicker = t > ERROR_BREAK_AT + 0.6 and int(t * 20) % 3 == 0
        if t >= self.beats[self.beat_index].seconds - 0.2 or flicker:
            return  # обломки мигают и пропадают
        upper_pos = (left - round(e * 24), top - round(e * 8))
        lower_pos = (left + round(e * 24), top + half + round(e * 14))
        surface.blit(box.subsurface((0, 0, ERROR_W, half)), upper_pos)
        surface.blit(box.subsurface((0, half, ERROR_W, ERROR_H - half)), lower_pos)
        self._error_texts(hires, t, upper_pos, pygame.Rect(upper_pos, (ERROR_W, half)))
        lower_origin = (lower_pos[0], lower_pos[1] - half)  # где был бы верх сообщения для нижней половины
        self._error_texts(hires, t, lower_origin, pygame.Rect(lower_pos, (ERROR_W, ERROR_H - half)))
        # Рваный край на месте разлома — поверх надписей.
        y = top + half
        points = [(left + x, y + (3 if (x // 8) % 2 else -3) * (1 - e)) for x in range(0, ERROR_W + 1, 8)]
        with logical_target(surface, hires, pygame.Rect(left - 1, y - 4, ERROR_W + 3, 9)) as front:
            pygame.draw.lines(front, PLUM_COLOR, False, points, 1)

    def _error_texts(self, hires: HiResLayer | None, t: float, origin: tuple[int, int], clip: pygame.Rect) -> None:
        """Надписи сообщения об ошибке в разрешении окна: origin — где левый верхний угол сообщения,
        clip — видимая часть (целое сообщение или одна из половин)."""
        if hires is None:
            return
        x, y = origin
        band = self._error_band()
        hires.text(ERROR_TITLE, ERROR_TITLE_STYLE, (x + band.centerx, y + band.centery), anchor="center", clip=clip)
        for row, (line, start) in enumerate(zip(ERROR_LINES, ERROR_LINE_TIMES)):
            if t >= start:
                middle = y + band.bottom + 8 + row * ERROR_LINE_STEP + ERROR_LINE_STEP / 2
                hires.text(line, ERROR_LINE_STYLE, (x + 12, middle), anchor="midleft", clip=clip)

    @staticmethod
    def _error_band() -> pygame.Rect:
        """Полоса заголовка сообщения об ошибке (в координатах сообщения)."""
        return pygame.Rect(4, 4, ERROR_W - 8, 17)

    @staticmethod
    def _error_top() -> int:
        return (HEIGHT - ERROR_H) // 2 - 4

    def _render_error_box(self, t: float, with_text: bool = True) -> pygame.Surface:
        """Сообщение об ошибке на логическом холсте; with_text=False — без надписей (их рисует слой окна)."""
        box = pygame.Surface((ERROR_W, ERROR_H))
        box.fill(PARCHMENT_COLOR)
        pygame.draw.rect(box, PLUM_COLOR, box.get_rect(), 2)
        pygame.draw.rect(box, GOLD_COLOR, box.get_rect().inflate(-6, -6), 1)
        band = self._error_band()
        pygame.draw.rect(box, PLUM_COLOR, band)
        if with_text:
            title = self._text(self._font10, ERROR_TITLE, CREAM_COLOR)
            box.blit(title, title.get_rect(center=band.center))
        _draw_star(box, band.left + 9, band.centery, GOLD_COLOR)
        _draw_star(box, band.right - 10, band.centery, GOLD_COLOR)
        y = band.bottom + 8
        for line, start in zip(ERROR_LINES, ERROR_LINE_TIMES):
            if t >= start and with_text:
                box.blit(self._text(self._font, line, INK_COLOR), (12, y))
            y += ERROR_LINE_STEP
        # Полоска «восстановления» из страничек: доходит до трети и застревает.
        progress = 0.35 * min(1.0, max(0.0, (t - ERROR_LINE_TIMES[1]) / 1.2))
        filled = int(progress * ERROR_SEGMENTS)
        for index in range(ERROR_SEGMENTS):
            color = GOLD_COLOR if index < filled else (232, 218, 188)
            box.fill(color, (14 + index * 12, ERROR_H - 18, 10, 6))
        return box


def _tear_bands(slot: int, amplitude: int) -> list[tuple[int, int, int]]:
    """Какие горизонтальные полосы сдвинуть при сбое: (y, высота, сдвиг) в пикселях холста."""
    bands = []
    for index, y in enumerate(range(0, HEIGHT, TEAR_BAND)):
        if (slot + index) % 3:
            continue
        offset = ((slot * 7 + index * 13) % (2 * amplitude + 1)) - amplitude
        if offset:
            bands.append((y, min(TEAR_BAND, HEIGHT - y), offset))
    return bands


def _ellipse(surface: pygame.Surface, color: tuple, center: tuple[float, float], rx: float, ry: float,
             width: int = 0) -> None:
    """Эллипс с центром center и полуосями rx, ry (на земле круги видны сбоку — сплюснутыми)."""
    rect = pygame.Rect(0, 0, max(2, round(2 * rx)), max(2, round(2 * ry)))
    rect.center = (round(center[0]), round(center[1]))
    pygame.draw.ellipse(surface, color, rect, width)


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


def _draw_burrow_back(surface: pygame.Surface, open_t: float, ground: int, rim: float = 1.0) -> None:
    """Тёмный вход в землю с тенью и пучками травы. Задняя половина: за ней появляется Чучмек.

    rim — окантовка, которая проявляется последней: светлый дальний край и корни внутри."""
    rect = _burrow_rect(open_t, ground)
    pygame.draw.ellipse(surface, HOLE_SHADOW_COLOR, rect.inflate(10, 5))
    pygame.draw.ellipse(surface, EARTH_COLOR, rect.inflate(4, 2))
    pygame.draw.ellipse(surface, HOLE_COLOR, rect)
    if rim > 0 and open_t > 0.5:
        # Дальний край норы освещён, а из него внутрь свисают корни.
        old_clip = surface.get_clip()
        surface.set_clip(old_clip.clip(pygame.Rect(0, 0, WIDTH, rect.centery)))
        pygame.draw.ellipse(surface, RIM_LIGHT_COLOR, rect.inflate(4, 2), 1)
        surface.set_clip(old_clip)
        for dx, length in ((-9, 4), (-2, 3), (6, 5)):
            x, top = rect.centerx + dx, rect.top + 1
            pygame.draw.line(surface, ROOT_COLOR, (x, top), (x + (1 if dx > 0 else -1), top + round(length * rim)))
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
