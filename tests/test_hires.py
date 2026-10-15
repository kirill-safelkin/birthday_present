"""Проверки слоя высокого разрешения: персонажи из исходных кадров и текст в разрешении окна.

Тесты не зависят от того, какой именно шрифт установлен: всё, что касается текста,
проверяется и с найденным системным шрифтом, и с запасным встроенным шрифтом Pygame.
"""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import hashlib  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.display import Display, fit_viewport  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.dialogue.box import NAME_PADDING_X, PADDING_X, TEXT_STYLE, DialogueBox, wrap_spans  # noqa: E402
from game.dialogue.model import DialogueController  # noqa: E402
from game.graphics.animation import WALK, Animation, AnimationError, AnimationPlayer, Direction  # noqa: E402
from game.graphics.fonts import LAYOUT_SCALES, TextFonts, TextStyle  # noqa: E402
from game.graphics.hires import (  # noqa: E402
    FillCommand,
    HiResLayer,
    PatchCommand,
    SpriteCommand,
    TearCommand,
    TextCommand,
    ViewTransform,
    scale_sprite,
)
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story import hub_dialogue, intro_dialogue  # noqa: E402
from game.story.intro_scene import (  # noqa: E402
    ERROR_H,
    ERROR_LINE_STYLE,
    ERROR_TITLE_STYLE,
    ERROR_W,
    FINALE_STYLE,
    FINALE_TEXT,
    TITLE_BOTTOM,
    TITLE_FINAL_STYLE,
    TITLE_STYLE,
    IntroScene,
)
from game.world.character import Character  # noqa: E402
from game.world.hub import (  # noqa: E402
    HUD_HEIGHT,
    HUD_STYLE,
    MOSAIC_CENTER,
    PORTALS,
    SIGN_STYLE,
    SPAWN,
    STATUS_TOP,
    TREES,
    HubScene,
)
from game.world.progress import TRIALS, GameProgress  # noqa: E402

WIDTH, HEIGHT = config.LOGICAL_SIZE
WINDOWED = (960, 540)  # окно ×3
FULLSCREEN = (1920, 1200)  # полный экран 16:10: ×6 с полями сверху и снизу
RUSSIAN = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
LONG_TEXT = (
    "Чучмек сказал, что сказка перезапустилась слишком рано, и теперь придётся пройти три испытания, "
    "собрать фрагменты праздника и восстановить последнюю страницу — желательно до обеда."
)


def transform_for(window_size) -> ViewTransform:
    return ViewTransform(fit_viewport(window_size, config.LOGICAL_SIZE, config.INTEGER_SCALING))


def font_variants():
    """Найденный системный шрифт без засечек и запасной встроенный шрифт Pygame."""
    return {"системный": TextFonts(), "встроенный": TextFonts(None)}


def screen_pixels(surface: pygame.Surface, rect: pygame.Rect) -> bytes:
    return pygame.image.tobytes(surface.subsurface(rect), "RGB")


class PygameTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode(WINDOWED)

    def tearDown(self) -> None:
        pygame.quit()


class ViewTransformTest(unittest.TestCase):
    def test_windowed_and_fullscreen_geometry_comes_from_the_viewport(self) -> None:
        windowed, fullscreen = transform_for(WINDOWED), transform_for(FULLSCREEN)
        self.assertEqual((windowed.viewport, windowed.scale), (pygame.Rect(0, 0, 960, 540), 3))
        self.assertEqual((fullscreen.viewport, fullscreen.scale), (pygame.Rect(0, 60, 1920, 1080), 6))
        rect = pygame.Rect(144, 126, 32, 32)
        self.assertEqual(windowed.rect(rect), pygame.Rect(432, 378, 96, 96))
        self.assertEqual(fullscreen.rect(rect), pygame.Rect(864, 60 + 756, 192, 192))  # с полем сверху

    def test_bars_left_and_right_and_other_scales(self) -> None:
        ultrawide = transform_for((2560, 1080))  # поля слева и справа
        self.assertEqual(ultrawide.point((0, 0)), (320, 0))
        self.assertEqual(ultrawide.point((WIDTH, HEIGHT)), (2240, 1080))
        small = transform_for((700, 420))  # окно, растянутое вручную: ×2 с полями
        self.assertEqual(small.scale, 2)
        expected = pygame.Rect(small.viewport.x + 20, small.viewport.y + 20, 8, 8)
        self.assertEqual(small.rect(pygame.Rect(10, 10, 4, 4)), expected)

    def test_logical_pixels_map_to_the_same_blocks_as_the_scaled_canvas(self) -> None:
        # Пиксель холста, увеличенный Display.present(), и прямоугольник трансформации совпадают.
        pygame.display.init()
        try:
            display = Display()
            for size in (WINDOWED, FULLSCREEN, (1366, 768), (2560, 1080)):
                with self.subTest(window=size):
                    pygame.display.set_mode(size, pygame.RESIZABLE)
                    display.canvas.fill((0, 0, 0))
                    display.canvas.set_at((37, 101), (255, 0, 0))
                    display.present()
                    screen = pygame.display.get_surface()
                    block = display.transform().rect(pygame.Rect(37, 101, 1, 1))
                    mask = pygame.mask.from_threshold(screen, (255, 0, 0), (1, 1, 1, 255))
                    self.assertEqual(mask.get_bounding_rects(), [block])
        finally:
            pygame.quit()


