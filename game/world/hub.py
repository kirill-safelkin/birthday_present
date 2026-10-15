"""Центральная площадь: первая управляемая локация, откуда Алиса заходит в три испытания.

Оформление временное — геометрия, дорожки и подписи; настоящий дизайн появится позже.
Используются существующие системы: Character (движение и анимации), CollisionMap
(границы и препятствия), DialogueController/DialogueBox (реплики), SceneManager (переходы).

Портал открывает сцену испытания (TRIAL_SCENES) через менеджер, если она
зарегистрирована; иначе Чучмек объясняет, что портал не готов. Фрагменты выдают сами
испытания через общий GameProgress, площадь их только показывает и, вернувшись из
испытания, сообщает итог.

Мозаика в центре площади собирает фрагменты: у каждого пройденного испытания — свой
символ в ней. Когда собраны все три, мозаика светится, и E рядом с ней открывает финал
(FINALE_SCENE). Сам по себе третий фрагмент финал не запускает — только игрок.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
from game.story.hub_dialogue import CHUCHMEK_TALK, PORTAL_NOT_READY, all_scripts
from game.world.character import Character
from game.world.collision import CollisionMap
from game.world.progress import TRIAL_NAMES, TRIALS, GameProgress

HUB_SCENE = "hub"  # имя площади в SceneManager
FINALE_SCENE = "finale"  # последняя страница сказки: её открывает мозаика при всех фрагментах
# Имена будущих сцен испытаний. Пока они не зарегистрированы, порталы закрыты.
TRIAL_SCENES = {trial_id: f"trial_{trial_id}" for trial_id in TRIALS}

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 32  # кадры 64×64 уменьшаются ровно вдвое ближайшим соседом
WALK_SPEED = 64  # логических пикселей в секунду
HUD_HEIGHT = 12  # верхняя полоса: название площади и фрагменты
STATUS_TOP = 168  # нижняя полоса: подсказки; персонажи до неё не доходят
# Где могут стоять ноги персонажа: между полосами интерфейса, и так, чтобы кадр шириной
# SPRITE_SIZE не вылезал за края экрана (ноги уже кадра на SPRITE_SIZE/2 − 6 с каждой стороны).
WALK_BOUNDS = pygame.Rect(10, 44, WIDTH - 20, STATUS_TOP - 4 - 44)
SPAWN = (160, 158)  # точка появления Алисы — внизу площади
TOAST_SECONDS = 3.0
TOAST_PRIORITY_SECONDS = 2.0  # столько свежее сообщение (например, итог испытания) важнее подсказки у цели
PORTAL_TOUCH = 6  # вплотную к порталу с любой стороны (по ногам Алисы) — тоже можно войти
MOSAIC_CENTER = (160, 106)  # мозаика в центре площади
MOSAIC_RADIUS = 12  # на таком расстоянии от центра (по ногам Алисы) с ней можно взаимодействовать
# Гнёзда фрагментов в мозаике: каждый — со стороны своего портала.
MOSAIC_SLOTS = {"sushi": (150, 108), "forms": (160, 98), "cakes": (170, 108)}


@dataclass(frozen=True)
class Portal:
    """Вход в испытание: сам портал (препятствие), точка, у которой с ним можно взаимодействовать,
    и табличка с названием."""

    id: str
    rect: pygame.Rect
    point: tuple[int, int]
    radius: int
    sign_center: tuple[int, int]
    color: config.Color
    glow: config.Color

    @property
    def name(self) -> str:
        return TRIAL_NAMES[self.id]


PORTALS = (
    Portal("sushi", pygame.Rect(8, 70, 30, 30), (48, 92), 16, (23, 62), (196, 72, 66), (250, 170, 150)),
    Portal("forms", pygame.Rect(144, 14, 32, 30), (160, 54), 18, (114, 22), (88, 110, 160), (176, 196, 236)),
    Portal("cakes", pygame.Rect(282, 70, 30, 30), (272, 92), 16, (297, 62), (214, 120, 170), (252, 196, 226)),
)
CHUCHMEK_POSITION = (214, 80)  # недалеко от центра, выше дорожки к тортам
CHUCHMEK_RADIUS = 24
CHUCHMEK_OBSTACLE = pygame.Rect(206, 74, 16, 7)
# Декорации: стволы деревьев и клумбы — препятствия в стороне от дорожек.
TREES = ((62, 58), (258, 58))
FLOWER_BEDS = (pygame.Rect(54, 138, 34, 12), pygame.Rect(232, 138, 34, 12))

GRASS_COLOR = (150, 186, 120)
GRASS_DARK_COLOR = (136, 172, 108)
PATH_COLOR = (222, 202, 160)
PATH_EDGE_COLOR = (196, 172, 128)
PLAZA_COLOR = (232, 216, 180)
MOSAIC_COLOR = (206, 178, 134)
SPAWN_COLOR = (246, 232, 196)
BED_COLOR = (124, 92, 66)
FLOWER_COLORS = ((232, 120, 140), (250, 214, 110), (180, 150, 230))
TREE_TRUNK_COLOR = (120, 88, 62)
TREE_LEAF_COLOR = (92, 140, 84)
HUD_COLOR = (44, 38, 58)
HUD_TEXT_COLOR = (240, 230, 206)
HUD_ACCENT_COLOR = (250, 206, 108)
SIGN_COLOR = (150, 110, 74)
SIGN_EDGE_COLOR = (98, 70, 48)
SIGN_TEXT_COLOR = (252, 240, 214)
PORTAL_INNER_COLOR = (54, 46, 72)
MARK_COLOR = (255, 236, 140)

# Надписи в разрешении окна (слой высокого разрешения); размер — в логических пикселях.
TEXT_SIZE = 8
HUD_STYLE = TextStyle(TEXT_SIZE, HUD_TEXT_COLOR, background=HUD_COLOR)  # полосы вверху и внизу
FRAGMENTS_STYLE = TextStyle(TEXT_SIZE, HUD_ACCENT_COLOR, background=HUD_COLOR)
SIGN_STYLE = TextStyle(TEXT_SIZE, SIGN_TEXT_COLOR)


@dataclass(frozen=True)
class Interaction:
    """С чем Алиса может взаимодействовать сейчас: портал испытания или Чучмек."""

    kind: str  # "portal", "chuchmek" или "mosaic"
    target: str  # идентификатор испытания, "chuchmek" или "finale"
    prompt: str


class HubScene(Scene):
    """Площадь: Алиса ходит, разговаривает с Чучмеком и подходит к порталам испытаний.

    Backspace (действие cancel) закрывает открытую реплику, а без реплики — возвращает
    к предыдущей сцене, если она есть (например, к экрану проверки).

    Со слоем высокого разрешения Алиса и Чучмек рисуются из исходных кадров 64×64, а надписи —
    шрифтом размера окна; площадь, порталы и деревья остаются пиксельными на холсте.
    """

    supports_hires = True

    def __init__(self, progress: GameProgress | None = None, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.progress = progress if progress is not None else GameProgress()
        root = Path(characters_dir)
        obstacles = [portal.rect for portal in PORTALS] + [CHUCHMEK_OBSTACLE] + list(FLOWER_BEDS)
        obstacles += [pygame.Rect(x - 3, y - 4, 6, 4) for x, y in TREES]
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
        self._background = _render_background()
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
            # У дорожки (point) — как раньше; а подойдя к порталу сбоку, сверху или снизу,
            # Алиса тоже может войти: портал отзывается, когда она стоит к нему вплотную.
            distance = math.dist((x, y), portal.point)
            touch = _distance_to_rect((x, y), portal.rect)
            if distance <= portal.radius or touch <= PORTAL_TOUCH:
                distance = min(distance, touch)
                done = " (пройдено)" if self.progress.is_completed(portal.id) else ""
                prompt = f"{portal.name}{done}   E — войти"
                candidates.append((distance, Interaction("portal", portal.id, prompt)))
        distance = math.dist((x, y), self._chuchmek_point())
        if distance <= CHUCHMEK_RADIUS:
            candidates.append((distance, Interaction("chuchmek", "chuchmek", "Чучмек   E — поговорить")))
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
            self._open_dialogue(CHUCHMEK_TALK)
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
        """Рисует площадь на холсте; со слоем hires персонажи и надписи уходят в него
        (см. game/graphics/hires.py), а порядок слоёв остаётся тем же."""
        surface.blit(self._background, (0, 0))
        target = self.nearby() if self.dialogue is None else None
        self._draw_mosaic(surface, target)
        # Всё, что стоит на площади, рисуется по высоте ног: ближние к игроку — поверх дальних.
        drawables = [
            (portal.rect.bottom, lambda p=portal: self._draw_portal(surface, p, target, hires)) for portal in PORTALS
        ]
        drawables += [(y, lambda t=(x, y): self._draw_tree(surface, t, hires)) for x, y in TREES]
        drawables.append((self.chuchmek.y, lambda: self._draw_chuchmek(surface, target, hires)))
        drawables.append((self.alice.y + 0.1, lambda: self.alice.draw(surface, hires)))
        for _, draw in sorted(drawables, key=lambda item: item[0]):
            draw()
        self._draw_hud(surface, hires)
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue, hires)
        else:
            self._draw_status(surface, hires)

    def _text(self, text: str, color: config.Color) -> pygame.Surface:
        key = (text, color)
        image = self._text_cache.get(key)
        if image is None:
            image = self._text_cache[key] = render_text(self._font, text, color)
        return image

    def plaque_rect(self, portal: Portal, hires: bool = False) -> pygame.Rect:
        """Табличка с названием портала: по размеру надписи пиксельным шрифтом или шрифтом окна."""
        if hires:
            width, height = self.text_metrics.size(portal.name)
            label = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        else:
            label = self._text(portal.name, SIGN_TEXT_COLOR).get_rect()
        label.center = portal.sign_center
        return label.inflate(6, 2)

    def _draw_portal(
        self, canvas: pygame.Surface, portal: Portal, target: Interaction | None, hires: HiResLayer | None
    ) -> None:
        plaque = self.plaque_rect(portal, hires is not None)
        # Портал с подсветкой, табличка и звёздочка у неё — вся графика портала.
        area = portal.rect.inflate(8, 8).union(plaque.inflate(10, 10))
        with logical_target(canvas, hires, area) as surface:
            rect = portal.rect
            near = target is not None and target.target == portal.id
            pygame.draw.rect(surface, portal.color, rect, border_radius=6)
            inner = rect.inflate(-8, -8)
            pygame.draw.rect(surface, PORTAL_INNER_COLOR, inner, border_radius=4)
            # Мерцание внутри портала: две полосы, бегущие сверху вниз.
            for k in range(2):
                y = inner.top + int((self.time * 10 + k * inner.height / 2) % inner.height)
                pygame.draw.line(surface, portal.glow, (inner.left + 2, y), (inner.right - 3, y))
            _draw_trial_icon(surface, portal.id, inner.center)
            if near:
                pulse = 1 + round(abs(math.sin(self.time * 5)))
                pygame.draw.rect(surface, MARK_COLOR, rect.inflate(2 + pulse * 2, 2 + pulse * 2), 1, border_radius=7)
            # Табличка с названием.
            pygame.draw.rect(surface, SIGN_COLOR, plaque)
            pygame.draw.rect(surface, SIGN_EDGE_COLOR, plaque, 1)
            if hires is None:
                label = self._text(portal.name, SIGN_TEXT_COLOR)
                surface.blit(label, label.get_rect(center=plaque.center))
            if self.progress.is_completed(portal.id):
                # Испытание пройдено: золотая звёздочка у таблички.
                x, y = plaque.right + 1, plaque.top
                if x + 3 > WIDTH:
                    x = plaque.left - 1
                pygame.draw.polygon(surface, HUD_ACCENT_COLOR, [(x, y - 3), (x + 1, y - 1), (x + 3, y), (x + 1, y + 1),
                                                                (x, y + 3), (x - 1, y + 1), (x - 3, y), (x - 1, y - 1)])
        if hires is not None:
            hires.text(portal.name, SIGN_STYLE, plaque.center, anchor="center")

    @staticmethod
    def _draw_tree(canvas: pygame.Surface, base: tuple[int, int], hires: HiResLayer | None) -> None:
        x, y = base
        with logical_target(canvas, hires, pygame.Rect(x - 10, y - 24, 21, 25)) as surface:
            _draw_tree(surface, base)

    def _draw_mosaic(self, surface: pygame.Surface, target: Interaction | None) -> None:
        """Символы собранных фрагментов в мозаике; при всех трёх — пульсирующее свечение."""
        for trial_id, center in MOSAIC_SLOTS.items():
            if self.progress.is_completed(trial_id):
                _draw_fragment(surface, trial_id, center)
        if self.progress.has_all_fragments:
            x, y = MOSAIC_CENTER
            pulse = abs(math.sin(self.time * 3))
            pygame.draw.circle(surface, MARK_COLOR, (x, y), 15 + round(pulse * 2), 1)
            pygame.draw.circle(surface, HUD_ACCENT_COLOR, (x, y), 12, 1)
            for k in range(4):  # искры бегут по кругу
                angle = self.time * 1.5 + k * math.pi / 2
                surface.set_at((x + round(math.cos(angle) * 20), y + round(math.sin(angle) * 20)), MARK_COLOR)
        if target is not None and target.kind == "mosaic":
            pygame.draw.circle(surface, MARK_COLOR, MOSAIC_CENTER, 22, 1)

    def _draw_chuchmek(self, canvas: pygame.Surface, target: Interaction | None, hires: HiResLayer | None) -> None:
        self.chuchmek.draw(canvas, hires)
        if target is not None and target.kind == "chuchmek":
            # Ромбик над шляпкой: с Чучмеком можно поговорить.
            x, y = self.chuchmek.rect.centerx, self.chuchmek.rect.top - 4 - round(abs(math.sin(self.time * 4)) * 2)
            with logical_target(canvas, hires, pygame.Rect(x - 4, y - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

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


def _draw_trial_icon(surface: pygame.Surface, trial_id: str, center: tuple[int, int]) -> None:
    """Простая геометрическая эмблема испытания внутри портала (не картинка и не эмодзи)."""
    x, y = center
    if trial_id == "sushi":  # ролл: рис, водоросль, начинка
        pygame.draw.circle(surface, (250, 248, 240), (x, y), 6)
        pygame.draw.circle(surface, (40, 60, 48), (x, y), 6, 1)
        pygame.draw.circle(surface, (236, 120, 96), (x, y), 2)
    elif trial_id == "forms":  # стопка бумаг со строчками
        for offset in (2, 0):
            pygame.draw.rect(surface, (244, 244, 236), (x - 5 + offset, y - 7 + offset, 10, 13))
            pygame.draw.rect(surface, (120, 130, 150), (x - 5 + offset, y - 7 + offset, 10, 13), 1)
        for row in range(3):
            pygame.draw.line(surface, (120, 130, 150), (x - 2, y - 2 + row * 3), (x + 4, y - 2 + row * 3))
    else:  # торт: два яруса и вишенка
        pygame.draw.rect(surface, (248, 214, 228), (x - 7, y, 14, 6))
        pygame.draw.rect(surface, (252, 238, 214), (x - 5, y - 5, 10, 5))
        pygame.draw.circle(surface, (210, 40, 60), (x, y - 7), 2)


def _distance_to_rect(point: tuple[float, float], rect: pygame.Rect) -> float:
    x = min(max(point[0], rect.left), rect.right)
    y = min(max(point[1], rect.top), rect.bottom)
    return math.dist(point, (x, y))


def _draw_fragment(surface: pygame.Surface, trial_id: str, center: tuple[int, int]) -> None:
    """Маленький символ фрагмента в мозаике: ролл, документ с печатью, торт."""
    x, y = center
    if trial_id == "sushi":
        pygame.draw.circle(surface, (40, 60, 48), (x, y), 3)
        pygame.draw.circle(surface, (236, 120, 96), (x, y), 1)
    elif trial_id == "forms":
        pygame.draw.rect(surface, (244, 244, 236), (x - 2, y - 3, 5, 6))
        surface.set_at((x + 1, y + 1), (196, 52, 60))
    else:
        pygame.draw.rect(surface, (248, 214, 228), (x - 3, y - 1, 7, 3))
        surface.set_at((x, y - 2), (210, 40, 60))


def _draw_tree(surface: pygame.Surface, base: tuple[int, int]) -> None:
    x, y = base
    pygame.draw.rect(surface, TREE_TRUNK_COLOR, (x - 2, y - 8, 4, 8))
    pygame.draw.circle(surface, TREE_LEAF_COLOR, (x, y - 14), 9)
    pygame.draw.circle(surface, GRASS_DARK_COLOR, (x - 3, y - 17), 3)


def _render_background() -> pygame.Surface:
    """Трава, дорожки к трём порталам и к точке появления, мозаика в центре, клумбы."""
    page = pygame.Surface(config.LOGICAL_SIZE)
    page.fill(GRASS_COLOR)
    for x in range(4, WIDTH, 16):  # редкие тёмные травинки, чтобы было видно движение
        for y in range(18 + (x // 16) % 2 * 8, STATUS_TOP, 16):
            page.fill(GRASS_DARK_COLOR, (x, y, 2, 1))
    paths = [
        pygame.Rect(38, 86, 104, 14),  # к суши
        pygame.Rect(178, 86, 104, 14),  # к тортам
        pygame.Rect(152, 44, 16, 50),  # к формулярам
        pygame.Rect(152, 120, 16, 44),  # к точке появления
    ]
    for path in paths:
        pygame.draw.rect(page, PATH_COLOR, path)
        pygame.draw.rect(page, PATH_EDGE_COLOR, path, 1)
    pygame.draw.circle(page, PLAZA_COLOR, (160, 106), 28)
    pygame.draw.circle(page, PATH_EDGE_COLOR, (160, 106), 28, 1)
    pygame.draw.circle(page, MOSAIC_COLOR, (160, 106), 10, 2)
    for angle in range(0, 360, 45):
        dx, dy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        page.fill(MOSAIC_COLOR, (160 + round(dx * 18) - 1, 106 + round(dy * 18) - 1, 3, 3))
    pygame.draw.ellipse(page, SPAWN_COLOR, (148, 151, 24, 10))
    pygame.draw.ellipse(page, PATH_EDGE_COLOR, (148, 151, 24, 10), 1)
    for bed in FLOWER_BEDS:
        pygame.draw.rect(page, BED_COLOR, bed, border_radius=3)
        for index, x in enumerate(range(bed.left + 4, bed.right - 2, 6)):
            page.fill(FLOWER_COLORS[index % 3], (x, bed.top + 3 + index % 2 * 4, 3, 3))
    return page
