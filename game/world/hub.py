"""Центральная площадь: волшебная лесная поляна, откуда Алиса заходит в три испытания.

Каждое испытание — своё огромное дерево с тёмным отверстием в стволе: дерево суши слева,
формуляров вверху и тортиков справа. Алиса подходит к отверстию снизу и жмёт E или Enter:
рядом с входом (PORTALS[i].point) подсвечивается дупло и открывается испытание. Ствол и крона —
препятствие (PORTALS[i].rect), но у входа остаётся свободный коврик.
Используются существующие системы: Character (движение и анимации), CollisionMap
(границы и препятствия), DialogueController/DialogueBox (реплики), SceneManager (переходы).
Внешний вид нарисован кодом: земля — game/world/hub_ground.py, деревья, стол, мелкие предметы —
game/world/hub_scenery.py; здесь их порядок, свечение, огоньки и взаимодействия.

Вход открывает сцену испытания (TRIAL_SCENES) через менеджер, если она зарегистрирована;
иначе Чучмек объясняет, что вход не готов. Фрагменты выдают сами испытания через общий
GameProgress, площадь их только показывает и, вернувшись из испытания, сообщает итог.

В центре стоит круглый стол мозаики: у каждого пройденного испытания на нём своя плитка-фрагмент
(источник правды — GameProgress, а не отдельный счётчик), пустые гнёзда показывают, чего не хватает.
Когда собраны все три, мозаика сияет, и E рядом со столом открывает финал (FINALE_SCENE).
Сам по себе третий фрагмент финал не запускает — только игрок.

Слева от стола, напротив Чучмека, в корзинке спит Лео — главный инспектор праздничного
настроения. Он не ходит и не мешает: корзинка стоит на траве в стороне от тропинок и деревьев
и не является препятствием. Рядом с ней E показывает одну короткую реплику и сразу возвращает
управление; прогресс это не меняет.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pygame

import config
from game.core.input import Action, actions_for
from game.core.scenes import Scene
from game.dialogue.box import DialogueBox
from game.dialogue.model import DialogueController, DialogueScript
from game.graphics.animation import Direction
from game.graphics.fonts import TextFonts, TextStyle, load_font, render_text
from game.graphics.hires import HiResLayer, logical_target
from game.graphics.sprite_manifest import CHARACTERS_DIR, try_load_character_sprites
from game.story.hub_dialogue import CHUCHMEK_TALK, CHUCHMEK_TALK_AGAIN, PORTAL_NOT_READY, all_scripts, leo_script
from game.world import hub_scenery
from game.world.character import Character
from game.world.collision import CollisionMap
from game.world.hub_ground import (  # noqa: F401  (цвета земли нужны и тестам, и другим сценам)
    GRASS_COLOR,
    GRASS_DARK_COLOR,
    render_ground,
)
from game.world.hub_scenery import MOSAIC_SLOTS, SLOT_SIZE, TABLE_CENTER, TREE_SPECS, WARM_LIGHT
from game.world.progress import TRIAL_NAMES, TRIALS, GameProgress

HUB_SCENE = "hub"  # имя площади в SceneManager
FINALE_SCENE = "finale"  # последняя страница сказки: её открывает мозаика при всех фрагментах
# Имена сцен испытаний. Пока сцена не зарегистрирована, вход закрыт.
TRIAL_SCENES = {trial_id: f"trial_{trial_id}" for trial_id in TRIALS}

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 32  # кадры 64×64 уменьшаются ровно вдвое ближайшим соседом
WALK_SPEED = 64  # логических пикселей в секунду
HUD_HEIGHT = 12  # верхняя полоса: название площади и фрагменты
STATUS_TOP = 168  # нижняя полоса: подсказки; персонажи до неё не доходят
# Где могут стоять ноги персонажа: между полосами интерфейса, и так, чтобы кадр шириной
# SPRITE_SIZE не вылезал за края экрана (ноги уже кадра на SPRITE_SIZE/2 − 6 с каждой стороны).
WALK_BOUNDS = pygame.Rect(10, 44, WIDTH - 20, STATUS_TOP - 4 - 44)
SPAWN = (160, 160)  # точка появления Алисы — внизу площади
TOAST_SECONDS = 3.0
TOAST_PRIORITY_SECONDS = 2.0  # столько свежее сообщение (например, итог испытания) важнее подсказки у цели
MOSAIC_CENTER = (160, 140)  # где стоит Алиса, чтобы обратиться к столу мозаики (перед ним)
MOSAIC_RADIUS = 12  # на таком расстоянии от этой точки (по ногам Алисы) с ней можно взаимодействовать
FRAGMENT_POP_SECONDS = 1.4  # сколько искрится только что положенный на стол фрагмент


@dataclass(frozen=True)
class Portal:
    """Вход в испытание — дерево с отверстием в стволе.

    rect — ствол и крона, препятствие для ног; door — отверстие (холст); point — где стоят ноги
    Алисы у входа, а radius — с какого расстояния от этой точки он открывается; sign — надпись
    на табличке (sign_rect — её место на холсте)."""

    id: str
    rect: pygame.Rect
    door: pygame.Rect
    point: tuple[int, int]
    radius: int
    sign: str
    sign_rect: pygame.Rect

    @property
    def name(self) -> str:
        return TRIAL_NAMES[self.id]


PORTALS = tuple(
    Portal(trial_id, spec.block, spec.door, spec.stand, spec.radius, spec.sign_text, spec.sign)
    for trial_id, spec in TREE_SPECS.items()
)
CHUCHMEK_POSITION = (214, 80)  # недалеко от центра, выше тропинки к тортикам
CHUCHMEK_RADIUS = 24
CHUCHMEK_OBSTACLE = pygame.Rect(206, 74, 16, 7)
CHUCHMEK_AREA = pygame.Rect(198, 52, 32, 36)  # здесь земля — простая трава
# Лео в корзинке: середина её дна. Зеркально Чучмеку, на траве между тропинками к суши и к формулярам.
LEO_POSITION = (104, 84)
# Откуда Алиса заглядывает в корзинку: справа, со стороны ног Лео (голова у кадра слева) —
# так она его не заслоняет. Дотянуться можно и с края тропинки.
LEO_POINT = (130, 86)
LEO_RADIUS = 16
LEO_FRAME = "sleep_blanket"  # «спит под одеялом» из манифеста leo: лежит, ему не нужна ходьба
BASKET_BACK = pygame.Rect(LEO_POSITION[0] - 15, LEO_POSITION[1] - 12, 30, 9)  # проём корзинки
BASKET_FRONT = pygame.Rect(LEO_POSITION[0] - 16, LEO_POSITION[1] - 7, 32, 8)  # передняя стенка поверх одеяла
# Весь участок Лео — кадр и корзинка: на нём земля остаётся простой травой.
LEO_AREA = pygame.Rect(LEO_POSITION[0] - 17, LEO_POSITION[1] - 34, 34, 36)

BASKET_COLOR = (196, 146, 92)
BASKET_DARK_COLOR = (150, 104, 62)
BASKET_INSIDE_COLOR = (238, 220, 196)
BLANKET_COLOR = (170, 196, 236)
SLEEP_MARK_COLOR = (250, 250, 255)
HUD_COLOR = (44, 38, 58)
HUD_TEXT_COLOR = (240, 230, 206)
HUD_ACCENT_COLOR = (250, 206, 108)
SIGN_TEXT_COLOR = (252, 240, 214)
MARK_COLOR = (255, 236, 140)
# Свет в дупле каждого дерева (цвет) и свечение собранной мозаики.
DOOR_GLOW_COLORS = {"sushi": (255, 168, 110), "forms": (190, 212, 255), "cakes": (255, 186, 214)}
MOSAIC_GOLD = (250, 206, 108)

# Надписи в разрешении окна (слой высокого разрешения); размер — в логических пикселях.
TEXT_SIZE = 8
HUD_STYLE = TextStyle(TEXT_SIZE, HUD_TEXT_COLOR, background=HUD_COLOR)  # полосы вверху и внизу
FRAGMENTS_STYLE = TextStyle(TEXT_SIZE, HUD_ACCENT_COLOR, background=HUD_COLOR)
# Вывески на деревьях: жирные буквы с тенью, чтобы читались и в окне 960×540, и на весь экран.
SIGN_STYLE = TextStyle(TEXT_SIZE, SIGN_TEXT_COLOR, bold=True, shadow=(40, 24, 30), shadow_offset=0.5)

# Светлячки: центр кружения (x, y), размах по осям, скорость и фаза.
FIREFLIES = (
    (26, 70, 10, 6, 0.55, 0.0), (68, 62, 9, 7, 0.45, 1.7), (40, 108, 12, 4, 0.5, 3.1), (86, 100, 8, 5, 0.6, 4.4),
    (250, 68, 10, 6, 0.5, 0.9), (296, 64, 9, 7, 0.42, 2.5), (262, 108, 12, 4, 0.58, 4.0), (300, 112, 7, 5, 0.47, 5.2),
    (140, 58, 8, 6, 0.5, 1.1), (184, 56, 9, 5, 0.44, 3.6), (118, 112, 6, 8, 0.52, 2.2), (204, 112, 6, 8, 0.46, 5.5),
    (160, 138, 16, 4, 0.4, 0.4), (60, 148, 12, 6, 0.5, 3.3), (262, 148, 12, 6, 0.48, 1.9),
)


@dataclass(frozen=True)
class Interaction:
    """С чем Алиса может взаимодействовать сейчас: портал испытания или Чучмек."""

    kind: str  # "portal", "chuchmek", "mosaic" или "leo"
    target: str  # идентификатор испытания, "chuchmek", "finale" или "leo"
    prompt: str


class HubScene(Scene):
    """Площадь: Алиса ходит, разговаривает с Чучмеком и подходит к порталам испытаний.

    Backspace (действие cancel) закрывает открытую реплику, а без реплики — возвращает
    к предыдущей сцене, если она есть (например, к экрану проверки).

    Со слоем высокого разрешения Алиса, Чучмек и Лео рисуются из исходных кадров 64×64, а надписи —
    шрифтом размера окна; площадь, порталы, деревья и корзинка остаются пиксельными на холсте.
    """

    supports_hires = True

    def __init__(self, progress: GameProgress | None = None, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.progress = progress if progress is not None else GameProgress()
        root = Path(characters_dir)
        obstacles = [portal.rect for portal in PORTALS] + [CHUCHMEK_OBSTACLE]
        obstacles += list(hub_scenery.table().footprint) + hub_scenery.prop_obstacles()
        self.collision = CollisionMap(WALK_BOUNDS, obstacles)

        alice_sprites = try_load_character_sprites(root / "alice")
        self.alice = Character(
            "Алиса",
            alice_sprites.animation_set(SPRITE_SIZE) if alice_sprites else None,
            position=SPAWN,
            speed=WALK_SPEED,
            direction=Direction.UP,
        )
        self.alice.collider = self.collision.move
        chuchmek_sprites = try_load_character_sprites(root / "chuchmek")
        # Чучмек стоит на месте лицом к игроку; его кадры никогда не отражаются.
        self.chuchmek = Character(
            "Чучмек",
            chuchmek_sprites.animation_set(SPRITE_SIZE) if chuchmek_sprites else None,
            position=CHUCHMEK_POSITION,
            direction=Direction.DOWN,
        )
        # Лео — не Character: он не ходит и не поворачивается, это одна поза из манифеста.
        self.leo_sprites = try_load_character_sprites(root / "leo")
        self._leo_frames: tuple[pygame.Surface, pygame.Surface] | None = None  # исходный кадр и он же 32×32
        self.leo_visits = 0  # сколько раз Алиса заглядывала в корзинку: реплики идут по кругу
        self.talked_to_chuchmek = False  # знакомство с площадью — только в первом разговоре

        self.box = DialogueBox()
        for script in all_scripts():
            self.box.check_fits(script)
        self.dialogue: DialogueController | None = None
        self.active_trial: str | None = None  # последний портал, к которому подходила Алиса
        self.toast = ""  # короткое сообщение в нижней полосе
        self._toast_time = 0.0
        self.time = 0.0
        self._font = load_font(9)
        self._text_cache: dict[tuple[str, config.Color], pygame.Surface] = {}
        self._fonts = TextFonts()
        self.text_metrics = self._fonts.metrics(HUD_STYLE)  # все надписи площади одного размера
        self._background = _ground()
        self._backdrop = _backdrop()
        self._seen_fragments = set(self.progress.completed)  # какие плитки уже лежат на столе
        self._placed_at: dict[str, float] = {}  # когда на стол лёг свежий фрагмент (время площади)
        self._trial_in_progress: str | None = None  # испытание, в которое Алиса только что ушла
        self._trial_scene: Scene | None = None
        self._finale_scene: Scene | None = None  # открытый финал (не больше одного)
        self._fragments_before = self.progress.fragments

    # --- Состояние ---

    def nearby(self) -> Interaction | None:
        """Ближайшее, с чем можно взаимодействовать из текущей точки Алисы, или None."""
        candidates: list[tuple[float, Interaction]] = []
        x, y = self.alice.x, self.alice.y
        for portal in PORTALS:
            # Вход открывается у самого отверстия: на коврике под ним и в нескольких шагах от него.
            distance = math.dist((x, y), portal.point)
            if distance <= portal.radius:
                done = " (пройдено)" if self.progress.is_completed(portal.id) else ""
                prompt = f"{portal.name}{done}   E — войти"
                candidates.append((distance, Interaction("portal", portal.id, prompt)))
        distance = math.dist((x, y), self._chuchmek_point())
        if distance <= CHUCHMEK_RADIUS:
            candidates.append((distance, Interaction("chuchmek", "chuchmek", "Чучмек   E — поговорить")))
        distance = math.dist((x, y), LEO_POINT)
        if distance <= LEO_RADIUS:
            candidates.append((distance, Interaction("leo", "leo", "Лео   E — заглянуть в корзинку")))
        distance = math.dist((x, y), MOSAIC_CENTER)
        if distance <= MOSAIC_RADIUS:
            if self.progress.has_all_fragments:
                prompt = "Мозаика   E — восстановить последнюю страницу"
            else:
                prompt = f"Мозаика   нужны все фрагменты: {self.progress.fragments}/{self.progress.total}"
            candidates.append((distance, Interaction("mosaic", "finale", prompt)))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def fragments_text(self) -> str:
        return f"Фрагменты праздника: {self.progress.fragments}/{self.progress.total}"

    def status_text(self) -> str:
        """Что показывает нижняя полоса: подсказку рядом с целью, недавнее сообщение или управление."""
        if self.toast and TOAST_SECONDS - self._toast_time < TOAST_PRIORITY_SECONDS:
            return self.toast
        target = self.nearby()
        if target is not None:
            return target.prompt
        if self.toast:
            return self.toast
        return "Стрелки/WASD — идти   E — действие"

    @staticmethod
    def _chuchmek_point() -> tuple[int, int]:
        return CHUCHMEK_POSITION[0], CHUCHMEK_POSITION[1] + 6

    # --- Управление ---

    def handle_event(self, event: pygame.event.Event) -> None:
        actions = actions_for(event) if event.type == pygame.KEYDOWN else frozenset()
        if self.dialogue is not None:
            if Action.CANCEL in actions:
                self._close_dialogue()
                return
            if Action.INTERACT in actions and Action.CONFIRM not in actions:
                self.dialogue.confirm()  # «E — поговорить»: той же клавишей и продолжаем разговор
            else:
                self.dialogue.handle_event(event)
            if self.dialogue.is_finished:
                self._close_dialogue()
            return
        if Action.CANCEL in actions:
            self.finish()
            return
        self.alice.handle_event(event)
        if Action.INTERACT in actions:
            self.interact()

    def interact(self) -> bool:
        """Действие «interact» (E или Enter): работает только рядом с целью. True, если что-то произошло."""
        target = self.nearby()
        if target is None:
            return False
        self.alice.release_controls()
        if target.kind == "chuchmek":
            self._face(self._chuchmek_point())
            self._open_dialogue(CHUCHMEK_TALK_AGAIN if self.talked_to_chuchmek else CHUCHMEK_TALK)
            self.talked_to_chuchmek = True
            return True
        if target.kind == "leo":
            # Одна реплика и снова управление: ни прогресса, ни перехода.
            self._face(LEO_POSITION)
            self.leo_visits += 1
            self._open_dialogue(leo_script(self.leo_visits))
            return True
        if target.kind == "mosaic":
            return self._use_mosaic()
        portal = next(portal for portal in PORTALS if portal.id == target.target)
        self._face(portal.point)
        self.active_trial = portal.id
        scene_name = TRIAL_SCENES[portal.id]
        manager = self.manager
        if manager is not None and manager.is_registered(scene_name):
            self._trial_in_progress = portal.id
            self._fragments_before = self.progress.fragments
            self._trial_scene = manager.push(scene_name)  # испытание вернёт сюда же, на эту площадь
        else:
            # Испытание ещё не сделано: переходить некуда, фрагмент не выдаётся.
            self._open_dialogue(PORTAL_NOT_READY[portal.id])
            self._show_toast(f"Испытание «{portal.name}»: портал пока не готов")
        return True

    def _use_mosaic(self) -> bool:
        """E у мозаики: финал — только при всех фрагментах и только один."""
        progress = self.progress
        if not progress.has_all_fragments:
            self._show_toast(f"Мозаике не хватает фрагментов: {progress.fragments}/{progress.total}")
            return True
        if self._finale_scene is not None and self._finale_scene.manager is not None:
            return False  # финал уже открыт — второй не нужен
        manager = self.manager
        if manager is None or not manager.is_registered(FINALE_SCENE):
            self._show_toast("Последняя страница пока не готова")
            return True
        self._finale_scene = manager.push(FINALE_SCENE)
        return True

    def _face(self, point: tuple[int, int]) -> None:
        dx, dy = point[0] - self.alice.x, point[1] - self.alice.y
        if abs(dx) >= abs(dy):
            self.alice.face(Direction.RIGHT if dx > 0 else Direction.LEFT)
        else:
            self.alice.face(Direction.DOWN if dy > 0 else Direction.UP)

    def _open_dialogue(self, script: DialogueScript) -> None:
        self.dialogue = DialogueController(script)

    def _close_dialogue(self) -> None:
        """Реплика закрыта — управление снова у Алисы."""
        self.dialogue = None
        self.alice.release_controls()

    def _show_toast(self, text: str) -> None:
        self.toast = text
        self._toast_time = TOAST_SECONDS

    def enter(self) -> None:
        """Возврат на площадь (в том числе из испытания): сообщить, чем оно закончилось."""
        finale, self._finale_scene = self._finale_scene, None
        if finale is not None and not getattr(finale, "completed", False):
            self._show_toast("Последняя страница подождёт: E у мозаики")
        trial_id, self._trial_in_progress = self._trial_in_progress, None
        trial, self._trial_scene = self._trial_scene, None
        if trial_id is None:
            return
        name = TRIAL_NAMES[trial_id]
        if not getattr(trial, "completed", False):  # сцена испытания сама знает, досмотрена ли она
            self._show_toast(f"Испытание «{name}» прервано — фрагмент не получен")
        elif self.progress.fragments > self._fragments_before:
            message = f"Получен фрагмент праздника! Теперь {self.progress.fragments}/{self.progress.total}"
            if self.progress.has_all_fragments:
                message += ". Мозаика засветилась"
            self._show_toast(message)
        else:
            self._show_toast(f"Испытание «{name}» уже пройдено — фрагмент тот же")

    def update(self, dt: float) -> None:
        self.time += dt
        for trial_id in self.progress.completed:  # свежий фрагмент ложится на стол с искрами
            if trial_id not in self._seen_fragments:
                self._seen_fragments.add(trial_id)
                self._placed_at[trial_id] = self.time
        if self.dialogue is not None:
            self.dialogue.update(dt)
        self.alice.update(dt)
        self.chuchmek.update(dt)
        if self._toast_time > 0 and self.dialogue is None:
            self._toast_time -= dt
            if self._toast_time <= 0:
                self.toast = ""

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рисует площадь на холсте; со слоем hires деревья, стол, предметы и персонажи уходят в него
        картинками вдвое подробнее холста (см. game/graphics/hires.py), а порядок слоёв остаётся тем же:
        всё, что стоит на земле, рисуется по линии земли — ближние к игроку поверх дальних."""
        surface.blit(self._background, (0, 0))
        target = self.nearby() if self.dialogue is None else None
        scenery = hub_scenery
        # Каждая запись: (линия земли, порядок при равных линиях, что рисовать).
        drawables: list[tuple[float, int, object]] = []
        for portal in PORTALS:
            drawables.append((TREE_SPECS[portal.id].ground, 0, lambda p=portal: self._draw_tree(surface, p, target, hires)))
        drawables.append((scenery.table().base_y, 0, lambda: self._draw_table(surface, target, hires)))
        for prop in scenery.props():
            if prop.flat:
                continue  # вшито в землю
            drawables.append((prop.sort_y, 0, lambda p=prop: self._draw_prop(surface, p, hires)))
        drawables.append((self.chuchmek.y, 0, lambda: self._draw_chuchmek(surface, target, hires)))
        drawables.append((LEO_POSITION[1], 0, lambda: self._draw_leo(surface, target, hires)))
        drawables.append((self.alice.y + 0.1, 0, lambda: self.alice.draw(surface, hires)))
        if hires is not None:
            hires.sprite(self._backdrop.image, self._backdrop.rect, opaque=True)  # земля, деревья и предметы
            table = hub_scenery.table()
            people = ((self.alice.y + 0.1, self.alice.rect), (self.chuchmek.y, self.chuchmek.rect),
                      (LEO_POSITION[1], self.leo_rect()), (table.base_y, table.body.rect))
            drawables += self._in_front_of(people, hires)
            for index, spot in enumerate(FIREFLIES):
                x, y, level = self._firefly(index, spot)
                if level >= 2:  # самые тусклые вспышки не стоят отдельной картинки
                    drawables.append((y, 0, lambda p=(x, y), v=level: scenery.firefly(v).draw(surface, hires, center=p)))
        for _, _, draw in sorted(drawables, key=lambda item: item[:2]):
            draw()
        self._draw_hud(surface, hires)
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue, hires)
        else:
            self._draw_status(surface, hires)

    @staticmethod
    def _in_front_of(people: tuple[tuple[float, pygame.Rect], ...], hires: HiResLayer) -> list[tuple[float, int, object]]:
        """Неподвижное из фона, что стоит ближе к игроку, чем человек, и закрывает его, — рисуется
        поверх него заново, но только в его границах (слой окна обрежет остальное)."""
        redraws: list[tuple[float, int, object]] = []
        for y, rect in people:
            for sort_y, piece in hub_scenery.static_items():
                if sort_y > y and piece.rect.colliderect(rect):
                    # порядок -1: перед светом и надписью того же дерева, которые лежат на нём
                    redraws.append((sort_y, -1, lambda p=piece, r=rect: hires.sprite(p.image, p.rect, clip=r)))
        return redraws

    def _text(self, text: str, color: config.Color) -> pygame.Surface:
        key = (text, color)
        image = self._text_cache.get(key)
        if image is None:
            image = self._text_cache[key] = render_text(self._font, text, color)
        return image

    def _firefly(self, index: int, spot: tuple[float, float, float, float, float, float]) -> tuple[int, int, int]:
        """Где светлячок сейчас и насколько ярок (0 — погас); зависит только от времени площади."""
        x, y, dx, dy, speed, phase = spot
        t = self.time * speed + phase
        px = x + math.sin(t) * dx + math.sin(t * 2.3 + index) * dx * 0.2
        py = y + math.cos(t * 0.8) * dy
        glow = 0.5 + 0.5 * math.sin(self.time * speed * 2.6 + phase * 2.0)
        return round(px), round(py), int(glow * glow * 3.99)

    def plaque_rect(self, portal: Portal, hires: bool = False) -> pygame.Rect:
        """Табличка с названием на дереве-входе: её место нарисовано вместе с деревом."""
        return portal.sign_rect.copy()

    def _draw_tree(self, canvas: pygame.Surface, portal: Portal, target: Interaction | None,
                   hires: HiResLayer | None) -> None:
        """Дерево-вход: само дерево, свет в дупле, огоньки на ветвях, табличка с надписью и отметки."""
        art = {"sushi": hub_scenery.sushi_tree, "forms": hub_scenery.forms_tree, "cakes": hub_scenery.cakes_tree}[portal.id]()
        if hires is None:  # со слоем окна дерево уже лежит в подробном фоне
            art.piece.draw(canvas, None)
        done = self.progress.is_completed(portal.id)
        if hires is not None:
            pulse = 0.5 + 0.5 * math.sin(self.time * 1.6 + portal.door.x)
            glow_color = DOOR_GLOW_COLORS[portal.id] if not done else MOSAIC_GOLD
            glow = hub_scenery.glow(13, glow_color, 120 if done else 84)
            glow.draw(canvas, hires, alpha=round(150 + 105 * pulse), center=(portal.door.centerx, portal.door.centery + 3))
            for index, (x, y, color, radius) in enumerate(art.lights):
                flicker = 0.5 + 0.5 * math.sin(self.time * 2.1 + index * 1.9)
                hub_scenery.glow(radius, color, 150).draw(canvas, hires, alpha=round(90 + 140 * flicker), center=(x, y))
            for index, group in enumerate(art.garland):  # лампочки гирлянды мигают тремя группами по очереди
                twinkle = 0.5 + 0.5 * math.sin(self.time * 1.7 + index * math.tau / 3)
                group.draw(canvas, hires, alpha=round(60 + 195 * twinkle * twinkle))
            near = target is not None and target.kind == "portal" and target.target == portal.id
            if near:
                hub_scenery.door_ring(portal.id).draw(canvas, hires, alpha=round(150 + 105 * abs(math.sin(self.time * 5))))
            if done:
                badge = hub_scenery.badge()
                badge.draw(canvas, hires, center=(portal.sign_rect.right - 1, portal.sign_rect.top - 1))
            hires.text(portal.sign, SIGN_STYLE, portal.sign_rect.center, anchor="center")
        else:
            label = self._text(portal.sign, SIGN_TEXT_COLOR)
            canvas.blit(label, label.get_rect(center=portal.sign_rect.center))
        if target is not None and target.kind == "portal" and target.target == portal.id:
            # Ромбик над кроной: сюда можно войти.
            x, y = portal.sign_rect.centerx, portal.sign_rect.top - 8 - round(abs(math.sin(self.time * 4)) * 2)
            with logical_target(canvas, hires, pygame.Rect(x - 4, y - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

    def _draw_prop(self, canvas: pygame.Surface, prop: hub_scenery.Prop, hires: HiResLayer | None) -> None:
        if hires is None:  # со слоем окна предмет уже лежит в подробном фоне
            prop.piece.draw(canvas, None)
            return
        for index, (x, y) in enumerate(prop.glow):  # тёплый свет фонарей и холодный — кристаллов
            flicker = 0.5 + 0.5 * math.sin(self.time * 3.1 + prop.foot[0] * 0.37 + index)
            hub_scenery.glow(9, WARM_LIGHT, 96).draw(canvas, hires, alpha=round(120 + 100 * flicker), center=(x, y))

    def _draw_table(self, canvas: pygame.Surface, target: Interaction | None, hires: HiResLayer | None) -> None:
        """Стол мозаики: собранные плитки лежат на своих местах, пустые гнёзда ждут остальных."""
        art = hub_scenery.table()
        complete = self.progress.has_all_fragments
        cx, cy = TABLE_CENTER
        if hires is not None and complete:  # золотое сияние под столом, мерцающее
            pulse = 0.5 + 0.5 * math.sin(self.time * 2.2)
            hub_scenery.glow(52, MOSAIC_GOLD, 120).draw(canvas, hires, alpha=round(110 + 120 * pulse), center=(cx, cy + 10))
        art.body.draw(canvas, hires)
        for trial_id, (x, y) in MOSAIC_SLOTS.items():
            if not self.progress.is_completed(trial_id):
                continue
            if hires is not None:  # едва заметный цветной отсвет вокруг собранного фрагмента
                tint = hub_scenery.FRAGMENT_COLORS[trial_id]
                hub_scenery.glow(SLOT_SIZE, tint, 80).draw(canvas, hires, alpha=150, center=(x, y))
            art.fragments[trial_id].draw(canvas, hires)
            age = self.time - self._placed_at.get(trial_id, -FRAGMENT_POP_SECONDS)
            if hires is not None and 0 <= age < FRAGMENT_POP_SECONDS:
                self._draw_pop(canvas, hires, (x, y), age / FRAGMENT_POP_SECONDS)
        if complete:
            if hires is not None:
                shimmer = 0.5 + 0.5 * math.sin(self.time * 3.0)
                art.inlay.draw(canvas, hires, alpha=round(170 + 85 * shimmer))
                for k in range(5):  # искры бегут по краю доски
                    angle = self.time * 0.9 + k * math.tau / 5
                    spot = (cx + math.cos(angle) * 27, cy + 1 + math.sin(angle) * 11)
                    twinkle = 0.5 + 0.5 * math.sin(self.time * 4 + k * 2.1)
                    hub_scenery.sparkle((255, 230, 150), 3).draw(canvas, hires, alpha=round(120 + 135 * twinkle), center=spot)
            else:
                art.inlay.draw(canvas, None)
        if target is not None and target.kind == "mosaic":
            if hires is not None:
                hub_scenery.table_ring().draw(canvas, hires, alpha=round(140 + 100 * abs(math.sin(self.time * 5))))
            x, y = cx, cy - hub_scenery.TABLE_RY - 6 - round(abs(math.sin(self.time * 4)) * 2)
            with logical_target(canvas, hires, pygame.Rect(x - 4, y - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

    @staticmethod
    def _draw_pop(canvas: pygame.Surface, hires: HiResLayer, center: tuple[int, int], progress: float) -> None:
        """Искры разлетаются от только что положенного фрагмента и гаснут."""
        fade = 1 - progress
        for k in range(6):
            angle = k * math.tau / 6 + progress
            reach = 4 + progress * 11
            spot = (center[0] + math.cos(angle) * reach, center[1] + math.sin(angle) * reach * 0.7)
            hub_scenery.sparkle((255, 236, 160), 2).draw(canvas, hires, alpha=round(255 * fade), center=spot)

    def _draw_chuchmek(self, canvas: pygame.Surface, target: Interaction | None, hires: HiResLayer | None) -> None:
        self.chuchmek.draw(canvas, hires)
        if target is not None and target.kind == "chuchmek":
            # Ромбик над шляпкой: с Чучмеком можно поговорить.
            x, y = self.chuchmek.rect.centerx, self.chuchmek.rect.top - 4 - round(abs(math.sin(self.time * 4)) * 2)
            with logical_target(canvas, hires, pygame.Rect(x - 4, y - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

    def leo_frames(self) -> tuple[pygame.Surface, pygame.Surface] | None:
        """Кадр Лео из манифеста: исходный 64×64 и он же 32×32 (ближайший сосед). None — спрайтов нет."""
        if self._leo_frames is None and self.leo_sprites is not None:
            try:
                source = self.leo_sprites.frame(LEO_FRAME).image
            except KeyError:
                source = self.leo_sprites.frames[0].image
            self._leo_frames = (source, pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE)))
        return self._leo_frames

    def leo_rect(self) -> pygame.Rect:
        """Где на холсте стоит кадр Лео: ноги кадра чуть ниже края корзинки — одеяло заправлено."""
        return pygame.Rect(0, 0, SPRITE_SIZE, SPRITE_SIZE).move(LEO_POSITION[0] - SPRITE_SIZE // 2,
                                                                 LEO_POSITION[1] - 2 - SPRITE_SIZE)

    def _draw_leo(self, canvas: pygame.Surface, target: Interaction | None, hires: HiResLayer | None) -> None:
        """Корзинка, спящий Лео из манифеста и передняя стенка корзинки поверх его одеяла."""
        x, y = LEO_POSITION
        with logical_target(canvas, hires, BASKET_BACK.union(pygame.Rect(x - 16, y - 2, 33, 4))) as surface:
            pygame.draw.ellipse(surface, GRASS_DARK_COLOR, (x - 16, y - 2, 33, 4))  # тень на траве
            pygame.draw.ellipse(surface, BASKET_DARK_COLOR, BASKET_BACK)
            pygame.draw.ellipse(surface, BASKET_INSIDE_COLOR, BASKET_BACK.inflate(-4, -3))
        frames = self.leo_frames()
        if frames is not None:
            source, image = frames
            if hires is not None:
                hires.sprite(source, self.leo_rect())  # исходный кадр на том же месте и того же размера
            else:
                canvas.blit(image, self.leo_rect())
        else:
            # Спрайтов нет: в корзинке просто одеяло — без временного манекена в полный рост.
            with logical_target(canvas, hires, pygame.Rect(x - 13, y - 14, 26, 10)) as surface:
                pygame.draw.ellipse(surface, BLANKET_COLOR, (x - 12, y - 13, 24, 9))
                pygame.draw.circle(surface, BASKET_INSIDE_COLOR, (x - 7, y - 10), 3)
        with logical_target(canvas, hires, BASKET_FRONT) as surface:
            pygame.draw.rect(surface, BASKET_COLOR, BASKET_FRONT, border_radius=3)
            pygame.draw.rect(surface, BASKET_DARK_COLOR, BASKET_FRONT, 1, border_radius=3)
            for k in range(BASKET_FRONT.left + 4, BASKET_FRONT.right - 2, 4):  # плетение
                pygame.draw.line(surface, BASKET_DARK_COLOR, (k, BASKET_FRONT.top + 2), (k, BASKET_FRONT.bottom - 3))
        # Сонные «з-з» над головой (голова у кадра слева): тихо покачиваются.
        bob = round(abs(math.sin(self.time * 1.5)) * 2)
        marks = pygame.Rect(x - 13, y - 33 - bob, 11, 10)
        with logical_target(canvas, hires, marks) as surface:
            for mx, my, size in ((marks.x, marks.y + 5, 3), (marks.x + 6, marks.y, 4)):
                zigzag = [(mx, my), (mx + size, my), (mx, my + size), (mx + size, my + size)]
                pygame.draw.lines(surface, SLEEP_MARK_COLOR, False, zigzag)
        if target is not None and target.kind == "leo":
            # Ромбик над корзинкой, как у Чучмека: сюда можно заглянуть.
            mx, my = x + 10, y - 26 - round(abs(math.sin(self.time * 4)) * 2)
            with logical_target(canvas, hires, pygame.Rect(mx - 4, my - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(mx, my - 3), (mx + 3, my), (mx, my + 3), (mx - 3, my)])

    def _draw_hud(self, canvas: pygame.Surface, hires: HiResLayer | None) -> None:
        middle = HUD_HEIGHT / 2
        bar = pygame.Rect(0, 0, WIDTH, HUD_HEIGHT)
        with logical_target(canvas, hires, bar) as surface:
            surface.fill(HUD_COLOR, bar)
            if hires is None:
                surface.blit(self._text("Центральная площадь", HUD_TEXT_COLOR), (4, 1))
                fragments = self._text(self.fragments_text(), HUD_ACCENT_COLOR)
                surface.blit(fragments, fragments.get_rect(topright=(WIDTH - 4, 1)))
        if hires is not None:
            hires.text("Центральная площадь", HUD_STYLE, (4, middle), anchor="midleft")
            hires.text(self.fragments_text(), FRAGMENTS_STYLE, (WIDTH - 4, middle), anchor="midright")

    def _draw_status(self, canvas: pygame.Surface, hires: HiResLayer | None) -> None:
        center = (WIDTH // 2, STATUS_TOP + (HEIGHT - STATUS_TOP) // 2)
        bar = pygame.Rect(0, STATUS_TOP, WIDTH, HEIGHT - STATUS_TOP)
        with logical_target(canvas, hires, bar) as surface:
            surface.fill(HUD_COLOR, bar)
            if hires is None:
                text = self._text(self.status_text(), HUD_TEXT_COLOR)
                surface.blit(text, text.get_rect(center=center))
        if hires is not None:
            hires.text(self.status_text(), HUD_STYLE, center, anchor="center")


@lru_cache(maxsize=1)
def _ground() -> pygame.Surface:
    """Земля площади: рисуется один раз и общая для всех площадей (её никто не меняет)."""
    shadows = [(TREE_SPECS["sushi"].cx + 5, 90, 33, 7), (TREE_SPECS["cakes"].cx + 5, 90, 33, 7), (TREE_SPECS["forms"].cx + 4, 72, 28, 5),
               (TABLE_CENTER[0] + 2, TABLE_CENTER[1] + 27, 44, 9)]
    page = render_ground((LEO_AREA, CHUCHMEK_AREA), shadows, HUD_COLOR)
    for prop in hub_scenery.props():
        if prop.flat:  # грибы, папоротники и цветы у земли: уменьшенные до холста, как и сама земля
            prop.piece.draw(page, None)
    return page


@lru_cache(maxsize=1)
def _backdrop() -> hub_scenery.Piece:
    """Подробный фон для слоя высокого разрешения: общая картинка, как и земля."""
    return hub_scenery.build_backdrop(_ground())
