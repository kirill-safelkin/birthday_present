"""Окно игры: оконный и полноэкранный режимы, вывод логического холста на экран."""

from __future__ import annotations

import pygame
from pygame._sdl2.video import Window

import config


def fit_viewport(window_size: config.Size, logical_size: config.Size, integer_scaling: bool) -> pygame.Rect:
    """Возвращает область окна, в которую выводится холст.

    Пропорции холста сохраняются, а оставшееся место становится полями.
    При integer_scaling масштаб округляется вниз до целого, чтобы все игровые
    пиксели были одного размера. Если окно меньше холста, масштаб остаётся
    дробным, иначе картинка бы не поместилась.
    """
    window_w, window_h = window_size
    logical_w, logical_h = logical_size
    if window_w <= 0 or window_h <= 0:
        return pygame.Rect(0, 0, 0, 0)

    scale = min(window_w / logical_w, window_h / logical_h)
    if integer_scaling and scale >= 1:
        scale = int(scale)

    width = min(window_w, max(1, round(logical_w * scale)))
    height = min(window_h, max(1, round(logical_h * scale)))
    return pygame.Rect((window_w - width) // 2, (window_h - height) // 2, width, height)


class Display:
    """Окно игры и логический холст, на котором рисуется вся графика."""

    def __init__(self) -> None:
        pygame.display.set_caption(config.GAME_TITLE)
        pygame.display.set_mode(config.WINDOW_SIZE, pygame.RESIZABLE)
        # Обёртка над SDL-окном нужна для переключения полноэкранного режима.
        # Её нужно хранить, пока окно живо: Pygame сохраняет в окне ссылку на неё
        # без счётчика ссылок и подставляет её в event.window.
        self._window = Window.from_display_module()
        self.is_fullscreen = False

        # Холст создаётся после окна и поэтому получает формат пикселей экрана.
        # Это нужно present(): масштабировать прямо в окно можно только между
        # поверхностями одного формата.
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def toggle_fullscreen(self) -> None:
        """Переключает оконный и полноэкранный режимы.

        Полноэкранный режим «как рабочий стол»: окно занимает весь свой монитор
        без смены видеорежима, поэтому размер берётся у системы, а не задаётся
        в коде. При возврате SDL восстанавливает прежние размер и положение окна.

        pygame.display.set_mode() здесь не подходит: в Muffin (Linux Mint) окно
        после выхода из полноэкранного режима остаётся размером почти с монитор.
        pygame.display.toggle_fullscreen() тоже не подходит: для программной
        поверхности он меняет разрешение монитора.
        """
        if self.is_fullscreen:
            self._window.set_windowed()
        else:
            self._window.set_fullscreen(desktop=True)
        self.is_fullscreen = not self.is_fullscreen

    def present(self) -> None:
        """Увеличивает холст до размера окна и выводит кадр на экран."""
        screen = pygame.display.get_surface()
        width, height = screen.get_size()
        viewport = fit_viewport((width, height), self.canvas.get_size(), config.INTEGER_SCALING)

        # Заливаем только поля вокруг картинки: заливка всего экрана каждый кадр
        # в полноэкранном режиме заметно добавляет нагрузки на процессор.
        for bar in (
            pygame.Rect(0, 0, width, viewport.top),
            pygame.Rect(0, viewport.bottom, width, height - viewport.bottom),
            pygame.Rect(0, viewport.top, viewport.left, viewport.height),
            pygame.Rect(viewport.right, viewport.top, width - viewport.right, viewport.height),
        ):
            screen.fill(config.LETTERBOX_COLOR, bar)

        if viewport.width and viewport.height:
            # transform.scale берёт ближайший пиксель без сглаживания (в отличие от
            # smoothscale), поэтому пиксельная графика остаётся чёткой. Масштабируем
            # сразу в область окна: промежуточный буфер в полноэкранном режиме
            # стоил около 1 мс на кадр и не давал держать 60 кадров в секунду.
            pygame.transform.scale(self.canvas, viewport.size, screen.subsurface(viewport))

        pygame.display.flip()
