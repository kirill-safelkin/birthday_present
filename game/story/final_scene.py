"""Финал: последняя страница сказки, письмо Алисе, секрет подарка, титры и выход.

Открывается с площади мозаикой, когда собраны все три фрагмента (это решает площадь).
Тексты — в game/story/final_dialogue.py. Сцена ничего не меняет в GameProgress: она
только показывает собранные фрагменты.

Этапы: страница восстанавливается (фрагменты становятся символами, поляна украшается) →
разговор с Чучмеком → письмо по страницам → тихая пауза → секрет настоящего подарка →
реплика Чучмека → титры → последний экран. На последнем экране E или Enter завершает
прохождение: сцена просит приложение закрыться (SceneManager.request_quit). Backspace до
этого возвращает на площадь — прогресс не трогается, мозаика по-прежнему светится.
Все паузы и анимации идут по dt, без ожиданий и своих циклов.

На странице вместе с Алисой и Чучмеком — Лео: он сидит на мягком покрывале между Алисой
и подставкой с фрагментами. Он не говорит и не ходит — только меняет позы из своего манифеста
(удивляется, смеётся), когда Чучмек даёт слово «комиссии». В письмо и секрет подарка он не вмешивается.

Со слоем высокого разрешения (game/graphics/hires.py) Алиса, Чучмек и Лео рисуются из исходных
кадров 64×64, а все надписи — письмо, секрет подарка, штамп, титры, последний экран и
подсказки — шрифтом размера окна. Письмо для этого переносится по метрикам того же шрифта
(своя раскладка, те же листы и те же границы строк); страница и символы остаются пиксельными.
"""

from __future__ import annotations

import math
from pathlib import Path

import pygame

import config
from game.core.input import Action, actions_for
from game.core.scenes import Scene
from game.dialogue.box import DialogueBox, wrap_text
from game.dialogue.model import DialogueController, DialogueScript
from game.graphics.fonts import TextFonts, TextStyle, load_font, render_text
from game.graphics.hires import HiResLayer, logical_target
from game.graphics.placeholder import placeholder_animations
from game.graphics.sprite_manifest import CHARACTERS_DIR, CharacterSprites, try_load_character_sprites
from game.story import final_dialogue as text
from game.world.hub import FINALE_SCENE
from game.world.progress import TRIALS, GameProgress

__all__ = ["FINALE_SCENE", "FinalScene"]

# Этапы финала.
ARRIVAL = "arrival"  # страница восстанавливается
TALK = "talk"  # разговор с Чучмеком
LETTER = "letter"  # письмо Алисе
PAUSE = "pause"  # тишина после письма
GIFT = "gift"  # секрет настоящего подарка
GIFT_REACTION = "gift_reaction"  # Чучмек про формуляр F-17
CREDITS = "credits"
THE_END = "the_end"  # «Конец сказки. Начало настоящего праздника»
DONE = "done"  # прохождение завершено, игра закрывается

WIDTH, HEIGHT = config.LOGICAL_SIZE
SPRITE_SIZE = 48  # как во вступлении: страница книги, персонажи крупнее, чем на площади
ALICE_POSITION = (104, 108)  # точки под ногами; выше любого окна реплики
CHUCHMEK_POSITION = (218, 108)
LEO_POSITION = (134, 108)  # на покрывале рядом с Алисой, у подставки с фрагментами
LEO_SIZE = 32  # малыш меньше взрослых: как персонажи на площади
BLANKET = pygame.Rect(LEO_POSITION[0] - 17, LEO_POSITION[1] - 6, 34, 9)
# Где собираются три фрагмента: суши, документ с печатью, торт.
SYMBOL_POSITIONS = {"sushi": (136, 64), "forms": (160, 52), "cakes": (184, 64)}
FRAGMENT_STARTS = {"sushi": (-12, 90), "forms": (160, -14), "cakes": (WIDTH + 12, 90)}
ARRIVAL_SECONDS = 3.6
PAGE_FADE_SECONDS = 0.5  # страница письма проявляется; первое нажатие проявляет её сразу
PAUSE_SECONDS = 2.5  # тишина между письмом и шуткой про подарок — её не пропустить
CREDITS_SCROLL_SECONDS = 5.0
CREDITS_SECONDS = 8.0
CREDITS_SKIP_DELAY = 1.0  # титры можно пролистать, но не случайным первым нажатием
END_INPUT_DELAY = 1.5  # последний экран не закрыть случайным нажатием, оставшимся от титров
PANEL = pygame.Rect(16, 8, WIDTH - 32, HEIGHT - 16)  # лист письма
PANEL_PADDING = 12
# Поля вокруг листа письма — то, что видно от страницы, когда лист проявился целиком.
LETTER_MARGINS = (
    pygame.Rect(0, 0, WIDTH, PANEL.top),
    pygame.Rect(0, PANEL.bottom, WIDTH, HEIGHT - PANEL.bottom),
    pygame.Rect(0, PANEL.top, PANEL.left, PANEL.height),
    pygame.Rect(PANEL.right, PANEL.top, WIDTH - PANEL.right, PANEL.height),
)
GARLAND_FLAGS = 15

