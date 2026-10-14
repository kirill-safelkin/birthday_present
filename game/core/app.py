"""Главный игровой цикл: события → обновление → отрисовка."""

from __future__ import annotations

import os

import pygame

import config
from game.core.display import Display
from game.core.input import ActionInput
from game.core.scenes import SceneManager
from game.debug.debug_screen import DebugScreen
from game.trials.forms_scene import FORMS_SCENE, FormsTrialScene
from game.trials.sushi_scene import SUSHI_SCENE, SushiTrialScene
from game.world.hub import HUB_SCENE, HubScene
from game.world.progress import GameProgress


class App:
    """Владеет окном, часами, общим вводом и менеджером сцен и крутит игровой цикл."""

    def __init__(self) -> None:
        self.display = Display()
        self._clock = pygame.time.Clock()
        self.input = ActionInput()
        self.scenes = SceneManager(self.input)
        # Прогресс общий для всей игры: площадь, создаваемая заново, видит те же фрагменты.
        self.progress = GameProgress()
        self.scenes.register(HUB_SCENE, lambda: HubScene(self.progress))
        # Испытания: суши и формуляры. Торты не регистрируются — их портал закрыт.
        self.scenes.register(SUSHI_SCENE, lambda: SushiTrialScene(self.progress))
        self.scenes.register(FORMS_SCENE, lambda: FormsTrialScene(self.progress))
        # Стартовая сцена — временный экран проверки. Его заменит первая игровая сцена.
        self.screen = DebugScreen(self._clock)
        self.scenes.push(self.screen)
        self.running = False

    def run(self) -> None:
        self.running = True
        while self.running:
            # tick() ждёт, чтобы кадров было не больше FPS (процессор не крутится вхолостую),
            # и возвращает миллисекунды, прошедшие с прошлого кадра.
            dt = min(self._clock.tick(config.FPS) / 1000, config.MAX_FRAME_TIME)
            self._handle_events()
            self._update(dt)
            self._draw()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            # Общий ввод видит все события. Автоповтор зажатой клавиши пропускаем целиком:
            # он не должен второй раз подтверждать реплику или переключать полный экран.
            if not self.input.handle_event(event):
                continue
            if event.type == pygame.QUIT:  # крестик окна, Alt+F4
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self.display.toggle_fullscreen()
            else:
                # Остальные события получает только верхняя сцена.
                self.scenes.handle_event(event)

    def _update(self, dt: float) -> None:
        """Обновление состояния игры; dt — длительность кадра в секундах."""
        self.scenes.update(dt)

    def _draw(self) -> None:
        """Отрисовка: сцена рисует на холсте 320×180, затем холст выводится в окно."""
        self.scenes.draw(self.display.canvas)
        self.display.present()


def _init_pygame() -> None:
    """Инициализирует нужные модули Pygame или сообщает, что показать окно негде."""
    # Игра рисует программно, OpenGL ей не нужен. Без этой подсказки SDL на Linux
    # при создании окна проверяет OpenGL, и со сломанным драйвером видеокарты
    # процесс аварийно завершается с ошибкой «X Error … GLX». Значение,
    # заданное в окружении, имеет приоритет.
    os.environ.setdefault("SDL_FRAMEBUFFER_ACCELERATION", "0")
    # Звук появится на следующих этапах, поэтому инициализируем только экран и шрифты.
    pygame.display.init()
    # Без графического сеанса SDL молча выбирает драйвер offscreen, и игра работала бы
    # невидимо. Такие драйверы допустимы, только если их выбрали явно (например, в тестах).
    if pygame.display.get_driver() in ("offscreen", "dummy") and not os.environ.get("SDL_VIDEODRIVER"):
        raise pygame.error("графический дисплей не найден")
    pygame.font.init()


def run() -> None:
    """Запускает игру и при любом исходе освобождает ресурсы Pygame."""
    try:
        _init_pygame()
        App().run()
    finally:
        pygame.quit()
