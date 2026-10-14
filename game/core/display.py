"""Окно игры: оконный и полноэкранный режимы, вывод логического холста на экран.

Кадр выводится в два слоя: логический холст 320×180, увеличенный ближайшим соседом,
и поверх него — слой высокого разрешения (персонажи и текст в разрешении окна,
game/graphics/hires.py) в той же области окна.
"""

from __future__ import annotations

import pygame
from pygame._sdl2.video import Window

import config
from game.graphics.hires import HiResLayer, ViewTransform


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
        # Команды высокого разрешения текущего кадра: present() выводит их поверх холста и очищает.
        self.hires = HiResLayer()
        # Для целого масштаба: холст, растянутый только по ширине, и список копий его строк (см. scale_canvas).
        self._rows: pygame.Surface | None = None
        self._row_blits: list[tuple[pygame.Surface, tuple[int, int], pygame.Rect]] = []

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

    def transform(self) -> ViewTransform:
        """Где сейчас в окне холст: область и масштаб — общие для холста и слоя высокого разрешения."""
        size = pygame.display.get_surface().get_size()
        return ViewTransform(fit_viewport(size, self.canvas.get_size(), config.INTEGER_SCALING), self.canvas.get_size())

    def present(self) -> None:
        """Увеличивает холст до размера окна, выводит поверх него слой высокого разрешения и показывает кадр."""
        screen = pygame.display.get_surface()
        width, height = screen.get_size()
        transform = self.transform()
        viewport = transform.viewport

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
            self.scale_canvas(screen.subsurface(viewport))
            # Персонажи и текст — той же трансформацией, что и холст: на свои места мира.
            self.hires.render(screen, transform)
        self.hires.clear()

        pygame.display.flip()

    def scale_canvas(self, target: pygame.Surface) -> None:
        """Увеличивает холст ближайшим соседом во всю поверхность target (область окна).

        transform.scale берёт ближайший пиксель без сглаживания (в отличие от
        smoothscale), поэтому пиксельная графика остаётся чёткой. Масштабируем
        сразу в область окна: промежуточный буфер в полноэкранном режиме
        стоил около 1 мс на кадр и не давал держать 60 кадров в секунду.

        При целом масштабе (×3, ×6) холст сначала растягивается только по ширине, а потом
        каждая его строка копируется нужное число раз. Результат тот же пиксель в пиксель,
        но в полноэкранном режиме это примерно вдвое быстрее (1,3 мс вместо 2,5–3 мс
        на кадр) — запас для слоя высокого разрешения.
        """
        canvas_w, canvas_h = self.canvas.get_size()
        width, height = target.get_size()
        factor = height // canvas_h
        if factor < 2 or (width, height) != (canvas_w * factor, canvas_h * factor):
            pygame.transform.scale(self.canvas, (width, height), target)
            return
        if self._rows is None or self._rows.get_size() != (width, canvas_h):
            self._rows = pygame.Surface((width, canvas_h), 0, self.canvas)
            self._row_blits = [
                (self._rows, (0, y * factor + copy), pygame.Rect(0, y, width, 1))
                for y in range(canvas_h)
                for copy in range(factor)
            ]
        pygame.transform.scale(self.canvas, (width, canvas_h), self._rows)
        target.blits(self._row_blits, doreturn=False)
