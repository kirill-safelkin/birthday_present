"""Временный экран проверки: технический фундамент и вход в тестовые экраны.

Тестовые экраны (диалог, анимация, галерея спрайтов) открываются через менеджер сцен
поверх этого экрана и возвращают к нему по Backspace. Экран заменит первая игровая сцена.
"""

from __future__ import annotations

import pygame

import config
from game.core.input import matches_key
from game.core.scenes import Scene
from game.debug.animation_demo import AnimationDemo
from game.debug.demo_dialogue import DEMO_SCRIPT, QUESTION_ID
from game.debug.dialogue_demo import DialogueDemo
from game.debug.sprite_gallery import SpriteGallery
from game.dialogue.box import DialogueBox
from game.dialogue.model import DialogueChoice, DialogueController
from game.graphics.fonts import load_font, render_text

# Как часто обновлять число FPS (в секундах): каждый кадр цифры бы мелькали.
FPS_REFRESH_INTERVAL = 0.5
HINTS = (
    ("F11", "полный экран"),
    ("D", "тестовый диалог"),
    ("A", "тест анимации"),
    ("P", "галерея спрайтов"),
    ("ESC", "выход"),
)
# Отладочные сочетания: код клавиши и скан-код (буквы работают в русской и немецкой раскладках).
DIALOGUE_KEY = (pygame.K_d, pygame.KSCAN_D)
ANIMATION_KEY = (pygame.K_a, pygame.KSCAN_A)
GALLERY_KEY = (pygame.K_p, pygame.KSCAN_P)
# Вертикальная раскладка: центры заголовка, подзаголовка и итога диалога, верх подсказок.
TITLE_Y = 44
SUBTITLE_Y = 62
RESULT_Y = 82
HINTS_TOP = 108
LINE_STEP = 13


class DebugScreen(Scene):
    """Тёмный фон, название игры, подсказки, счётчик FPS и итог последнего тестового диалога."""

    def __init__(self, clock: pygame.time.Clock) -> None:
        self._clock = clock
        # 9 px: при 8 и 10 px ноль в DejaVu Sans Mono без сглаживания похож на «8».
        self._fps_font = load_font(9)
        self._text_font = load_font(10)
        title_font = load_font(16)

        self._center_x = config.LOGICAL_SIZE[0] // 2
        title = render_text(title_font, "АЛИСА И ЧУЧМЕК", config.TITLE_COLOR)
        subtitle = render_text(self._text_font, "Технический прототип", config.TEXT_COLOR)
        hints = [render_text(self._text_font, f"{key:<3} — {action}", config.HINT_COLOR) for key, action in HINTS]

        # Статичные надписи рендерятся один раз, в кадре их только копируют на холст.
        self._labels: list[tuple[pygame.Surface, pygame.Rect]] = [
            (title, title.get_rect(center=(self._center_x, TITLE_Y))),
            (subtitle, subtitle.get_rect(center=(self._center_x, SUBTITLE_Y))),
        ]
        # Подсказки выровнены по левому краю общего блока, чтобы тире стояли друг под другом.
        hints_left = self._center_x - max(hint.get_width() for hint in hints) // 2
        for index, hint in enumerate(hints):
            self._labels.append((hint, hint.get_rect(topleft=(hints_left, HINTS_TOP + index * LINE_STEP))))
        # Итог последней демонстрации диалога; пусто, пока диалог не пройден.
        self._result_labels: list[tuple[pygame.Surface, pygame.Rect]] = []

        self._fps_timer = 0.0
        self._fps_label = self._render_fps()

        self._dialogue_box = DialogueBox()
        # Проверяем при запуске, а не посреди демонстрации, что все реплики помещаются на экран.
        self._dialogue_box.check_fits(DEMO_SCRIPT)
        # Ответ на вопрос из последнего завершённого прохода демонстрации.
        self.last_answer: DialogueChoice | None = None

    # Что сейчас открыто поверх экрана проверки. Только для чтения: переходы делает менеджер.

    @property
    def dialogue(self) -> DialogueController | None:
        scene = self._open_scene(DialogueDemo)
        return scene.dialogue if scene is not None else None

    @property
    def animation_demo(self) -> AnimationDemo | None:
        return self._open_scene(AnimationDemo)

    @property
    def sprite_gallery(self) -> SpriteGallery | None:
        return self._open_scene(SpriteGallery)

    def _open_scene(self, kind: type[Scene]) -> Scene | None:
        current = self.manager.current if self.manager is not None else None
        return current if isinstance(current, kind) else None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN or self.manager is None:
            return
        if matches_key(event, *DIALOGUE_KEY):
            self._result_labels = []  # итог прошлого прохода устарел и мешал бы окну диалога
            self.manager.push(DialogueDemo(DEMO_SCRIPT, self._dialogue_box, on_finish=self._finish_dialogue))
        elif matches_key(event, *ANIMATION_KEY):
            self.manager.push(AnimationDemo())
        elif matches_key(event, *GALLERY_KEY):
            self.manager.push(SpriteGallery())

    def update(self, dt: float) -> None:
        self._fps_timer += dt
        if self._fps_timer >= FPS_REFRESH_INTERVAL:
            self._fps_timer = 0.0
            self._fps_label = self._render_fps()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND_COLOR)
        for image, rect in self._labels + self._result_labels:
            surface.blit(image, rect)
        surface.blit(self._fps_label, (4, 3))

    def _finish_dialogue(self, dialogue: DialogueController) -> None:
        """Показывает на экране проверки, какой ответ выбран в завершённом диалоге."""
        self.last_answer = dialogue.answers.get(QUESTION_ID)
        lines = ["Диалог завершён. D — запустить снова"]
        if self.last_answer is not None:
            lines.append(f"Ваш ответ: «{self.last_answer.text}»")
        self._result_labels = []
        for index, text in enumerate(lines):
            image = render_text(self._text_font, text, config.TEXT_COLOR)
            self._result_labels.append((image, image.get_rect(center=(self._center_x, RESULT_Y + index * LINE_STEP))))

    def _render_fps(self) -> pygame.Surface:
        return render_text(self._fps_font, f"{self._clock.get_fps():.0f} кадр/с", config.FPS_COLOR)
