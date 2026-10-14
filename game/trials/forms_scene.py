"""Испытание формуляров: архив гуся-инспектора, где Алиса ищет три документа и сдаёт их
в правильном порядке.

Логика архива и стола подачи — в game/trials/forms_puzzle.py (без Pygame), реплики — в
game/story/forms_dialogue.py. Здесь только сцена: движение Алисы (Character и
CollisionMap, как на площади), шкафы-разделы, стол подачи с тремя местами, гусь и интерфейс.

Этапы: вступление → поиск и раскладка документов → реакция гуся → финальная проверка →
награда. Фрагмент (GameProgress.complete("forms")) выдаётся только после финальной
реплики; отмена (Backspace) в любой момент до этого возвращает на площадь без награды.
Оформление временное: архив нарисован геометрией.
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
from game.graphics.fonts import load_font, render_text
from game.graphics.placeholder import placeholder_animations
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, try_load_character_sprites
from game.story.forms_dialogue import (
    FINAL,
    GOOSE_IDLE_POSE,
    GOOSE_POSES,
    INSPECTION,
    INTRO,
    all_scripts,
    goose_hint,
    goose_holding,
    goose_rejection,
    search_script,
)
from game.trials.forms_puzzle import (
    DOCUMENT_NAMES,
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
REACTION = "reaction"
FINAL_PHASE = "final"
DONE = "done"

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 32  # как на площади
WALK_SPEED = 64
HUD_HEIGHT = 24  # две строки: задача и порядок на столе
STATUS_TOP = 168
SHELVES = pygame.Rect(0, HUD_HEIGHT, WIDTH, 40)  # ряд высоких шкафов у задней стены
# Ноги Алисы: между шкафами и барьером приёма. Нижняя граница выше любого окна
# реплики, поэтому окно никогда не закрывает персонажей.
WALK_BOUNDS = pygame.Rect(10, SHELVES.bottom, WIDTH - 20, 108 - SHELVES.bottom)
CABINET_WIDTH = 50
CABINET_XS = (35, 95, 155, 215, 275)  # центры шкафов, по одному на раздел архива
CABINET_POINT_Y = WALK_BOUNDS.top + 6  # точка взаимодействия — вплотную к шкафу
CABINET_REACH = 14
TABLE = pygame.Rect(100, 88, 120, 20)  # стол подачи: столешница и передняя стенка
SLOT_XS = (124, 156, 188)  # места 1, 2, 3 на столе
SLOT_Y = TABLE.top - 2  # Алиса стоит за столом, лицом к залу
SLOT_REACH = 10
GOOSE_POSITION = (284, 104)
GOOSE_REACH = 24
# Шире самого гуся: Алиса останавливается на шаг от него, и спрайты не наползают друг на друга.
GOOSE_OBSTACLE = pygame.Rect(268, 94, 30, 12)
PAPER_STACKS = (pygame.Rect(10, 80, 12, 10), pygame.Rect(298, 66, 12, 10))  # стопки бумаг у стен
COUNTER = pygame.Rect(0, 116, WIDTH, 14)  # барьер приёма документов (декорация)
SPAWN = (30, 104)  # у входа в архив, вдали от шкафов и стола
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
TABLE_COLOR = (170, 128, 88)
TABLE_FRONT_COLOR = (124, 88, 60)
TABLE_EDGE_COLOR = (96, 66, 46)
COUNTER_COLOR = (96, 64, 46)
COUNTER_TOP_COLOR = (140, 100, 70)
PAPER_COLOR = (248, 244, 230)
PAPER_EDGE_COLOR = (170, 160, 140)
SIGN_COLOR = (230, 220, 190)
DOCUMENT_COLORS = {"application": (60, 90, 170), "approval": (120, 70, 150), "permission": (190, 50, 50)}
HUD_COLOR = (44, 38, 58)
HUD_TEXT_COLOR = (240, 230, 206)
HUD_ACCENT_COLOR = (250, 206, 108)
DONE_COLOR = (140, 220, 150)
TODO_COLOR = (200, 196, 214)
EMPTY_COLOR = (130, 124, 146)
MARK_COLOR = (255, 236, 140)
# Короткие надписи на карточках документов — бюрократические сокращения.
DOCUMENT_ABBREVIATIONS = {"application": "ЗАЯВ", "approval": "СОГЛ", "permission": "РАЗР"}


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
        self._goose_frames: dict[str, pygame.Surface] = {}

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
        self.time = 0.0
        self._font = load_font(9)
        self._small_font = load_font(7)
        self._text_cache: dict[tuple[str, config.Color, bool], pygame.Surface] = {}
        self._background = self._render_background()
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
        if puzzle.solved:
            return "Документы приняты"
        if not puzzle.all_found:
            return f"Задача: найди документы {puzzle.found_count}/{len(DOCUMENTS)}"
        return "Задача: разложи по порядку и сдай гусю"

    def held_text(self) -> str:
        held = self.puzzle.held
        return f"В руках: {DOCUMENT_NAMES[held]}" if held else ""

    def order_parts(self) -> list[tuple[str, config.Color]]:
        """Вторая строка интерфейса по кусочкам: что лежит на местах стола 1, 2, 3."""
        color = DONE_COLOR if self.puzzle.solved else TODO_COLOR
        parts: list[tuple[str, config.Color]] = [("Стол:", HUD_TEXT_COLOR)]
        for index, document in enumerate(self.puzzle.order):
            if index:
                parts.append(("→", HUD_TEXT_COLOR))
            if document is None:
                parts.append((f"{index + 1} —", EMPTY_COLOR))
            else:
                parts.append((f"{index + 1} {DOCUMENT_NAMES[document]}", color))
        return parts

    def order_text(self) -> str:
        return " ".join(text for text, _ in self.order_parts())

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
            document = self.puzzle.found[-1]
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

    def _dialogue_finished(self) -> None:
        """Реплика закрыта: следующий этап испытания."""
        self.dialogue = None
        self.goose_pose = GOOSE_IDLE_POSE
        if self._toast_after_dialogue:
            self._show_toast(self._toast_after_dialogue)
            self._toast_after_dialogue = ""
        if self.phase == INTRO_PHASE:
            self.phase = EXPLORE
        elif self.phase == REACTION:
            self.phase = FINAL_PHASE
            self._open_dialogue(FINAL)
        elif self.phase == FINAL_PHASE:
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

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self._background, (0, 0))
        target = self.nearby() if self.phase == EXPLORE and self.dialogue is None else None
        for cabinet in CABINETS:
            self._draw_cabinet_marks(surface, cabinet, target is not None and target.section == cabinet.section.id)
        drawables = [
            (TABLE.bottom, lambda: self._draw_table(surface, target)),
            (GOOSE_POSITION[1], lambda: self._draw_goose(surface, target is not None and target.kind == "goose")),
            (self.alice.y + 0.1, lambda: self._draw_alice(surface)),
        ]
        for _, draw in sorted(drawables, key=lambda item: item[0]):
            draw()
        self._draw_hud(surface)
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue)
        else:
            self._draw_status(surface)

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
        """Где рисуется документ в руках: над головой Алисы (шкафы ниже полосы интерфейса)."""
        rect = self.alice.rect
        return rect.centerx, rect.top - 5

    def _draw_alice(self, surface: pygame.Surface) -> None:
        self.alice.draw(surface)
        held = self.puzzle.held
        if held is not None:
            x, y = self.held_icon_center()
            self._draw_card(surface, held, (x, y - round(abs(math.sin(self.time * 4)))))

    def _draw_card(self, surface: pygame.Surface, document: str, center: tuple[int, int]) -> None:
        """Карточка документа: лист с сокращённым названием и цветной пометкой своего вида."""
        card = pygame.Rect(0, 0, 26, 11)
        card.center = center
        pygame.draw.rect(surface, PAPER_COLOR, card)
        pygame.draw.rect(surface, PAPER_EDGE_COLOR, card, 1)
        color = DOCUMENT_COLORS[document]
        surface.blit(self._text(DOCUMENT_ABBREVIATIONS[document], color, small=True), (card.x + 2, card.y + 1))
        draw_document_mark(surface, document, (card.right - 4, card.centery))

    def _draw_table(self, surface: pygame.Surface, target: Target | None) -> None:
        top = pygame.Rect(TABLE.x, TABLE.y, TABLE.width, 12)
        front = pygame.Rect(TABLE.x + 2, top.bottom, TABLE.width - 4, TABLE.height - top.height)
        pygame.draw.rect(surface, TABLE_FRONT_COLOR, front)
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, front, 1)
        pygame.draw.rect(surface, TABLE_COLOR, top)
        pygame.draw.rect(surface, TABLE_EDGE_COLOR, top, 1)
        # Стопка бумаг слева, штемпельная подушка и штамп справа.
        for k in range(3):
            pygame.draw.rect(surface, PAPER_COLOR, (TABLE.x + 3, top.y + 6 - k * 2, 9, 3))
            pygame.draw.rect(surface, PAPER_EDGE_COLOR, (TABLE.x + 3, top.y + 6 - k * 2, 9, 3), 1)
        pygame.draw.rect(surface, (40, 40, 60), (TABLE.right - 15, top.y + 6, 10, 4))
        pygame.draw.rect(surface, DOCUMENT_COLORS["permission"], (TABLE.right - 14, top.y + 7, 8, 2))
        pygame.draw.rect(surface, (90, 60, 40), (TABLE.right - 11, top.y + 1, 3, 4))
        pygame.draw.rect(surface, (40, 30, 26), (TABLE.right - 13, top.y + 4, 7, 2))
        for index, x in enumerate(SLOT_XS):
            number = self._text(str(index + 1), PAPER_COLOR, small=True)
            surface.blit(number, number.get_rect(center=(x, front.centery)))
            document = self.puzzle.order[index]
            center = (x, top.centery)
            if document is None:
                slot = pygame.Rect(0, 0, 26, 11)
                slot.center = center
                pygame.draw.rect(surface, TABLE_EDGE_COLOR, slot, 1)
            else:
                self._draw_card(surface, document, center)
            if target is not None and target.kind == "slot" and target.slot == index:
                mark = pygame.Rect(0, 0, 30, 15)
                mark.center = center
                pygame.draw.rect(surface, MARK_COLOR, mark, 1)
        if self.puzzle.solved:  # принято: на столе сияет печать
            radius = 4 + round(abs(math.sin(self.time * 5)))
            pygame.draw.circle(surface, DONE_COLOR, (SLOT_XS[-1] + 12, top.y + 2), radius, 1)

    def _draw_goose(self, surface: pygame.Surface, highlighted: bool) -> None:
        image = self._goose_image()
        rect = image.get_rect(midbottom=GOOSE_POSITION)
        surface.blit(image, rect)
        if highlighted:
            x, y = rect.centerx, rect.top - 4
            pygame.draw.polygon(surface, MARK_COLOR, [(x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y)])

    def _goose_image(self) -> pygame.Surface:
        """Поза гуся из манифеста goose_inspector, уменьшенная ближайшим соседом; без отражения."""
        pose = self.goose_pose
        if pose not in self._goose_frames:
            sprites: CharacterSprites | None = self.goose_sprites
            if sprites is None:
                image = placeholder_animations().default.frames[0]
            else:
                try:
                    source = sprites.frame(pose).image
                except KeyError:
                    source = sprites.frames[0].image
                image = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
            self._goose_frames[pose] = image
        return self._goose_frames[pose]

    def _draw_hud(self, surface: pygame.Surface) -> None:
        surface.fill(HUD_COLOR, (0, 0, WIDTH, HUD_HEIGHT))
        surface.blit(self._text(self.task_text(), HUD_ACCENT_COLOR), (4, 1))
        held = self.held_text()
        if held:
            image = self._text(held, HUD_TEXT_COLOR)
            surface.blit(image, image.get_rect(topright=(WIDTH - 4, 1)))
        x = 4
        for text, color in self.order_parts():
            image = self._text(text, color)
            surface.blit(image, (x, 12))
            x += image.get_width() + self._font.size(" ")[0]

    def _draw_status(self, surface: pygame.Surface) -> None:
        surface.fill(HUD_COLOR, (0, STATUS_TOP, WIDTH, HEIGHT - STATUS_TOP))
        text = self._text(self.status_text(), HUD_TEXT_COLOR)
        surface.blit(text, text.get_rect(center=(WIDTH // 2, STATUS_TOP + (HEIGHT - STATUS_TOP) // 2)))

    def _render_background(self) -> pygame.Surface:
        """Стена со шкафами, паркет, стопки бумаг, барьер приёма с табличками."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        page.fill(WALL_COLOR)
        for row, y in enumerate(range(SHELVES.bottom, STATUS_TOP, 6)):  # паркет «ёлочкой» попроще
            for column, x in enumerate(range(-(row % 2) * 8, WIDTH, 16)):
                page.fill(FLOOR_COLORS[(row + column) % 2], (x, y, 16, 6))
        for cabinet in CABINETS:
            self._draw_cabinet(page, cabinet)
        for stack in PAPER_STACKS:
            draw_paper_stack(page, stack)
        # Барьер приёма документов с табличками, под ним — ещё бумаги.
        pygame.draw.rect(page, COUNTER_COLOR, COUNTER)
        pygame.draw.rect(page, COUNTER_TOP_COLOR, (COUNTER.x, COUNTER.y, COUNTER.width, 4))
        for text, x in (("ПРИЁМ ДОКУМЕНТОВ: ВЧЕРА", 80), ("ТИХО! ИДЁТ СОГЛАСОВАНИЕ", 240)):
            label = render_text(self._small_font, text, PLAQUE_TEXT_COLOR)
            sign = label.get_rect(center=(x, COUNTER.y + 9)).inflate(6, 0)
            pygame.draw.rect(page, SIGN_COLOR, sign)
            page.blit(label, label.get_rect(center=sign.center))
        for rect in (pygame.Rect(20, 140, 18, 16), pygame.Rect(150, 146, 14, 10), pygame.Rect(276, 138, 20, 18)):
            draw_paper_stack(page, rect)
        return page

    def _draw_cabinet(self, page: pygame.Surface, cabinet: Cabinet) -> None:
        """Высокий шкаф: табличка раздела, полки с папками; у некоторых разделов — свои детали."""
        rect = cabinet.rect
        pygame.draw.rect(page, CABINET_DARK_COLOR, rect)
        pygame.draw.rect(page, CABINET_COLOR, rect.inflate(-4, -2))
        pygame.draw.rect(page, CABINET_EDGE_COLOR, rect, 1)
        plaque = pygame.Rect(rect.x + 3, rect.y + 2, rect.width - 6, 9)
        pygame.draw.rect(page, PLAQUE_COLOR, plaque)
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


