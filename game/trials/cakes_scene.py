"""Испытание тортов: перевёрнутая кондитерская Чучмека и сбежавшая клубника.

Две части в одной сцене:
1. Рецепт на доске перепутан задом наперёд — этапы переставляются стрелками и E/Enter
   (логика — game/trials/cakes_puzzle.py, без Pygame).
2. После правильного рецепта клубника сбегает в кладовую, и Алиса ищет её в небольшом
   лабиринте (раскладка — game/trials/cakes_maze.py), где ходит как на площади.
Реплики — в game/story/cakes_dialogue.py.

Этапы: вступление → рецепт → реакция на успех → побег клубники → поиск в кладовой →
находка → финальный диалог у рабочего стола → награда. Фрагмент
(GameProgress.complete("cakes")) выдаётся только после финальной реплики; отмена
(Backspace) в любой момент до этого возвращает на площадь без награды.
Оформление временное: кондитерская и кладовая нарисованы геометрией.

Со слоем высокого разрешения (game/graphics/hires.py) Алиса и Чучмек рисуются из исходных
кадров 64×64, а надписи — шрифтом размера окна; перевёрнутые надписи (заголовок доски до
исправления рецепта, таблички «ТОРТЫ» и «КЛАДОВАЯ») — тем же шрифтом, повёрнутым на 180°.
Кондитерская, кладовая, торт и клубника остаются пиксельными.
"""

from __future__ import annotations

import math
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
from game.story import cakes_dialogue as lines
from game.trials.cakes_maze import (
    MAZE_BOUNDS,
    MAZE_START,
    MAZE_WALLS,
    STRAWBERRY_POSITION,
    MazeWall,
    maze_collision,
    strawberry_in_reach,
)
from game.trials.cakes_puzzle import STEP_NAMES, STEP_SHORT_NAMES, STEPS, CakeRecipe, CheckResult, PickResult
from game.world.character import Character
from game.world.hub import TRIAL_SCENES
from game.world.progress import GameProgress

CAKES_SCENE = TRIAL_SCENES["cakes"]  # «trial_cakes» — имя, которое ищет портал площади
TRIAL_ID = "cakes"

# Этапы испытания.
INTRO_PHASE = "intro"
ORDERING = "ordering"  # перестановка этапов рецепта
SUCCESS_PHASE = "success"  # реакция Чучмека на правильный рецепт
ESCAPE_PHASE = "escape"  # клубника убегает, затем реплики о побеге
MAZE = "maze"  # поиск клубники в кладовой
FOUND_PHASE = "found"  # клубника поймана — короткая реакция
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
# Чучмека, порядок этапов виден целиком.
BOARD = pygame.Rect(6, 26, 196, 84)
ROW_TOP = 40
ROW_HEIGHT = 11
CHECK_ROW = len(STEPS)  # шестая строка доски — кнопка «Проверить рецепт»
CHECK_BUTTON = pygame.Rect(BOARD.x + 38, ROW_TOP + CHECK_ROW * ROW_HEIGHT + 2, 120, ROW_HEIGHT)
FLOOR_TOP = 98  # где в кондитерской стена переходит в пол
ALICE_SPOT = (222, 106)  # у доски и рабочего стола; ноги выше окна реплики
CHUCHMEK_SPOT = (298, 106)
CHUCHMEK_DOOR = (22, 100)  # в дверях кладовой — за границей лабиринта
TABLE = pygame.Rect(240, 88, 44, 12)  # рабочий стол с тортом
CAKE_CENTER = (258, 86)
STRAWBERRY_ON_TABLE = (277, 84)
ESCAPE_SECONDS = 1.4  # сколько клубника убегает до реплик
ESCAPE_FLOOR_Y = 116
TOAST_SECONDS = 3.0
TOAST_PRIORITY_SECONDS = 1.5  # столько свежее сообщение показывается вместо подсказки

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

