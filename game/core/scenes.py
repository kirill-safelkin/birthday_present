"""Сцены и менеджер сцен.

Сцена — экран игры со своими handle_event(), update(dt), draw(surface), enter() и exit().
Менеджер держит стек сцен: события, обновление и отрисовку получает только верхняя.
push() открывает сцену поверх текущей (например, тестовый экран над экраном проверки),
pop() возвращает к предыдущей, replace() заменяет текущую (будущие переходы между
локациями). Сцены можно регистрировать по имени и открывать без прямого импорта:

    manager.register("intro", IntroScene)
    manager.replace("intro")
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

import config
from game.core.input import ActionInput


class SceneError(RuntimeError):
    """Недопустимый переход между сценами. Состояние менеджера при этом не меняется."""


class Scene:
    """Базовая сцена: методы по умолчанию ничего не делают.

    enter() вызывается, когда сцена становится верхней (в том числе при возврате к ней),
    exit() — когда перестаёт быть верхней. manager задаётся, пока сцена в стеке.
    Прозрачная сцена (is_overlay) рисуется поверх предыдущей, например окно диалога.
    """

    manager: SceneManager | None = None
    is_finished = False  # сцена завершилась и закрыта (или будет закрыта, если стека нет)
    is_overlay = False

    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass

    def finish(self) -> None:
        """Завершает сцену и возвращает к предыдущей, если эта сцена сейчас верхняя."""
        self.is_finished = True
        manager = self.manager
        if manager is not None and manager.current is self and len(manager.stack) > 1:
            manager.pop()


SceneFactory = Callable[[], Scene]


class SceneManager:
    """Стек сцен и общий ввод, доступный сценам через manager.input."""

    def __init__(self, input_state: ActionInput | None = None) -> None:
        self.input = input_state if input_state is not None else ActionInput()
        self._stack: list[Scene] = []
        self._factories: dict[str, SceneFactory] = {}

    @property
    def current(self) -> Scene | None:
        return self._stack[-1] if self._stack else None

    @property
    def stack(self) -> tuple[Scene, ...]:
        """Сцены снизу вверх."""
        return tuple(self._stack)

    def register(self, name: str, factory: SceneFactory) -> None:
        """Регистрирует сцену по имени: factory() создаёт новый экземпляр при каждом переходе."""
        if not isinstance(name, str) or not name.strip():
            raise SceneError("имя сцены должно быть непустой строкой")
        if name in self._factories:
            raise SceneError(f"сцена «{name}» уже зарегистрирована")
        if not callable(factory):
            raise SceneError(f"для сцены «{name}» нужна функция или класс, создающие сцену")
        self._factories[name] = factory

    def is_registered(self, name: str) -> bool:
        return name in self._factories

    def push(self, scene: Scene | str) -> Scene:
        """Открывает сцену поверх текущей. Текущая замирает и получает exit()."""
        scene = self._resolve(scene)
        previous = self.current
        self._stack.append(scene)
        scene.manager = self
        scene.is_finished = False
        if previous is not None:
            previous.exit()
        scene.enter()
        return scene

    def replace(self, scene: Scene | str) -> Scene:
        """Заменяет текущую сцену новой; заменённая закрывается. Пустой стек — то же, что push()."""
        scene = self._resolve(scene)
        old = self._stack.pop() if self._stack else None
        self._stack.append(scene)
        scene.manager = self
        scene.is_finished = False
        if old is not None:
            old.exit()
            old.manager = None
        scene.enter()
        return scene

    def pop(self) -> Scene:
        """Закрывает текущую сцену и возвращает к предыдущей, которая снова получает enter()."""
        if len(self._stack) < 2:
            raise SceneError("возвращаться некуда: под текущей сценой нет другой")
        old = self._stack.pop()
        old.exit()
        old.manager = None
        old.is_finished = True
        self._stack[-1].enter()
        return old

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.current is not None:
            self.current.handle_event(event)

    def update(self, dt: float) -> None:
        if self.current is not None:
            self.current.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        """Рисует верхнюю сцену, а под прозрачной — и сцены ниже (они при этом не обновляются)."""
        if not self._stack:
            surface.fill(config.BACKGROUND_COLOR)
            return
        bottom = len(self._stack) - 1
        while bottom > 0 and self._stack[bottom].is_overlay:
            bottom -= 1
        for scene in self._stack[bottom:]:
            scene.draw(surface)

    def _resolve(self, scene: Scene | str) -> Scene:
        if isinstance(scene, str):
            factory = self._factories.get(scene)
            if factory is None:
                raise SceneError(f"сцена «{scene}» не зарегистрирована")
            scene = factory()
        if not isinstance(scene, Scene):
            raise SceneError(f"ожидалась сцена, а получено {type(scene).__name__}")
        if scene in self._stack:
            raise SceneError(f"сцена {type(scene).__name__} уже открыта")
        return scene