def draw_document_mark(surface: pygame.Surface, document: str, center: tuple[int, int]) -> None:
    """Пометка вида документа: строки заявления, подпись согласования или печать разрешения."""
    x, y = center
    color = DOCUMENT_COLORS[document]
    if document == "application":
        for dy in (-2, 0, 2):
            pygame.draw.line(surface, color, (x - 2, y + dy), (x + 1, y + dy))
    elif document == "approval":
        pygame.draw.lines(surface, color, False, [(x - 2, y + 1), (x - 1, y - 2), (x, y + 2), (x + 1, y - 1)])
    else:
        pygame.draw.circle(surface, color, (x, y), 3, 1)


def draw_paper_stack(surface: pygame.Surface, rect: pygame.Rect) -> None:
    """Стопка бумаг: листы со сдвигом, сверху — перевязка."""
    for k, y in enumerate(range(rect.bottom - 3, rect.top - 1, -2)):
        sheet = pygame.Rect(rect.x + (k % 2), y, rect.width - 1, 3)
        pygame.draw.rect(surface, PAPER_COLOR, sheet)
        pygame.draw.line(surface, PAPER_EDGE_COLOR, sheet.bottomleft, (sheet.right - 1, sheet.bottom - 1))
    pygame.draw.line(surface, (170, 60, 50), (rect.centerx, rect.top), (rect.centerx, rect.bottom - 1))
