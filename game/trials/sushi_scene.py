"""Испытание суши: кухня, где Алиса собирает три заказа под присмотром кота-повара.

Логика заказов — в game/trials/sushi_orders.py (без Pygame), реплики — в
game/story/sushi_dialogue.py. Здесь только сцена: движение Алисы (Character и
CollisionMap, как на площади), станции ингредиентов, тарелка, повар и интерфейс.

Этапы: вступление → сбор заказа → реакция повара → … → финальная реплика → награда.
Фрагмент (GameProgress.complete("sushi")) выдаётся только после финальной реплики;
отмена (Backspace) в любой момент до этого возвращает на площадь без награды.
Оформление временное: кухня нарисована геометрией. Тарелка и готовые блюда — в
game/trials/sushi_dishes.py: пока заказ не собран, на тарелке отдельные ингредиенты, а когда
SushiOrders.order_complete — одно готовое блюдо этого заказа.

Со слоем высокого разрешения (game/graphics/hires.py) Алиса и кот-повар рисуются из исходных
кадров 64×64, а надписи — шрифтом размера окна; кухня и значки остаются пиксельными.
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
from game.graphics.placeholder import placeholder_animations
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, try_load_character_sprites
from game.story.sushi_dialogue import (
    CHEF_DISAPPROVING_POSE,
    CHEF_IDLE_POSE,
    CHEF_POSES,
    FINAL,
    INTRO,
    REACTIONS,
    all_scripts,
    chef_tip,
)
from game.trials.sushi_dishes import (
    FINISH_EFFECT_SECONDS,
    draw_dish,
    draw_food_shadow,
    draw_plate,
    draw_sparks,
    plate_rect,
)
from game.trials.sushi_orders import INGREDIENT_NAMES, INGREDIENTS, PlateResult, SushiOrders, TakeResult
from game.world.character import Character
from game.world.collision import CollisionMap
from game.world.hub import TRIAL_SCENES
from game.world.progress import GameProgress

SUSHI_SCENE = TRIAL_SCENES["sushi"]  # «trial_sushi» — имя, которое ищет портал площади
TRIAL_ID = "sushi"

# Этапы испытания.
INTRO_PHASE = "intro"
COOKING = "cooking"
REACTION = "reaction"
FINAL_PHASE = "final"
DONE = "done"

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 32  # как на площади
WALK_SPEED = 64
HUD_HEIGHT = 24  # две строки: заказ и его ингредиенты
STATUS_TOP = 168
COUNTER = pygame.Rect(0, HUD_HEIGHT, WIDTH, 26)  # задняя стойка со станциями ингредиентов
# Ноги Алисы: между стойкой и барной стойкой посетителей. Нижняя граница выше любого
# окна реплики, поэтому окно никогда не закрывает персонажей.
WALK_BOUNDS = pygame.Rect(10, COUNTER.bottom, WIDTH - 20, 108 - COUNTER.bottom)
BAR = pygame.Rect(0, 112, WIDTH, 16)  # барная стойка для посетителей (декорация)
TABLE = pygame.Rect(132, 76, 56, 14)  # рабочий стол с тарелкой
TABLE_REACH = 9  # насколько близко к столу нужно подойти
STATION_Y = 60  # точка взаимодействия со станцией — у края стойки
STATION_REACH = 12
STATION_XS = (36, 84, 132, 180, 228)
CHEF_POSITION = (286, 96)
CHEF_REACH = 20
CHEF_OBSTACLE = pygame.Rect(278, 90, 16, 6)
SPAWN = (40, 100)  # у входа на кухню, вдали от станций
TOAST_SECONDS = 3.0
TOAST_PRIORITY_SECONDS = 1.5  # столько свежее сообщение показывается вместо подсказки у цели
DISAPPROVAL_SECONDS = 1.5

WALL_COLOR = (230, 214, 186)
WALL_LINE_COLOR = (214, 194, 162)
COUNTER_TOP_COLOR = (196, 150, 104)
COUNTER_FRONT_COLOR = (150, 104, 70)
FLOOR_COLORS = ((222, 214, 196), (210, 200, 180))
BAR_COLOR = (124, 82, 56)
BAR_TOP_COLOR = (170, 122, 82)
STOOL_COLOR = (92, 64, 48)
TABLE_COLOR = (186, 140, 96)
TABLE_EDGE_COLOR = (130, 92, 62)
LABEL_COLOR = (252, 240, 214)
HUD_COLOR = (44, 38, 58)
HUD_TEXT_COLOR = (240, 230, 206)
HUD_ACCENT_COLOR = (250, 206, 108)
DONE_COLOR = (140, 220, 150)
TODO_COLOR = (200, 196, 214)
MARK_COLOR = (255, 236, 140)
RED_ACCENT = (200, 60, 60)

# Надписи в разрешении окна (слой высокого разрешения); размер — в логических пикселях, как на площади.
TEXT_SIZE = 8
HUD_STYLE = TextStyle(TEXT_SIZE, HUD_TEXT_COLOR, background=HUD_COLOR)  # полосы вверху и внизу
ORDER_STYLE = TextStyle(TEXT_SIZE, HUD_ACCENT_COLOR, background=HUD_COLOR)
DONE_STYLE = TextStyle(TEXT_SIZE, DONE_COLOR, background=HUD_COLOR)
TODO_STYLE = TextStyle(TEXT_SIZE, TODO_COLOR, background=HUD_COLOR)
LABEL_STYLE = TextStyle(TEXT_SIZE, LABEL_COLOR)  # на стойке под подписью — линия, фон не однотонный
HUD_ROWS = (6.5, 17.5)  # середины двух строк верхней полосы
LABEL_MIDDLE = COUNTER.top + 21  # середина подписи станции на передней стенке стойки
# Где рисуется стол с тарелкой: подсветка, сияние собранного заказа и тень столешницы.
# Над столом — место для вспышки над готовым блюдом.
TABLE_AREA = TABLE.inflate(6, 8).union(TABLE.move(0, 2)).union(
    pygame.Rect(TABLE.centerx - 16, TABLE.centery - 17, 32, 16))


@dataclass(frozen=True)
class Station:
    ingredient: str
    x: int

    @property
    def point(self) -> tuple[int, int]:
        return self.x, STATION_Y

    @property
    def name(self) -> str:
        return INGREDIENT_NAMES[self.ingredient]


STATIONS = tuple(Station(ingredient, x) for ingredient, x in zip(INGREDIENTS, STATION_XS))


@dataclass(frozen=True)
class Target:
    """С чем Алиса может взаимодействовать сейчас: станция, тарелка или повар."""

    kind: str  # "station", "plate" или "chef"
    ingredient: str | None = None


def _distance_to_rect(point: tuple[float, float], rect: pygame.Rect) -> float:
    x = min(max(point[0], rect.left), rect.right)
    y = min(max(point[1], rect.top), rect.bottom)
    return math.dist(point, (x, y))


class SushiTrialScene(Scene):
    """Кухня кота-повара. Открывается порталом «Суши» на площади и закрывается возвратом на неё."""

    supports_hires = True

    def __init__(self, progress: GameProgress | None = None, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.progress = progress if progress is not None else GameProgress()
        self.orders = SushiOrders()
        root = Path(characters_dir)
        obstacles = [COUNTER, TABLE, CHEF_OBSTACLE]
        self.collision = CollisionMap(WALK_BOUNDS, obstacles)
        alice_sprites = try_load_character_sprites(root / "alice")
        self.alice = Character(
            "Алиса",
            alice_sprites.animation_set(SPRITE_SIZE) if alice_sprites else None,
            position=SPAWN,
            speed=WALK_SPEED,
            direction=Direction.RIGHT,
        )
        self.alice.collider = self.collision.move
        self.chef_sprites = try_load_character_sprites(root / "cat_chef")
        self.chef_pose = CHEF_IDLE_POSE
        self._chef_frames: dict[str, tuple[pygame.Surface, pygame.Surface]] = {}  # поза → (исходник, на холсте)

        self.box = DialogueBox()
        for script in all_scripts():
            self.box.check_fits(script)
        self.phase = INTRO_PHASE
        self.dialogue: DialogueController | None = None
        self.reward_given = False  # True, если именно это прохождение добавило фрагмент
        self.completed = False
        self.toast = ""
        self._toast_time = 0.0
        self._disapproval_time = 0.0
        self._dish_age: float | None = None  # сколько секунд назад заказ собран (None — не собран)
        self.time = 0.0
        self._font = load_font(9)
        self._text_cache: dict[tuple[str, config.Color], pygame.Surface] = {}
        self._fonts = TextFonts()
        self.text_metrics = self._fonts.metrics(HUD_STYLE)  # все надписи кухни одного размера
        self._background = self._render_background()
        self._background_plain = self._render_background(labels=False)  # подписи станций рисует слой окна
        self._open_dialogue(INTRO)

    # --- Состояние ---

    def nearby(self) -> Target | None:
        """Ближайшее, с чем можно взаимодействовать из точки под ногами Алисы."""
        feet = (self.alice.x, self.alice.y)
        candidates: list[tuple[float, Target]] = []
        for station in STATIONS:
            distance = math.dist(feet, station.point)
            if distance <= STATION_REACH:
                candidates.append((distance, Target("station", station.ingredient)))
        distance = _distance_to_rect(feet, TABLE)
        if distance <= TABLE_REACH:
            candidates.append((distance, Target("plate")))
        distance = math.dist(feet, (CHEF_POSITION[0], CHEF_POSITION[1] + 4))
        if distance <= CHEF_REACH:
            candidates.append((distance, Target("chef")))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def order_text(self) -> str:
        recipe = self.orders.current
        if recipe is None:
            return "Все заказы готовы"
        return f"Заказ {self.orders.index + 1}/{len(self.orders.recipes)}: {recipe.name}"

    def plate_dish(self) -> str | None:
        """Какое готовое блюдо лежит на тарелке: id рецепта, если модель заказа подтвердила
        сборку (по идентификаторам ингредиентов), иначе None — тогда видны отдельные ингредиенты."""
        recipe = self.orders.current
        return recipe.id if recipe is not None and self.orders.order_complete else None

    def held_text(self) -> str:
        held = self.orders.held
        return f"В руках: {INGREDIENT_NAMES[held] if held else '—'}"

    def prompt(self) -> str | None:
        target = self.nearby() if self.phase == COOKING and self.dialogue is None else None
        if target is None:
            return None
        held = self.orders.held
        if target.kind == "station":
            name = INGREDIENT_NAMES[target.ingredient]
            if held == target.ingredient:
                return f"{name}   E — вернуть на место"
            return f"{name}   E — {'взять' if held is None else 'поменять'}"
        if target.kind == "plate":
            return "Тарелка   E — положить" if held else "Тарелка   сначала возьми ингредиент"
        return "Кот-повар   E — спросить про заказ"

    def status_text(self) -> str:
        """Нижняя полоса: свежее сообщение (например, об ошибке), подсказка у цели или управление."""
        if self.toast and TOAST_SECONDS - self._toast_time < TOAST_PRIORITY_SECONDS:
            return self.toast
        return self.prompt() or self.toast or "Стрелки/WASD — идти   E — действие   Backspace — уйти"

    # --- Управление ---

    def handle_event(self, event: pygame.event.Event) -> None:
        actions = actions_for(event) if event.type == pygame.KEYDOWN else frozenset()
        if Action.CANCEL in actions and self.phase != DONE:
            self.finish()  # отказ от испытания: назад на площадь без награды
            return
        if self.dialogue is not None:
            if Action.INTERACT in actions and Action.CONFIRM not in actions:
                self.dialogue.confirm()  # как на площади: E продолжает реплику
            else:
                self.dialogue.handle_event(event)
            self._sync_dialogue()
            if self.dialogue.is_finished:
                self._dialogue_finished()
            return
        if self.phase != COOKING:
            return
        self.alice.handle_event(event)
        if Action.INTERACT in actions:
            self.interact()

    def interact(self) -> bool:
        """E или Enter во время готовки. True, если рядом была цель."""
        target = self.nearby()
        if self.phase != COOKING or target is None:
            return False
        if target.kind == "station":
            self._use_station(target.ingredient)
        elif target.kind == "plate":
            self._use_plate()
        else:
            recipe = self.orders.current
            missing = [INGREDIENT_NAMES[item].lower() for item in self.orders.missing]
            self._open_dialogue(chef_tip(recipe.name if recipe else "", missing))
        return True

    def _use_station(self, ingredient: str) -> None:
        previous = self.orders.held
        result = self.orders.take(ingredient)
        name = INGREDIENT_NAMES[ingredient]
        if result is TakeResult.TAKEN:
            self._show_toast(f"Взяла: {name}")
        elif result is TakeResult.RETURNED:
            self._show_toast(f"Вернула на место: {name}")
        elif result is TakeResult.SWAPPED:
            self._show_toast(f"Вернула на место: {INGREDIENT_NAMES[previous]}. Взяла: {name}")

    def _use_plate(self) -> None:
        held = self.orders.held
        result = self.orders.place()
        name = INGREDIENT_NAMES[held] if held else ""
        if result is PlateResult.EMPTY_HANDS:
            self._show_toast("Руки пусты — сначала возьми ингредиент")
        elif result is PlateResult.ADDED:
            self._show_toast(f"На тарелке: {name}")
        elif result in (PlateResult.WRONG, PlateResult.DUPLICATE):
            # Ничего не испорчено: ингредиент остаётся в руках, его можно вернуть или поменять.
            reason = "не для этого заказа" if result is PlateResult.WRONG else "уже на тарелке"
            self._show_toast(f"{name}: {reason} — верни на место")
            self.chef_pose = CHEF_DISAPPROVING_POSE
            self._disapproval_time = DISAPPROVAL_SECONDS
        elif result is PlateResult.ORDER_COMPLETE:
            self.phase = REACTION
            self._dish_age = 0.0  # вспышка над готовым блюдом; повторно её ничто не запускает
            self._show_toast(f"На тарелке: {name}")
            self._open_dialogue(REACTIONS[self.orders.index])

    def _open_dialogue(self, script: DialogueScript) -> None:
        self.alice.release_controls()  # во время реплик Алиса стоит
        self.dialogue = DialogueController(script)
        self._sync_dialogue()

    def _sync_dialogue(self) -> None:
        node = self.dialogue.node if self.dialogue is not None else None
        if node is not None and node.id in CHEF_POSES:
            self.chef_pose = CHEF_POSES[node.id]

    def _dialogue_finished(self) -> None:
        """Реплика закрыта: следующий этап испытания."""
        self.dialogue = None
        self.chef_pose = CHEF_IDLE_POSE
        if self.phase == INTRO_PHASE:
            self.phase = COOKING
        elif self.phase == REACTION:
            self.orders.next_order()
            self._dish_age = None
            if self.orders.all_done:
                self.phase = FINAL_PHASE
                self._open_dialogue(FINAL)
            else:
                self.phase = COOKING
                self._show_toast(f"Новый заказ: {self.orders.current.name}")
        elif self.phase == FINAL_PHASE:
            self._complete()

    def _complete(self) -> None:
        """Финальная реплика сказана: фрагмент (без повторов — это решает GameProgress) и назад."""
        self.phase = DONE
        self.completed = True
        self.reward_given = self.progress.complete(TRIAL_ID)
        self.finish()

    def _show_toast(self, text: str) -> None:
        self.toast = text
        self._toast_time = TOAST_SECONDS

    def update(self, dt: float) -> None:
        self.time += dt
        if self.dialogue is not None:
            self.dialogue.update(dt)
        self.alice.update(dt)
        if self._dish_age is not None:
            self._dish_age += dt
        if self._toast_time > 0:
            self._toast_time -= dt
            if self._toast_time <= 0:
                self.toast = ""
        if self._disapproval_time > 0:
            self._disapproval_time -= dt
            if self._disapproval_time <= 0 and self.chef_pose == CHEF_DISAPPROVING_POSE:
                self.chef_pose = CHEF_IDLE_POSE

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рисует кухню на холсте; со слоем hires персонажи и надписи уходят в него
        (см. game/graphics/hires.py), а порядок слоёв остаётся тем же."""
        surface.blit(self._background if hires is None else self._background_plain, (0, 0))
        target = self.nearby() if self.phase == COOKING and self.dialogue is None else None
        for station in STATIONS:
            if target is not None and target.kind == "station" and target.ingredient == station.ingredient:
                rect = pygame.Rect(0, 0, 22, 16)
                rect.center = (station.x, COUNTER.top + 9)
                pygame.draw.rect(surface, MARK_COLOR, rect, 1)
            if hires is not None:  # подпись на стойке — под персонажами, как часть фона
                hires.text(station.name, LABEL_STYLE, (station.x, LABEL_MIDDLE), anchor="center")
        drawables = [
            (TABLE.bottom, lambda: self._draw_table(surface, target is not None and target.kind == "plate", hires)),
            (CHEF_POSITION[1], lambda: self._draw_chef(surface, target is not None and target.kind == "chef", hires)),
            (self.alice.y + 0.1, lambda: self._draw_alice(surface, hires)),
        ]
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

    def held_icon_center(self) -> tuple[int, int]:
        """Где рисуется значок того, что в руках: над головой Алисы, а у самой стойки, где
        сверху уже полоса интерфейса, — сбоку от головы."""
        rect = self.alice.rect
        if rect.top - 10 >= HUD_HEIGHT:
            return rect.centerx, rect.top - 5
        if rect.right + 8 <= WIDTH:
            return rect.right + 2, rect.top + 8
        return rect.left - 2, rect.top + 8  # у правого края — слева от головы

    def _draw_alice(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        self.alice.draw(canvas, hires)
        if self.orders.held is not None:
            # Что в руках — видно значком (не текстом: персонажа ничего не закрывает).
            x, y = self.held_icon_center()
            with logical_target(canvas, hires, pygame.Rect(x - 8, y - 9, 17, 17)) as surface:
                draw_ingredient(surface, self.orders.held, (x, y - round(abs(math.sin(self.time * 4)))))

    def _draw_table(self, canvas: pygame.Surface, highlighted: bool, hires: HiResLayer | None = None) -> None:
        with logical_target(canvas, hires, TABLE_AREA) as surface:
            self._draw_table_on(surface, highlighted)

    def _draw_table_on(self, surface: pygame.Surface, highlighted: bool) -> None:
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, TABLE.move(0, 2), border_radius=2)
        pygame.draw.rect(surface, TABLE_COLOR, TABLE, border_radius=2)
        plate = plate_rect(TABLE)
        draw_plate(surface, plate)
        if self.orders.order_complete:  # заказ собран: тарелка сияет
            glow = plate.inflate(6 + round(abs(math.sin(self.time * 6)) * 2), 6)
            pygame.draw.ellipse(surface, MARK_COLOR, glow, 1)
        dish = self.plate_dish()
        if dish is not None:
            draw_dish(surface, dish, plate.center)
            if self._dish_age is not None:
                draw_sparks(surface, plate.center, self._dish_age / FINISH_EFFECT_SECONDS)
        else:
            items = self.orders.plate
            for index, item in enumerate(items):
                x = round(plate.centerx + (index - (len(items) - 1) / 2) * 8)
                y = plate.centery - 2
                draw_food_shadow(surface, pygame.Rect(x - 5, y - 1, 10, 5))
                draw_ingredient(surface, item, (x, y), small=True)
        if highlighted:
            pygame.draw.rect(surface, MARK_COLOR, TABLE.inflate(4, 6), 1, border_radius=3)

    def _draw_chef(self, canvas: pygame.Surface, highlighted: bool, hires: HiResLayer | None = None) -> None:
        source, image = self._chef_frame()
        rect = image.get_rect(midbottom=CHEF_POSITION)
        if hires is not None:
            hires.sprite(source, rect)  # исходный кадр на том же месте и того же размера
        else:
            canvas.blit(image, rect)
        if highlighted:
            x, y = rect.centerx, rect.top - 4
            with logical_target(canvas, hires, pygame.Rect(x - 4, y - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

    def _chef_image(self) -> pygame.Surface:
        """Поза повара из манифеста cat_chef, уменьшенная ближайшим соседом; без отражения."""
        return self._chef_frame()[1]

    def _chef_frame(self) -> tuple[pygame.Surface, pygame.Surface]:
        """Поза повара: исходный кадр манифеста cat_chef (без отражения) и он же на холсте."""
        pose = self.chef_pose
        if pose not in self._chef_frames:
            sprites: CharacterSprites | None = self.chef_sprites
            if sprites is None:
                source = image = placeholder_animations().default.frames[0]
            else:
                try:
                    source = sprites.frame(pose).image
                except KeyError:
                    source = sprites.frames[0].image
                image = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
            self._chef_frames[pose] = (source, image)
        return self._chef_frames[pose]

    def hud_items(self, hires: bool = False) -> list[tuple[str, bool, int, int]]:
        """Вторая строка интерфейса: (ингредиент, лежит ли на тарелке, x подписи, x галочки).

        Подписи меряются тем шрифтом, которым будут нарисованы: пиксельным или шрифтом окна."""
        recipe = self.orders.current
        if recipe is None:
            return []
        items = []
        x = 4
        for ingredient in recipe.ingredients:
            done = ingredient in self.orders.plate
            name = INGREDIENT_NAMES[ingredient]
            if hires:
                width = math.ceil(self.text_metrics.width(name))
            else:
                width = self._text(name, DONE_COLOR if done else TODO_COLOR).get_width()
            items.append((ingredient, done, x + 10, x + 10 + width))
            x += 10 + width + 12
        return items

    def _draw_hud(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        bar = pygame.Rect(0, 0, WIDTH, HUD_HEIGHT)
        items = self.hud_items(hires is not None)
        with logical_target(canvas, hires, bar) as surface:
            surface.fill(HUD_COLOR, bar)
            if hires is None:
                surface.blit(self._text(self.order_text(), HUD_ACCENT_COLOR), (4, 1))
                held = self._text(self.held_text(), HUD_TEXT_COLOR)
                surface.blit(held, held.get_rect(topright=(WIDTH - 4, 1)))
            for ingredient, done, label_x, check_x in items:
                draw_ingredient(surface, ingredient, (label_x - 6, 17), small=True)
                if hires is None:
                    label = self._text(INGREDIENT_NAMES[ingredient], DONE_COLOR if done else TODO_COLOR)
                    surface.blit(label, (label_x, 12))
                if done:  # галочка из двух линий
                    x = check_x
                    pygame.draw.lines(surface, DONE_COLOR, False, [(x + 1, 17), (x + 3, 19), (x + 7, 14)])
        if hires is not None:
            hires.text(self.order_text(), ORDER_STYLE, (4, HUD_ROWS[0]), anchor="midleft")
            hires.text(self.held_text(), HUD_STYLE, (WIDTH - 4, HUD_ROWS[0]), anchor="midright")
            for ingredient, done, label_x, _ in items:
                style = DONE_STYLE if done else TODO_STYLE
                hires.text(INGREDIENT_NAMES[ingredient], style, (label_x, HUD_ROWS[1]), anchor="midleft")

    def _draw_status(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        center = (WIDTH // 2, STATUS_TOP + (HEIGHT - STATUS_TOP) // 2)
        bar = pygame.Rect(0, STATUS_TOP, WIDTH, HEIGHT - STATUS_TOP)
        with logical_target(canvas, hires, bar) as surface:
            surface.fill(HUD_COLOR, bar)
            if hires is None:
                text = self._text(self.status_text(), HUD_TEXT_COLOR)
                surface.blit(text, text.get_rect(center=center))
        if hires is not None:
            hires.text(self.status_text(), HUD_STYLE, center, anchor="center")

    def _render_background(self, labels: bool = True) -> pygame.Surface:
        """Стена, задняя стойка со станциями, пол, барная стойка и табуреты.

        labels=False — без подписей станций: их рисует слой высокого разрешения."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        for row, y in enumerate(range(COUNTER.bottom, BAR.top, 8)):  # плитка на полу
            for column, x in enumerate(range(0, WIDTH, 8)):
                page.fill(FLOOR_COLORS[(row + column) % 2], (x, y, 8, 8))
        page.fill(WALL_COLOR, (0, HUD_HEIGHT, WIDTH, 4))
        pygame.draw.rect(page, COUNTER_FRONT_COLOR, COUNTER)
        pygame.draw.rect(page, COUNTER_TOP_COLOR, (COUNTER.left, COUNTER.top, COUNTER.width, 16))
        pygame.draw.line(page, WALL_LINE_COLOR, (0, COUNTER.top + 16), (WIDTH, COUNTER.top + 16))
        for station in STATIONS:
            bowl = pygame.Rect(0, 0, 20, 10)
            bowl.center = (station.x, COUNTER.top + 9)
            pygame.draw.ellipse(page, (236, 228, 214), bowl)
            pygame.draw.ellipse(page, (150, 130, 110), bowl, 1)
            draw_ingredient(page, station.ingredient, (station.x, COUNTER.top + 8))
            if labels:
                label = render_text(self._font, station.name, LABEL_COLOR)
                page.blit(label, label.get_rect(midtop=(station.x, COUNTER.top + 16)))
        # Рисоварка и подставка для ножей — декорации на стойке справа.
        pygame.draw.rect(page, (236, 236, 240), (266, COUNTER.top + 2, 20, 13), border_radius=4)
        pygame.draw.rect(page, (120, 120, 130), (266, COUNTER.top + 2, 20, 13), 1, border_radius=4)
        pygame.draw.circle(page, RED_ACCENT, (276, COUNTER.top + 8), 2)
        pygame.draw.rect(page, (90, 64, 48), (296, COUNTER.top + 4, 12, 11))
        for k in range(3):
            pygame.draw.line(page, (200, 204, 210), (298 + k * 4, COUNTER.top + 1), (298 + k * 4, COUNTER.top + 5))
        # Барная стойка для посетителей и табуреты под ней.
        pygame.draw.rect(page, BAR_COLOR, BAR)
        pygame.draw.rect(page, BAR_TOP_COLOR, (BAR.left, BAR.top, BAR.width, 4))
        page.fill(FLOOR_COLORS[1], (0, BAR.bottom, WIDTH, STATUS_TOP - BAR.bottom))
        for x in range(30, WIDTH, 44):
            pygame.draw.ellipse(page, STOOL_COLOR, (x - 8, BAR.bottom + 8, 16, 7))
            pygame.draw.rect(page, STOOL_COLOR, (x - 1, BAR.bottom + 14, 3, 14))
        for x in (60, 160, 260):  # соевый соус на стойке
            pygame.draw.rect(page, (60, 34, 30), (x, BAR.top - 4, 4, 6))
            pygame.draw.rect(page, RED_ACCENT, (x, BAR.top - 5, 4, 2))
        return page


def draw_ingredient(surface: pygame.Surface, ingredient: str, center: tuple[int, int], small: bool = False) -> None:
    """Геометрический значок ингредиента (не картинка и не эмодзи)."""
    x, y = center
    k = 0.7 if small else 1.0

    def r(value: float) -> int:
        return max(1, round(value * k))

    if ingredient == "rice":  # горка риса
        pygame.draw.ellipse(surface, (250, 250, 246), (x - r(6), y - r(3), r(12), r(7)))
        for dx in (-2, 1, 3):
            surface.set_at((x + round(dx * k), y - 1), (210, 210, 200))
    elif ingredient == "salmon":  # кусок лосося с белыми прожилками
        rect = pygame.Rect(x - r(6), y - r(3), r(12), r(6))
        pygame.draw.rect(surface, (244, 128, 88), rect, border_radius=2)
        for dx in (-2, 2):
            stripe_x = x + round(dx * k)
            pygame.draw.line(surface, (255, 214, 190), (stripe_x, rect.top + 1), (stripe_x + 1, rect.bottom - 2))
    elif ingredient == "nori":  # лист нори
        pygame.draw.rect(surface, (34, 64, 44), (x - r(5), y - r(4), r(10), r(8)))
        pygame.draw.rect(surface, (64, 100, 70), (x - r(5), y - r(4), r(10), r(8)), 1)
    elif ingredient == "cucumber":  # срез огурца
        pygame.draw.circle(surface, (70, 150, 70), (x, y), r(5))
        pygame.draw.circle(surface, (196, 236, 170), (x, y), r(3))
    else:  # половинка авокадо с косточкой
        pygame.draw.ellipse(surface, (70, 120, 50), (x - r(5), y - r(5), r(10), r(11)))
        pygame.draw.ellipse(surface, (196, 220, 120), (x - r(4), y - r(4), r(8), r(9)))
        pygame.draw.circle(surface, (130, 84, 50), (x, y + round(k)), r(2))
