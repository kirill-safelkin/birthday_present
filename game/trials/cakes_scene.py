"""Испытание тортов: перевёрнутая кондитерская Тортища и сбежавшая клубника.

Две части в одной сцене:
1. Рецепт на доске перепутан задом наперёд — этапы переставляются стрелками и E/Enter
   (логика — game/trials/cakes_puzzle.py, без Pygame).
2. После правильного рецепта клубника сбегает в кладовую — захламлённую комнату с книжными
   стеллажами, расставленными вразброс (раскладка, столкновения и поиск пути —
   game/trials/cakes_maze.py, своя для каждой погони). Клубника носится по ней со скоростью
   Алисы, иногда останавливается сказать что-нибудь абсурдное (облачко над ней) и снова
   убегает (game/trials/strawberry_chase.py). Алиса ходит как на площади и ловит её E/Enter,
   только подойдя вплотную (CATCH_REACH) и не через стеллаж.
Реплики — в game/story/cakes_dialogue.py.

Этапы: вступление → рецепт (после первой перестановки — разговор с Тортищем) → реакция на
успех → побег клубники → погоня в кладовой → поимка (реакция уже у рабочего стола) →
финальный диалог → награда. Фрагмент (GameProgress.complete("cakes")) выдаётся только после
финальной реплики; отмена (Backspace) в любой момент до этого возвращает на площадь без награды.
Оформление временное: кондитерская и кладовая нарисованы геометрией.

Тортище (манифест great_cake) — хозяин кондитерской и единственный ведущий испытания: стоит на
своей подставке над дверью кладовой, крупнее Алисы, ведёт все главные разговоры (вступление,
шутки на неверный рецепт, успех, побег и поимка клубники, финал) и меняет позы
(CharacterSprites.pose) по репликам. После первой перестановки этапов он ещё и требует объяснений;
рецепт, клубника и награда от его разговоров не зависят. Черновые группы ходьбы не используются,
кадры не отражаются. Чучмека в испытании нет — он ждёт на центральной площади.

Со слоем высокого разрешения (game/graphics/hires.py) Алиса и Тортище рисуются из
исходных кадров 64×64, а надписи — шрифтом размера окна; перевёрнутые надписи (заголовок доски
до исправления рецепта, таблички «ТОРТЫ» и «КЛАДОВАЯ») — тем же шрифтом, повёрнутым на 180°.
Кондитерская, кладовая, подставка Тортища, торт и клубника остаются пиксельными, облачко
реплики клубники — пиксельная рамка с текстом шрифта окна.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import pygame

import config
from game.core.input import Action, actions_for
from game.core.scenes import Scene
from game.dialogue.box import DialogueBox, wrap_text
from game.dialogue.model import DialogueController, DialogueScript
from game.graphics.animation import Direction
from game.graphics.fonts import TextFonts, TextStyle, load_font, render_text
from game.graphics.hires import HiResLayer, logical_target
from game.graphics.placeholder import placeholder_animations
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, try_load_character_sprites
from game.story import cakes_dialogue as lines
from game.trials.cakes_maze import MAZE_BOUNDS, MAZE_START, PantryItem, PantryLayout, generate_layout, line_of_sight
from game.trials.cakes_puzzle import STEP_NAMES, STEP_SHORT_NAMES, STEPS, CakeRecipe, CheckResult, PickResult
from game.trials.strawberry_chase import CAUGHT, TALKING, StrawberryChase
from game.world.character import Character
from game.world.hub import TRIAL_SCENES
from game.world.progress import GameProgress

CAKES_SCENE = TRIAL_SCENES["cakes"]  # «trial_cakes» — имя, которое ищет портал площади
TRIAL_ID = "cakes"

# Этапы испытания.
INTRO_PHASE = "intro"
ORDERING = "ordering"  # перестановка этапов рецепта
SUCCESS_PHASE = "success"  # реакция Тортища на правильный рецепт
ESCAPE_PHASE = "escape"  # клубника убегает, затем реплики о побеге
MAZE = "maze"  # погоня за клубникой в кладовой
FOUND_PHASE = "found"  # клубника поймана — короткая реакция у рабочего стола
FINAL_PHASE = "final"  # финальный диалог у рабочего стола
DONE = "done"

BAKERY = "bakery"  # где сейчас Алиса: кондитерская или кладовая
PANTRY = "pantry"

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 32  # как на площади
WALK_SPEED = 64
HUD_HEIGHT = 24  # две строки: задача и часть испытания
STATUS_TOP = 168
# Доска с рецептом. Нижний край — выше любого окна реплики, поэтому, пока Алиса слушает
# Тортище, порядок этапов виден целиком.
BOARD = pygame.Rect(6, 26, 196, 84)
ROW_TOP = 40
ROW_HEIGHT = 11
CHECK_ROW = len(STEPS)  # шестая строка доски — кнопка «Проверить рецепт»
CHECK_BUTTON = pygame.Rect(BOARD.x + 38, ROW_TOP + CHECK_ROW * ROW_HEIGHT + 2, 120, ROW_HEIGHT)
FLOOR_TOP = 98  # где в кондитерской стена переходит в пол
ALICE_SPOT = (222, 106)  # у доски и рабочего стола; ноги выше окна реплики
# Тортище: кадр GREAT_CAKE_SIZE×GREAT_CAKE_SIZE, привязанный серединой нижнего края к GREAT_CAKE_SPOT,
# — на золотой подставке над дверью кладовой, правее стола с клубникой: его видно над окном реплики.
# Голова не заходит под верхнюю полосу, ноги — выше любого окна реплики.
GREAT_CAKE_SIZE = 44
GREAT_CAKE_SPOT = (296, 68)
GREAT_CAKE_PLATE = pygame.Rect(GREAT_CAKE_SPOT[0] - 18, GREAT_CAKE_SPOT[1] - 2, 36, 3)  # золотое блюдо под ногами
GREAT_CAKE_SHELF = pygame.Rect(GREAT_CAKE_PLATE.x - 4, GREAT_CAKE_PLATE.bottom, WIDTH - GREAT_CAKE_PLATE.x + 4, 3)
PANTRY_DOOR = pygame.Rect(WIDTH - 8, GREAT_CAKE_SHELF.bottom, 8, FLOOR_TOP - GREAT_CAKE_SHELF.bottom)  # под полкой
TABLE = pygame.Rect(240, 88, 44, 12)  # рабочий стол с тортом
CAKE_CENTER = (258, 86)
STRAWBERRY_ON_TABLE = (277, 84)
ESCAPE_SECONDS = 1.4  # сколько клубника убегает до реплик
ESCAPE_FLOOR_Y = 116
TOAST_SECONDS = 3.0
TOAST_PRIORITY_SECONDS = 1.5  # столько свежее сообщение показывается вместо подсказки
# Поймать клубнику можно, если точки под ногами Алисы и клубники не дальше CATCH_REACH и между
# ними нет стеллажа (а не по ширине картинки).
CATCH_REACH = 16
STRAWBERRY_LIFT = 5  # середина ягоды выше точки под ногами: низ ягоды стоит на полу
CHASE_TOAST = "Клубника сбежала! Поймай её: E — когда будешь рядом"
FAR_TOAST = "Ещё не поймана — подойди к клубнике ближе"

HUD_COLOR = (44, 38, 58)
HUD_TEXT_COLOR = (240, 230, 206)
HUD_ACCENT_COLOR = (250, 206, 108)
DONE_COLOR = (140, 220, 150)
MARK_COLOR = (255, 236, 140)
WALL_COLOR = (248, 214, 222)
WALL_STRIPE_COLOR = (238, 196, 208)
CEILING_COLOR = (150, 96, 110)
FLOOR_COLORS = ((250, 236, 220), (226, 170, 186))
BOARD_COLOR = (46, 78, 64)
BOARD_FRAME_COLOR = (150, 104, 70)
CHALK_COLOR = (236, 240, 230)
CHALK_DIM_COLOR = (170, 196, 180)
PICKED_COLOR = (90, 130, 108)
TABLE_COLOR = (196, 150, 104)
TABLE_EDGE_COLOR = (130, 92, 62)
TRAY_COLOR = (90, 90, 104)
TRAY_EDGE_COLOR = (160, 160, 176)
CREAM_COLOR = (252, 246, 236)
SPONGE_COLOR = (228, 184, 112)
PLATE_COLOR = (236, 236, 244)
STRAWBERRY_COLOR = (222, 44, 62)
STRAWBERRY_DARK_COLOR = (160, 24, 44)
SEED_COLOR = (255, 226, 120)
LEAF_COLOR = (64, 168, 72)
PANTRY_WALL_COLOR = (120, 84, 62)
PANTRY_FLOOR_COLORS = ((176, 132, 94), (164, 120, 84))
PLANK_LINE_COLOR = (140, 100, 70)
SIGN_COLOR = (236, 222, 190)
SIGN_TEXT_COLOR = (90, 56, 48)
GOLD_COLOR = (240, 200, 96)  # блюдо-подставка Тортища
GOLD_EDGE_COLOR = (170, 120, 44)
GREAT_CAKE_PLACEHOLDER_COLOR = (128, 32, 52)  # бордовая накидка — у манекена, если кадров нет
SPEECH_COLOR = (255, 250, 236)
SPEECH_BORDER_COLOR = (90, 56, 48)
SPEECH_TEXT_COLOR = (64, 36, 40)
SHELF_WOOD_COLOR = (112, 74, 50)
SHELF_TOP_COLOR = (164, 116, 78)
SHELF_DARK_COLOR = (60, 40, 30)
BOOK_COLORS = ((196, 72, 66), (88, 110, 160), (230, 190, 90), (120, 160, 110), (180, 120, 190), (236, 150, 170),
               (240, 232, 214))
PAGE_COLOR = (246, 238, 220)
BOX_COLOR = (206, 164, 112)
BOX_DARK_COLOR = (156, 118, 76)

# Надписи в разрешении окна (слой высокого разрешения); размер — в логических пикселях.
TEXT_SIZE = 8  # интерфейс и доска, как на площади
HUD_STYLE = TextStyle(TEXT_SIZE, HUD_TEXT_COLOR, background=HUD_COLOR)  # полосы вверху и внизу
TASK_STYLE = TextStyle(TEXT_SIZE, HUD_ACCENT_COLOR, background=HUD_COLOR)
CHALK_STYLE = TextStyle(TEXT_SIZE, CHALK_COLOR)
CHALK_DIM_STYLE = TextStyle(TEXT_SIZE, CHALK_DIM_COLOR)
SIGN_STYLE = TextStyle(6, SIGN_TEXT_COLOR)  # подвешенные таблички
SPEECH_STYLE = TextStyle(7, SPEECH_TEXT_COLOR, background=SPEECH_COLOR)  # облачко реплики клубники
SPEECH_MAX_WIDTH = 150  # ширина строки в облачке, логические пиксели
SPEECH_PADDING = (5, 3)
SPEECH_AREA = pygame.Rect(2, HUD_HEIGHT + 2, WIDTH - 4, STATUS_TOP - HUD_HEIGHT - 4)  # облачко — между полосами
HUD_ROWS = (6.5, 17.5)  # середины двух строк верхней полосы
BOARD_TITLE_MIDDLE = BOARD.y + 8  # середина заголовка доски — над первой строкой этапов
# Табличка кондитерской висит между противнями: справа под потолком — Тортище.
SIGNS = {"bakery": ("ТОРТЫ", (243, 34)), "pantry": ("КЛАДОВАЯ", (170, 34))}
# Где рисуется рабочий стол: столешница с ножками и торт на ней.
TABLE_AREA = pygame.Rect(TABLE.x, CAKE_CENTER[1] - 16, TABLE.width, TABLE.bottom + 8 - (CAKE_CENTER[1] - 16))


def draw_strawberry(surface: pygame.Surface, center: tuple[float, float]) -> None:
    """Клубника: красная ягода с жёлтыми семечками и зелёными листьями (рисуется, не ассет)."""
    x, y = round(center[0]), round(center[1])
    body = [(x - 5, y - 3), (x + 5, y - 3), (x + 4, y + 1), (x + 1, y + 5), (x - 1, y + 5), (x - 4, y + 1)]
    pygame.draw.polygon(surface, STRAWBERRY_COLOR, body)
    pygame.draw.polygon(surface, STRAWBERRY_DARK_COLOR, body, 1)
    for dx, dy in ((-2, -1), (1, -1), (3, 0), (-1, 2), (1, 3), (-3, 0)):
        surface.set_at((x + dx, y + dy), SEED_COLOR)
    leaves = [(x - 5, y - 4), (x, y - 2), (x + 5, y - 4), (x + 2, y - 6), (x - 2, y - 6)]
    pygame.draw.polygon(surface, LEAF_COLOR, leaves)
    pygame.draw.line(surface, LEAF_COLOR, (x, y - 6), (x + 1, y - 8))


def draw_step_icon(surface: pygame.Surface, step: str, center: tuple[int, int]) -> None:
    """Значок этапа рецепта 8×8: яйцо, миска с тестом, огонь духовки, снежинка, крем с ягодой."""
    x, y = center
    if step == "ingredients":
        pygame.draw.ellipse(surface, (250, 246, 230), (x - 4, y - 3, 5, 7))
        pygame.draw.rect(surface, (214, 190, 150), (x + 1, y - 1, 4, 5))
    elif step == "dough":
        pygame.draw.ellipse(surface, (236, 214, 160), (x - 3, y - 3, 7, 4))
        pygame.draw.rect(surface, (120, 160, 200), (x - 4, y - 1, 9, 4))
    elif step == "bake":
        pygame.draw.polygon(surface, (250, 140, 60), [(x - 3, y + 3), (x, y - 4), (x + 3, y + 3)])
        pygame.draw.polygon(surface, (255, 220, 110), [(x - 1, y + 3), (x, y), (x + 1, y + 3)])
    elif step == "cool":
        for dx, dy in ((4, 0), (0, 4), (3, 3), (3, -3)):
            pygame.draw.line(surface, (170, 220, 250), (x - dx, y - dy), (x + dx, y + dy))
    else:
        pygame.draw.ellipse(surface, CREAM_COLOR, (x - 4, y - 1, 9, 5))
        pygame.draw.circle(surface, STRAWBERRY_COLOR, (x, y - 2), 2)


class CakesTrialScene(Scene):
    """Перевёрнутая кондитерская. Открывается правым порталом площади и закрывается возвратом на неё."""

    supports_hires = True

    def __init__(
        self,
        progress: GameProgress | None = None,
        characters_dir: str | Path = CHARACTERS_DIR,
        seed: int | None = None,
    ) -> None:
        """seed — случайность кладовой и клубники (None — каждый раз своя; тесты задают число)."""
        self.progress = progress if progress is not None else GameProgress()
        self.recipe = CakeRecipe()
        self.cursor = 0  # строка доски: этапы 0–4 и кнопка проверки
        self.rng = random.Random(seed)
        # Кладовая и клубника появляются, когда начинается погоня (_enter_pantry).
        self.pantry: PantryLayout | None = None
        self.collision = None
        self.chase: StrawberryChase | None = None
        root = Path(characters_dir)
        alice_sprites = try_load_character_sprites(root / "alice")
        self.alice = Character(
            "Алиса",
            alice_sprites.animation_set(SPRITE_SIZE) if alice_sprites else None,
            position=ALICE_SPOT,
            speed=WALK_SPEED,
            direction=Direction.RIGHT,
        )
        self.great_cake_sprites = try_load_character_sprites(root / "great_cake")
        self.great_cake_pose = lines.GREAT_CAKE_IDLE_POSE
        self._great_cake_frames: dict[str, tuple[pygame.Surface, pygame.Surface]] = {}
        self.great_cake_met = False  # разговор с Тортищем уже был (один раз за прохождение)

        self.box = DialogueBox()
        for script in lines.all_scripts():
            self.box.check_fits(script)
        self.phase = INTRO_PHASE
        self.area = BAKERY
        self.dialogue: DialogueController | None = None
        self.escape_time = 0.0
        self.strawberry_found = False
        self.reward_given = False  # True, если именно это прохождение добавило фрагмент
        self.completed = False
        self.toast = ""
        self._toast_time = 0.0
        self.time = 0.0
        self._font = load_font(9)
        self._small_font = load_font(7)
        self._text_cache: dict[tuple[str, config.Color, bool], pygame.Surface] = {}
        self._fonts = TextFonts()
        self.text_metrics = self._fonts.metrics(HUD_STYLE)
        self.sign_metrics = self._fonts.metrics(SIGN_STYLE)
        self.speech_metrics = self._fonts.metrics(SPEECH_STYLE)
        self._bakery = self._render_bakery()
        # Без надписей на табличках: их рисует слой высокого разрешения.
        self._bakery_plain = self._render_bakery(labels=False)
        self._pantry: pygame.Surface | None = None
        self._pantry_plain: pygame.Surface | None = None
        self._open_dialogue(lines.INTRO)

    # --- Состояние ---

    def near_strawberry(self) -> bool:
        """Можно ли сейчас поймать клубнику: идёт погоня, ноги Алисы не дальше CATCH_REACH от ног
        клубники и между ними нет стеллажа. Бежит клубника или болтает — неважно."""
        chase = self.chase
        if self.phase != MAZE or self.dialogue is not None or chase is None or chase.state == CAUGHT:
            return False
        feet = (self.alice.x, self.alice.y)
        return math.dist(feet, chase.position) <= CATCH_REACH and line_of_sight(self.pantry.obstacles, feet,
                                                                                 chase.position)

    def strawberry_position(self) -> tuple[float, float] | None:
        """Где нарисовать клубнику — середина ягоды (None — её не видно)."""
        if self.area == PANTRY:
            if self.chase is None or self.chase.state == CAUGHT:
                return None
            x, y = self.chase.position
            hop = abs(math.sin(self.time * 14)) * 2 if self.chase.is_moving else 0.0  # бежит вприпрыжку
            return x, y - STRAWBERRY_LIFT - hop
        if self.phase in (INTRO_PHASE, ORDERING, SUCCESS_PHASE):
            return STRAWBERRY_ON_TABLE
        if self.phase == ESCAPE_PHASE:
            return self._escape_position()
        if self.phase == FOUND_PHASE:
            return None  # у Алисы над головой (см. _draw_alice)
        if self.strawberry_found:
            return CAKE_CENTER[0], CAKE_CENTER[1] - 11  # на вершине торта
        return None

    def _escape_position(self) -> tuple[float, float]:
        """Побег: спрыгивает со стола на пол и, подпрыгивая, убегает в дверь кладовой справа."""
        t = min(self.escape_time / ESCAPE_SECONDS, 1.0)
        start_x, start_y = STRAWBERRY_ON_TABLE
        if t < 0.3:  # прыжок со стола дугой
            k = t / 0.3
            return start_x + 8 * k, start_y + (ESCAPE_FLOOR_Y - start_y) * k - math.sin(k * math.pi) * 10
        k = (t - 0.3) / 0.7
        return start_x + 8 + (WIDTH + 20 - start_x - 8) * k, ESCAPE_FLOOR_Y - abs(math.sin(k * math.pi * 4)) * 4

    def task_text(self) -> str:
        """Текущая задача — верхняя строка интерфейса."""
        if self.phase == INTRO_PHASE:
            return "Перевёрнутая кондитерская"
        if self.phase == ORDERING:
            return "Задача: расставь этапы рецепта по порядку"
        if self.phase == SUCCESS_PHASE:
            return "Рецепт исправлен!"
        if self.phase == ESCAPE_PHASE:
            return "Клубника сбежала!"
        if self.phase == MAZE:
            return "Задача: догони и поймай клубнику"
        return "Клубника поймана"

    def part_text(self) -> str:
        if self.phase in (INTRO_PHASE, ORDERING, SUCCESS_PHASE):
            return "Часть 1 из 2 — рецепт"
        if self.phase in (ESCAPE_PHASE, MAZE, FOUND_PHASE):
            return "Часть 2 из 2 — клубника"
        return "Осталось закончить торт"

    def held_text(self) -> str:
        picked = self.recipe.picked
        return f"Взят этап: {STEP_SHORT_NAMES[self.recipe.order[picked]]}" if picked is not None else ""

    def prompt(self) -> str | None:
        """Подсказка по управлению для текущей стадии (без реплики на экране)."""
        if self.dialogue is not None:
            return None
        if self.phase == ORDERING:
            picked = self.recipe.picked
            if self.cursor == CHECK_ROW:
                return "E — проверить рецепт   Стрелки — к этапам"
            if picked is None:
                return "Стрелки — выбрать этап   E — взять   Backspace — уйти"
            if picked == self.cursor:
                return "E — положить обратно   Стрелки — с чем поменять"
            return "Стрелки — куда поставить   E — поменять местами"
        if self.phase == ESCAPE_PHASE:
            return "Клубника убегает!"
        if self.phase == MAZE:
            if self.near_strawberry():
                return "Клубника   E — поймать"
            return "Стрелки/WASD — догнать   E — поймать рядом   Backspace — уйти"
        return None

    def status_text(self) -> str:
        """Нижняя полоса: свежее сообщение, подсказка по управлению или старое сообщение."""
        if self.toast and TOAST_SECONDS - self._toast_time < TOAST_PRIORITY_SECONDS:
            return self.toast
        return self.prompt() or self.toast or "Backspace — уйти"

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
        if self.phase == ORDERING:
            # Стрелки двигают выделение по доске, а не Алису.
            if Action.MOVE_UP in actions:
                self.cursor = (self.cursor - 1) % (CHECK_ROW + 1)
            elif Action.MOVE_DOWN in actions:
                self.cursor = (self.cursor + 1) % (CHECK_ROW + 1)
            elif Action.INTERACT in actions or Action.CONFIRM in actions:
                self.activate()
        elif self.phase == MAZE:
            self.alice.handle_event(event)
            if Action.INTERACT in actions:
                self.interact()

    def activate(self) -> None:
        """E или Enter на доске: взять или поменять этап, а на кнопке — проверить рецепт."""
        if self.phase != ORDERING:
            return
        if self.cursor == CHECK_ROW:
            self._check()
            return
        order = self.recipe.order
        picked = self.recipe.picked
        result = self.recipe.pick(self.cursor)
        if result is PickResult.PICKED:
            self._show_toast(f"Взят этап: {STEP_SHORT_NAMES[order[self.cursor]]}")
        elif result is PickResult.DROPPED:
            self._show_toast(f"Положила обратно: {STEP_SHORT_NAMES[order[self.cursor]]}")
        elif result is PickResult.SWAPPED:
            first, second = STEP_SHORT_NAMES[order[picked]], STEP_SHORT_NAMES[order[self.cursor]]
            self._show_toast(f"Поменяла местами: {first} и {second}")
            if not self.great_cake_met:
                # Алиса впервые изменила рецепт — Тортище требует объяснений. Обмен уже сделан,
                # после разговора можно переставлять дальше с того же места.
                self.great_cake_met = True
                self._open_dialogue(lines.GREAT_CAKE_TALK)

    def _check(self) -> None:
        result = self.recipe.check()
        if result is CheckResult.SOLVED:
            self.phase = SUCCESS_PHASE
            self._open_dialogue(lines.SUCCESS)
        elif result is CheckResult.WRONG:
            # Не засчитано, но ничего не испорчено: порядок на доске остаётся, можно переставлять дальше.
            self._open_dialogue(lines.wrong_order(self.recipe.failed_checks, self.recipe.first_mistake()))

    def interact(self) -> bool:
        """E или Enter в кладовой. True, если клубника поймана (ровно один раз).

        Издалека — только сообщение: погоня идёт дальше, Алиса никуда не переносится."""
        if self.phase != MAZE:
            return False
        if not self.near_strawberry():
            self._show_toast(FAR_TOAST)
            return False
        if not self.chase.catch():
            return False
        self.strawberry_found = True
        self.phase = FOUND_PHASE
        self._back_to_table()  # реакция — уже у рабочего стола, где её видно над окном реплики
        self._open_dialogue(lines.FOUND)
        return True

    def _open_dialogue(self, script: DialogueScript) -> None:
        self.alice.release_controls()  # во время реплик Алиса стоит
        self.dialogue = DialogueController(script)
        self.great_cake_pose = self.great_cake_rest_pose()  # реплики без своей позы её не меняют
        self._sync_dialogue()

    def _sync_dialogue(self) -> None:
        node = self.dialogue.node if self.dialogue is not None else None
        if node is not None and node.id in lines.GREAT_CAKE_POSES:
            self.great_cake_pose = lines.GREAT_CAKE_POSES[node.id]

    def great_cake_rest_pose(self) -> str:
        """Поза Тортища без реплик: строго следит за рецептом после разговора, сердится,
        пока клубника убегает, а в остальное время просто величественно стоит."""
        if self.phase == ESCAPE_PHASE:
            return lines.GREAT_CAKE_ESCAPE_POSE
        if self.phase == ORDERING and self.great_cake_met:
            return lines.GREAT_CAKE_WATCH_POSE
        return lines.GREAT_CAKE_IDLE_POSE

    def _dialogue_finished(self) -> None:
        """Реплика закрыта: следующий этап испытания."""
        self.dialogue = None
        if self.phase == INTRO_PHASE:
            self.phase = ORDERING
        elif self.phase == SUCCESS_PHASE:
            self.phase = ESCAPE_PHASE  # клубника убегает — дальше в update
            self.escape_time = 0.0
        elif self.phase == ESCAPE_PHASE:
            self._enter_pantry()
        elif self.phase == FOUND_PHASE:
            self.phase = FINAL_PHASE
            self._open_dialogue(lines.FINAL)
        elif self.phase == FINAL_PHASE:
            self._complete()
        if self.dialogue is None:
            self.great_cake_pose = self.great_cake_rest_pose()  # уже для нового этапа

    def _enter_pantry(self) -> None:
        """Погоня: новая раскладка кладовой, Алиса у двери, клубника — в дальней части комнаты."""
        self.phase = MAZE
        self.area = PANTRY
        self.pantry = generate_layout(self.rng.randrange(1 << 30))
        self.collision = self.pantry.collision()
        self._pantry = self._render_pantry()
        self._pantry_plain = self._render_pantry(labels=False)
        self.alice.release_controls()
        self.alice.set_position(*MAZE_START)
        self.alice.face(Direction.RIGHT)
        self.alice.collider = self.collision.move
        self.chase = StrawberryChase(self.pantry, self.alice.speed, random.Random(self.rng.randrange(1 << 30)),
                                     lines.STRAWBERRY_LINES, pursuer=MAZE_START)
        self._show_toast(CHASE_TOAST)

    def _back_to_table(self) -> None:
        """Клубника поймана — назад к рабочему столу: реакция, финальный разговор и награда там."""
        self.area = BAKERY
        self.alice.release_controls()
        self.alice.collider = None
        self.alice.set_position(*ALICE_SPOT)
        self.alice.face(Direction.RIGHT)

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
        elif self.phase == ESCAPE_PHASE:
            self.escape_time += dt
            if self.escape_time >= ESCAPE_SECONDS:
                self._open_dialogue(lines.ESCAPE)
        self.alice.update(dt)
        if self.phase == MAZE and self.dialogue is None and self.chase is not None:
            self.chase.update(dt, (self.alice.x, self.alice.y))  # убегает от того места, где Алиса сейчас
        if self._toast_time > 0:
            self._toast_time -= dt
            if self._toast_time <= 0:
                self.toast = ""

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рисует кондитерскую или кладовую на холсте; со слоем hires персонажи и надписи уходят
        в него (см. game/graphics/hires.py), а порядок слоёв остаётся тем же."""
        if self.area == BAKERY:
            surface.blit(self._bakery if hires is None else self._bakery_plain, (0, 0))
            self._draw_table(surface, hires)
            self._draw_board(surface, hires)
        else:
            surface.blit(self._pantry if hires is None else self._pantry_plain, (0, 0))
        if hires is not None:  # перевёрнутая табличка — часть фона, под персонажами
            text, center = SIGNS[self.area]
            hires.text(text, SIGN_STYLE, self.sign_rect(text, center, hires=True).center, anchor="center", angle=180)
        drawables = [(self.alice.y + 0.1, lambda: self._draw_alice(surface, hires))]
        if self.area == BAKERY:  # в кладовую Тортище не ходит
            drawables.append((GREAT_CAKE_SPOT[1], lambda: self._draw_great_cake(surface, hires)))
        strawberry = self.strawberry_position()
        if strawberry is not None:
            drawables.append((strawberry[1] + 5, lambda: self._draw_loose_strawberry(surface, strawberry, hires)))
        for _, draw in sorted(drawables, key=lambda item: item[0]):
            draw()
        self._draw_speech(surface, hires)  # облачко клубники — поверх героев, под интерфейсом
        self._draw_hud(surface, hires)
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue, hires)
        else:
            self._draw_status(surface, hires)

    def _text(self, text: str, color: config.Color, small: bool = False) -> pygame.Surface:
        key = (text, color, small)
        image = self._text_cache.get(key)
        if image is None:
            image = self._text_cache[key] = render_text(self._small_font if small else self._font, text, color)
        return image

    def held_icon_center(self) -> tuple[int, int]:
        """Пойманная клубника — над головой Алисы."""
        rect = self.alice.rect
        return rect.centerx, rect.top - 6

    def _draw_alice(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        self.alice.draw(canvas, hires)
        if self.phase == FOUND_PHASE:
            x, y = self.held_icon_center()
            with logical_target(canvas, hires, pygame.Rect(x - 6, y - 10, 13, 16)) as surface:
                draw_strawberry(surface, (x, y - round(abs(math.sin(self.time * 4)))))

    def _draw_loose_strawberry(
        self, canvas: pygame.Surface, center: tuple[float, float], hires: HiResLayer | None = None
    ) -> None:
        x, y = round(center[0]), round(center[1])
        # Ягода, блёстки и ромбик над ней — вокруг той же точки, что и область, где её ловят.
        with logical_target(canvas, hires, pygame.Rect(x - 11, y - 19, 23, 25)) as surface:
            draw_strawberry(surface, center)
            if self.area == PANTRY:  # блёстки, чтобы ягоду было видно издалека
                for k, (dx, dy) in enumerate(((-9, -7), (8, -9), (10, 3), (-10, 4))):
                    if int(self.time * 3 + k) % 2 == 0:
                        surface.set_at((x + dx, y + dy), MARK_COLOR)
                        surface.set_at((x + dx + 1, y + dy), MARK_COLOR)
                if self.near_strawberry():
                    top = y - 13 - round(abs(math.sin(self.time * 4)) * 2)
                    pygame.draw.polygon(surface, MARK_COLOR, [(x, top - 3), (x + 3, top), (x, top + 3), (x - 3, top)])

    def speech_bubble(self, hires: bool = False) -> tuple[pygame.Rect, list[str]] | None:
        """Облачко реплики клубники: где оно на холсте и строки в нём (None — она молчит).

        Над ягодой, а если там Алиса или край — под ней; всегда между полосами интерфейса.
        Строки размечены шрифтом окна (hires=True) или пиксельным — для своего способа вывода."""
        chase = self.chase
        center = self.strawberry_position()
        if self.area != PANTRY or chase is None or chase.state != TALKING or not chase.line or center is None:
            return None
        if hires:
            text_lines = wrap_text(chase.line, self.speech_metrics, SPEECH_MAX_WIDTH)
            width = max(math.ceil(self.speech_metrics.width(line)) for line in text_lines)
            line_height = math.ceil(self.speech_metrics.height)
        else:
            text_lines = wrap_text(chase.line, self._small_font, SPEECH_MAX_WIDTH)
            width = max(self._small_font.size(line)[0] for line in text_lines)
            line_height = self._small_font.get_linesize()
        size = (width + 2 * SPEECH_PADDING[0], len(text_lines) * line_height + 2 * SPEECH_PADDING[1])
        x, y = round(center[0]), round(center[1])
        berry = pygame.Rect(x - 6, y - 9, 13, 15)  # ягода с листиками
        alice = self.alice.rect.inflate(-14, -4)  # сама Алиса, без пустых краёв кадра
        above, below = pygame.Rect((0, 0), size), pygame.Rect((0, 0), size)
        above.midbottom = (x, berry.top - 4)
        below.midtop = (x, berry.bottom + 3)
        options = [rect.clamp(SPEECH_AREA) for rect in (above, below)]
        options.sort(key=lambda rect: (rect.colliderect(berry), _overlap(rect, alice)))
        return options[0], text_lines

    def _draw_speech(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        bubble = self.speech_bubble(hires is not None)
        if bubble is None:
            return
        rect, text_lines = bubble
        center = self.strawberry_position()
        tip_x = min(max(round(center[0]), rect.left + 4), rect.right - 5)
        if rect.bottom <= center[1]:  # облачко над ягодой — хвостик вниз
            tail = [(tip_x - 3, rect.bottom - 1), (tip_x + 3, rect.bottom - 1), (tip_x, rect.bottom + 3)]
        else:
            tail = [(tip_x - 3, rect.top), (tip_x + 3, rect.top), (tip_x, rect.top - 4)]
        with logical_target(canvas, hires, rect.inflate(2, 10)) as surface:
            pygame.draw.polygon(surface, SPEECH_BORDER_COLOR, tail)
            pygame.draw.rect(surface, SPEECH_COLOR, rect, border_radius=3)
            pygame.draw.rect(surface, SPEECH_BORDER_COLOR, rect, 1, border_radius=3)
            if hires is None:
                line_height = self._small_font.get_linesize()
                for row, line in enumerate(text_lines):
                    surface.blit(self._text(line, SPEECH_TEXT_COLOR, small=True),
                                 (rect.x + SPEECH_PADDING[0], rect.y + SPEECH_PADDING[1] + row * line_height))
        if hires is not None:
            line_height = math.ceil(self.speech_metrics.height)
            for row, line in enumerate(text_lines):
                middle = rect.y + SPEECH_PADDING[1] + row * line_height + line_height / 2
                hires.text(line, SPEECH_STYLE, (rect.x + SPEECH_PADDING[0], middle), anchor="midleft")

    def great_cake_rect(self) -> pygame.Rect:
        """Где стоит Тортище на холсте: одно и то же место и размер при любой позе."""
        width, height = self._great_cake_frame()[1].get_size()
        return pygame.Rect(GREAT_CAKE_SPOT[0] - width // 2, GREAT_CAKE_SPOT[1] - height, width, height)

    def _draw_great_cake(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        source, image = self._great_cake_frame()
        rect = self.great_cake_rect()
        if hires is not None:
            hires.sprite(source, rect)  # исходный кадр 64×64 в окне, без отражения
        else:
            canvas.blit(image, rect)

    def _great_cake_frame(self) -> tuple[pygame.Surface, pygame.Surface]:
        """Поза Тортища: исходный кадр манифеста great_cake (без отражения) и он же на холсте.

        Позу ищет CharacterSprites.pose (псевдоним из poses или id кадра). Если её нет —
        основная поза idle, нет и её — первый кадр; без манифеста — временный манекен,
        как у остальных персонажей. Испытание от этого не ломается."""
        pose = self.great_cake_pose
        if pose not in self._great_cake_frames:
            sprites: CharacterSprites | None = self.great_cake_sprites
            if sprites is None:
                source = image = placeholder_animations(GREAT_CAKE_PLACEHOLDER_COLOR).default.frames[0]
            else:
                source = sprites.frames[0].image
                for name in (pose, lines.GREAT_CAKE_IDLE_POSE):
                    try:
                        source = sprites.pose(name).image
                        break
                    except KeyError:
                        continue
                image = pygame.transform.scale(source, (GREAT_CAKE_SIZE, GREAT_CAKE_SIZE))
            self._great_cake_frames[pose] = (source, image)
        return self._great_cake_frames[pose]

    def row_rect(self, index: int) -> pygame.Rect:
        """Строка доски: этапы 0–4, а CHECK_ROW — кнопка проверки."""
        if index == CHECK_ROW:
            return CHECK_BUTTON.copy()
        return pygame.Rect(BOARD.x + 4, ROW_TOP + index * ROW_HEIGHT, BOARD.width - 8, ROW_HEIGHT)

    def _draw_board(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Доска рецепта: на холсте — рамки строк и значки, надписи — на холсте или в слое окна."""
        recipe = self.recipe
        title_text = "РЕЦЕПТ ТОРТА"
        # Перевёрнутая кондитерская: даже заголовок вверх ногами, пока рецепт не исправлен.
        title_angle = 0 if recipe.solved else 180
        choosing = self.phase == ORDERING and self.dialogue is None
        texts = []  # (текст, цвет, точка, привязка) — в слой окна после графики доски
        with logical_target(canvas, hires, BOARD) as surface:
            if hires is None:
                title = self._text(title_text, CHALK_COLOR)
                if title_angle:
                    title = pygame.transform.rotate(title, title_angle)
                surface.blit(title, title.get_rect(midtop=(BOARD.centerx, BOARD.y + 2)))
            for index, step in enumerate(recipe.order):
                rect = self.row_rect(index)
                if recipe.picked == index:
                    surface.fill(PICKED_COLOR, rect)
                if choosing and self.cursor == index:
                    pygame.draw.rect(surface, MARK_COLOR, rect, 1)
                color = DONE_COLOR if recipe.solved else (HUD_ACCENT_COLOR if recipe.picked == index else CHALK_COLOR)
                draw_step_icon(surface, step, (rect.x + 20, rect.centery))
                if hires is None:
                    surface.blit(self._text(f"{index + 1}.", CHALK_DIM_COLOR), (rect.x + 2, rect.y))
                    surface.blit(self._text(STEP_NAMES[step], color), (rect.x + 28, rect.y))
                texts.append((f"{index + 1}.", CHALK_DIM_COLOR, (rect.x + 2, rect.centery), "midleft"))
                texts.append((STEP_NAMES[step], color, (rect.x + 28, rect.centery), "midleft"))
            button = self.row_rect(CHECK_ROW)
            selected = choosing and self.cursor == CHECK_ROW
            pygame.draw.rect(surface, PICKED_COLOR if selected else BOARD_COLOR, button)
            pygame.draw.rect(surface, MARK_COLOR if selected else CHALK_DIM_COLOR, button, 1)
            button_text = "Рецепт верный!" if recipe.solved else "Проверить рецепт"
            if hires is None:
                label = self._text(button_text, CHALK_COLOR)
                surface.blit(label, label.get_rect(center=button.center))
            texts.append((button_text, CHALK_COLOR, button.center, "center"))
        if hires is not None:
            hires.text(title_text, CHALK_STYLE, (BOARD.centerx, BOARD_TITLE_MIDDLE), anchor="center", angle=title_angle)
            for text, color, point, anchor in texts:
                hires.text(text, TextStyle(TEXT_SIZE, color), point, anchor=anchor)

    def _draw_table(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рабочий стол с тортом: до исправления рецепта торт стоит вверх ногами."""
        with logical_target(canvas, hires, TABLE_AREA) as surface:
            self._draw_table_on(surface)

    def _draw_table_on(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, (TABLE.x + 3, TABLE.bottom, 3, 8))
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, (TABLE.right - 6, TABLE.bottom, 3, 8))
        pygame.draw.rect(surface, TABLE_COLOR, TABLE)
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, TABLE, 1)
        x, y = CAKE_CENTER
        layers = [(PLATE_COLOR, 24, 2), (SPONGE_COLOR, 18, 4), (CREAM_COLOR, 18, 2), (SPONGE_COLOR, 18, 4),
                  (CREAM_COLOR, 18, 3)]
        if not self.recipe.solved:
            layers.reverse()  # тарелка сверху, крем снизу
        bottom = y + 2
        for color, width, height in layers:
            pygame.draw.rect(surface, color, (x - width // 2, bottom - height, width, height))
            bottom -= height

    def _draw_hud(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        bar = pygame.Rect(0, 0, WIDTH, HUD_HEIGHT)
        held = self.held_text()
        with logical_target(canvas, hires, bar) as surface:
            surface.fill(HUD_COLOR, bar)
            if hires is None:
                surface.blit(self._text(self.task_text(), HUD_ACCENT_COLOR), (4, 1))
                surface.blit(self._text(self.part_text(), HUD_TEXT_COLOR), (4, 12))
                if held:
                    image = self._text(held, HUD_TEXT_COLOR)
                    surface.blit(image, image.get_rect(topright=(WIDTH - 4, 12)))
        if hires is not None:
            hires.text(self.task_text(), TASK_STYLE, (4, HUD_ROWS[0]), anchor="midleft")
            hires.text(self.part_text(), HUD_STYLE, (4, HUD_ROWS[1]), anchor="midleft")
            hires.text(held, HUD_STYLE, (WIDTH - 4, HUD_ROWS[1]), anchor="midright")

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

    def sign_rect(self, text: str, center: tuple[int, int], hires: bool = False) -> pygame.Rect:
        """Подвешенная табличка — по размеру надписи пиксельным шрифтом или шрифтом окна."""
        if hires:
            width, height = self.sign_metrics.size(text)
            label = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        else:
            label = render_text(self._small_font, text, SIGN_TEXT_COLOR).get_rect()
        label.center = center
        return label.inflate(6, 2)

    def _upside_down_sign(self, page: pygame.Surface, text: str, center: tuple[int, int], labels: bool) -> None:
        """Табличка вверх ногами, подвешенная к потолку; labels=False — без надписи (её рисует слой окна)."""
        sign = self.sign_rect(text, center, hires=not labels)
        pygame.draw.rect(page, SIGN_COLOR, sign)
        pygame.draw.rect(page, SIGN_TEXT_COLOR, sign, 1)
        if labels:
            label = pygame.transform.rotate(render_text(self._small_font, text, SIGN_TEXT_COLOR), 180)
            page.blit(label, label.get_rect(center=sign.center))
        for dx in (-sign.width // 2 + 4, sign.width // 2 - 4):  # подвешена к потолку
            pygame.draw.line(page, SIGN_TEXT_COLOR, (center[0] + dx, HUD_HEIGHT + 4), (center[0] + dx, sign.top))

    def _render_bakery(self, labels: bool = True) -> pygame.Surface:
        """Кондитерская вверх дном: противни и венчик свисают с потолка, полка с банками
        прибита вверх ногами, табличка перевёрнута. Сама доска с рецептом и стол рисуются отдельно.
        labels=False — табличка без надписи: её рисует слой высокого разрешения."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        page.fill(WALL_COLOR)
        for x in range(0, WIDTH, 12):
            page.fill(WALL_STRIPE_COLOR, (x, HUD_HEIGHT, 4, FLOOR_TOP - HUD_HEIGHT))
        page.fill(CEILING_COLOR, (0, HUD_HEIGHT, WIDTH, 4))
        for row, y in enumerate(range(FLOOR_TOP, STATUS_TOP, 8)):  # плитка
            for column, x in enumerate(range(0, WIDTH, 8)):
                page.fill(FLOOR_COLORS[(row + column) % 2], (x, y, 8, 8))
        pygame.draw.line(page, CEILING_COLOR, (0, FLOOR_TOP - 1), (WIDTH, FLOOR_TOP - 1))
        # Доска с рецептом в деревянной раме.
        pygame.draw.rect(page, BOARD_FRAME_COLOR, BOARD.inflate(4, 4))
        pygame.draw.rect(page, BOARD_COLOR, BOARD)
        # Противни на потолке (о них спрашивает Алиса) и венчик ручкой вниз — у самой доски.
        for x, y in ((217, 40), (246, 46)):
            pygame.draw.line(page, TRAY_EDGE_COLOR, (x + 4, HUD_HEIGHT + 4), (x + 4, y))
            pygame.draw.line(page, TRAY_EDGE_COLOR, (x + 22, HUD_HEIGHT + 4), (x + 22, y))
            pygame.draw.rect(page, TRAY_COLOR, (x, y, 26, 4))
            pygame.draw.rect(page, TRAY_EDGE_COLOR, (x, y, 26, 4), 1)
        pygame.draw.line(page, TRAY_EDGE_COLOR, (211, HUD_HEIGHT + 4), (211, 36))
        pygame.draw.ellipse(page, TRAY_EDGE_COLOR, (206, 36, 11, 14), 1)
        pygame.draw.line(page, TRAY_EDGE_COLOR, (211, 36), (211, 50))
        # Полка вверх ногами: банки висят под ней крышками вниз.
        pygame.draw.rect(page, TABLE_EDGE_COLOR, (206, 58, 54, 3))
        for k, color in enumerate(((236, 120, 140), (250, 214, 110), (180, 150, 230), (150, 210, 160))):
            jar = pygame.Rect(210 + k * 12, 61, 8, 9)
            pygame.draw.rect(page, color, jar)
            pygame.draw.rect(page, (120, 90, 80), (jar.x, jar.bottom - 2, jar.width, 2))
        self._upside_down_sign(page, *SIGNS["bakery"], labels)
        # Дверь в кладовую справа — туда сбежит клубника.
        pygame.draw.rect(page, (150, 104, 70), PANTRY_DOOR)
        # Над дверью — полка с золотым блюдом Тортища. Единственная вещь здесь, которая не
        # перевёрнута: на нём стоит сам Тортище (рисуется отдельно, как персонаж).
        pygame.draw.rect(page, TABLE_COLOR, GREAT_CAKE_SHELF)
        pygame.draw.rect(page, TABLE_EDGE_COLOR, GREAT_CAKE_SHELF, 1)
        pygame.draw.ellipse(page, GOLD_COLOR, GREAT_CAKE_PLATE)
        pygame.draw.ellipse(page, GOLD_EDGE_COLOR, GREAT_CAKE_PLATE, 1)
        # Внизу тоже всё наоборот: табурет ножками вверх, кастрюля дном вверх и мешок муки.
        stool = pygame.Rect(40, 146, 22, 5)
        pygame.draw.rect(page, TABLE_EDGE_COLOR, stool)
        for x in (stool.left + 2, stool.right - 5):
            pygame.draw.rect(page, TABLE_EDGE_COLOR, (x, stool.top - 14, 3, 14))
        pygame.draw.rect(page, TRAY_COLOR, (120, 140, 26, 12), border_top_left_radius=8, border_top_right_radius=8)
        pygame.draw.rect(page, TRAY_EDGE_COLOR, (116, 150, 34, 3))
        pygame.draw.ellipse(page, (240, 232, 214), (196, 136, 22, 18))
        pygame.draw.line(page, (200, 180, 140), (201, 140), (213, 140))
        return page

    def _render_pantry(self, labels: bool = True) -> pygame.Surface:
        """Кладовая-библиотека: дощатый пол, задняя стена с полками книг, дверь из кондитерской
        и предметы раскладки — ровно по их основаниям (так видно, где можно пройти).
        labels=False — табличка без надписи: её рисует слой высокого разрешения."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        page.fill(PANTRY_WALL_COLOR)
        for row, y in enumerate(range(MAZE_BOUNDS.top - 6, STATUS_TOP, 7)):  # доски пола
            page.fill(PANTRY_FLOOR_COLORS[row % 2], (0, y, WIDTH, 7))
            for x in range((row * 37) % 60, WIDTH, 60):
                pygame.draw.line(page, PLANK_LINE_COLOR, (x, y), (x, y + 6))
        for x in range(0, WIDTH, 16):  # стена из досок
            pygame.draw.line(page, (100, 68, 50), (x, HUD_HEIGHT), (x, MAZE_BOUNDS.top - 7))
        # Полки с книгами на задней стене — по обе стороны от таблички.
        sign = self.sign_rect(*SIGNS["pantry"], hires=not labels)
        for left, right in ((MAZE_BOUNDS.left, sign.left - 6), (sign.right + 6, MAZE_BOUNDS.right)):
            shelf = pygame.Rect(left, HUD_HEIGHT + 9, right - left, 9)
            self._draw_spines(page, shelf.inflate(0, -2).move(0, -1), seed=left)
            pygame.draw.rect(page, SHELF_WOOD_COLOR, (shelf.x, shelf.bottom - 2, shelf.width, 2))
        self._upside_down_sign(page, *SIGNS["pantry"], labels)
        # Дверной проём слева, откуда пришла Алиса: в нём видна розовая кондитерская.
        doorway = pygame.Rect(0, 58, MAZE_BOUNDS.left - 4, 50)
        for row, y in enumerate(range(doorway.top, doorway.bottom, 6)):
            for column, x in enumerate(range(doorway.left, doorway.right, 6)):
                page.fill(FLOOR_COLORS[(row + column) % 2], (x, y, 6, 6))
        page.fill(PANTRY_WALL_COLOR, (0, doorway.bottom, doorway.right, 2))
        pygame.draw.line(page, (196, 150, 104), (doorway.right, doorway.top), (doorway.right, doorway.bottom))
        pygame.draw.line(page, (196, 150, 104), doorway.topleft, doorway.topright)
        if self.pantry is not None:
            for item in self.pantry.decor:  # плоские листы на полу — под всем остальным
                self._draw_item(page, item)
            for item in self.pantry.items:
                self._draw_item(page, item)
        return page

    def _draw_spines(self, page: pygame.Surface, area: pygame.Rect, seed: int) -> None:
        """Ряд книжных корешков разной ширины и цвета; рисунок зависит только от seed."""
        x = area.left
        k = seed
        while x < area.right:
            k = (k * 1103515245 + 12345) & 0x7FFFFFFF
            width = 2 + k % 3
            height = area.height - (k >> 4) % 3
            color = BOOK_COLORS[(k >> 8) % len(BOOK_COLORS)]
            page.fill(color, (x, area.bottom - height, min(width, area.right - x), height))
            x += width + ((k >> 12) % 4 == 0)

    def _draw_item(self, page: pygame.Surface, item: PantryItem) -> None:
        """Предмет кладовой по его основанию: стеллаж, стопка книг, коробки или листы на полу."""
        rect = item.rect
        seed = rect.x * 31 + rect.y * 17 + rect.width
        if item.kind == "bookcase":  # спереди: две полки корешков, сверху — доска
            visual = rect
            if rect.top == MAZE_BOUNDS.top:  # у задней стены дотянут до неё — щели нет
                visual = rect.union(pygame.Rect(rect.x, MAZE_BOUNDS.top - 8, rect.width, 1))
            pygame.draw.rect(page, SHELF_WOOD_COLOR, visual)
            page.fill(SHELF_TOP_COLOR, (visual.x, visual.y, visual.width, 3))
            inner = pygame.Rect(visual.x + 2, visual.y + 4, visual.width - 4, visual.height - 6)
            rows = 2 if inner.height >= 8 else 1
            shelf_height = inner.height // rows
            for row in range(rows):
                band = pygame.Rect(inner.x, inner.y + row * shelf_height, inner.width, shelf_height - 1)
                self._draw_spines(page, band, seed + row)
            pygame.draw.rect(page, SHELF_DARK_COLOR, visual, 1)
        elif item.kind == "tall_bookcase":  # боком, длинный в глубину: видны верхние обрезы книг
            pygame.draw.rect(page, SHELF_WOOD_COLOR, rect)
            page.fill(SHELF_TOP_COLOR, (rect.x, rect.y, rect.width, 3))
            k = seed
            for y in range(rect.y + 4, rect.bottom - 3, 3):
                k = (k * 1103515245 + 12345) & 0x7FFFFFFF
                page.fill(BOOK_COLORS[k % len(BOOK_COLORS)], (rect.x + 2, y, rect.width - 4 - (k >> 6) % 3, 2))
            pygame.draw.rect(page, SHELF_DARK_COLOR, rect, 1)
            pygame.draw.line(page, SHELF_DARK_COLOR, (rect.left, rect.bottom - 3), (rect.right - 1, rect.bottom - 3))
        elif item.kind in ("books", "cookbooks"):  # стопка: книги лежат друг на друге
            k = seed
            y = rect.bottom
            while y > rect.top:
                k = (k * 1103515245 + 12345) & 0x7FFFFFFF
                height = min(3 + k % 2, y - rect.top)
                inset = (k >> 5) % 3
                if item.kind == "cookbooks":
                    color = ((236, 150, 170), (250, 214, 228), (240, 232, 214))[(k >> 9) % 3]
                else:
                    color = BOOK_COLORS[(k >> 9) % len(BOOK_COLORS)]
                book = pygame.Rect(rect.x + inset, y - height, rect.width - 3 + (k >> 7) % 2 - inset, height)
                page.fill(color, book)
                page.fill(PAGE_COLOR, (book.right - 2, book.y + 1, 1, max(1, book.height - 1)))  # обрез страниц
                y -= height
            if item.kind == "cookbooks":  # на верхней — клубничка, это кулинарные книги
                pygame.draw.circle(page, STRAWBERRY_COLOR, (rect.centerx - 1, rect.top + 2), 1)
            pygame.draw.rect(page, SHELF_DARK_COLOR, rect, 1)
        elif item.kind == "boxes":  # коробка с лентой и клапанами
            pygame.draw.rect(page, BOX_COLOR, rect)
            page.fill(BOX_DARK_COLOR, (rect.x, rect.bottom - 4, rect.width, 4))
            pygame.draw.line(page, BOX_DARK_COLOR, (rect.centerx, rect.top), (rect.centerx, rect.bottom - 5))
            pygame.draw.line(page, PAGE_COLOR, (rect.left + 2, rect.top + 3), (rect.right - 3, rect.top + 3))
            pygame.draw.rect(page, SHELF_DARK_COLOR, rect, 1)
        else:  # плоские листы рецептов на полу: по ним ходят
            page.fill(PAGE_COLOR, rect)
            for y in range(rect.y + 1, rect.bottom - 1, 2):
                pygame.draw.line(page, (190, 176, 150), (rect.x + 1, y), (rect.right - 2, y))


def _overlap(first: pygame.Rect, second: pygame.Rect) -> int:
    """Площадь пересечения прямоугольников."""
    clip = first.clip(second)
    return clip.width * clip.height
