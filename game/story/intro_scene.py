"""Сцена вступления: сказочная страница, которая сгибается и превращается в абсурдное приключение.

Сценарий (реплики, паузы, ремарки) — в game/story/intro_dialogue.py; здесь только показ.
Всё неблокирующее: шаги вступления переключаются по накопленному времени dt и по
завершению диалогов, поэтому результат не зависит от частоты кадров.

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
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, ManifestError, load_character_sprites
from game.story.intro_dialogue import BEATS, CHOICE_ID, POSES, SPEAKER_ACTORS, Beat, Cue, Lines, all_scripts

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 48  # кадры 64×64 уменьшаются до 48×48 ближайшим соседом
# Где стоит каждый персонаж (x — середина под ногами) и с какой позы начинает.
ACTOR_LAYOUT = {
    "white_rabbit": (72, "idle_front"),
    "alice": (152, "idle_down"),
    "chuchmek": (240, "idle"),
}
DRAW_ORDER = ("white_rabbit", "chuchmek", "alice")
BOB_SPEED = 9.0  # покачивание говорящего, радиан в секунду

# Палитра временной сказочной страницы и её «сломанной» версии.
PAGE_COLOR = (246, 236, 208)
PAGE_EDGE_COLOR = (196, 160, 112)
INK_COLOR = (120, 84, 52)
SUN_COLOR = (250, 206, 108)
HILL_COLORS = ((178, 206, 146), (154, 188, 126))
PATH_COLOR = (226, 204, 160)
TREE_COLORS = ((106, 150, 96), (132, 98, 70))
FLAP_COLOR = (232, 220, 190)
ABSURD_COLOR = (226, 214, 238)
ABSURD_DOT_COLOR = (196, 232, 214)
ABSURD_HILL_COLORS = ((236, 168, 196), (150, 206, 204))
SPARKLE_COLOR = (255, 236, 160)
KEY_COLOR = (255, 0, 255)  # прозрачный цвет вырезанного угла страницы

HEADINGS = {"fairy": "Глава первая", "absurd": "Глава… какая-то"}
FINALE_TEXT = "…и сказка пошла совсем не по плану"


def _ease(t: float) -> float:
    """Плавный разгон и торможение: 0 → 1."""
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


class StageActor:
    """Персонаж на сцене вступления: поза или анимация из манифеста, позиция и прозрачность.

    Если спрайтов нет или нужного кадра нет в манифесте, показывается ближайшая замена,
    а в крайнем случае — временный манекен: вступление не падает из-за ресурса.
    """

    def __init__(self, char_id: str, sprites: CharacterSprites | None, home_x: int, pose: str) -> None:
        self.id = char_id
        self.sprites = sprites
        self.home_x = home_x
        self.x = float(home_x)
        self.lift = 0.0  # насколько персонаж поднят над землёй, пиксели
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

    def draw(self, surface: pygame.Surface, ground: int) -> None:
        if not self.visible or self.alpha <= 0:
            return
        image = self.image()
        rect = image.get_rect(midbottom=(round(self.x), ground - round(self.lift)))
        if self.alpha < 255:
            image = image.copy()
            image.set_alpha(self.alpha)
        surface.blit(image, rect)


_FALLBACK: pygame.Surface | None = None


def _fallback_frame() -> pygame.Surface:
    """Временный манекен (16×26), увеличенный вдвое, — если спрайтов персонажа нет."""
    global _FALLBACK
    if _FALLBACK is None:
        frame = placeholder_animations().default.frames[0]
        _FALLBACK = pygame.transform.scale(frame, (frame.get_width() * 2, frame.get_height() * 2))
    return _FALLBACK


def _load_sprites(root: Path, char_id: str) -> CharacterSprites | None:
    try:
        return load_character_sprites(root / char_id)
    except (ManifestError, FileNotFoundError, pygame.error):
        return None


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
            char_id: StageActor(char_id, _load_sprites(root, char_id), x, pose)
            for char_id, (x, pose) in ACTOR_LAYOUT.items()
        }
        self.box = DialogueBox()
        for script in all_scripts():
            self.box.check_fits(script)
        # Персонажи стоят выше самого высокого окна диалога: текст их не закрывает.
        self.ground = min(self._box_top(node) for script in all_scripts() for node in script.nodes.values()) - 3

        self.beat_index = 0
        self.beat_time = 0.0
        self.time = 0.0  # общее время сцены — для покачиваний и мерцаний
        self.dialogue: DialogueController | None = None
        self.answers: dict[str, DialogueChoice] = {}
        self.completed = False
        self.backdrop = "fairy"
        self._shown_node_id: str | None = None

        self._heading_font = load_font(10)
        self._pages = {"fairy": _render_fairy_page(), "absurd": _render_absurd_page()}
        self._headings = {
            name: render_text(self._heading_font, text, INK_COLOR) for name, text in HEADINGS.items()
        }
        self._finale = render_text(self._heading_font, FINALE_TEXT, INK_COLOR)
        self._start_beat()

    # --- Состояние ---

    @property
    def beat(self) -> Beat | None:
        return self.beats[self.beat_index] if self.beat_index < len(self.beats) else None

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

    # --- Управление ---

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and Action.CANCEL in actions_for(event):
            self.finish()  # тестовое вступление прервано, итога нет
            return
        if self.dialogue is None:
            return  # во время пауз и эффектов нажатия ничего не пропускают
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
            step = min(remaining, beat.seconds - self.beat_time)
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
            self._begin_cue(beat.name)

    def _next_beat(self) -> None:
        beat = self.beat
        if isinstance(beat, Cue):
            self._end_cue(beat.name)
        self.dialogue = None
        self.beat_index += 1
        self._start_beat()

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
            for char_id, frame_id in POSES.get(node.id, {}).items():
                self.actors[char_id].set_pose(frame_id)

    def _animate_speaker(self) -> None:
        """Говорящий покачивается, пока печатается его реплика; Алиса ещё и шевелит губами."""
        dialogue = self.dialogue
        speaker = SPEAKER_ACTORS.get(dialogue.node.speaker) if dialogue is not None and dialogue.node else None
        for char_id, actor in self.actors.items():
            if self.beat is not None and isinstance(self.beat, Cue):
                continue  # эффекты двигают персонажей сами
            talking = char_id == speaker and dialogue.is_typing
            actor.lift = abs(math.sin(self.time * BOB_SPEED)) * 1.5 if talking else 0.0
            if char_id == "alice":
                pinned = char_id in POSES.get(dialogue.node.id if dialogue and dialogue.node else "", {})
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

    # --- Постановочные события ---

    def _begin_cue(self, name: str) -> None:
        alice, rabbit, chuchmek = self.actors["alice"], self.actors["white_rabbit"], self.actors["chuchmek"]
        if name == "alice_appears":
            alice.visible, alice.alpha = True, 0
        elif name == "rabbit_runs_in":
            rabbit.visible = True
            rabbit.set_pose("run_right_2")
            rabbit.x = -SPRITE_SIZE
        elif name == "page_folds":
            rabbit.set_pose("panic_gasp")
            alice.set_pose("idle_left")
        elif name == "chuchmek_appears":
            chuchmek.visible, chuchmek.alpha = True, 0
            chuchmek.set_pose("arms_up_panic")
            alice.set_pose("idle_right")
        elif name == "alice_reacts":
            alice.set_pose("idle_down")
            alice.play("react_down")
        elif name == "finale":
            chuchmek.set_pose("smug_wink")
            alice.set_pose("idle_down")
            alice.play("happy_down")

    def _animate_cue(self, beat: Beat) -> None:
        if not isinstance(beat, Cue):
            return
        p = self.beat_time / beat.seconds
        alice, rabbit, chuchmek = self.actors["alice"], self.actors["white_rabbit"], self.actors["chuchmek"]
        if beat.name == "alice_appears":
            alice.alpha = round(255 * _ease(p))
            alice.lift = 8 * (1 - _ease(p))
        elif beat.name == "rabbit_runs_in":
            rabbit.x = -SPRITE_SIZE + (rabbit.home_x + SPRITE_SIZE) * _ease(p)
            rabbit.lift = abs(math.sin(p * math.pi * 5)) * 4 * (1 - p)  # торопливые прыжки
        elif beat.name == "page_folds":
            # Кролик в панике убегает за край страницы, пока сказка сгибается.
            run = _ease(min(1.0, p / 0.45))
            rabbit.x = rabbit.home_x + (WIDTH + SPRITE_SIZE - rabbit.home_x) * run
            rabbit.lift = abs(math.sin(p * math.pi * 8)) * 3
            rabbit.set_pose("panic_gasp" if run < 0.3 else "run_right_3")
        elif beat.name == "chuchmek_appears":
            # Чучмек «вырастает» из земли с небольшим отскоком.
            rise = _ease(min(1.0, p / 0.7))
            bounce = math.sin(min(1.0, max(0.0, (p - 0.7) / 0.3)) * math.pi) * 3
            chuchmek.alpha = round(255 * rise)
            chuchmek.lift = -SPRITE_SIZE * (1 - rise) + bounce
            if p > 0.75:
                chuchmek.set_pose("clipboard_confident")
        elif beat.name == "finale":
            chuchmek.lift = abs(math.sin(p * math.pi * 2)) * 3

    def _end_cue(self, name: str) -> None:
        alice, rabbit, chuchmek = self.actors["alice"], self.actors["white_rabbit"], self.actors["chuchmek"]
        for actor in self.actors.values():
            actor.lift = 0.0
        if name == "alice_appears":
            alice.alpha = 255
        elif name == "rabbit_runs_in":
            rabbit.x = rabbit.home_x
            rabbit.set_pose("checks_watch_happy")
        elif name == "page_folds":
            rabbit.visible = False
            self.backdrop = "absurd"
        elif name == "chuchmek_appears":
            chuchmek.alpha = 255
            chuchmek.set_pose("clipboard_confident")

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface) -> None:
        beat = self.beat
        folding = isinstance(beat, Cue) and beat.name == "page_folds"
        if folding:
            self._draw_fold(surface, self.beat_time / beat.seconds)
        else:
            surface.blit(self._pages[self.backdrop], (0, 0))
            heading = self._headings[self.backdrop]
            surface.blit(heading, heading.get_rect(midtop=(WIDTH // 2, 8)))
        if isinstance(beat, Cue) and beat.name in ("alice_appears", "chuchmek_appears", "finale"):
            self._draw_sparkles(surface, beat)
        for char_id in DRAW_ORDER:
            self.actors[char_id].draw(surface, self.ground)
        if isinstance(beat, Cue) and beat.name == "finale":
            text = self._finale
            alpha = round(255 * _ease(self.beat_time / (beat.seconds * 0.4)))
            image = text.copy()
            image.set_alpha(alpha)
            rect = image.get_rect(center=(WIDTH // 2, 34))
            pygame.draw.rect(surface, PAGE_COLOR, rect.inflate(10, 6))
            pygame.draw.rect(surface, PAGE_EDGE_COLOR, rect.inflate(10, 6), 1)
            surface.blit(image, rect)
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue)

    def _draw_fold(self, surface: pygame.Surface, p: float) -> None:
        """Сказочная страница дрожит, потом её угол загибается, открывая абсурдную страницу."""
        fairy = self._pages["fairy"]
        absurd = self._pages["absurd"].copy()
        absurd.blit(self._headings["absurd"], self._headings["absurd"].get_rect(midtop=(WIDTH // 2, 8)))
        if p < 0.25:
            # Страница вздрагивает, как от неожиданного сквозняка.
            shake = round(math.sin(p * 90) * 2 * (p / 0.25))
            surface.blit(absurd, (0, 0))
            surface.blit(fairy, (shake, 0))
            surface.blit(self._headings["fairy"], self._headings["fairy"].get_rect(midtop=(WIDTH // 2 + shake, 8)))
            return
        s = _ease((p - 0.25) / 0.75) * (WIDTH + HEIGHT)
        surface.blit(absurd, (0, 0))
        page = fairy.copy()
        page.blit(self._headings["fairy"], self._headings["fairy"].get_rect(midtop=(WIDTH // 2, 8)))
        page.set_colorkey(KEY_COLOR)
        pygame.draw.polygon(page, KEY_COLOR, [(WIDTH - s, HEIGHT), (WIDTH, HEIGHT - s), (WIDTH, HEIGHT)])
        surface.blit(page, (0, 0))
        # Загнутый угол — обратная сторона страницы с тенью на сгибе.
        flap = [(WIDTH - s, HEIGHT), (WIDTH, HEIGHT - s), (WIDTH - s, HEIGHT - s)]
        pygame.draw.polygon(surface, FLAP_COLOR, flap)
        pygame.draw.polygon(surface, PAGE_EDGE_COLOR, flap, 1)

    def _draw_sparkles(self, surface: pygame.Surface, beat: Cue) -> None:
        """Мерцающие звёздочки вокруг появляющегося персонажа."""
        actor = self.actors["chuchmek" if beat.name == "chuchmek_appears" else "alice"]
        for index in range(5):
            phase = self.time * 6 + index * 1.7
            if math.sin(phase) < 0.2:
                continue
            x = round(actor.x + math.cos(index * 2.4) * 26)
            y = round(self.ground - SPRITE_SIZE // 2 + math.sin(index * 1.9) * 22)
            pygame.draw.line(surface, SPARKLE_COLOR, (x - 2, y), (x + 2, y))
            pygame.draw.line(surface, SPARKLE_COLOR, (x, y - 2), (x, y + 2))


def _render_fairy_page() -> pygame.Surface:
    """Тёплая сказочная страница: рамка, солнце, холмы, дорожка, деревья."""
    page = pygame.Surface(config.LOGICAL_SIZE)
    page.fill(PAGE_COLOR)
    horizon = 96
    pygame.draw.circle(page, SUN_COLOR, (268, 40), 12)
    for angle in range(0, 360, 45):
        dx, dy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        pygame.draw.line(page, SUN_COLOR, (268 + dx * 16, 40 + dy * 16), (268 + dx * 21, 40 + dy * 21))
    pygame.draw.ellipse(page, HILL_COLORS[0], (-40, horizon - 22, 220, 70))
    pygame.draw.ellipse(page, HILL_COLORS[1], (130, horizon - 16, 240, 70))
    pygame.draw.rect(page, HILL_COLORS[1], (0, horizon + 10, WIDTH, HEIGHT))
    pygame.draw.polygon(page, PATH_COLOR, [(150, horizon - 6), (160, horizon - 6), (205, HEIGHT), (110, HEIGHT)])
    for x, y in ((38, horizon - 8), (292, horizon - 4), (216, horizon - 14)):
        pygame.draw.rect(page, TREE_COLORS[1], (x - 1, y - 6, 3, 8))
        pygame.draw.circle(page, TREE_COLORS[0], (x, y - 10), 7)
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
    pygame.draw.rect(page, SUN_COLOR, (276, 20, 16, 16))
    pygame.draw.rect(page, PAGE_EDGE_COLOR, (276, 20, 16, 16), 1)
    _draw_border(page, (168, 132, 190))
    return page


def _draw_border(page: pygame.Surface, color: config.Color) -> None:
    """Двойная рамка книжной страницы с уголками."""
    pygame.draw.rect(page, color, page.get_rect().inflate(-6, -6), 1)
    pygame.draw.rect(page, color, page.get_rect().inflate(-10, -10), 1)
    for x, y in ((5, 5), (WIDTH - 6, 5), (5, HEIGHT - 6), (WIDTH - 6, HEIGHT - 6)):
        pygame.draw.circle(page, color, (x, y), 2)
