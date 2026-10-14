"""Демонстрация диалога: окно диалога поверх предыдущей сцены. Открывается клавишей D с экрана проверки."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from game.core.input import Action, actions_for
from game.core.scenes import Scene
from game.dialogue.box import DialogueBox
from game.dialogue.model import DialogueController, DialogueScript


class DialogueDemo(Scene):
    """Проводит игрока по сценарию. Когда диалог завершён, передаёт его в on_finish и закрывается.

    Backspace (действие cancel) закрывает диалог досрочно, без итога.
    """

    is_overlay = True  # под окном диалога виден экран, с которого его открыли

    def __init__(
        self,
        script: DialogueScript,
        box: DialogueBox | None = None,
        on_finish: Callable[[DialogueController], None] | None = None,
    ) -> None:
        self.dialogue = DialogueController(script)
        self.box = box if box is not None else DialogueBox()
        self._on_finish = on_finish

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and Action.CANCEL in actions_for(event):
            self.finish()
            return
        self.dialogue.handle_event(event)
        if self.dialogue.is_finished:
            if self._on_finish is not None:
                self._on_finish(self.dialogue)
            self.finish()

    def update(self, dt: float) -> None:
        self.dialogue.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        self.box.draw(surface, self.dialogue)
