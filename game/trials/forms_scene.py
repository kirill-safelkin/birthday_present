"""Испытание формуляров: архив гуся-инспектора, где Алиса оформляет документы Лео — находит
три документа и сдаёт их в правильном порядке, чтобы сказочный архив зарегистрировал его
рождение и признал гражданином Страны Чудес.

Логика архива, стола подачи и выдачи документов — в game/trials/forms_puzzle.py (без Pygame),
реплики — в game/story/forms_dialogue.py. Здесь только сцена: движение Алисы (Character и
CollisionMap, как на площади), шкафы-разделы, стол подачи с тремя местами, гусь, лист
выданного документа и интерфейс.

Комната компактная и вся доступна: у задней стены пять шкафов, в середине — большой стол подачи,
справа у стены — гусь, слева внизу — вход. Документы — листы бумаги примерно формата A4 с полным
названием (draw_paper): найденный документ Алиса рассматривает крупным листом рядом с собой, в руках
несёт маленький лист того же вида, а на столе он лежит листом, где название читается целиком.
Разговоры начинаются только выше окна реплики (у шкафов, у гуся и у входа), поэтому окно
никогда не закрывает персонажей, хотя ходить можно до самого низа комнаты.

Этапы: вступление → поиск и раскладка документов → приём документов и разрешение на получение
гражданства → гражданство Лео и финал → награда. Фрагмент (GameProgress.complete("forms"))
выдаётся только после финальной реплики; отмена (Backspace) в любой момент до этого
возвращает на площадь без награды. Оформление временное: архив нарисован геометрией.

Со слоем высокого разрешения (game/graphics/hires.py) Алиса и гусь рисуются из исходных
кадров 64×64, а надписи (таблички шкафов, стола и плаката, названия на листах документов,
интерфейс) — шрифтом размера окна; архив остаётся пиксельным. Листы документов и лист
выданного документа над столом — логическая графика, их надписи — тоже шрифтом окна.
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
from game.story.forms_dialogue import (
    FINAL,
    GOOSE_IDLE_POSE,
    GOOSE_POSES,
    INSPECTION,
    INTRO,
    ISSUE_NODES,
    all_scripts,
    goose_hint,
    goose_holding,
    goose_rejection,
    search_script,
)
from game.trials.forms_puzzle import (
    DOCUMENT_NAMES,
    DOCUMENT_TITLES,
    DOCUMENTS,
    SECTIONS,
    CheckResult,
    FormsPuzzle,
    SearchResult,
    Section,
    SlotResult,
)
from game.world.character import Character
from game.world.collision import CollisionMap
from game.world.hub import TRIAL_SCENES
from game.world.progress import GameProgress

FORMS_SCENE = TRIAL_SCENES["forms"]  # «trial_forms» — имя, которое ищет портал площади
TRIAL_ID = "forms"

# Этапы испытания.
INTRO_PHASE = "intro"
EXPLORE = "explore"  # поиск документов, раскладка на столе и сдача гусю
REACTION = "reaction"  # приём документов и разрешение на получение гражданства
FINAL_PHASE = "final"  # гражданство Лео и фрагмент
DONE = "done"

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 32  # как на площади
WALK_SPEED = 64
HUD_HEIGHT = 12  # одна строка: задача, а пока документ в руках — его полное название
STATUS_TOP = 168
SHELVES = pygame.Rect(0, HUD_HEIGHT, WIDTH, 44)  # задняя стена со шкафами
# Ноги Алисы: весь пол комнаты, от шкафов до низа. Внизу только пол вокруг стола — разговоров там
# не бывает: их начинают у шкафов, у гуся и у входа, а это всё выше окна реплики.
WALK_BOUNDS = pygame.Rect(10, SHELVES.bottom, WIDTH - 20, STATUS_TOP - 4 - SHELVES.bottom)
CABINET_WIDTH = 50
CABINET_XS = (30, 83, 136, 189, 242)  # центры шкафов, по одному на раздел архива; справа — место гуся
CABINET_POINT_Y = WALK_BOUNDS.top + 6  # точка взаимодействия — вплотную к шкафу
CABINET_REACH = 12
# Главный стол подачи — в середине комнаты: столешница с тремя листами и передняя стенка с табличкой.
TABLE = pygame.Rect(66, 78, 188, 88)
TABLE_TOP = pygame.Rect(TABLE.x, TABLE.y, TABLE.width, 78)  # столешница; ниже — передняя стенка
PAPER_SIZE = (48, 64)  # лист на столе — примерно A4, название в нём читается целиком
SLOT_XS = (104, 160, 216)  # места 1, 2, 3 на столе: середины листов
PAPER_TOP = TABLE.top + 4
SLOT_Y = TABLE.top - 2  # Алиса стоит за столом, лицом к залу, листы — перед ней
SLOT_REACH = 12
GOOSE_POSITION = (292, 82)  # у правой стены, рядом со столом; подойти можно слева и снизу
GOOSE_REACH = 24
# Шире самого гуся: Алиса останавливается на шаг от него, и спрайты не наползают друг на друга.
GOOSE_OBSTACLE = pygame.Rect(276, 72, 30, 12)
PAPER_STACKS = (pygame.Rect(16, 148, 14, 12), pygame.Rect(288, 146, 16, 14))  # стопки бумаг в углах
SPAWN = (30, 104)  # у входа в архив, вдали от шкафов и стола
DOORMAT = pygame.Rect(16, 99, 28, 9)  # коврик у входа
TOAST_SECONDS = 3.0
TOAST_PRIORITY_SECONDS = 1.5  # столько свежее сообщение показывается вместо подсказки у цели

WALL_COLOR = (74, 60, 58)
CABINET_COLOR = (112, 80, 56)
CABINET_DARK_COLOR = (76, 52, 38)
CABINET_EDGE_COLOR = (150, 112, 78)
SHELF_COLOR = (60, 42, 32)
PLAQUE_COLOR = (236, 222, 180)
PLAQUE_TEXT_COLOR = (60, 44, 36)
FOLDER_COLORS = ((196, 170, 110), (150, 170, 196), (196, 132, 112), (170, 190, 140), (214, 200, 160))
FLOOR_COLORS = ((150, 124, 96), (138, 112, 86))
BASEBOARD_COLOR = (58, 44, 40)
DOORMAT_COLOR = (150, 60, 56)
DOORMAT_EDGE_COLOR = (226, 196, 120)
TABLE_COLOR = (170, 128, 88)
TABLE_LIGHT_COLOR = (186, 144, 102)
TABLE_FRONT_COLOR = (124, 88, 60)
TABLE_EDGE_COLOR = (96, 66, 46)
PAPER_COLOR = (248, 244, 230)
PAPER_EDGE_COLOR = (170, 160, 140)
PAPER_SHADOW_COLOR = (112, 78, 52)
INK_COLOR = (150, 140, 126)  # строки бланка и штрихи вместо мелкого текста
SIGN_COLOR = (230, 220, 190)
DOCUMENT_COLORS = {"form_request": (60, 90, 170), "filing_permit": (190, 50, 50), "leo_application": (120, 70, 150)}
STAMP_COLOR = (190, 50, 50)  # штемпельная подушка и печать на разрешении
SEAL_COLOR = (214, 168, 60)  # золотая печать свидетельства
SEAL_RIBBON_COLOR = (60, 110, 180)
ISSUED_SHEET_COLOR = (250, 240, 214)
ISSUED_TITLE_COLOR = (150, 40, 40)
ISSUED_TEXT_COLOR = (70, 50, 40)
BUNDLE_COLORS = ((176, 204, 236), (236, 196, 212))  # свёртки на полке «Рождений»
BUNDLE_FACE_COLOR = (244, 214, 186)
HUD_COLOR = (44, 38, 58)
HUD_TEXT_COLOR = (240, 230, 206)
HUD_ACCENT_COLOR = (250, 206, 108)
DONE_COLOR = (140, 220, 150)
EMPTY_COLOR = (130, 124, 146)
MARK_COLOR = (255, 236, 140)
# Названия на листах — целиком, по смыслу разбитые на строки: предлог остаётся со своим словом.
PAPER_TITLE_LINES = {
    "form_request": ("Заявление", "на выдачу", "бланка", "заявления"),
    "filing_permit": ("Разрешение", "на подачу", "заявления"),
    "leo_application": ("Заявление", "о регистрации", "рождения", "и гражданстве", "Лео"),
}
# Лист выданного документа над столом подачи: заголовок и строки под ним.
ISSUED_SHEET = pygame.Rect(86, 50, 148, 26)  # над столом, в проходе у шкафов: листы на столе видны
ISSUED_LINES = {
    "citizenship_permit": ("РАЗРЕШЕНИЕ", "на получение гражданства Лео"),
    "citizenship": ("СВИДЕТЕЛЬСТВО", "Рождение Лео зарегистрировано", "Лео — гражданин Страны Чудес"),
}
ISSUED_LINE_HEIGHT = 7
APRON_SIGN = "ПРИЁМ ДОКУМЕНТОВ: ВЧЕРА"  # табличка на передней стенке стола подачи
POSTER = pygame.Rect(270, 15, 46, 32)  # плакат на стене над гусем
POSTER_LINES = ("ТИХО!", "ИДЁТ", "СОГЛАСОВАНИЕ")

# Надписи в разрешении окна (слой высокого разрешения); размер — в логических пикселях.
TEXT_SIZE = 8  # интерфейс, как на площади
SMALL_SIZE = 6  # таблички шкафов и стола, номера мест на столе
PAPER_TITLE_SIZE = 5  # название на листе, лежащем на столе
PREVIEW_TITLE_SIZE = 6  # название на крупном листе, который Алиса рассматривает
POSTER_SIZE = 4.5
ISSUED_SIZE = 5.5
HUD_STYLE = TextStyle(TEXT_SIZE, HUD_TEXT_COLOR, background=HUD_COLOR)  # полосы вверху и внизу
TASK_STYLE = TextStyle(TEXT_SIZE, HUD_ACCENT_COLOR, background=HUD_COLOR)
PLAQUE_STYLE = TextStyle(SMALL_SIZE, PLAQUE_TEXT_COLOR, background=PLAQUE_COLOR)  # табличка шкафа
SIGN_STYLE = TextStyle(SMALL_SIZE, PLAQUE_TEXT_COLOR, background=SIGN_COLOR)  # табличка стола
POSTER_STYLE = TextStyle(POSTER_SIZE, STAMP_COLOR, bold=True, background=SIGN_COLOR)
SLOT_NUMBER_STYLE = TextStyle(SMALL_SIZE, PAPER_COLOR)
ISSUED_TITLE_STYLE = TextStyle(ISSUED_SIZE, ISSUED_TITLE_COLOR)
ISSUED_TEXT_STYLE = TextStyle(ISSUED_SIZE, ISSUED_TEXT_COLOR)
# Где рисуется стол подачи: столешница, листы, рамка у выбранного места и сияющая печать.
TABLE_AREA = TABLE.inflate(4, 4)
PREVIEW_SIZE = (58, 78)  # найденный документ крупно — Алиса рассматривает его рядом с собой
HELD_PAPER_SIZE = (12, 16)  # тот же лист в руках, над головой Алисы


def paper_style(document: str, size: float) -> TextStyle:
    """Шрифт названия на листе: цвет вида документа, фон — бумага (строки стоят на чистом листе)."""
    return TextStyle(size, DOCUMENT_COLORS[document], background=PAPER_COLOR)


def slot_paper(index: int) -> pygame.Rect:
    """Лист на месте index стола подачи."""
    rect = pygame.Rect((0, 0), PAPER_SIZE)
    rect.midtop = (SLOT_XS[index], PAPER_TOP)
    return rect


@dataclass(frozen=True)
class Cabinet:
    section: Section
    x: int

    @property
    def point(self) -> tuple[int, int]:
        return self.x, CABINET_POINT_Y

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x - CABINET_WIDTH // 2, SHELVES.top, CABINET_WIDTH, SHELVES.height)


CABINETS = tuple(Cabinet(section, x) for section, x in zip(SECTIONS, CABINET_XS))


@dataclass(frozen=True)
class Target:
    """С чем Алиса может взаимодействовать сейчас: шкаф, место на столе или гусь."""

    kind: str  # "cabinet", "slot" или "goose"
    section: str | None = None
    slot: int | None = None


class FormsTrialScene(Scene):
    """Архив формуляров. Открывается верхним порталом площади и закрывается возвратом на неё."""

    supports_hires = True

    def __init__(self, progress: GameProgress | None = None, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.progress = progress if progress is not None else GameProgress()
        self.puzzle = FormsPuzzle()
        root = Path(characters_dir)
        self.collision = CollisionMap(WALK_BOUNDS, [SHELVES, TABLE, GOOSE_OBSTACLE, *PAPER_STACKS])
        alice_sprites = try_load_character_sprites(root / "alice")
        self.alice = Character(
            "Алиса",
            alice_sprites.animation_set(SPRITE_SIZE) if alice_sprites else None,
            position=SPAWN,
            speed=WALK_SPEED,
            direction=Direction.RIGHT,
        )
        self.alice.collider = self.collision.move
        self.goose_sprites = try_load_character_sprites(root / "goose_inspector")
        self.goose_pose = GOOSE_IDLE_POSE
        self._goose_frames: dict[str, tuple[pygame.Surface, pygame.Surface]] = {}  # поза → (исходник, на холсте)

        self.box = DialogueBox()
        for script in all_scripts():
            self.box.check_fits(script)
        self.phase = INTRO_PHASE
        self.dialogue: DialogueController | None = None
        self.reward_given = False  # True, если именно это прохождение добавило фрагмент
        self.completed = False
        self.toast = ""
        self._toast_time = 0.0
        self._toast_after_dialogue = ""  # сообщение, которое появится, когда закроется реплика
        self.found_document: str | None = None  # только что найденный документ: Алиса его рассматривает
        self.time = 0.0
        self._font = load_font(9)
        self._small_font = load_font(7)
        self._text_cache: dict[tuple[str, config.Color, bool], pygame.Surface] = {}
        self._fonts = TextFonts()
        self.text_metrics = self._fonts.metrics(HUD_STYLE)
        self._background = self._render_background()
        self._background_plain = self._render_background(labels=False)  # надписи рисует слой окна
        self._open_dialogue(INTRO)

    # --- Состояние ---

    def nearby(self) -> Target | None:
        """Ближайшее, с чем можно взаимодействовать из точки под ногами Алисы."""
        feet = (self.alice.x, self.alice.y)
        candidates: list[tuple[float, Target]] = []
        for cabinet in CABINETS:
            # Перед любой частью шкафа, а не только перед его серединой: шкафы не соприкасаются,
            # поэтому выбор раздела однозначен.
            dx = abs(feet[0] - cabinet.x)
            distance = abs(feet[1] - CABINET_POINT_Y)
            if dx <= CABINET_WIDTH // 2 and distance <= CABINET_REACH:
                candidates.append((distance, Target("cabinet", section=cabinet.section.id)))
        for index, x in enumerate(SLOT_XS):
            distance = math.dist(feet, (x, SLOT_Y))
            if distance <= SLOT_REACH:
                candidates.append((distance, Target("slot", slot=index)))
        distance = math.dist(feet, GOOSE_POSITION)
        if distance <= GOOSE_REACH:
            candidates.append((distance, Target("goose")))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def task_text(self) -> str:
        """Текущая задача — верхняя строка интерфейса."""
        puzzle = self.puzzle
        if self.phase == INTRO_PHASE:
            return "Архив формуляров"
        if puzzle.citizen:
            return "Лео — гражданин Страны Чудес"
        if puzzle.solved:
            return "Документы Лео приняты"
        if not puzzle.all_found:
            return f"Задача: найди документы Лео {puzzle.found_count}/{len(DOCUMENTS)}"
        return "Задача: сложи по порядку и сдай гусю"

    def held_text(self) -> str:
        """Документ в руках — полным названием (строка интерфейса вместо задачи)."""
        held = self.puzzle.held
        return f"В руках: {DOCUMENT_TITLES[held]}" if held else ""

    def hud_text(self) -> str:
        """Верхняя строка: документ в руках, а без него — текущая задача."""
        return self.held_text() or self.task_text()

    def preview_rect(self) -> pygame.Rect:
        """Где Алиса рассматривает найденный документ: крупный лист сбоку от неё, где больше места,
        выше окна реплики и ниже полосы интерфейса."""
        rect = pygame.Rect((0, 0), PREVIEW_SIZE)
        alice = self.alice.rect
        if alice.centerx < WIDTH // 2:
            rect.left = alice.right + 2
        else:
            rect.right = alice.left - 2
        rect.clamp_ip(pygame.Rect(4, HUD_HEIGHT + 4, WIDTH - 8, STATUS_TOP))
        rect.top = HUD_HEIGHT + 8
        return rect

    def prompt(self) -> str | None:
        target = self.nearby() if self.phase == EXPLORE and self.dialogue is None else None
        if target is None:
            return None
        puzzle = self.puzzle
        if target.kind == "cabinet":
            return f"«{puzzle.sections[target.section].name}»   E — искать"
        if target.kind == "slot":
            number = target.slot + 1
            if not puzzle.all_found:
                return f"Стол подачи   найдено документов: {puzzle.found_count}/{len(DOCUMENTS)}"
            if puzzle.held is None:
                return f"Место {number}: {DOCUMENT_NAMES[puzzle.order[target.slot]]}   E — взять"
            if target.slot == puzzle.held_from:
                return f"Место {number}   E — положить обратно"
            return f"Место {number}: {DOCUMENT_NAMES[puzzle.order[target.slot]]}   E — поменять местами"
        if puzzle.all_found and puzzle.held is None:
            return "Гусь-инспектор   E — сдать документы"
        return "Гусь-инспектор   E — спросить совета"

    def status_text(self) -> str:
        """Нижняя полоса: свежее сообщение, подсказка у цели или управление."""
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
        if self.phase != EXPLORE:
            return
        self.alice.handle_event(event)
        if Action.INTERACT in actions:
            self.interact()

    def interact(self) -> bool:
        """E или Enter во время поиска. True, если рядом была цель."""
        target = self.nearby()
        if self.phase != EXPLORE or target is None:
            return False
        if target.kind == "cabinet":
            self._search(target.section)
        elif target.kind == "slot":
            self._use_slot(target.slot)
        else:
            self._submit()
        return True

    def _search(self, section_id: str) -> None:
        result = self.puzzle.search(section_id)
        if result is SearchResult.FOUND:
            found, total = self.puzzle.found_count, len(DOCUMENTS)
            document = self.found_document = self.puzzle.found[-1]
            if found < total:
                self._toast_after_dialogue = f"На столе подачи: {DOCUMENT_NAMES[document]} ({found}/{total})"
            else:
                self._toast_after_dialogue = "Все документы на столе — разложи их по порядку"
        self._open_dialogue(search_script(section_id, result, self.puzzle.searches[section_id]))

    def _use_slot(self, index: int) -> None:
        puzzle = self.puzzle
        held, here = puzzle.held, puzzle.order[index]
        result = puzzle.use_slot(index)
        if result is SlotResult.NOT_READY:
            self._show_toast(f"Сначала найди все документы: {puzzle.found_count}/{len(DOCUMENTS)}")
        elif result is SlotResult.TAKEN:
            self._show_toast(f"Взяла: {DOCUMENT_NAMES[here]}")
        elif result is SlotResult.PUT_BACK:
            self._show_toast(f"Положила обратно: {DOCUMENT_NAMES[held]}")
        elif result is SlotResult.SWAPPED:
            self._show_toast(f"Поменяла местами: {DOCUMENT_NAMES[held]} и {DOCUMENT_NAMES[here]}")

    def _submit(self) -> None:
        """Разговор с гусём: сдать документы, если они готовы, иначе — подсказка."""
        puzzle = self.puzzle
        result = puzzle.check()
        if result is CheckResult.MISSING:
            missing = next(document for document in DOCUMENTS if not puzzle.is_found(document))
            self._open_dialogue(goose_hint(missing))
        elif result is CheckResult.HOLDING:
            self._open_dialogue(goose_holding())
        elif result is CheckResult.WRONG_ORDER:
            # Не засчитано, но ничего не испорчено: документы остаются на столе.
            self._open_dialogue(goose_rejection(puzzle.failed_checks, puzzle.first_mistake()))
        elif result is CheckResult.ACCEPTED:
            self.phase = REACTION
            self._open_dialogue(INSPECTION)

    def _open_dialogue(self, script: DialogueScript) -> None:
        self.alice.release_controls()  # во время реплик Алиса стоит
        self.dialogue = DialogueController(script)
        self._sync_dialogue()

    def _sync_dialogue(self) -> None:
        node = self.dialogue.node if self.dialogue is not None else None
        if node is not None and node.id in GOOSE_POSES:
            self.goose_pose = GOOSE_POSES[node.id]
        if node is not None and node.id in ISSUE_NODES:
            self.puzzle.issue(ISSUE_NODES[node.id])  # печать и лист документа — на этой реплике

    def _dialogue_finished(self) -> None:
        """Реплика закрыта: следующий этап испытания."""
        self.dialogue = None
        self.found_document = None  # рассмотрела — документ уже лежит на столе
        self.goose_pose = GOOSE_IDLE_POSE
        if self._toast_after_dialogue:
            self._show_toast(self._toast_after_dialogue)
            self._toast_after_dialogue = ""
        if self.phase == INTRO_PHASE:
            self.phase = EXPLORE
        elif self.phase == REACTION:
            self.puzzle.issue("citizenship_permit")  # уже выдано на реплике — повторно не выдаётся
            self.phase = FINAL_PHASE
            self._open_dialogue(FINAL)
        elif self.phase == FINAL_PHASE:
            self.puzzle.issue("citizenship")
            self._complete()

    def _complete(self) -> None:
        """Финальная проверка пройдена: фрагмент (без повторов — это решает GameProgress) и назад."""
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
        if self._toast_time > 0:
            self._toast_time -= dt
            if self._toast_time <= 0:
                self.toast = ""

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рисует архив на холсте; со слоем hires персонажи и надписи уходят в него
        (см. game/graphics/hires.py), а порядок слоёв остаётся тем же."""
        surface.blit(self._background if hires is None else self._background_plain, (0, 0))
        target = self.nearby() if self.phase == EXPLORE and self.dialogue is None else None
        for cabinet in CABINETS:
            self._draw_cabinet_marks(surface, cabinet, target is not None and target.section == cabinet.section.id)
        if hires is not None:  # надписи фона — под персонажами
            for cabinet in CABINETS:
                hires.text(cabinet.section.label, PLAQUE_STYLE, self.cabinet_plaque(cabinet).center, anchor="center")
            for text, center in poster_layout():
                hires.text(text, POSTER_STYLE, center, anchor="center")
        near_goose = target is not None and target.kind == "goose"
        drawables = [
            (TABLE.bottom, lambda: self._draw_table(surface, target, hires)),
            (GOOSE_POSITION[1], lambda: self._draw_goose(surface, near_goose, hires)),
            (self.alice.y + 0.1, lambda: self._draw_alice(surface, hires)),
        ]
        for _, draw in sorted(drawables, key=lambda item: item[0]):
            draw()
        if self.puzzle.issued:
            self._draw_issued(surface, self.puzzle.issued[-1], hires)
        if self.found_document is not None and self.dialogue is not None:
            self._draw_preview(surface, self.found_document, hires)
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

    def _draw_cabinet_marks(self, surface: pygame.Surface, cabinet: Cabinet, highlighted: bool) -> None:
        """Что меняется на шкафу: галочка, если в нём уже искали, и рамка, если Алиса рядом."""
        rect = cabinet.rect
        if self.puzzle.searches[cabinet.section.id]:
            # Значок в нижнем углу, чтобы не закрывать табличку: зелёный — здесь нашёлся документ.
            badge = pygame.Rect(rect.right - 13, rect.bottom - 10, 10, 8)
            surface.fill(HUD_COLOR, badge)
            color = DONE_COLOR if cabinet.section.document else EMPTY_COLOR
            x, y = badge.x + 2, badge.y + 2
            pygame.draw.lines(surface, color, False, [(x, y + 2), (x + 2, y + 4), (x + 6, y)])
        if highlighted:
            pygame.draw.rect(surface, MARK_COLOR, rect.inflate(2, 0), 1)

    def held_icon_center(self) -> tuple[int, int]:
        """Где рисуется документ в руках: маленький лист над головой Алисы (шкафы ниже полосы интерфейса)."""
        rect = self.alice.rect
        return rect.centerx, rect.top - HELD_PAPER_SIZE[1] // 2 - 1

    def _draw_alice(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        self.alice.draw(canvas, hires)
        held = self.puzzle.held
        if held is not None:
            x, y = self.held_icon_center()
            paper = pygame.Rect((0, 0), HELD_PAPER_SIZE)
            paper.center = (x, y - round(abs(math.sin(self.time * 4))))
            with logical_target(canvas, hires, paper.inflate(2, 4)) as surface:
                draw_paper(surface, paper, held)  # тот же лист, что на столе; название — в строке интерфейса

    def _draw_preview(self, canvas: pygame.Surface, document: str, hires: HiResLayer | None = None) -> None:
        """Найденный документ крупно: Алиса рассматривает лист, пока звучит реплика о находке."""
        rect = self.preview_rect()
        with logical_target(canvas, hires, rect.inflate(4, 4)) as surface:
            draw_paper(surface, rect, document, PREVIEW_TITLE_SIZE, with_title=hires is None)
        if hires is not None:
            for text, center in paper_title_layout(rect, document, PREVIEW_TITLE_SIZE):
                hires.text(text, paper_style(document, PREVIEW_TITLE_SIZE), center, anchor="center")

    def _draw_table(self, canvas: pygame.Surface, target: Target | None, hires: HiResLayer | None = None) -> None:
        with logical_target(canvas, hires, TABLE_AREA) as surface:
            self._draw_table_on(surface, target, with_text=hires is None)
        if hires is not None:  # номера мест, табличка и названия на листах — поверх стола
            for index in range(len(SLOT_XS)):
                hires.text(str(index + 1), SLOT_NUMBER_STYLE, self.slot_number(index).center, anchor="center")
                document = self.puzzle.order[index]
                if document is not None:
                    for text, center in paper_title_layout(slot_paper(index), document, PAPER_TITLE_SIZE):
                        hires.text(text, paper_style(document, PAPER_TITLE_SIZE), center, anchor="center")
            hires.text(APRON_SIGN, SIGN_STYLE, self.apron_sign(hires=True).center, anchor="center")

    @staticmethod
    def slot_number(index: int) -> pygame.Rect:
        """Табличка с номером места — на столешнице под листом."""
        plate = pygame.Rect(0, 0, 9, 8)
        plate.midtop = (SLOT_XS[index], PAPER_TOP + PAPER_SIZE[1] + 1)
        return plate

    def apron_sign(self, hires: bool = False) -> pygame.Rect:
        """Табличка на передней стенке стола — по размеру надписи пиксельным шрифтом или шрифтом окна."""
        if hires:
            width, height = self._fonts.metrics(SIGN_STYLE).size(APRON_SIGN)
            label = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        else:
            label = render_text(self._small_font, APRON_SIGN, PLAQUE_TEXT_COLOR).get_rect()
        label.center = (TABLE.centerx, (TABLE_TOP.bottom + TABLE.bottom) // 2)
        return label.inflate(6, 2)

    def _draw_table_on(self, surface: pygame.Surface, target: Target | None, with_text: bool) -> None:
        """Большой стол подачи: столешница с тремя местами, передняя стенка с табличкой."""
        top, front = TABLE_TOP, pygame.Rect(TABLE.x + 2, TABLE_TOP.bottom, TABLE.width - 4, TABLE.bottom - TABLE_TOP.bottom)
        pygame.draw.rect(surface, TABLE_FRONT_COLOR, front)
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, front, 1)
        pygame.draw.rect(surface, TABLE_COLOR, top)
        for y in range(top.y + 6, top.bottom - 2, 9):  # доски столешницы
            pygame.draw.line(surface, TABLE_LIGHT_COLOR, (top.x + 2, y), (top.right - 3, y))
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, top, 1)
        sign = self.apron_sign(hires=not with_text)
        pygame.draw.rect(surface, SIGN_COLOR, sign)
        if with_text:
            label = render_text(self._small_font, APRON_SIGN, PLAQUE_TEXT_COLOR)
            surface.blit(label, label.get_rect(center=sign.center))
        # Слева на столешнице — стопка чистых бланков, справа — штемпельная подушка и штамп.
        for k in range(4):
            sheet = pygame.Rect(top.x + 3 + (k % 2), top.y + 30 - k * 2, 9, 12)
            pygame.draw.rect(surface, PAPER_COLOR, sheet)
            pygame.draw.rect(surface, PAPER_EDGE_COLOR, sheet, 1)
        pygame.draw.rect(surface, (40, 40, 60), (top.right - 13, top.y + 34, 10, 5))
        pygame.draw.rect(surface, STAMP_COLOR, (top.right - 12, top.y + 35, 8, 3))
        pygame.draw.rect(surface, (90, 60, 40), (top.right - 10, top.y + 26, 4, 6))
        pygame.draw.rect(surface, (40, 30, 26), (top.right - 12, top.y + 31, 8, 3))
        for index in range(len(SLOT_XS)):
            plate = self.slot_number(index)
            pygame.draw.rect(surface, TABLE_EDGE_COLOR, plate)
            if with_text:
                number = self._text(str(index + 1), PAPER_COLOR, small=True)
                surface.blit(number, number.get_rect(center=plate.center))
            paper = slot_paper(index)
            document = self.puzzle.order[index]
            if document is None:
                draw_dashed_rect(surface, TABLE_EDGE_COLOR, paper)  # место ждёт свой лист
            else:
                draw_paper(surface, paper, document, with_title=with_text)
            if target is not None and target.kind == "slot" and target.slot == index:
                pygame.draw.rect(surface, MARK_COLOR, paper.inflate(4, 4), 1)
        if self.puzzle.solved:  # принято: на столе сияет печать
            radius = 4 + round(abs(math.sin(self.time * 5)))
            pygame.draw.circle(surface, DONE_COLOR, (top.right - 8, top.y + 12), radius, 1)

    def _draw_goose(self, canvas: pygame.Surface, highlighted: bool, hires: HiResLayer | None = None) -> None:
        source, image = self._goose_frame()
        rect = image.get_rect(midbottom=GOOSE_POSITION)
        if hires is not None:
            hires.sprite(source, rect)  # исходный кадр на том же месте и того же размера
        else:
            canvas.blit(image, rect)
        if highlighted:
            x, y = rect.centerx, rect.top - 4
            with logical_target(canvas, hires, pygame.Rect(x - 4, y - 4, 9, 9)) as surface:
                pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

    def issued_layout(self, document: str) -> list[tuple[str, TextStyle, tuple[float, float]]]:
        """Надписи листа выданного документа: (строка, стиль, середина левого края) — по центру листа
        по высоте, слева от печати."""
        lines = ISSUED_LINES[document]
        top = ISSUED_SHEET.centery - (len(lines) - 1) * ISSUED_LINE_HEIGHT / 2
        return [
            (text, ISSUED_TITLE_STYLE if index == 0 else ISSUED_TEXT_STYLE,
             (ISSUED_SHEET.x + 5, top + index * ISSUED_LINE_HEIGHT))
            for index, text in enumerate(lines)
        ]

    def _draw_issued(self, canvas: pygame.Surface, document: str, hires: HiResLayer | None = None) -> None:
        """Что гусь только что выдал: лист над столом подачи с печатью — красной на разрешении,
        золотой с лентой на свидетельстве. Печать пульсирует, как свежая."""
        with logical_target(canvas, hires, ISSUED_SHEET.inflate(2, 2)) as surface:
            sheet = ISSUED_SHEET
            pygame.draw.rect(surface, ISSUED_SHEET_COLOR, sheet)
            pygame.draw.rect(surface, PAPER_EDGE_COLOR, sheet, 1)
            seal = (sheet.right - 11, sheet.centery)
            radius = 6 + round(abs(math.sin(self.time * 5)) * 0.6)
            if document == "citizenship":
                for dx in (-3, 2):  # ленточки под печатью
                    end = (seal[0] + dx * 2, sheet.bottom - 2)
                    pygame.draw.line(surface, SEAL_RIBBON_COLOR, (seal[0] + dx, seal[1]), end, 2)
                pygame.draw.circle(surface, SEAL_COLOR, seal, radius)
                pygame.draw.circle(surface, ISSUED_TITLE_COLOR, seal, radius - 3, 1)
            else:
                pygame.draw.circle(surface, STAMP_COLOR, seal, radius, 1)
                pygame.draw.circle(surface, STAMP_COLOR, seal, radius - 3, 1)
            if hires is None:
                for text, style, (x, y) in self.issued_layout(document):
                    image = self._text(text, style.color, small=True)
                    surface.blit(image, image.get_rect(midleft=(x, round(y))))
        if hires is not None:
            for text, style, position in self.issued_layout(document):
                hires.text(text, style, position, anchor="midleft")

    def _goose_image(self) -> pygame.Surface:
        """Поза гуся из манифеста goose_inspector, уменьшенная ближайшим соседом; без отражения."""
        return self._goose_frame()[1]

    def _goose_frame(self) -> tuple[pygame.Surface, pygame.Surface]:
        """Поза гуся: исходный кадр манифеста goose_inspector (без отражения) и он же на холсте."""
        pose = self.goose_pose
        if pose not in self._goose_frames:
            sprites: CharacterSprites | None = self.goose_sprites
            if sprites is None:
                source = image = placeholder_animations().default.frames[0]
            else:
                try:
                    source = sprites.frame(pose).image
                except KeyError:
                    source = sprites.frames[0].image
                image = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
            self._goose_frames[pose] = (source, image)
        return self._goose_frames[pose]

    def _draw_hud(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Одна строка вверху: задача, а пока документ в руках — его полное название."""
        bar = pygame.Rect(0, 0, WIDTH, HUD_HEIGHT)
        held = self.held_text()
        text, style = (held, HUD_STYLE) if held else (self.task_text(), TASK_STYLE)
        with logical_target(canvas, hires, bar) as surface:
            surface.fill(HUD_COLOR, bar)
            if hires is None:
                surface.blit(self._text(text, style.color), (4, 1))
        if hires is not None:
            hires.text(text, style, (4, HUD_HEIGHT / 2), anchor="midleft")

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

    @staticmethod
    def cabinet_plaque(cabinet: Cabinet) -> pygame.Rect:
        """Табличка раздела на шкафу (полное название — в подсказке, когда Алиса рядом)."""
        rect = cabinet.rect
        return pygame.Rect(rect.x + 3, rect.y + 2, rect.width - 6, 9)

    def _render_background(self, labels: bool = True) -> pygame.Surface:
        """Стена со шкафами и плакатом, паркет до самого низа комнаты, коврик у входа, стопки бумаг.

        labels=False — без надписей на табличках и плакате: их рисует слой высокого разрешения."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        page.fill(WALL_COLOR)
        for row, y in enumerate(range(SHELVES.bottom, STATUS_TOP, 6)):  # паркет «ёлочкой» попроще
            for column, x in enumerate(range(-(row % 2) * 8, WIDTH, 16)):
                page.fill(FLOOR_COLORS[(row + column) % 2], (x, y, 16, 6))
        page.fill(BASEBOARD_COLOR, (0, SHELVES.bottom, WIDTH, 2))  # плинтус у задней стены
        for cabinet in CABINETS:
            self._draw_cabinet(page, cabinet, labels)
        # Плакат над гусем: «ТИХО! ИДЁТ СОГЛАСОВАНИЕ».
        pygame.draw.rect(page, CABINET_DARK_COLOR, POSTER.inflate(2, 2))
        pygame.draw.rect(page, SIGN_COLOR, POSTER)
        for x in (POSTER.x + 2, POSTER.right - 3):  # кнопки
            page.set_at((x, POSTER.y + 1), STAMP_COLOR)
        if labels:  # на холсте мелкий текст не читается — вместо него строки
            for text, (x, y) in poster_layout():
                width = min(POSTER.width - 6, len(text) * 3)
                page.fill(STAMP_COLOR, (round(x - width / 2), round(y), width, 1))
        # Коврик у входа и стопки бумаг в углах.
        pygame.draw.rect(page, DOORMAT_COLOR, DOORMAT, border_radius=2)
        pygame.draw.rect(page, DOORMAT_EDGE_COLOR, DOORMAT, 1, border_radius=2)
        for stack in PAPER_STACKS:
            draw_paper_stack(page, stack)
        return page

    def _draw_cabinet(self, page: pygame.Surface, cabinet: Cabinet, labels: bool = True) -> None:
        """Высокий шкаф: табличка раздела, полки с папками; у некоторых разделов — свои детали."""
        rect = cabinet.rect
        pygame.draw.rect(page, CABINET_DARK_COLOR, rect)
        pygame.draw.rect(page, CABINET_COLOR, rect.inflate(-4, -2))
        pygame.draw.rect(page, CABINET_EDGE_COLOR, rect, 1)
        plaque = self.cabinet_plaque(cabinet)
        pygame.draw.rect(page, PLAQUE_COLOR, plaque)
        if labels:
            label = render_text(self._small_font, cabinet.section.label, PLAQUE_TEXT_COLOR)
            page.blit(label, label.get_rect(center=plaque.center))
        section = cabinet.section.id
        if section == "department":  # закрытые дверцы с замком: отдел, которого как бы нет
            doors = pygame.Rect(rect.x + 4, rect.y + 13, rect.width - 8, rect.height - 15)
            pygame.draw.rect(page, CABINET_DARK_COLOR, doors)
            pygame.draw.line(page, CABINET_EDGE_COLOR, (doors.centerx, doors.top), (doors.centerx, doors.bottom - 1))
            pygame.draw.rect(page, (200, 180, 90), (doors.centerx - 2, doors.centery - 1, 5, 4))
            note = pygame.Rect(doors.x + 3, doors.y + 4, 12, 9)
            pygame.draw.rect(page, PAPER_COLOR, note)
            pygame.draw.line(page, PAPER_EDGE_COLOR, (note.x + 2, note.y + 3), (note.right - 3, note.y + 3))
            pygame.draw.line(page, PAPER_EDGE_COLOR, (note.x + 2, note.y + 5), (note.right - 5, note.y + 5))
            return
        for shelf, y in enumerate(range(rect.y + 21, rect.bottom, 9)):
            pygame.draw.line(page, SHELF_COLOR, (rect.x + 2, y), (rect.right - 3, y))
            if section == "births" and shelf == 0:  # рождения, ожидающие регистрации, — свёртки на полке
                for k, x in enumerate(range(rect.x + 5, rect.right - 8, 10)):
                    pygame.draw.rect(page, BUNDLE_COLORS[k % 2], (x, y - 5, 8, 5))
                    pygame.draw.rect(page, BUNDLE_FACE_COLOR, (x + 5, y - 4, 2, 2))
                continue
            if section == "cakes" and shelf == 0:  # торты, признанные документами, — прямо на полке
                for k, x in enumerate(range(rect.x + 6, rect.right - 8, 13)):
                    pygame.draw.rect(page, (236, 170, 190) if k % 2 else (200, 150, 100), (x, y - 6, 10, 6))
                    pygame.draw.rect(page, (250, 246, 240), (x, y - 7, 10, 2))
                    page.set_at((x + 5, y - 9), (220, 40, 60))
                continue
            x = rect.x + 4
            k = shelf * 3 + cabinet.x
            while x < rect.right - 6:  # корешки папок разной ширины и высоты
                width = 3 + (k % 3)
                height = 6 + (k % 2)
                pygame.draw.rect(page, FOLDER_COLORS[k % len(FOLDER_COLORS)], (x, y - height, width, height))
                x += width + 1
                k += 1
        top_shelf = pygame.Rect(rect.x + 4, rect.y + 13, rect.width - 8, 3)
        for k in range(3):  # бумаги, торчащие с верхней полки
            pygame.draw.rect(page, PAPER_COLOR, (top_shelf.x + 2 + k * 14, top_shelf.y, 9, 3))


def paper_title_layout(rect: pygame.Rect, document: str, size: float) -> list[tuple[str, tuple[float, float]]]:
    """Строки полного названия на листе rect шрифтом размера size: (строка, её середина).

    Строки идут под цветной шапкой бланка, по середине листа; шаг — с запасом, чтобы строки
    любого шрифта не задевали друг друга."""
    step = size * 1.3
    top = rect.y + _band_height(rect) + 3 + step / 2
    return [(text, (rect.centerx, top + index * step)) for index, text in enumerate(PAPER_TITLE_LINES[document])]


def _band_height(rect: pygame.Rect) -> int:
    return max(1, rect.height // 14)


def draw_paper(surface: pygame.Surface, rect: pygame.Rect, document: str, title_size: float = PAPER_TITLE_SIZE,
               with_title: bool = False) -> None:
    """Лист документа примерно формата A4 — один вид везде: на столе, в руках и крупно при находке.

    Кремовая бумага с тонким контуром и тенью, цветная шапка бланка (цвет вида документа), место
    под название, строки для заполнения и пометка вида в углу. Название пишет слой окна
    (paper_title_layout); with_title=True — без слоя окна: вместо мелкого текста штрихи."""
    surface.fill(PAPER_SHADOW_COLOR, rect.move(1, 1))
    pygame.draw.rect(surface, PAPER_COLOR, rect)
    pygame.draw.rect(surface, PAPER_EDGE_COLOR, rect, 1)
    color = DOCUMENT_COLORS[document]
    band = _band_height(rect)
    surface.fill(color, (rect.x + 2, rect.y + 2, rect.width - 4, band))
    if rect.height < 30:  # маленький лист в руках: только штрихи под цветной шапкой
        for k, y in enumerate(range(rect.y + band + 4, rect.bottom - 2, 3)):
            surface.fill(INK_COLOR, (rect.x + 2, y, rect.width - 4 - (k % 2) * 3, 1))
        return
    lines = paper_title_layout(rect, document, title_size)
    if with_title:
        for text, (x, y) in lines:
            width = min(rect.width - 8, len(text) * 3)
            surface.fill(color, (round(x - width / 2), round(y), width, 1))
    # Строки для заполнения и подпись — под названием, пометка вида — в нижнем правом углу.
    first = round(lines[-1][1][1]) + 6
    for y in range(first, rect.bottom - 6, 4):
        surface.fill(INK_COLOR, (rect.x + 4, y, rect.width - 16, 1))
    draw_document_mark(surface, document, (rect.right - 6, rect.bottom - 6))


def draw_dashed_rect(surface: pygame.Surface, color: config.Color, rect: pygame.Rect, dash: int = 3) -> None:
    """Пунктирный контур пустого места на столе."""
    for x in range(rect.left, rect.right, dash * 2):
        surface.fill(color, (x, rect.top, min(dash, rect.right - x), 1))
        surface.fill(color, (x, rect.bottom - 1, min(dash, rect.right - x), 1))
    for y in range(rect.top, rect.bottom, dash * 2):
        surface.fill(color, (rect.left, y, 1, min(dash, rect.bottom - y)))
        surface.fill(color, (rect.right - 1, y, 1, min(dash, rect.bottom - y)))


def poster_layout() -> list[tuple[str, tuple[float, float]]]:
    """Строки плаката над гусем: (строка, середина)."""
    step = POSTER.height / (len(POSTER_LINES) + 1)
    return [(text, (POSTER.centerx, POSTER.y + step * (index + 1))) for index, text in enumerate(POSTER_LINES)]


def draw_document_mark(surface: pygame.Surface, document: str, center: tuple[int, int]) -> None:
    """Пометка вида документа: строки заявления на бланк, печать разрешения, сердечко заявления о Лео."""
    x, y = center
    color = DOCUMENT_COLORS[document]
    if document == "form_request":
        for dy in (-2, 0, 2):
            pygame.draw.line(surface, color, (x - 2, y + dy), (x + 1, y + dy))
    elif document == "filing_permit":
        pygame.draw.circle(surface, color, (x, y), 3, 1)
    else:
        pygame.draw.polygon(surface, color, [(x, y + 3), (x - 3, y), (x - 3, y - 2), (x - 2, y - 3), (x, y - 1),
                                             (x + 2, y - 3), (x + 3, y - 2), (x + 3, y)])


def draw_paper_stack(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Стопка бумаг: листы со сдвигом, сверху — перевязка."""
    for k, y in enumerate(range(rect.bottom - 3, rect.top - 1, -2)):
        sheet = pygame.Rect(rect.x + (k % 2), y, rect.width - 1, 3)
        pygame.draw.rect(surface, PAPER_COLOR, sheet)
        pygame.draw.line(surface, PAPER_EDGE_COLOR, sheet.bottomleft, (sheet.right - 1, sheet.bottom - 1))
    pygame.draw.line(surface, (170, 60, 50), (rect.centerx, rect.top), (rect.centerx, rect.bottom - 1))