class ScaleSpriteTest(PygameTestCase):
    def frame(self) -> pygame.Surface:
        return load_character_sprites(CHARACTERS_DIR / "alice").frame("idle_down").image

    def test_source_is_not_changed_and_size_is_exact(self) -> None:
        source = self.frame()
        before = pygame.image.tobytes(source, "RGBA")
        for size in ((96, 96), (192, 192), (144, 144), (288, 288), (144, 127)):
            with self.subTest(size=size):
                scaled = scale_sprite(source, size)
                self.assertEqual(scaled.get_size(), size)
                self.assertIsNot(scaled, source)
        self.assertEqual(pygame.image.tobytes(source, "RGBA"), before)

    def test_integer_scale_is_nearest_neighbour_without_new_shades(self) -> None:
        source = self.frame()
        scaled = scale_sprite(source, (192, 192))  # площадь в полном экране: ровно ×3
        expected = pygame.transform.scale(source.premul_alpha(), (192, 192))
        self.assertEqual(pygame.image.tobytes(scaled, "RGBA"), pygame.image.tobytes(expected, "RGBA"))

    def test_fractional_scale_uses_every_source_pixel(self) -> None:
        # Шахматная доска 64×64: при уменьшении до 32×32 ближайшим соседом остаётся один цвет,
        # а при ×1,5 (площадь в окне 960×540) в кадре должны быть оба цвета.
        board = pygame.Surface((64, 64), pygame.SRCALPHA)
        for x in range(64):
            for y in range(64):
                board.set_at((x, y), (255, 255, 255, 255) if (x + y) % 2 else (0, 0, 0, 255))
        colors = set(pygame.image.tobytes(scale_sprite(board, (96, 96)), "RGB")[0::3])
        old = pygame.transform.scale(pygame.transform.scale(board, (32, 32)), (96, 96))
        old_colors = set(pygame.image.tobytes(old, "RGB")[0::3])
        self.assertEqual(len(old_colors), 1)  # прежний путь терял половину пикселей исходника
        self.assertTrue({0, 255} <= colors)

    def test_opaque_colors_stay_exact_at_every_size(self) -> None:
        # Окно ×3 и ×6 на площади и во вступлении, приседание Алисы, окна других размеров.
        sprite = pygame.Surface((64, 64), pygame.SRCALPHA)
        sprite.fill((200, 40, 90, 255))
        for size in ((96, 96), (192, 192), (144, 144), (288, 288), (144, 126), (288, 252), (144, 129), (100, 100)):
            with self.subTest(size=size):
                pixels = pygame.image.tobytes(scale_sprite(sprite, size), "RGBA")
                self.assertEqual(set(zip(*[iter(pixels)] * 4)), {(200, 40, 90, 255)})

    def test_transparent_edges_do_not_get_a_dark_fringe(self) -> None:
        # Красный квадрат на прозрачном (чёрном) фоне поверх белого: на краях — только смесь красного
        # с белым. Если бы чёрный цвет прозрачных пикселей подмешивался, красный канал упал бы ниже 255.
        sprite = pygame.Surface((64, 64), pygame.SRCALPHA)
        sprite.fill((0, 0, 0, 0))
        sprite.fill((255, 0, 0, 255), (16, 16, 32, 32))
        for size in ((96, 96), (144, 144), (288, 288)):
            with self.subTest(size=size):
                target = pygame.Surface(size)
                target.fill((255, 255, 255))
                target.blit(scale_sprite(sprite, size), (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
                reds = set(pygame.image.tobytes(target, "RGB")[0::3])
                self.assertEqual(reds, {255})


class AnimationSourcesTest(PygameTestCase):
    def test_scaled_animation_set_keeps_the_original_frames(self) -> None:
        sprites = load_character_sprites(CHARACTERS_DIR / "alice")
        animations = sprites.animation_set(32)
        for direction in (Direction.LEFT, Direction.RIGHT):
            walk = animations.get(WALK, direction)
            group = sprites.groups[f"walk_{direction.name.lower()}"]
            self.assertTrue(all(frame.get_size() == (32, 32) for frame in walk.frames))
            self.assertEqual([source for source in walk.sources], [sprites.frame(i).image for i in group.frame_ids])
        unscaled = sprites.animation_set()
        self.assertIsNone(unscaled.get(WALK, Direction.LEFT).sources)  # исходники и есть кадры

    def test_player_source_follows_the_current_frame(self) -> None:
        sprites = load_character_sprites(CHARACTERS_DIR / "alice")
        walk = sprites.animation_set(32).get(WALK, Direction.RIGHT)
        player = AnimationPlayer(walk)
        seen = []
        for _ in range(len(walk.frames) * 2):
            self.assertIs(player.source, walk.sources[player.frame_index])
            seen.append(player.frame_index)
            player.update(1 / walk.fps)
        self.assertEqual(sorted(set(seen)), list(range(len(walk.frames))))

    def test_sources_must_match_frames(self) -> None:
        frame = pygame.Surface((4, 4))
        with self.assertRaises(AnimationError):
            Animation([frame, frame], 4, sources=[frame])
        with self.assertRaises(AnimationError):
            Animation([frame], 4, sources=["кадр"])
        big = pygame.Surface((8, 8), pygame.SRCALPHA)
        big.fill((255, 0, 0, 255), (0, 0, 2, 8))  # красная полоса слева
        flipped = Animation([frame], 4, sources=[big]).flipped()
        self.assertEqual(tuple(flipped.sources[0].get_at((7, 0))), (255, 0, 0, 255))  # отражены и исходники

    def test_character_draws_its_source_frame_on_its_own_place(self) -> None:
        sprites = load_character_sprites(CHARACTERS_DIR / "alice")
        alice = Character("Алиса", sprites.animation_set(32), position=(100.4, 120.6))
        layer, canvas = HiResLayer(), pygame.Surface(config.LOGICAL_SIZE)
        canvas.fill((1, 2, 3))
        alice.draw(canvas, layer)
        (command,) = layer.commands
        self.assertIsInstance(command, SpriteCommand)
        self.assertIs(command.image, alice.player.source)
        self.assertEqual(command.image.get_size(), (64, 64))
        self.assertEqual(command.rect, alice.rect)  # тот же прямоугольник 32×32, что и на холсте
        self.assertEqual((alice.x, alice.y), (100.4, 120.6))  # игровая позиция не меняется
        self.assertEqual(set(pygame.image.tobytes(canvas, "RGB")), {1, 2, 3})  # на холсте её нет


class HiResLayerTest(PygameTestCase):
    def opaque_sprite(self) -> pygame.Surface:
        sprite = pygame.Surface((64, 64), pygame.SRCALPHA)
        sprite.fill((200, 40, 90, 255))
        return sprite

    def test_sprite_lands_on_the_transformed_rect_in_window_and_fullscreen(self) -> None:
        rect = pygame.Rect(150, 120, 32, 32)
        for size in (WINDOWED, FULLSCREEN):
            with self.subTest(window=size):
                transform = transform_for(size)
                screen = pygame.Surface(size)
                layer = HiResLayer()
                layer.sprite(self.opaque_sprite(), rect)
                layer.render(screen, transform)
                drawn = pygame.mask.from_threshold(screen, (200, 40, 90), (1, 1, 1, 255)).get_bounding_rects()
                self.assertEqual(drawn, [transform.rect(rect)])
                self.assertEqual(drawn[0].width, 32 * transform.scale)  # без растяжения: квадрат остаётся квадратом
                self.assertEqual(drawn[0].height, 32 * transform.scale)

    def test_sprite_never_paints_the_letterbox_bars(self) -> None:
        transform = transform_for(FULLSCREEN)
        screen = pygame.Surface(FULLSCREEN)
        layer = HiResLayer()
        layer.sprite(self.opaque_sprite(), pygame.Rect(-10, -10, 48, 48))  # частично за краем холста
        layer.render(screen, transform)
        drawn = pygame.mask.from_threshold(screen, (200, 40, 90), (1, 1, 1, 255)).get_bounding_rects()
        self.assertEqual(drawn, [pygame.Rect(0, 60, 38 * 6, 38 * 6)])

    def test_alpha_clip_and_rotation(self) -> None:
        transform = transform_for(WINDOWED)
        screen = pygame.Surface(WINDOWED)
        layer = HiResLayer()
        layer.sprite(self.opaque_sprite(), pygame.Rect(10, 10, 32, 32), alpha=128)
        layer.sprite(self.opaque_sprite(), pygame.Rect(100, 10, 32, 32), clip=pygame.Rect(0, 0, WIDTH, 30))
        layer.sprite(self.opaque_sprite(), pygame.Rect(200, 10, 32, 32), angle=30)
        layer.render(screen, transform)
        half = screen.get_at((transform.x(26), transform.y(26)))
        self.assertTrue(90 < half.r < 110 and 15 < half.g < 25)  # наполовину прозрачен поверх чёрного
        clipped = pygame.mask.from_threshold(screen.subsurface((270, 0, 150, 200)), (200, 40, 90), (1, 1, 1, 255))
        self.assertEqual(clipped.get_bounding_rects()[0].bottom, 90)  # ниже линии y=30 холста не видно
        rotated = pygame.mask.from_threshold(screen.subsurface((540, 0, 300, 250)), (200, 40, 90), (1, 1, 1, 255))
        self.assertGreater(rotated.get_bounding_rects()[0].width, 96)  # повёрнутый квадрат шире
        corner = (transform.x(200) + 2, transform.y(10) + 2)
        self.assertEqual(tuple(screen.get_at(corner))[:3], (0, 0, 0))  # углы повёрнутого кадра прозрачны

    def test_logical_drawing_goes_to_canvas_until_something_overlaps(self) -> None:
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer()
        with layer.logical(canvas, pygame.Rect(0, 0, 10, 10)) as surface:
            self.assertIs(surface, canvas)  # команд нет — прямо на холст
        layer.sprite(self.opaque_sprite(), pygame.Rect(100, 100, 32, 32))
        with layer.logical(canvas, pygame.Rect(0, 0, 10, 10)) as surface:
            self.assertIs(surface, canvas)  # персонаж далеко — порядок не нарушится
        with layer.logical(canvas, pygame.Rect(110, 110, 30, 30)) as surface:
            self.assertIsNot(surface, canvas)  # перекрывает персонажа — заплатка поверх него
            surface.fill((9, 9, 9), (110, 110, 30, 30))
        self.assertIsInstance(layer.commands[-1], PatchCommand)
        self.assertEqual(layer.commands[-1].rect, pygame.Rect(110, 110, 30, 30))
        with layer.logical(canvas) as surface:  # область неизвестна — заплатка по нарисованному
            surface.fill((9, 9, 9), (2, 3, 4, 5))
        self.assertEqual(layer.commands[-1].rect, pygame.Rect(2, 3, 4, 5))

    def test_strict_layer_catches_drawing_outside_the_declared_area(self) -> None:
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer(strict=True)
        with self.assertRaises(AssertionError):
            with layer.logical(canvas, pygame.Rect(0, 0, 10, 10)) as surface:
                surface.fill((9, 9, 9), (5, 5, 10, 10))

    def test_patch_is_drawn_over_the_sprite_in_order(self) -> None:
        transform = transform_for(WINDOWED)
        screen = pygame.Surface(WINDOWED)
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer()
        layer.sprite(self.opaque_sprite(), pygame.Rect(100, 100, 32, 32))
        with layer.logical(canvas, pygame.Rect(110, 110, 4, 4)) as surface:
            surface.fill((0, 255, 0), (110, 110, 4, 4))
        layer.render(screen, transform)
        self.assertEqual(tuple(screen.get_at((transform.x(111), transform.y(111))))[:3], (0, 255, 0))
        self.assertEqual(tuple(screen.get_at((transform.x(105), transform.y(105))))[:3], (200, 40, 90))

    def test_torn_frame_shifts_bands_in_window_pixels(self) -> None:
        transform = transform_for(WINDOWED)
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        for x in range(WIDTH):
            canvas.fill((x % 256, 0, 0), (x, 0, 1, HEIGHT))
        layer = HiResLayer()
        layer.torn(canvas, (), ((12, 6, 5),))
        screen = pygame.Surface(WINDOWED)
        layer.render(screen, transform)
        self.assertEqual(screen.get_at((transform.x(50), transform.y(13))).r, 45)  # полоса сдвинута на 5 вправо
        self.assertEqual(screen.get_at((transform.x(50), transform.y(30))).r, 50)  # остальное на месте
        self.assertEqual(screen.get_at((transform.x(2), transform.y(13))).r, (WIDTH - 3) % 256)  # вернулось слева

    def test_scaled_patches_are_reused_until_their_content_changes(self) -> None:
        layer = HiResLayer()
        patch = pygame.Surface((20, 10), pygame.SRCALPHA)
        patch.fill((10, 20, 30, 255))
        first = layer.scaled_patch(patch, (60, 30))
        same = pygame.Surface((20, 10), pygame.SRCALPHA)
        same.fill((10, 20, 30, 255))
        self.assertIs(layer.scaled_patch(same, (60, 30)), first)  # то же содержимое — без нового увеличения
        same.set_at((3, 3), (200, 0, 0, 255))
        changed = layer.scaled_patch(same, (60, 30))
        self.assertIsNot(changed, first)
        self.assertEqual(tuple(changed.get_at((10, 10)))[:3], (200, 0, 0))
        self.assertIsNot(layer.scaled_patch(patch, (120, 60)), first)  # другой размер окна — другое увеличение

    def test_keyed_patch_draws_the_same_pixels_as_alpha_blending(self) -> None:
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        for patch_color in ((255, 0, 255), (14, 18, 42)):  # даже если в заплатке есть цвет первого ключа
            layer = HiResLayer()
            layer.sprite(pygame.Surface((64, 64), pygame.SRCALPHA), pygame.Rect(0, 0, 64, 64))  # чтобы была заплатка
            with layer.logical(canvas, pygame.Rect(10, 10, 40, 20)) as surface:
                surface.fill(patch_color, (10, 10, 40, 20))
                surface.fill((0, 0, 0, 0), (12, 12, 6, 6))  # прозрачная дырка
                surface.fill((206, 210, 230), (30, 15, 10, 1))
            patch = layer.commands[-1]
            for size in (WINDOWED, FULLSCREEN):
                transform = transform_for(size)
                screen, expected = pygame.Surface(size), pygame.Surface(size)
                screen.fill((90, 160, 60))
                expected.fill((90, 160, 60))
                layer.render(screen, transform)
                rect = transform.rect(patch.rect)
                expected.blit(pygame.transform.scale(patch.surface, rect.size), rect)
                with self.subTest(color=patch_color, window=size):
                    self.assertEqual(pygame.image.tobytes(screen, "RGB"), pygame.image.tobytes(expected, "RGB"))

    def test_group_draws_like_its_commands_and_is_rebuilt_only_when_they_change(self) -> None:
        style = TextStyle(9, (40, 30, 20), background=(250, 242, 220))
        panel = pygame.Rect(20, 20, 200, 60)

        def fill(layer: HiResLayer, text: str) -> None:
            layer.rect((250, 242, 220), panel)
            layer.rect((222, 176, 84), panel, 2)
            layer.text(text, style, (30, 40), anchor="midleft")

        for size in (WINDOWED, FULLSCREEN):
            transform = transform_for(size)
            direct, grouped = HiResLayer(), HiResLayer()
            fill(direct, "Для Алисы")
            with grouped.group(panel) as sheet:
                fill(sheet, "Для Алисы")
            expected, screen = pygame.Surface(size), pygame.Surface(size)
            direct.render(expected, transform)
            grouped.render(screen, transform)
            with self.subTest(window=size):
                self.assertEqual(pygame.image.tobytes(screen, "RGB"), pygame.image.tobytes(expected, "RGB"))
                built = list(grouped._groups.values())
                grouped.render(screen, transform)  # те же команды — та же картинка
                self.assertEqual(list(grouped._groups.values()), built)
                grouped.clear()
                with grouped.group(panel) as sheet:
                    fill(sheet, "Твой муж")
                grouped.render(screen, transform)  # другие слова — новая картинка
                self.assertEqual(len(grouped._groups), 2)

    def test_group_fades_as_one_picture(self) -> None:
        layer = HiResLayer()
        with layer.group(pygame.Rect(0, 0, 10, 10), alpha=128) as sheet:
            sheet.rect((200, 100, 50), pygame.Rect(0, 0, 10, 10))
        screen = pygame.Surface(WINDOWED)
        layer.render(screen, transform_for(WINDOWED))
        pixel = screen.get_at((5, 5))
        self.assertTrue(95 < pixel.r < 105 and 45 < pixel.g < 55)
        self.assertEqual(tuple(screen.get_at((40, 40)))[:3], (0, 0, 0))

    def test_text_images_are_cached_by_every_parameter(self) -> None:
        layer = HiResLayer()
        style = TextStyle(9, (255, 255, 255))
        image = layer.text_image("Привет", style, 3)
        self.assertIs(layer.text_image("Привет", style, 3), image)
        others = (
            layer.text_image("Привет!", style, 3),  # другой текст
            layer.text_image("Привет", TextStyle(9, (1, 2, 3)), 3),  # цвет
            layer.text_image("Привет", TextStyle(8, (255, 255, 255)), 3),  # размер
            layer.text_image("Привет", style, 6),  # масштаб окна
            layer.text_image("Привет", style, 3, 180),  # поворот
        )
        for other in others:
            self.assertIsNot(other, image)

    def test_rect_draws_a_border_of_window_fills(self) -> None:
        layer = HiResLayer()
        layer.rect((255, 0, 0), pygame.Rect(10, 10, 20, 10), 2)
        self.assertTrue(all(isinstance(c, FillCommand) for c in layer.commands))
        screen = pygame.Surface(WINDOWED)
        transform = transform_for(WINDOWED)
        layer.render(screen, transform)
        red = pygame.mask.from_threshold(screen, (255, 0, 0), (1, 1, 1, 255))
        self.assertEqual(red.count(), (20 * 10 - 16 * 6) * 9)  # рамка в 2 логических пикселя, внутри пусто
        self.assertEqual(tuple(screen.get_at(transform.point((20, 15))))[:3], (0, 0, 0))

    def test_fill_covers_the_whole_canvas_area(self) -> None:
        layer = HiResLayer()
        layer.fill((255, 255, 255), alpha=255)
        self.assertTrue(layer.covers(pygame.Rect(0, 0, 1, 1)))
        screen = pygame.Surface(FULLSCREEN)
        layer.render(screen, transform_for(FULLSCREEN))
        self.assertEqual(tuple(screen.get_at((5, 59)))[:3], (0, 0, 0))  # поле не залито
        self.assertEqual(tuple(screen.get_at((5, 60)))[:3], (255, 255, 255))


class TextTest(PygameTestCase):
    def all_game_texts(self) -> str:
        texts = [RUSSIAN, FINALE_TEXT, intro_dialogue.ERROR_TITLE, *intro_dialogue.ERROR_LINES]
        texts += [step.text for step in intro_dialogue.TITLE_REWRITE]
        for script in (*intro_dialogue.all_scripts(), *hub_dialogue.all_scripts()):
            for node in script.nodes.values():
                texts += [node.speaker, node.text] + [choice.text for choice in node.choices or ()]
        texts += ["Фрагменты праздника: 0/3", "Стрелки/WASD — идти   E — действие", "Мозаика   E — «…»"]
        return "".join(texts)

    def test_every_letter_of_the_game_exists_in_the_font(self) -> None:
        text = self.all_game_texts()
        for name, fonts in font_variants().items():
            for bold in (False, True):
                with self.subTest(font=name, bold=bold):
                    metrics = fonts.metrics(TextStyle(9, (0, 0, 0), bold=bold))
                    self.assertEqual(metrics.missing_glyphs(text), set())

    def test_text_is_rendered_at_window_resolution_with_smooth_edges(self) -> None:
        layer = HiResLayer()
        for scale in (3, 6):
            with self.subTest(scale=scale):
                image = layer.text_image("Щёлкнул выключатель", TEXT_STYLE, scale)
                old = round(TEXT_STYLE.size * scale)
                # Буквы — шрифтом в пикселях окна (не увеличенные пиксели холста) и со сглаживанием.
                self.assertGreaterEqual(image.get_height(), old)
                alphas = set(pygame.image.tobytes(image, "RGBA")[3::4])
                self.assertGreater(len(alphas), 10)

    def test_fallback_font_is_as_tall_as_the_system_one(self) -> None:
        heights = {name: fonts.metrics(TEXT_STYLE).height for name, fonts in font_variants().items()}
        self.assertLess(max(heights.values()) / min(heights.values()), 1.4, heights)

    def test_long_russian_text_wraps_by_words_and_fits_at_every_scale(self) -> None:
        for name, fonts in font_variants().items():
            metrics = fonts.metrics(TEXT_STYLE)
            for max_width in (120, 200, 292):
                with self.subTest(font=name, width=max_width):
                    spans = wrap_spans(LONG_TEXT, metrics, max_width)
                    self.assertGreater(len(spans), 1)
                    lines = [LONG_TEXT[start:end] for start, end in spans]
                    self.assertEqual(" ".join(lines).split(), LONG_TEXT.split())  # слова не режутся и не теряются
                    for scale in LAYOUT_SCALES:
                        font = fonts.font(TEXT_STYLE.size, scale)
                        for line in lines:
                            self.assertLessEqual(font.size(line)[0], max_width * scale, (scale, line))

    def test_text_command_anchors_to_the_logical_point(self) -> None:
        style = TextStyle(9, (255, 255, 255))
        for size in (WINDOWED, FULLSCREEN):
            with self.subTest(window=size):
                transform = transform_for(size)
                screen = pygame.Surface(size)
                layer = HiResLayer()
                layer.text("Центр", style, (160, 90), anchor="center")
                layer.render(screen, transform)
                drawn = pygame.mask.from_threshold(screen, (255, 255, 255), (60, 60, 60, 255)).get_bounding_rects()
                box = drawn[0].unionall(drawn[1:])
                center = transform.point((160, 90))
                self.assertLessEqual(abs(box.centerx - center[0]), transform.scale)
                self.assertLessEqual(abs(box.centery - center[1]), 2 * transform.scale)


class DialogueLayoutTest(PygameTestCase):
    def scripts(self):
        return (*intro_dialogue.all_scripts(), *hub_dialogue.all_scripts())

    def test_every_line_fits_its_box_in_both_target_windows(self) -> None:
        for name, fonts in font_variants().items():
            box = DialogueBox(fonts)
            for script in self.scripts():
                box.check_fits(script)
                for node in script.nodes.values():
                    layout = box.layout(node, hires=True)
                    inner = layout.box.width - 2 * PADDING_X
                    for scale in (3, 6):
                        with self.subTest(font=name, node=node.id, scale=scale):
                            font = fonts.font(TEXT_STYLE.size, scale)
                            for start, end in layout.text_spans:
                                self.assertLessEqual(font.size(node.text[start:end])[0], inner * scale)
                            bold = fonts.font(TEXT_STYLE.size, scale, bold=True)
                            if layout.name_tab is not None:
                                tab_width = layout.name_tab.width - NAME_PADDING_X
                                self.assertLessEqual(bold.size(node.speaker)[0], tab_width * scale)
                            self.assertGreaterEqual(layout.box.top, 0)
                            self.assertLessEqual(layout.box.bottom, HEIGHT)
                            rows = len(layout.text_spans) * layout.line_height
                            self.assertLessEqual(layout.box.y + rows, layout.box.bottom)

    def test_hires_layout_keeps_line_rhythm_and_does_not_lift_the_intro_stage(self) -> None:
        box = DialogueBox()
        self.assertGreaterEqual(box.hires_line_height, box.line_height)
        scene = IntroScene()
        nodes = [node for script in intro_dialogue.all_scripts() for node in script.nodes.values()]
        pixel_ground = min(scene._box_top(node) for node in nodes) - 3
        self.assertEqual(scene.ground, pixel_ground)  # персонажи вступления стоят там же, где и раньше

    def test_box_draws_frame_on_the_layer_and_text_at_window_resolution(self) -> None:
        box = DialogueBox()
        script = hub_dialogue.CHUCHMEK_TALK
        dialogue = DialogueController(script)
        dialogue.update(30.0)  # реплика дописана
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer()
        layer.sprite(pygame.Surface((64, 64), pygame.SRCALPHA), pygame.Rect(140, 120, 32, 32))  # кто-то под окном
        box.draw(canvas, dialogue, layer)
        layout = box.layout(dialogue.node, hires=True)
        patches = [c for c in layer.commands if isinstance(c, PatchCommand)]
        texts = [c for c in layer.commands if isinstance(c, TextCommand)]
        self.assertEqual(len(patches), 1)
        self.assertTrue(patches[0].rect.contains(layout.box))
        self.assertEqual(texts[0].text, dialogue.node.speaker)
        self.assertEqual("".join("".join(c.text for c in texts[1:]).split()), "".join(dialogue.node.text.split()))
        self.assertLess(layer.commands.index(patches[0]), layer.commands.index(texts[0]))  # текст поверх рамки
        for scale_window in (WINDOWED, FULLSCREEN):
            transform = transform_for(scale_window)
            screen = pygame.Surface(scale_window)
            layer.render(screen, transform)
            frame = transform.rect(layout.box)
            for command in texts[1:]:
                image = layer.text_image(command.text, command.style, transform.scale)
                rect = image.get_rect(**{command.anchor: transform.point(command.pos)})
                self.assertTrue(frame.contains(rect), (scale_window, command.text))


class HubHiResTest(PygameTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fonts = TextFonts()

    def draw(self, hub: HubScene) -> tuple[HiResLayer, pygame.Surface]:
        layer, canvas = HiResLayer(self.fonts, strict=True), pygame.Surface(config.LOGICAL_SIZE)
        hub.draw(canvas, layer)
        return layer, canvas

    def sprites(self, layer: HiResLayer) -> list[SpriteCommand]:
        return [c for c in layer.commands if isinstance(c, SpriteCommand)]

    def test_alice_and_chuchmek_are_drawn_once_from_original_frames(self) -> None:
        hub = HubScene()
        hub.update(0.1)
        layer, canvas = self.draw(hub)
        sprites = self.sprites(layer)
        self.assertEqual(len(sprites), 3)  # Алиса, Чучмек и Лео в корзинке — каждый по одному разу
        chuchmek_frame = load_character_sprites(CHARACTERS_DIR / "chuchmek").frame("idle").image
        by_rect = {command.rect.topleft: command for command in sprites}
        alice, chuchmek = by_rect[hub.alice.rect.topleft], by_rect[hub.chuchmek.rect.topleft]
        self.assertIs(alice.image, hub.alice.player.source)
        leo = by_rect[hub.leo_rect().topleft]
        self.assertIs(leo.image, hub.leo_frames()[0])  # исходный кадр 64×64, а не уменьшенная копия
        self.assertEqual(leo.rect, hub.leo_rect())
        # Чучмек не отражён: его кадр совпадает с исходным кадром манифеста.
        self.assertEqual(pygame.image.tobytes(chuchmek.image, "RGBA"), pygame.image.tobytes(chuchmek_frame, "RGBA"))
        # На холсте персонажей нет — двойного силуэта не будет.
        background = hub._background
        rect = hub.alice.rect
        self.assertEqual(screen_pixels(canvas, rect), screen_pixels(background, rect))

    def test_drawing_does_not_move_anyone(self) -> None:
        hub = HubScene()
        before = [(c.x, c.y, c.direction, c.state) for c in (hub.alice, hub.chuchmek)]
        for _ in range(5):
            self.draw(hub)
        self.assertEqual([(c.x, c.y, c.direction, c.state) for c in (hub.alice, hub.chuchmek)], before)
        self.assertEqual((hub.alice.x, hub.alice.y), SPAWN)

    def test_tree_in_front_covers_alice_and_tree_behind_does_not(self) -> None:
        hub = HubScene()
        x, y = TREES[0]
        hub.alice.set_position(x, y - 6)  # за стволом: крона дерева перед ней
        layer, _ = self.draw(hub)
        commands = layer.commands
        alice = next(i for i, c in enumerate(commands) if isinstance(c, SpriteCommand) and c.rect == hub.alice.rect)
        crown = (x, y - 14)
        tree_patches = [i for i, c in enumerate(commands) if isinstance(c, PatchCommand) and c.rect.collidepoint(crown)]
        self.assertTrue(tree_patches and tree_patches[0] > alice)
        hub.alice.set_position(x, y + 14)  # перед деревом: дерево на холсте, под ней
        layer, _ = self.draw(hub)
        self.assertFalse([c for c in layer.commands if isinstance(c, PatchCommand) and c.rect.collidepoint(x, y - 14)])

    def test_dialogue_box_is_over_alice_and_texts_are_in_the_layer(self) -> None:
        hub = HubScene()
        hub.alice.set_position(214, 100)
        hub.interact()
        hub.update(30.0)
        hub.alice.set_position(160, 164)  # стоит низко — окно реплики закрывает её
        layer, canvas = self.draw(hub)
        commands = layer.commands
        alice = next(i for i, c in enumerate(commands) if isinstance(c, SpriteCommand) and c.rect == hub.alice.rect)
        panel = next(i for i, c in enumerate(commands) if isinstance(c, PatchCommand) and c.rect.bottom > STATUS_TOP)
        self.assertGreater(panel, alice)
        texts = [c.text for c in commands if isinstance(c, TextCommand)]
        self.assertIn("Центральная площадь", texts)
        self.assertIn(hub.fragments_text(), texts)
        self.assertIn("Чучмек", texts)
        for portal in PORTALS:
            self.assertIn(portal.name, texts)

    def test_status_and_hud_text_are_not_baked_into_the_canvas(self) -> None:
        hub = HubScene()
        layer, canvas = self.draw(hub)
        bars = [pygame.Rect(0, 0, WIDTH, HUD_HEIGHT), pygame.Rect(0, STATUS_TOP, WIDTH, HEIGHT - STATUS_TOP)]
        for bar in bars:
            colors = set(zip(*[iter(pygame.image.tobytes(canvas.subsurface(bar), "RGB"))] * 3))
            self.assertEqual(len(colors), 1)  # однотонная полоса: буквы рисует слой окна
        self.assertIn(hub.status_text(), [c.text for c in layer.commands if isinstance(c, TextCommand)])

    def test_hud_signs_and_statuses_fit_in_both_target_windows(self) -> None:
        progress = GameProgress()
        for trial in TRIALS:
            progress.complete(trial)
        hub = HubScene(progress)
        statuses = [
            "Стрелки/WASD — идти   E — действие",
            "Мозаика   E — восстановить последнюю страницу",
            "Получен фрагмент праздника! Теперь 3/3. Мозаика засветилась",
            "Последняя страница подождёт: E у мозаики",
        ]
        statuses += [f"Испытание «{portal.name}» прервано — фрагмент не получен" for portal in PORTALS]
        statuses += [f"{portal.name} (пройдено)   E — войти" for portal in PORTALS]
        for name, fonts in font_variants().items():
            for scale in (3, 6):
                with self.subTest(font=name, scale=scale):
                    font = fonts.font(HUD_STYLE.size, scale)
                    self.assertLessEqual(font.get_height(), HUD_HEIGHT * scale)
                    left = font.size("Центральная площадь")[0]
                    right = font.size(hub.fragments_text())[0]
                    self.assertLess(left + right + 16 * scale, WIDTH * scale)  # не наезжают друг на друга
                    for text in statuses:
                        self.assertLessEqual(font.size(text)[0], (WIDTH - 8) * scale, text)
                    sign = fonts.font(SIGN_STYLE.size, scale)
                    for portal in PORTALS:
                        plaque = hub.plaque_rect(portal, hires=True)
                        self.assertTrue(pygame.Rect(0, 0, WIDTH, HEIGHT).contains(plaque))
                        self.assertLessEqual(sign.size(portal.name)[0], (plaque.width - 2) * scale)

    def test_strict_areas_everywhere_on_the_hub(self) -> None:
        progress = GameProgress()
        for trial in TRIALS:
            progress.complete(trial)
        hub = HubScene(progress)
        points = [portal.point for portal in PORTALS] + [MOSAIC_CENTER, (62, 52), (258, 52), (214, 92), (20, 160)]
        for point in points:
            hub.alice.set_position(*point)
            for _ in range(20):
                hub.update(1 / 20)
                self.draw(hub)  # строгий слой упадёт, если что-то нарисовано за заявленной областью
            if hub.interact() and hub.dialogue is not None:
                hub.update(30.0)
                self.draw(hub)
                hub._close_dialogue()


class IntroHiResTest(PygameTestCase):
    def frames(self, scene: IntroScene, limit: int = 30000):
        """Проигрывает вступление, после каждого шага рисуя его в строгий слой; отдаёт (сцену, слой)."""
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer(strict=True)
        for _ in range(limit):
            if scene.completed:
                return
            layer.clear()
            scene.draw(canvas, layer)
            yield layer
            dialogue = scene.dialogue
            if dialogue is not None and not dialogue.is_typing:
                dialogue.confirm()
                scene._sync_dialogue()
            else:
                scene.update(1 / 30)

    def test_whole_intro_draws_through_the_layer(self) -> None:
        scene = IntroScene()
        # Кадры манифестов как есть — те самые объекты: персонажей не масштабируют заранее и не отражают.
        originals = {id(frame.image) for actor in scene.actors.values() for frame in actor.sprites.frames}
        cues = set()
        for layer in self.frames(scene):
            cues.add(scene.cue_name)
            commands = layer.commands
            if scene.cue_name == "glitch":
                tears = [c for c in commands if isinstance(c, TearCommand)]
                self.assertEqual(len(tears), 1)
                commands = tears[0].commands  # подвисший кадр с персонажами и заголовком
            for command in commands:
                if isinstance(command, SpriteCommand):
                    self.assertIn(id(command.image), originals, scene.cue_name)
        self.assertTrue(scene.completed)
        self.assertTrue({"glitch", "error_message", "chuchmek_emerges", "title_rewrite", "finale"} <= cues)

    def test_actor_sprite_keeps_place_and_size_of_the_canvas_version(self) -> None:
        scene = IntroScene()
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        for actor in scene.actors.values():
            actor.visible, actor.alpha = True, 255
            for squash in (1.0, 0.88):
                actor.squash = squash
                layer = HiResLayer()
                actor.draw(canvas, scene.ground, None, layer)
                (command,) = layer.commands
                with self.subTest(actor=actor.id, squash=squash):
                    self.assertEqual(command.rect, actor.bounds(scene.ground))
                    self.assertIs(command.image, actor.source_image())

    def test_chuchmek_in_the_burrow_is_clipped_and_never_mirrored(self) -> None:
        scene = IntroScene()
        chuchmek = scene.actors["chuchmek"]
        chuchmek.visible = True
        for frame_id in ("idle", "clipboard_confident", "panicked", "arms_up_panic", "smug_wink", "confused"):
            chuchmek.set_pose(frame_id)
            layer = HiResLayer()
            chuchmek.draw(pygame.Surface(config.LOGICAL_SIZE), scene.ground, scene.ground + 1, layer)
            (command,) = layer.commands
            with self.subTest(frame=frame_id):
                self.assertIs(command.image, chuchmek.sprites.frame(frame_id).image)
                self.assertEqual(command.clip, pygame.Rect(0, 0, WIDTH, scene.ground + 1))

    def test_flash_covers_characters_and_title(self) -> None:
        scene = IntroScene()
        while scene.cue_name != "restart":
            dialogue = scene.dialogue
            if dialogue is not None and not dialogue.is_typing:
                dialogue.confirm()
                scene._sync_dialogue()
            else:
                scene.update(1 / 30)
        scene.update(0.1)
        layer = HiResLayer()
        scene.draw(pygame.Surface(config.LOGICAL_SIZE), layer)
        kinds = [type(c) for c in layer.commands]
        flash = kinds.index(FillCommand)
        self.assertLess(kinds.index(SpriteCommand), flash)
        self.assertLess(kinds.index(TextCommand), flash)  # заголовок под вспышкой

    def test_title_error_and_finale_texts_fit(self) -> None:
        scene = IntroScene()
        titles = {step.text for step in intro_dialogue.TITLE_REWRITE}
        for name, fonts in font_variants().items():
            for scale in (3, 6):
                with self.subTest(font=name, scale=scale):
                    title = fonts.font(TITLE_STYLE.size, scale, bold=True)
                    for text in titles:
                        self.assertLessEqual(title.size(text)[0], (WIDTH - 20) * scale, text)
                    self.assertLessEqual(9 * scale + title.get_height(), TITLE_BOTTOM * scale)  # над персонажами
                    self.assertEqual(TITLE_FINAL_STYLE.size, TITLE_STYLE.size)
                    band = fonts.font(ERROR_TITLE_STYLE.size, scale, bold=True)
                    self.assertLessEqual(band.size(intro_dialogue.ERROR_TITLE)[0], (ERROR_W - 40) * scale)
                    self.assertLessEqual(band.get_height(), 17 * scale)
                    line = fonts.font(ERROR_LINE_STYLE.size, scale)
                    for text in intro_dialogue.ERROR_LINES:
                        self.assertLessEqual(line.size(text)[0], (ERROR_W - 24) * scale, text)
                    finale = fonts.font(FINALE_STYLE.size, scale)
                    plaque = scene.finale_plaque_rect(hires=True)
                    self.assertLessEqual(finale.size(FINALE_TEXT)[0], (plaque.width - 4) * scale)
        self.assertLess(ERROR_H, HEIGHT)


class PlaceholderHiResTest(PygameTestCase):
    def test_scenes_without_sprites_draw_placeholders_through_the_layer(self) -> None:
        transform = transform_for(WINDOWED)
        screen = pygame.Surface(WINDOWED)
        canvas = pygame.Surface(config.LOGICAL_SIZE)
        layer = HiResLayer(strict=True)
        with tempfile.TemporaryDirectory() as empty:
            hub = HubScene(characters_dir=Path(empty))
            hub.update(0.1)
            hub.draw(canvas, layer)
            sprites = [c for c in layer.commands if isinstance(c, SpriteCommand)]
            # Временные манекены — на тех же местах и того же размера, что и на холсте.
            expected = sorted([tuple(hub.alice.rect), tuple(hub.chuchmek.rect)])
            self.assertEqual(sorted(tuple(c.rect) for c in sprites), expected)
            layer.render(screen, transform)
            scene = IntroScene(characters_dir=Path(empty))
            for _ in range(20000):
                if scene.completed:
                    break
                layer.clear()
                scene.draw(canvas, layer)
                layer.render(screen, transform)
                dialogue = scene.dialogue
                if dialogue is not None and not dialogue.is_typing:
                    dialogue.confirm()
                    scene._sync_dialogue()
                else:
                    scene.update(1 / 30)
            self.assertTrue(scene.completed)


class AppHiResTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App()

    def tearDown(self) -> None:
        pygame.quit()

    def test_alice_stays_on_her_place_in_window_and_fullscreen(self) -> None:
        hub = HubScene(self.app.progress)
        self.app.scenes.replace(hub)
        hub.alice.set_position(100, 120)
        hub.update(0.1)
        places = {}
        for size in (WINDOWED, FULLSCREEN, WINDOWED):
            pygame.display.set_mode(size, pygame.RESIZABLE)
            self.app._draw()
            transform = self.app.display.transform()
            screen = pygame.display.get_surface()
            rect = transform.rect(hub.alice.rect)
            expected = scale_sprite(hub.alice.player.source, rect.size)
            # Точки кадра — ровно там, куда их переносит трансформация области окна: цвет на экране
            # равен кадру (с предумноженной альфой), смешанному с фоном холста под этой точкой.
            canvas = self.app.display.canvas
            checked = 0
            for x in range(0, rect.w, 5):
                for y in range(0, rect.h, 5):
                    pixel = expected.get_at((x, y))
                    if pixel.a < 200:
                        continue
                    point = (rect.x + x, rect.y + y)
                    scale = round(transform.scale)
                    logical = ((point[0] - transform.viewport.x) // scale, (point[1] - transform.viewport.y) // scale)
                    background = canvas.get_at(logical)
                    for channel in range(3):
                        blended = pixel[channel] + background[channel] * (255 - pixel.a) / 255
                        self.assertLessEqual(abs(screen.get_at(point)[channel] - blended), 2, (size, point))
                    checked += 1
            self.assertGreater(checked, 50)
            viewport = transform.viewport
            places[size] = (rect.x - viewport.x) / transform.scale, (rect.y - viewport.y) / transform.scale
            self.assertEqual(self.app.display.hires.commands, [])  # слой очищен после вывода
        self.assertEqual(places[WINDOWED], places[FULLSCREEN])
        self.assertEqual((hub.alice.x, hub.alice.y), (100, 120))

    def test_fast_canvas_scaling_matches_transform_scale(self) -> None:
        canvas = self.app.display.canvas
        for x in range(0, WIDTH, 3):
            canvas.fill(((x * 7) % 256, (x * 3) % 256, x % 256), (x, 0, 2, HEIGHT))
        canvas.fill((250, 10, 10), (5, 7, 1, 1))
        for size in (WINDOWED, FULLSCREEN, (1280, 720), (2560, 1440), (700, 420), (1366, 768), (200, 120)):
            with self.subTest(window=size):
                pygame.display.set_mode(size, pygame.RESIZABLE)
                self.app.display.present()
                viewport = self.app.display.transform().viewport
                screen = pygame.display.get_surface()
                expected = pygame.transform.scale(canvas, viewport.size)
                self.assertEqual(screen_pixels(screen, viewport), pygame.image.tobytes(expected, "RGB"))

    def test_only_capable_scenes_get_the_layer(self) -> None:
        calls = []

        class Plain(Scene):
            def draw(self, surface):
                calls.append(("plain", None))

        class Capable(Scene):
            supports_hires = True

            def draw(self, surface, hires=None):
                calls.append(("capable", hires))

        class Overlay(Plain):
            is_overlay = True

        manager = SceneManager()
        layer = HiResLayer()
        manager.push(Capable())
        manager.draw(pygame.Surface(config.LOGICAL_SIZE), layer)
        self.assertEqual(calls, [("capable", layer)])
        calls.clear()
        manager.push(Overlay())  # прозрачная сцена без слоя поверх: нижняя рисует только на холсте
        manager.draw(pygame.Surface(config.LOGICAL_SIZE), layer)
        self.assertEqual(calls, [("capable", None), ("plain", None)])

    def test_original_assets_are_not_changed_by_rendering(self) -> None:
        files = sorted((config.PROJECT_DIR / "assets" / "characters").rglob("*.png"))
        digest = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        hub = HubScene(self.app.progress)
        self.app.scenes.replace(hub)
        # Исходные кадры, которые площадь передаёт слою: все направления и состояния Алисы и Чучмека.
        sources = {}
        for character in (hub.alice, hub.chuchmek):
            for state in ("idle", "walk", "talk"):
                for direction in Direction:
                    animation = character.animations.get(state, direction)
                    for index in range(len(animation.frames)):
                        source = animation.source(index)
                        sources[id(source)] = source
        before = {key: pygame.image.tobytes(source, "RGBA") for key, source in sources.items()}
        for size in (WINDOWED, FULLSCREEN):
            pygame.display.set_mode(size, pygame.RESIZABLE)
            for code in (pygame.K_LEFT, pygame.K_UP):
                hub.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode="", scancode=0))
                for _ in range(30):
                    self.app._update(1 / 30)
                    self.app._draw()
        self.assertEqual({key: pygame.image.tobytes(source, "RGBA") for key, source in sources.items()}, before)
        self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}, digest)


if __name__ == "__main__":
    unittest.main()
