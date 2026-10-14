"""Временный экран проверки технического фундамента, демонстрации диалогов и анимации.

Его заменит первая игровая сцена с теми же методами handle_event(), update() и draw().
"""

from __future__ import annotations

import pygame

import config
from game.debug.animation_demo import AnimationDemo
from game.debug.demo_dialogue import DEMO_SCRIPT, QUESTION_ID
from game.dialogue.model import DialogueChoice, DialogueController
from game.dialogue.box import DialogueBox
from game.graphics.fonts import load_font, render_text
from game.core.input import matches_key

# Как часто обновлять число FPS (в секундах): каждый кадр цифры бы мелькали.
FPS_REFRESH_INTERVAL = 0.5
HINTS = (("F11", "полный экран"), ("D", "тестовый диалог"), ("A", "тест анимации"), ("ESC", "выход"))


class DebugScreen:
    """Тёмный фон, название игры, подсказки по управлению, счётчик FPS, тестовые диалог и анимация."""

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
            (title, title.get_rect(center=(self._center_x, 56))),
            (subtitle, subtitle.get_rect(center=(self._center_x, 76))),
        ]
        # Подсказки выровнены по левому краю общего блока, чтобы тире стояли друг под другом.
        hints_left = self._center_x - max(hint.get_width() for hint in hints) // 2
        for index, hint in enumerate(hints):
            self._labels.append((hint, hint.get_rect(topleft=(hints_left, 124 + index * 13))))
        # Итог последней демонстрации диалога; пусто, пока диалог не пройден.
        self._result_labels: list[tuple[pygame.Surface, pygame.Rect]] = []

        self._fps_timer = 0.0
        self._fps_label = self._render_fps()

        self._dialogue_box = DialogueBox()
        # Проверяем при запуске, а не посреди демонстрации, что все реплики помещаются на экран.
        self._dialogue_box.check_fits(DEMO_SCRIPT)
        self.dialogue: DialogueController | None = None
        # Ответ на вопрос из последнего завершённого прохода демонстрации.
        self.last_answer: DialogueChoice | None = None
        self.animation_demo: AnimationDemo | None = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.animation_demo is not None:
            # Пока открыт тест анимации, клавиши достаются ему (D там — шаг вправо, а не диалог).
            self.animation_demo.handle_event(event)
            if self.animation_demo.is_finished:
                self.animation_demo = None
        elif self.dialogue is not None:
            # Пока открыт диалог, клавиши достаются ему.
            self.dialogue.handle_event(event)
            if self.dialogue.is_finished:
                self._finish_dialogue(self.dialogue)
        elif event.type == pygame.KEYDOWN and matches_key(event, pygame.K_d, pygame.KSCAN_D):
            self.dialogue = DialogueController(DEMO_SCRIPT)
            self._result_labels = []  # итог прошлого прохода устарел и мешал бы окну диалога
        elif event.type == pygame.KEYDOWN and matches_key(event, pygame.K_a, pygame.KSCAN_A):
            self.animation_demo = AnimationDemo()

    def update(self, dt: float) -> None:
        self._fps_timer += dt
        if self._fps_timer >= FPS_REFRESH_INTERVAL:
            self._fps_timer = 0.0
            self._fps_label = self._render_fps()
        if self.animation_demo is not None:
            self.animation_demo.update(dt)
        elif self.dialogue is not None:
            self.dialogue.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        if self.animation_demo is not None:
            self.animation_demo.draw(surface)
            return
        surface.fill(config.BACKGROUND_COLOR)
        for image, rect in self._labels + self._result_labels:
            surface.blit(image, rect)
        surface.blit(self._fps_label, (4, 3))
        if self.dialogue is not None:
            self._dialogue_box.draw(surface, self.dialogue)

    def _finish_dialogue(self, dialogue: DialogueController) -> None:
        """Возвращает экран проверки и показывает, какой ответ выбран в диалоге."""
        self.dialogue = None
        self.last_answer = dialogue.answers.get(QUESTION_ID)
        lines = ["Диалог завершён. D — запустить снова"]
        if self.last_answer is not None:
            lines.append(f"Ваш ответ: «{self.last_answer.text}»")
        self._result_labels = []
        for index, text in enumerate(lines):
            image = render_text(self._text_font, text, config.TEXT_COLOR)
            self._result_labels.append((image, image.get_rect(center=(self._center_x, 96 + index * 13))))

    def _render_fps(self) -> pygame.Surface:
        return render_text(self._fps_font, f"{self._clock.get_fps():.0f} кадр/с", config.FPS_COLOR)