# Надписи в разрешении окна (слой высокого разрешения); размер — в логических пикселях.
TEXT_SIZE = 8  # интерфейс и доска, как на площади
HUD_STYLE = TextStyle(TEXT_SIZE, HUD_TEXT_COLOR, background=HUD_COLOR)  # полосы вверху и внизу
TASK_STYLE = TextStyle(TEXT_SIZE, HUD_ACCENT_COLOR, background=HUD_COLOR)
CHALK_STYLE = TextStyle(TEXT_SIZE, CHALK_COLOR)
CHALK_DIM_STYLE = TextStyle(TEXT_SIZE, CHALK_DIM_COLOR)
SIGN_STYLE = TextStyle(6, SIGN_TEXT_COLOR)  # подвешенные таблички
HUD_ROWS = (6.5, 17.5)  # середины двух строк верхней полосы
BOARD_TITLE_MIDDLE = BOARD.y + 8  # середина заголовка доски — над первой строкой этапов
SIGNS = {"bakery": ("ТОРТЫ", (296, 62)), "pantry": ("КЛАДОВАЯ", (170, 34))}
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

    def __init__(self, progress: GameProgress | None = None, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.progress = progress if progress is not None else GameProgress()
        self.recipe = CakeRecipe()
        self.cursor = 0  # строка доски: этапы 0–4 и кнопка проверки
        self.collision = maze_collision()
        root = Path(characters_dir)
        alice_sprites = try_load_character_sprites(root / "alice")
        self.alice = Character(
            "Алиса",
            alice_sprites.animation_set(SPRITE_SIZE) if alice_sprites else None,
            position=ALICE_SPOT,
            speed=WALK_SPEED,
            direction=Direction.RIGHT,
        )
        self.chuchmek_sprites = try_load_character_sprites(root / "chuchmek")
        self.chuchmek_pose = lines.CHUCHMEK_IDLE_POSE
        self._chuchmek_frames: dict[str, tuple[pygame.Surface, pygame.Surface]] = {}  # поза → (исходник, на холсте)

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
        self._bakery = self._render_bakery()
        self._pantry = self._render_pantry()
        # Без надписей на табличках: их рисует слой высокого разрешения.
        self._bakery_plain = self._render_bakery(labels=False)
        self._pantry_plain = self._render_pantry(labels=False)
        self._open_dialogue(lines.INTRO)

    # --- Состояние ---

    def near_strawberry(self) -> bool:
        """Можно ли сейчас поймать клубнику: идёт поиск и Алиса в последнем закутке кладовой."""
        return self.phase == MAZE and self.dialogue is None and strawberry_in_reach(self.alice.x, self.alice.y)

    def strawberry_position(self) -> tuple[float, float] | None:
        """Где нарисовать клубнику (None — её не видно)."""
        if self.area == PANTRY:
            return None if self.strawberry_found else STRAWBERRY_POSITION
        if self.phase in (INTRO_PHASE, ORDERING, SUCCESS_PHASE):
            return STRAWBERRY_ON_TABLE
        if self.phase == ESCAPE_PHASE:
            return self._escape_position()
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
            return "Задача: найди сбежавшую клубнику"
        return "Клубника найдена"

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
            return "Стрелки/WASD — идти   E — поймать клубнику   Backspace — уйти"
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

    def _check(self) -> None:
        result = self.recipe.check()
        if result is CheckResult.SOLVED:
            self.phase = SUCCESS_PHASE
            self._open_dialogue(lines.SUCCESS)
        elif result is CheckResult.WRONG:
            # Не засчитано, но ничего не испорчено: порядок на доске остаётся, можно переставлять дальше.
            self._open_dialogue(lines.wrong_order(self.recipe.failed_checks, self.recipe.first_mistake()))

    def interact(self) -> bool:
        """E или Enter в кладовой. True, если клубника поймана."""
        if self.phase != MAZE:
            return False
        if not self.near_strawberry():
            self._show_toast("Клубника не здесь — она в дальнем углу кладовой")
            return False
        self.strawberry_found = True
        self.phase = FOUND_PHASE
        self._open_dialogue(lines.FOUND)
        return True

    def _open_dialogue(self, script: DialogueScript) -> None:
        self.alice.release_controls()  # во время реплик Алиса стоит
        self.dialogue = DialogueController(script)
        self._sync_dialogue()

    def _sync_dialogue(self) -> None:
        node = self.dialogue.node if self.dialogue is not None else None
        if node is not None and node.id in lines.CHUCHMEK_POSES:
            self.chuchmek_pose = lines.CHUCHMEK_POSES[node.id]

    def _dialogue_finished(self) -> None:
        """Реплика закрыта: следующий этап испытания."""
        self.dialogue = None
        self.chuchmek_pose = lines.CHUCHMEK_IDLE_POSE
        if self.phase == INTRO_PHASE:
            self.phase = ORDERING
        elif self.phase == SUCCESS_PHASE:
            self.phase = ESCAPE_PHASE  # клубника убегает — дальше в update
            self.escape_time = 0.0
            self.chuchmek_pose = lines.CHUCHMEK_PANIC_POSE
        elif self.phase == ESCAPE_PHASE:
            self._enter_pantry()
        elif self.phase == FOUND_PHASE:
            self._return_to_bakery()
        elif self.phase == FINAL_PHASE:
            self._complete()

    def _enter_pantry(self) -> None:
        """Погоня: Алиса у двери кладовой, дальше — пешком по лабиринту."""
        self.phase = MAZE
        self.area = PANTRY
        self.alice.release_controls()
        self.alice.set_position(*MAZE_START)
        self.alice.face(Direction.RIGHT)
        self.alice.collider = self.collision.move
        self._show_toast("Кладовая: найди клубнику в дальнем углу")

    def _return_to_bakery(self) -> None:
        """Клубника поймана — назад к рабочему столу, на финальный разговор."""
        self.phase = FINAL_PHASE
        self.area = BAKERY
        self.alice.release_controls()
        self.alice.collider = None
        self.alice.set_position(*ALICE_SPOT)
        self.alice.face(Direction.RIGHT)
        self._open_dialogue(lines.FINAL)

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
            chuchmek_spot = CHUCHMEK_SPOT
        else:
            surface.blit(self._pantry if hires is None else self._pantry_plain, (0, 0))
            chuchmek_spot = CHUCHMEK_DOOR
        if hires is not None:  # перевёрнутая табличка — часть фона, под персонажами
            text, center = SIGNS[self.area]
            hires.text(text, SIGN_STYLE, self.sign_rect(text, center, hires=True).center, anchor="center", angle=180)
        drawables = [
            (chuchmek_spot[1], lambda: self._draw_chuchmek(surface, chuchmek_spot, hires)),
            (self.alice.y + 0.1, lambda: self._draw_alice(surface, hires)),
        ]
        strawberry = self.strawberry_position()
        if strawberry is not None:
            drawables.append((strawberry[1] + 5, lambda: self._draw_loose_strawberry(surface, strawberry, hires)))
        for _, draw in sorted(drawables, key=lambda item: item[0]):
            draw()
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

    def _draw_chuchmek(self, canvas: pygame.Surface, spot: tuple[int, int], hires: HiResLayer | None = None) -> None:
        source, image = self._chuchmek_frame()
        rect = image.get_rect(midbottom=spot)
        if hires is not None:
            hires.sprite(source, rect)  # исходный кадр на том же месте и того же размера, без отражения
        else:
            canvas.blit(image, rect)

    def _chuchmek_image(self) -> pygame.Surface:
        """Поза Чучмека из манифеста chuchmek, уменьшенная ближайшим соседом; без отражения."""
        return self._chuchmek_frame()[1]

    def _chuchmek_frame(self) -> tuple[pygame.Surface, pygame.Surface]:
        """Поза Чучмека: исходный кадр манифеста chuchmek (без отражения) и он же на холсте."""
        pose = self.chuchmek_pose
        if pose not in self._chuchmek_frames:
            sprites: CharacterSprites | None = self.chuchmek_sprites
            if sprites is None:
                source = image = placeholder_animations().default.frames[0]
            else:
                try:
                    source = sprites.frame(pose).image
                except KeyError:
                    source = sprites.frames[0].image
                image = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
            self._chuchmek_frames[pose] = (source, image)
        return self._chuchmek_frames[pose]

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
        # Противни на потолке (о них спрашивает Алиса) и венчик ручкой вниз.
        for x, y in ((214, 40), (246, 46)):
            pygame.draw.line(page, TRAY_EDGE_COLOR, (x + 4, HUD_HEIGHT + 4), (x + 4, y))
            pygame.draw.line(page, TRAY_EDGE_COLOR, (x + 22, HUD_HEIGHT + 4), (x + 22, y))
            pygame.draw.rect(page, TRAY_COLOR, (x, y, 26, 4))
            pygame.draw.rect(page, TRAY_EDGE_COLOR, (x, y, 26, 4), 1)
        pygame.draw.line(page, TRAY_EDGE_COLOR, (284, HUD_HEIGHT + 4), (284, 36))
        pygame.draw.ellipse(page, TRAY_EDGE_COLOR, (279, 36, 11, 14), 1)
        pygame.draw.line(page, TRAY_EDGE_COLOR, (284, 36), (284, 50))
        # Полка вверх ногами: банки висят под ней крышками вниз.
        pygame.draw.rect(page, TABLE_EDGE_COLOR, (206, 58, 54, 3))
        for k, color in enumerate(((236, 120, 140), (250, 214, 110), (180, 150, 230), (150, 210, 160))):
            jar = pygame.Rect(210 + k * 12, 61, 8, 9)
            pygame.draw.rect(page, color, jar)
            pygame.draw.rect(page, (120, 90, 80), (jar.x, jar.bottom - 2, jar.width, 2))
        self._upside_down_sign(page, *SIGNS["bakery"], labels)
        # Дверь в кладовую справа — туда сбежит клубника.
        pygame.draw.rect(page, (150, 104, 70), (WIDTH - 8, 66, 8, FLOOR_TOP - 66))
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
        """Кладовая: дощатый пол, задняя стена, дверь из кондитерской и стеллажи-«змейка».
        labels=False — табличка без надписи: её рисует слой высокого разрешения."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        page.fill(PANTRY_WALL_COLOR)
        for row, y in enumerate(range(MAZE_BOUNDS.top - 6, STATUS_TOP, 7)):  # доски пола
            page.fill(PANTRY_FLOOR_COLORS[row % 2], (0, y, WIDTH, 7))
            for x in range((row * 37) % 60, WIDTH, 60):
                pygame.draw.line(page, PLANK_LINE_COLOR, (x, y), (x, y + 6))
        for x in range(0, WIDTH, 16):  # стена из досок
            pygame.draw.line(page, (100, 68, 50), (x, HUD_HEIGHT), (x, MAZE_BOUNDS.top - 7))
        self._upside_down_sign(page, *SIGNS["pantry"], labels)
        # Дверной проём слева, откуда пришли Алиса и Чучмек: в нём видна розовая кондитерская.
        doorway = pygame.Rect(0, 58, MAZE_BOUNDS.left - 4, 50)
        for row, y in enumerate(range(doorway.top, doorway.bottom, 6)):
            for column, x in enumerate(range(doorway.left, doorway.right, 6)):
                page.fill(FLOOR_COLORS[(row + column) % 2], (x, y, 6, 6))
        page.fill(PANTRY_WALL_COLOR, (0, doorway.bottom, doorway.right, 2))
        pygame.draw.line(page, (196, 150, 104), (doorway.right, doorway.top), (doorway.right, doorway.bottom))
        pygame.draw.line(page, (196, 150, 104), doorway.topleft, doorway.topright)
        for wall in MAZE_WALLS:
            self._draw_wall(page, wall)
        return page

    def _draw_wall(self, page: pygame.Surface, wall: MazeWall) -> None:
        """Стеллаж лабиринта ровно по его основанию (так видно, где можно пройти)."""
        rect = wall.rect
        # Стеллажи у задней стены дотянуты до неё — щели между ними и стеной нет.
        visual = rect
        if rect.top == MAZE_BOUNDS.top:
            visual = rect.union(pygame.Rect(rect.x, MAZE_BOUNDS.top - 8, rect.width, 1))
        palette = {
            "jars": ((130, 90, 64), (236, 120, 140)),
            "sacks": ((200, 180, 140), (240, 232, 214)),
            "trays": ((96, 96, 110), (176, 176, 190)),
            "boxes": ((226, 150, 176), (252, 214, 228)),
        }
        dark, light = palette[wall.kind]
        pygame.draw.rect(page, dark, visual)
        for k, y in enumerate(range(visual.top + 3, visual.bottom - 4, 9)):
            if wall.kind == "jars":  # полка с банками варенья
                pygame.draw.line(page, (90, 60, 44), (visual.left, y + 7), (visual.right - 1, y + 7))
                pygame.draw.rect(page, light if k % 2 else (250, 214, 110), (visual.left + 3, y + 1, 4, 6))
                pygame.draw.rect(page, (180, 150, 230), (visual.left + 9, y + 2, 4, 5))
            elif wall.kind == "sacks":  # мешки с мукой
                pygame.draw.rect(page, light, (visual.left + 1 + k % 2, y, visual.width - 3, 8), border_radius=3)
            elif wall.kind == "trays":  # стойка с противнями
                pygame.draw.line(page, light, (visual.left + 1, y + 4), (visual.right - 2, y + 4))
            else:  # коробки для тортов с лентой
                box = pygame.Rect(visual.left + 1, y, visual.width - 2, 8)
                pygame.draw.rect(page, light, box)
                pygame.draw.line(page, STRAWBERRY_COLOR, (box.centerx, box.top), (box.centerx, box.bottom - 1))
        pygame.draw.rect(page, (60, 40, 30), visual, 1)
        pygame.draw.line(page, (60, 40, 30), (visual.left, visual.bottom - 3), (visual.right - 1, visual.bottom - 3))