PAGE_COLOR = (246, 236, 208)
PAGE_EDGE_COLOR = (196, 160, 112)
SKY_COLOR = (238, 232, 246)
HILL_COLORS = ((178, 206, 146), (154, 188, 126))
INK_COLOR = (96, 64, 46)
PARCHMENT_COLOR = (250, 242, 220)
PLUM_COLOR = (128, 74, 126)
GOLD_COLOR = (222, 176, 84)
CREAM_COLOR = (252, 238, 204)
NIGHT_COLOR = (52, 38, 74)
GLOW_COLOR = (255, 236, 140)
FLAG_COLORS = ((232, 120, 140), (250, 214, 110), (150, 200, 230), (170, 220, 150), (200, 160, 230))
FRAGMENT_COLORS = {"sushi": (250, 170, 150), "forms": (176, 196, 236), "cakes": (252, 196, 226)}
STAMP_COLOR = (196, 52, 60)
BLANKET_COLOR = (186, 206, 240)
BLANKET_EDGE_COLOR = (132, 156, 204)
CREDITS_SMALL_COLOR = (196, 186, 214)

# Надписи в разрешении окна (слой высокого разрешения); размеры — в логических пикселях.
LETTER_SIZE = 9.5  # письмо и секрет подарка — крупно и спокойно
# Всё на листе стоит на бумаге: строки рисуются сразу на её цвете (см. TextStyle.background).
LETTER_STYLE = TextStyle(LETTER_SIZE, INK_COLOR, background=PARCHMENT_COLOR)
LETTER_TITLE_STYLE = TextStyle(LETTER_SIZE, PLUM_COLOR, bold=True, background=PARCHMENT_COLOR)
SIGNATURE_STYLE = TextStyle(LETTER_SIZE, PLUM_COLOR, background=PARCHMENT_COLOR)
STAMP_STYLE = TextStyle(6, STAMP_COLOR, bold=True, background=PARCHMENT_COLOR)
PAGE_NUMBER_STYLE = TextStyle(6, PAGE_EDGE_COLOR, background=PARCHMENT_COLOR)
RIBBON_STYLE = TextStyle(8.5, PLUM_COLOR)
HINT_SIZE = 9
SHEET_HINT_STYLE = TextStyle(HINT_SIZE, PAGE_EDGE_COLOR, background=PARCHMENT_COLOR)
CREDIT_STYLES = {
    "title": TextStyle(15, GOLD_COLOR, bold=True),
    "line": TextStyle(10, CREAM_COLOR),
    "small": TextStyle(8, CREDITS_SMALL_COLOR),
}
THE_END_STYLE = TextStyle(12, CREAM_COLOR)
CREDITS_HINT_BAR = pygame.Rect(0, HEIGHT - 18, WIDTH, 18)  # под ней скрываются уезжающие титры


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def draw_symbol(surface: pygame.Surface, trial_id: str, center: tuple[float, float]) -> None:
    """Символ фрагмента: ролл суши, документ с печатью или торт со свечой (геометрия, не ассет)."""
    x, y = round(center[0]), round(center[1])
    if trial_id == "sushi":
        pygame.draw.circle(surface, (40, 60, 48), (x, y), 8)
        pygame.draw.circle(surface, (250, 248, 240), (x, y), 6)
        pygame.draw.circle(surface, (236, 120, 96), (x, y), 3)
        pygame.draw.circle(surface, (120, 180, 110), (x + 1, y - 1), 1)
    elif trial_id == "forms":
        sheet = pygame.Rect(x - 7, y - 9, 14, 18)
        pygame.draw.rect(surface, (250, 250, 244), sheet)
        pygame.draw.rect(surface, (120, 130, 150), sheet, 1)
        for row in range(3):
            pygame.draw.line(surface, (140, 150, 170), (x - 4, y - 5 + row * 3), (x + 4, y - 5 + row * 3))
        pygame.draw.circle(surface, STAMP_COLOR, (x + 2, y + 4), 4, 1)
        surface.set_at((x + 2, y + 4), STAMP_COLOR)
    else:
        pygame.draw.rect(surface, (248, 214, 228), (x - 9, y, 18, 8))
        pygame.draw.rect(surface, (252, 238, 214), (x - 6, y - 6, 12, 6))
        pygame.draw.line(surface, (236, 120, 140), (x - 9, y), (x + 8, y))
        pygame.draw.line(surface, (120, 170, 220), (x, y - 11), (x, y - 7))
        pygame.draw.circle(surface, GLOW_COLOR, (x, y - 12), 1)


class FinalScene(Scene):
    """Последняя страница сказки. Открывается мозаикой на площади, закрывает игру."""

    supports_hires = True

    def __init__(self, progress: GameProgress | None = None, characters_dir: str | Path = CHARACTERS_DIR) -> None:
        self.progress = progress if progress is not None else GameProgress()
        root = Path(characters_dir)
        self.alice_sprites = try_load_character_sprites(root / "alice")
        self.chuchmek_sprites = try_load_character_sprites(root / "chuchmek")
        self.leo_sprites = try_load_character_sprites(root / "leo")
        self.alice_pose = "idle_right"
        self.chuchmek_pose = "idle"
        self.leo_pose = text.LEO_IDLE_POSE
        self._frames: dict[tuple[str, str], tuple[pygame.Surface, pygame.Surface]] = {}  # (исходник, на холсте)

        self.box = DialogueBox()
        for script in text.all_scripts():
            self.box.check_fits(script)
        self._font = load_font(9)
        self._letter_font = load_font(10)
        self._title_font = load_font(16)
        self._end_font = load_font(12)
        self._small_font = load_font(7)
        self._fonts = TextFonts()
        self.letter_metrics = self._fonts.metrics(LETTER_STYLE)
        self.ribbon_metrics = self._fonts.metrics(RIBBON_STYLE)
        # Строки письма в окне — не теснее пиксельных: те же поля листа, тот же предел строк.
        self.letter_line_height = max(self._letter_font.get_linesize(), math.ceil(self.letter_metrics.height))
        self._page_lines = [self._wrap(page) for page in text.LETTER_PAGES]
        self._gift_lines = self._wrap(text.GIFT_TEXT)
        # Раскладка того же письма для шрифта окна: переносы по его настоящим метрикам.
        self.hires_page_lines = [self._wrap(page, hires=True) for page in text.LETTER_PAGES]
        self.hires_gift_lines = self._wrap(text.GIFT_TEXT, hires=True)
        self._page_cache: dict[int, pygame.Surface] = {}
        self._text_cache: dict[tuple[str, config.Color, int], pygame.Surface] = {}

        self.phase = ARRIVAL
        self.phase_time = 0.0  # сколько секунд идёт текущий этап
        self.page = 0  # страница письма
        self.page_time = 0.0
        self.dialogue: DialogueController | None = None
        self.completed = False  # последний экран подтверждён: прохождение закончено
        self.time = 0.0
        self.shown: list[str] = []  # что игрок увидел, по порядку (для проверки сценария)
        self._background = self._render_page()
        self._background_plain = self._render_page(label=False)  # подпись ленточки рисует слой окна

    # --- Состояние ---

    @property
    def page_revealed(self) -> bool:
        return self.page_time >= PAGE_FADE_SECONDS

    @property
    def festive(self) -> float:
        """Насколько поляна уже украшена: 0 — пустая страница, 1 — праздник."""
        if self.phase != ARRIVAL:
            return 1.0
        return _ease((self.phase_time / ARRIVAL_SECONDS - 0.55) / 0.4)

    def symbols_assembled(self) -> bool:
        return self.phase != ARRIVAL or self.phase_time >= ARRIVAL_SECONDS * 0.65

    def hint(self) -> str:
        """Подсказка внизу экрана (кроме реплик — у них своя стрелка «дальше»)."""
        if self.phase == ARRIVAL:
            return "E — дальше"
        if self.phase in (LETTER, GIFT):
            return "E — дальше" if self.page_revealed else ""
        if self.phase == CREDITS:
            return "E — пропустить титры" if self.phase_time >= CREDITS_SKIP_DELAY else ""
        if self.phase == THE_END:
            return text.EXIT_HINT if self.phase_time >= END_INPUT_DELAY else ""
        return ""

    # --- Управление ---

    def handle_event(self, event: pygame.event.Event) -> None:
        actions = actions_for(event) if event.type == pygame.KEYDOWN else frozenset()
        if Action.CANCEL in actions and self.phase != DONE:
            self.finish()  # назад на площадь; прогресс тот же, мозаика по-прежнему откроет финал
            return
        if self.dialogue is not None:
            if Action.INTERACT in actions and Action.CONFIRM not in actions:
                self.dialogue.confirm()  # как везде: E продолжает реплику
            else:
                self.dialogue.handle_event(event)
            self._sync_dialogue()
            if self.dialogue.is_finished:
                self._dialogue_finished()
            return
        if Action.INTERACT not in actions and Action.CONFIRM not in actions:
            return
        if self.phase == ARRIVAL:
            self._start_talk()  # анимацию появления можно не ждать
        elif self.phase in (LETTER, GIFT):
            self._advance_page()
        elif self.phase == CREDITS and self.phase_time >= CREDITS_SKIP_DELAY:
            self._set_phase(THE_END)
        elif self.phase == THE_END and self.phase_time >= END_INPUT_DELAY:
            self._complete()
        # PAUSE и DONE нажатия не пропускают.

    def _set_phase(self, phase: str) -> None:
        self.phase = phase
        self.phase_time = 0.0
        self.shown.append(phase)

    def _start_talk(self) -> None:
        self._set_phase(TALK)
        self._open_dialogue(text.FINALE_TALK)

    def _advance_page(self) -> None:
        if not self.page_revealed:
            self.page_time = PAGE_FADE_SECONDS  # первое нажатие — проявить страницу целиком
            return
        if self.phase == GIFT:
            self._set_phase(GIFT_REACTION)
            self._open_dialogue(text.GIFT_REACTION)
            return
        if self.page + 1 < len(text.LETTER_PAGES):
            self.page += 1
            self.page_time = 0.0
            self.shown.append(f"letter_{self.page}")
            return
        self._set_phase(PAUSE)
        self.alice_pose = "happy_down_2"
        self.chuchmek_pose = "wink"
        self.leo_pose = text.LEO_PAUSE_POSE

    def _open_dialogue(self, script: DialogueScript) -> None:
        self.dialogue = DialogueController(script)
        self._sync_dialogue()

    def _sync_dialogue(self) -> None:
        node = self.dialogue.node if self.dialogue is not None else None
        if node is None:
            return
        if not self.shown or self.shown[-1] != node.id:
            self.shown.append(node.id)
        self.chuchmek_pose = text.CHUCHMEK_POSES.get(node.id, "idle")
        self.alice_pose = text.ALICE_POSES.get(node.id, "idle_right")
        self.leo_pose = text.LEO_POSES.get(node.id, text.LEO_IDLE_POSE)

    def _dialogue_finished(self) -> None:
        self.dialogue = None
        if self.phase == TALK:
            self._set_phase(LETTER)
            self.page = 0
            self.page_time = 0.0
            self.shown.append("letter_0")
            self.alice_pose = "idle_down"
            self.chuchmek_pose = "idle"
            self.leo_pose = text.LEO_IDLE_POSE
        elif self.phase == GIFT_REACTION:
            self._set_phase(CREDITS)

    def _complete(self) -> None:
        """Последний экран подтверждён: прохождение закончено, игра штатно закрывается."""
        self._set_phase(DONE)
        self.completed = True
        if self.manager is not None:
            self.manager.request_quit()

    def update(self, dt: float) -> None:
        self.time += dt
        self.phase_time += dt
        self.page_time += dt
        if self.dialogue is not None:
            self.dialogue.update(dt)
        elif self.phase == ARRIVAL and self.phase_time >= ARRIVAL_SECONDS:
            self._start_talk()
        elif self.phase == PAUSE and self.phase_time >= PAUSE_SECONDS:
            self._set_phase(GIFT)
            self.page_time = 0.0
        elif self.phase == CREDITS and self.phase_time >= CREDITS_SECONDS:
            self._set_phase(THE_END)

    # --- Отрисовка ---

    def draw(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Рисует финал на холсте; со слоем hires персонажи и надписи уходят в него
        (см. game/graphics/hires.py), а порядок слоёв и экранов остаётся тем же."""
        if self.phase in (CREDITS, THE_END, DONE):
            self._draw_night(surface)
            if self.phase == CREDITS:
                self._draw_credits(surface, hires)
            else:
                self._draw_the_end(surface, hires)
            self._draw_hint(surface, hires)
            return
        surface.blit(self._background if hires is None else self._background_plain, (0, 0))
        self._draw_festive(surface)
        self._draw_symbols(surface)
        if hires is not None:  # подпись ленточки — часть страницы, под героями
            hires.text("Последняя страница", RIBBON_STYLE, self.ribbon_rect(hires=True).center, anchor="center")
        self._draw_blanket(surface)
        self._draw_actor(surface, "chuchmek", CHUCHMEK_POSITION, hires)
        self._draw_actor(surface, "leo", LEO_POSITION, hires)
        self._draw_actor(surface, "alice", ALICE_POSITION, hires)
        if self.phase == ARRIVAL:
            # Страница «проявляется» из белого листа.
            whiteness = 1 - _ease(self.phase_time / (ARRIVAL_SECONDS * 0.25))
            if whiteness > 0:
                if hires is not None:
                    hires.fill(PARCHMENT_COLOR, alpha=round(255 * whiteness))  # закрывает и героев
                else:
                    veil = pygame.Surface(config.LOGICAL_SIZE)
                    veil.fill(PARCHMENT_COLOR)
                    veil.set_alpha(round(255 * whiteness))
                    surface.blit(veil, (0, 0))
        if self.phase in (LETTER, GIFT):
            self._draw_letter(surface, hires)
        if self.dialogue is not None and not self.dialogue.is_finished:
            self.box.draw(surface, self.dialogue, hires)
        else:
            self._draw_hint(surface, hires)

    def _text(self, line: str, color: config.Color, size: int = 9) -> pygame.Surface:
        key = (line, color, size)
        image = self._text_cache.get(key)
        if image is None:
            font = {7: self._small_font, 9: self._font, 10: self._letter_font, 12: self._end_font,
                    16: self._title_font}[size]
            image = self._text_cache[key] = render_text(font, line, color)
        return image

    def _wrap(self, page: str, hires: bool = False) -> list[str]:
        """Строки страницы письма пиксельным шрифтом или (hires=True) шрифтом окна — по его
        метрикам. Если текст не помещается на лист — ошибка сразу, а не обрезка в игре."""
        font = self.letter_metrics if hires else self._letter_font
        lines = wrap_text(page, font, PANEL.width - 2 * PANEL_PADDING)
        if len(lines) > self.max_letter_lines(hires):
            raise ValueError(f"страница письма не помещается на лист: {lines[0]}…")
        return lines

    def max_letter_lines(self, hires: bool = False) -> int:
        body = PANEL.height - 2 * PANEL_PADDING - 2 * self._font.get_linesize() - 4  # заголовок и подпись/подсказка
        return body // (self.letter_line_height if hires else self._letter_font.get_linesize())

    def letter_layout(self, key: int) -> dict[str, object]:
        """Где на листе (в координатах холста) стоят заголовок, строки, подпись, штамп и номер.

        key — номер страницы письма или -1 для секрета подарка. Те же места, что у пиксельного
        листа (_render_sheet), но строки — по раскладке шрифта окна."""
        gift = key < 0
        title_line = self._font.get_linesize()
        top = PANEL.y + PANEL_PADDING + title_line + 2
        lines = self.hires_gift_lines if gift else self.hires_page_lines[key]
        bottom = PANEL.bottom - PANEL_PADDING - title_line + 2
        last_page = not gift and key == len(text.LETTER_PAGES) - 1
        step = self.letter_line_height
        left = PANEL.x + PANEL_PADDING
        stamp = pygame.Rect(PANEL.right - PANEL_PADDING - 74, PANEL.y + PANEL_PADDING - 3, 74, 12)
        return {
            "title": (text.GIFT_TITLE if gift else text.LETTER_TITLE,
                      (left, PANEL.y + PANEL_PADDING - 2 + title_line / 2)),
            "lines": [(line, (left, top + row * step + step / 2)) for row, line in enumerate(lines)],
            "lines_bottom": top + len(lines) * step,
            "signature": (PANEL.right - PANEL_PADDING, bottom - 12 + title_line / 2) if gift or last_page else None,
            "signature_top": bottom - 12,
            "stamp": stamp if gift else None,
            "number": None if gift else (f"{key + 1}/{len(text.LETTER_PAGES)}", (PANEL.right - 8, PANEL.bottom - 10)),
        }

    def _actor_image(self, who: str) -> pygame.Surface:
        """Поза из манифеста, уменьшенная ближайшим соседом до 48×48 (Лео — до 32×32);
        кадры никогда не отражаются."""
        return self._actor_frame(who)[1]

    def _actor_frame(self, who: str) -> tuple[pygame.Surface, pygame.Surface]:
        """Поза из манифеста: исходный кадр (без отражения) и он же на холсте (48×48, у Лео 32×32)."""
        pose, sprites, size = {
            "alice": (self.alice_pose, self.alice_sprites, SPRITE_SIZE),
            "chuchmek": (self.chuchmek_pose, self.chuchmek_sprites, SPRITE_SIZE),
            "leo": (self.leo_pose, self.leo_sprites, LEO_SIZE),
        }[who]
        key = (who, pose)
        if key not in self._frames:
            if sprites is None:
                source = placeholder_animations().default.frames[0]
            else:
                try:
                    source = sprites.frame(pose).image
                except KeyError:
                    source = sprites.frames[0].image
            self._frames[key] = (source, pygame.transform.scale(source, (size, size)))
        return self._frames[key]

    def _draw_actor(
        self, surface: pygame.Surface, who: str, feet: tuple[int, int], hires: HiResLayer | None = None
    ) -> None:
        bob = 0
        if self.dialogue is not None and self.dialogue.node is not None:
            # Говорят только Алиса и Чучмек; Лео не покачивается «в такт» чужим репликам.
            speaker = "alice" if self.dialogue.node.speaker == text.ALICE else "chuchmek"
            if who == speaker and self.dialogue.is_typing:
                bob = round(abs(math.sin(self.time * 9)))
        source, image = self._actor_frame(who)
        rect = image.get_rect(midbottom=(feet[0], feet[1] - bob))
        if hires is not None:
            hires.sprite(source, rect)  # исходный кадр на том же месте и того же размера
        else:
            surface.blit(image, rect)

    @staticmethod
    def _draw_blanket(surface: pygame.Surface) -> None:
        """Мягкое покрывало Лео: часть страницы, под всеми героями."""
        pygame.draw.ellipse(surface, BLANKET_COLOR, BLANKET)
        pygame.draw.ellipse(surface, BLANKET_EDGE_COLOR, BLANKET, 1)
        for dx in (-9, 0, 9):  # звёздочки на покрывале
            surface.set_at((BLANKET.centerx + dx, BLANKET.centery + 1), CREAM_COLOR)

    def _draw_symbols(self, surface: pygame.Surface) -> None:
        """Три фрагмента: в начале летят к центру страницы и превращаются в символы."""
        t = self.phase_time / ARRIVAL_SECONDS if self.phase == ARRIVAL else 1.0
        # Подставка, над которой они парят.
        pygame.draw.ellipse(surface, PAGE_EDGE_COLOR, (138, 96, 44, 10))
        pygame.draw.ellipse(surface, CREAM_COLOR, (140, 96, 40, 7))
        for index, trial_id in enumerate(TRIALS):
            goal = SYMBOL_POSITIONS[trial_id]
            if t < 0.65:
                k = _ease((t - 0.15 - index * 0.06) / 0.4)
                start = FRAGMENT_STARTS[trial_id]
                x = start[0] + (goal[0] - start[0]) * k
                y = start[1] + (goal[1] - start[1]) * k
                size = 3 + round(k * 2)
                color = FRAGMENT_COLORS[trial_id]
                diamond = [(x, y - size), (x + size, y), (x, y + size), (x - size, y)]
                pygame.draw.polygon(surface, color, diamond)
                pygame.draw.polygon(surface, GLOW_COLOR, diamond, 1)
                continue
            bob = math.sin(self.time * 2 + index) * 1.5
            center = (goal[0], goal[1] + bob)
            glow = 11 + round(abs(math.sin(self.time * 2.5 + index)) * 2)
            pygame.draw.circle(surface, GLOW_COLOR, (round(center[0]), round(center[1])), glow, 1)
            if self.phase == ARRIVAL and t < 0.72:  # вспышка превращения
                pygame.draw.circle(surface, GLOW_COLOR, (round(center[0]), round(center[1])), 9)
            draw_symbol(surface, trial_id, center)

    def _draw_festive(self, surface: pygame.Surface) -> None:
        """Гирлянда флажков и огоньки: появляются по мере того, как страница становится праздничной."""
        k = self.festive
        if k <= 0:
            return
        visible = round(GARLAND_FLAGS * k)
        for i in range(GARLAND_FLAGS):
            x = 18 + i * (WIDTH - 36) / (GARLAND_FLAGS - 1)
            sag = math.sin(math.pi * i / (GARLAND_FLAGS - 1)) * 10
            y = 24 + sag
            if i + 1 < GARLAND_FLAGS:
                nx = 18 + (i + 1) * (WIDTH - 36) / (GARLAND_FLAGS - 1)
                ny = 24 + math.sin(math.pi * (i + 1) / (GARLAND_FLAGS - 1)) * 10
                pygame.draw.line(surface, INK_COLOR, (x, y), (nx, ny))
            if i < visible:
                color = FLAG_COLORS[i % len(FLAG_COLORS)]
                pygame.draw.polygon(surface, color, [(x - 4, y), (x + 4, y), (x, y + 8)])
        for i in range(12):  # огоньки на кустах вдоль края страницы мерцают по очереди
            if i / 12 >= k:
                break
            x, y = 22 + i * 25, 132 + (i % 2) * 6
            lit = math.sin(self.time * 3 + i * 1.7) > -0.2
            pygame.draw.circle(surface, GLOW_COLOR if lit else CREAM_COLOR, (x, y), 2)

    def _draw_letter(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        """Лист письма поверх притушенной страницы; проявляется за PAGE_FADE_SECONDS."""
        key = -1 if self.phase == GIFT else self.page
        alpha = round(255 * min(1.0, self.page_time / PAGE_FADE_SECONDS))
        if hires is not None:
            self._draw_letter_hires(surface, hires, key, alpha)
            return
        dim = pygame.Surface(config.LOGICAL_SIZE)
        dim.fill(NIGHT_COLOR)
        dim.set_alpha(150)
        surface.blit(dim, (0, 0))
        sheet = self._page_cache.get(key)
        if sheet is None:
            sheet = self._page_cache[key] = self._render_sheet(key)
        sheet.set_alpha(alpha)
        surface.blit(sheet, PANEL)

    def _draw_letter_hires(self, surface: pygame.Surface, hires: HiResLayer, key: int, alpha: int) -> None:
        """Лист — теми же рамками, что и на холсте, слова — шрифтом окна. Лист собирается одной
        картинкой (HiResLayer.group) и проявляется целиком, как картинка на холсте."""
        if alpha >= 255:
            # Непрозрачный лист закрывает почти всю страницу: притушить достаточно полей вокруг него
            # (затемнять весь экран 1920×1080 каждый кадр — около 3 мс).
            for margin in LETTER_MARGINS:
                hires.fill(NIGHT_COLOR, margin, alpha=150)
        else:
            hires.fill(NIGHT_COLOR, alpha=150)  # притушить страницу вместе с героями
        layout = self.letter_layout(key)
        with hires.group(PANEL, alpha=alpha) as sheet:
            sheet.rect(PARCHMENT_COLOR, PANEL)
            sheet.rect(GOLD_COLOR, PANEL, 2)
            sheet.rect(PAGE_EDGE_COLOR, PANEL.inflate(-6, -6), 1)
            title, point = layout["title"]
            sheet.text(title, LETTER_TITLE_STYLE, point, anchor="midleft")
            for line, point in layout["lines"]:
                sheet.text(line, LETTER_STYLE, point, anchor="midleft")
            if layout["signature"] is not None:
                sheet.text(text.LETTER_SIGNATURE, SIGNATURE_STYLE, layout["signature"], anchor="midright")
            if layout["stamp"] is not None:
                sheet.rect(STAMP_COLOR, layout["stamp"], 1)
                sheet.text("F-17: ОТКАЗАНО", STAMP_STYLE, layout["stamp"].center, anchor="center")
            if layout["number"] is not None:
                number, point = layout["number"]
                sheet.text(number, PAGE_NUMBER_STYLE, point, anchor="midright")

    def _render_sheet(self, key: int) -> pygame.Surface:
        sheet = pygame.Surface(PANEL.size)
        sheet.fill(PARCHMENT_COLOR)
        pygame.draw.rect(sheet, GOLD_COLOR, sheet.get_rect(), 2)
        pygame.draw.rect(sheet, PAGE_EDGE_COLOR, sheet.get_rect().inflate(-6, -6), 1)
        gift = key < 0
        title = text.GIFT_TITLE if gift else text.LETTER_TITLE
        sheet.blit(self._text(title, PLUM_COLOR), (PANEL_PADDING, PANEL_PADDING - 2))
        lines = self._gift_lines if gift else self._page_lines[key]
        y = PANEL_PADDING + self._font.get_linesize() + 2
        for line in lines:
            sheet.blit(self._text(line, INK_COLOR, 10), (PANEL_PADDING, y))
            y += self._letter_font.get_linesize()
        bottom = PANEL.height - PANEL_PADDING - self._font.get_linesize() + 2
        last_page = not gift and key == len(text.LETTER_PAGES) - 1
        if gift or last_page:
            signature = self._text(text.LETTER_SIGNATURE, PLUM_COLOR)
            sheet.blit(signature, signature.get_rect(topright=(PANEL.width - PANEL_PADDING, bottom - 12)))
        if gift:  # отказ по формуляру F-17 — штамп в верхнем углу листа, рядом с заголовком
            stamp = pygame.Rect(PANEL.width - PANEL_PADDING - 74, PANEL_PADDING - 3, 74, 12)
            pygame.draw.rect(sheet, STAMP_COLOR, stamp, 1)
            label = self._text("F-17: ОТКАЗАНО", STAMP_COLOR, 7)
            sheet.blit(label, label.get_rect(center=stamp.center))
        else:
            number = self._text(f"{key + 1}/{len(text.LETTER_PAGES)}", PAGE_EDGE_COLOR, 7)
            sheet.blit(number, number.get_rect(bottomright=(PANEL.width - 8, PANEL.height - 6)))
        return sheet

    def _draw_hint(self, canvas: pygame.Surface, hires: HiResLayer | None = None) -> None:
        line = self.hint()
        if not line:
            return
        dark = self.phase in (CREDITS, THE_END, DONE)
        if self.phase in (LETTER, GIFT):
            # Подсказка — внизу листа письма, чтобы не закрывать текст.
            if hires is not None:
                hires.text(line, SHEET_HINT_STYLE, (PANEL.centerx, PANEL.bottom - 10.5), anchor="center")
                return
            image = self._text(line, PAGE_EDGE_COLOR)
            canvas.blit(image, image.get_rect(midbottom=(PANEL.centerx, PANEL.bottom - 5)))
            return
        if self.phase == THE_END and int(self.time * 2) % 3 == 2:
            return  # мягко мигает
        color = CREAM_COLOR if dark else INK_COLOR
        if self.phase == CREDITS:  # титры уезжают под полосу подсказки, а не сквозь текст
            with logical_target(canvas, hires, CREDITS_HINT_BAR) as surface:
                surface.fill(NIGHT_COLOR, CREDITS_HINT_BAR)
        if hires is not None:
            # Под подсказкой титров — однотонная полоса; на последнем экране за ней звёзды.
            background = NIGHT_COLOR if self.phase == CREDITS else None
            hires.text(line, TextStyle(HINT_SIZE, color, background=background), (WIDTH // 2, HEIGHT - 11.5),
                       anchor="center")
            return
        image = self._text(line, color)
        canvas.blit(image, image.get_rect(midbottom=(WIDTH // 2, HEIGHT - 6)))

    def _draw_night(self, surface: pygame.Surface) -> None:
        surface.fill(NIGHT_COLOR)
        for i in range(40):  # звёзды и конфетти мерцают, без случайностей
            x = (i * 73) % WIDTH
            y = (i * 37 + 11) % HEIGHT
            if math.sin(self.time * 2 + i) > 0.1:
                surface.set_at((x, y), FLAG_COLORS[i % len(FLAG_COLORS)] if i % 3 == 0 else CREAM_COLOR)

    def credit_lines(self) -> list[tuple[str, str, int]]:
        """Титры с вертикальными отступами: (вид, текст, y) — y от верха блока."""
        result = []
        y = 0
        for kind, line in text.CREDITS:
            result.append((kind, line, y))
            y += {"title": 24, "line": 13, "small": 11, "gap": 8}[kind]
        return result

    def credits_top(self) -> float:
        """Где сейчас верх блока титров: они выезжают снизу к середине экрана."""
        lines = self.credit_lines()
        height = lines[-1][2] + 12
        start, end = HEIGHT, (HEIGHT - height) // 2
        return start + (end - start) * _ease(self.phase_time / CREDITS_SCROLL_SECONDS)

    def _draw_credits(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        top = self.credits_top()
        for kind, line, y in self.credit_lines():
            if not line:
                continue
            if hires is not None:
                # В окне титры едут плавно, по его пикселям, а не ступеньками холста.
                hires.text(line, CREDIT_STYLES[kind], (WIDTH / 2, top + y), anchor="midtop")
                continue
            if kind == "title":
                image = self._text(line, GOLD_COLOR, 16)
            elif kind == "small":
                image = self._text(line, CREDITS_SMALL_COLOR)
            else:
                image = self._text(line, CREAM_COLOR, 10)
            surface.blit(image, image.get_rect(midtop=(WIDTH // 2, round(top + y))))

    def _draw_the_end(self, surface: pygame.Surface, hires: HiResLayer | None = None) -> None:
        for index, trial_id in enumerate(TRIALS):
            draw_symbol(surface, trial_id, (130 + index * 30, 50 + math.sin(self.time * 2 + index) * 1.5))
        y = 82
        for line in text.THE_END_LINES:
            if hires is not None:
                hires.text(line, THE_END_STYLE, (WIDTH // 2, y), anchor="midtop")
            else:
                image = self._text(line, CREAM_COLOR, 12)
                surface.blit(image, image.get_rect(midtop=(WIDTH // 2, y)))
            y += 18

    def ribbon_rect(self, hires: bool = False) -> pygame.Rect:
        """Ленточка «Последняя страница» — по размеру подписи пиксельным шрифтом или шрифтом окна."""
        if hires:
            width, height = self.ribbon_metrics.size("Последняя страница")
            label = pygame.Rect(0, 0, math.ceil(width), math.ceil(height))
        else:
            label = render_text(self._font, "Последняя страница", PLUM_COLOR).get_rect()
        label.midtop = (WIDTH // 2, 6)
        return label.inflate(10, 2)

    def _render_page(self, label: bool = True) -> pygame.Surface:
        """Восстановленная страница книги: небо, холмы, тропинка, цветы — как на первой странице сказки.

        label=False — ленточка без подписи: её рисует слой высокого разрешения."""
        page = pygame.Surface(config.LOGICAL_SIZE)
        page.fill(PAGE_EDGE_COLOR)
        inner = pygame.Rect(4, 4, WIDTH - 8, HEIGHT - 8)
        pygame.draw.rect(page, PAGE_COLOR, inner)
        pygame.draw.rect(page, SKY_COLOR, (inner.x + 4, inner.y + 4, inner.width - 8, 86))
        pygame.draw.circle(page, GOLD_COLOR, (270, 46), 10)
        pygame.draw.ellipse(page, HILL_COLORS[1], (-40, 86, 220, 70))
        pygame.draw.ellipse(page, HILL_COLORS[0], (120, 82, 240, 70))
        pygame.draw.rect(page, HILL_COLORS[0], (inner.x, 112, inner.width, inner.bottom - 112))
        pygame.draw.polygon(page, (226, 204, 160), [(150, 112), (170, 112), (196, 172), (124, 172)])
        for i, x in enumerate(range(20, WIDTH - 10, 22)):  # цветы
            y = 150 + (i % 3) * 5
            page.fill(FLAG_COLORS[i % len(FLAG_COLORS)], (x, y, 3, 3))
        for x, y in ((40, 128), (290, 126)):  # кусты для огоньков
            pygame.draw.circle(page, HILL_COLORS[1], (x, y), 10)
        # Ленточка с подписью страницы.
        ribbon = self.ribbon_rect(hires=not label)
        pygame.draw.rect(page, CREAM_COLOR, ribbon)
        pygame.draw.rect(page, PLUM_COLOR, ribbon, 1)
        if label:
            image = render_text(self._font, "Последняя страница", PLUM_COLOR)
            page.blit(image, image.get_rect(center=ribbon.center))
        return page
