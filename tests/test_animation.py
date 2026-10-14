"""Проверки системы анимаций: кадры, проигрывание, наборы анимаций и листы спрайтов."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.graphics.animation import (  # noqa: E402
    IDLE,
    REACT,
    WALK,
    Animation,
    AnimationError,
    AnimationPlayer,
    AnimationSet,
    Direction,
    SpriteSheetError,
    load_image,
    load_sprite_sheet,
    resolve_path,
    slice_sheet,
)


def make_frames(count: int) -> list[pygame.Surface]:
    """Кадры 1×1 разного цвета, чтобы их можно было различить."""
    frames = []
    for index in range(count):
        frame = pygame.Surface((1, 1))
        frame.fill((index * 10, 0, 0))
        frames.append(frame)
    return frames


def make_sheet(columns: int, rows: int, frame_size: tuple[int, int] = (16, 16)) -> pygame.Surface:
    """Лист с прозрачным фоном, каждая клетка залита своим цветом, кроме левого верхнего пикселя."""
    frame_w, frame_h = frame_size
    sheet = pygame.Surface((columns * frame_w, rows * frame_h), pygame.SRCALPHA)
    for row in range(rows):
        for column in range(columns):
            sheet.fill((column * 40, row * 40, 200, 255), (column * frame_w, row * frame_h, frame_w, frame_h))
            sheet.set_at((column * frame_w, row * frame_h), (0, 0, 0, 0))
    return sheet


class AnimationTest(unittest.TestCase):
    def test_valid_animation_is_created(self) -> None:
        frames = make_frames(4)
        animation = Animation(frames, fps=8)
        self.assertEqual(animation.frames, tuple(frames))
        self.assertTrue(animation.loop)
        self.assertAlmostEqual(animation.frame_duration, 0.125)
        self.assertAlmostEqual(animation.duration, 0.5)

    def test_frames_are_copied_into_tuple(self) -> None:
        frames = make_frames(2)
        animation = Animation(frames, fps=5)
        frames.append(make_frames(1)[0])  # список снаружи изменился, а анимация — нет
        self.assertEqual(len(animation.frames), 2)

    def test_empty_frames_are_rejected(self) -> None:
        with self.assertRaisesRegex(AnimationError, "нет ни одного кадра"):
            Animation([], fps=10)

    def test_non_surface_frame_is_rejected(self) -> None:
        with self.assertRaisesRegex(AnimationError, "кадр 1"):
            Animation([make_frames(1)[0], "кадр.png"], fps=10)

    def test_invalid_fps_is_rejected(self) -> None:
        for fps in (0, -5, math.nan, math.inf, "10", None, True):
            with self.subTest(fps=fps), self.assertRaisesRegex(AnimationError, "скорость анимации"):
                Animation(make_frames(2), fps=fps)

    def test_flipped_mirrors_every_frame(self) -> None:
        frame = pygame.Surface((2, 1))
        frame.set_at((0, 0), (255, 0, 0))
        frame.set_at((1, 0), (0, 0, 255))
        flipped = Animation([frame], fps=4, loop=False).flipped()
        self.assertEqual(tuple(flipped.frames[0].get_at((0, 0)))[:3], (0, 0, 255))
        self.assertEqual(tuple(flipped.frames[0].get_at((1, 0)))[:3], (255, 0, 0))
        self.assertEqual((flipped.fps, flipped.loop), (4, False))


class AnimationPlayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frames = make_frames(4)
        self.player = AnimationPlayer(Animation(self.frames, fps=10))  # кадр длится 0,1 с

    def test_starts_with_first_frame(self) -> None:
        self.assertEqual(self.player.frame_index, 0)
        self.assertIs(self.player.frame, self.frames[0])

    def test_switches_frame_after_frame_duration(self) -> None:
        self.player.update(0.05)
        self.assertEqual(self.player.frame_index, 0)
        self.player.update(0.05)
        self.assertEqual(self.player.frame_index, 1)
        self.assertIs(self.player.frame, self.frames[1])

    def test_zero_dt_changes_nothing(self) -> None:
        self.player.update(0)
        self.assertEqual(self.player.frame_index, 0)

    def test_does_not_depend_on_update_rate(self) -> None:
        # 0,25 с при 60, 120, 144 и 240 обновлениях в секунду — всегда третий кадр (индекс 2).
        for updates_per_second in (60, 120, 144, 240):
            player = AnimationPlayer(Animation(make_frames(4), fps=10))
            for _ in range(updates_per_second // 4):
                player.update(1 / updates_per_second)
            with self.subTest(rate=updates_per_second):
                self.assertEqual(player.frame_index, 2)

    def test_exact_frame_boundary_with_many_small_steps(self) -> None:
        # Шесть шагов по 1/60 с — ровно 0,1 с, хотя сумма float чуть меньше 0,1.
        for _ in range(6):
            self.player.update(1 / 60)
        self.assertEqual(self.player.frame_index, 1)

    def test_large_dt_skips_several_frames_and_keeps_remainder(self) -> None:
        self.player.update(0.25)  # два с половиной кадра
        self.assertEqual(self.player.frame_index, 2)
        self.player.update(0.05)  # остаток 0,05 + 0,05 — ровно ещё один кадр
        self.assertEqual(self.player.frame_index, 3)

    def test_looping_animation_starts_over(self) -> None:
        self.player.update(0.45)  # четыре с половиной кадра из четырёх — снова первый
        self.assertEqual(self.player.frame_index, 0)
        self.assertFalse(self.player.is_finished)
        self.player.update(0.05)
        self.assertEqual(self.player.frame_index, 1)

    def test_looping_animation_survives_huge_dt(self) -> None:
        self.player.update(1000.15)  # 10 001,5 кадра: 10 001 % 4 == 1
        self.assertEqual(self.player.frame_index, 1)

    def test_one_shot_animation_plays_once(self) -> None:
        player = AnimationPlayer(Animation(make_frames(3), fps=10, loop=False))
        player.update(0.25)
        self.assertEqual(player.frame_index, 2)
        self.assertFalse(player.is_finished)  # последний кадр ещё показывается
        player.update(0.05)  # прошло 0,3 с — вся длительность анимации
        self.assertTrue(player.is_finished)

    def test_one_shot_animation_stops_on_last_frame(self) -> None:
        frames = make_frames(3)
        player = AnimationPlayer(Animation(frames, fps=10, loop=False))
        player.update(5.0)
        self.assertTrue(player.is_finished)
        self.assertIs(player.frame, frames[2])
        player.update(1.0)
        self.assertEqual(player.frame_index, 2)

    def test_reset_returns_to_first_frame_and_clears_time(self) -> None:
        self.player.update(0.28)
        self.player.reset()
        self.assertEqual(self.player.frame_index, 0)
        self.assertFalse(self.player.is_finished)
        self.player.update(0.05)  # остаток 0,08 с забыт, иначе здесь был бы уже второй кадр
        self.assertEqual(self.player.frame_index, 0)

    def test_reset_restarts_finished_one_shot(self) -> None:
        player = AnimationPlayer(Animation(make_frames(2), fps=10, loop=False))
        player.update(1.0)
        player.reset()
        self.assertFalse(player.is_finished)
        player.update(0.1)
        self.assertEqual(player.frame_index, 1)

    def test_play_other_animation_starts_from_first_frame(self) -> None:
        self.player.update(0.28)
        other = Animation(make_frames(3), fps=10)
        self.player.play(other)
        self.assertIs(self.player.animation, other)
        self.assertEqual(self.player.frame_index, 0)
        self.player.update(0.05)
        self.assertEqual(self.player.frame_index, 0)

    def test_play_same_animation_continues(self) -> None:
        self.player.update(0.15)
        self.player.play(self.player.animation)
        self.assertEqual(self.player.frame_index, 1)
        self.player.play(self.player.animation, restart=True)
        self.assertEqual(self.player.frame_index, 0)

    def test_invalid_dt_is_rejected(self) -> None:
        for dt in (-0.1, math.nan, math.inf):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                self.player.update(dt)


class AnimationSetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.default = Animation(make_frames(1), fps=1)
        self.animations = AnimationSet(self.default)

    def animation(self) -> Animation:
        return Animation(make_frames(2), fps=4)

    def test_exact_direction_is_preferred(self) -> None:
        general, left = self.animation(), self.animation()
        self.animations.add(WALK, general)
        self.animations.add(WALK, left, Direction.LEFT)
        self.assertIs(self.animations.get(WALK, Direction.LEFT), left)
        self.assertIs(self.animations.get(WALK, Direction.UP), general)

    def test_missing_state_falls_back_to_idle_of_same_direction(self) -> None:
        idle_up, idle_down = self.animation(), self.animation()
        self.animations.add(IDLE, idle_up, Direction.UP)
        self.animations.add(IDLE, idle_down, Direction.DOWN)
        self.assertIs(self.animations.get(REACT, Direction.UP), idle_up)
        self.assertIs(self.animations.get("неизвестное", Direction.DOWN), idle_down)

    def test_custom_fallback_chain(self) -> None:
        # Клубника: бега нет — показываем ходьбу; прятки — свои.
        walk = self.animation()
        animations = AnimationSet(self.default, fallbacks={"run": WALK})
        animations.add(WALK, walk)
        self.assertIs(animations.get("run", Direction.RIGHT), walk)

    def test_without_any_matching_animation_default_is_used(self) -> None:
        for state in (IDLE, WALK, "hide"):
            for direction in Direction:
                self.assertIs(self.animations.get(state, direction), self.default)

    def test_cyclic_fallbacks_do_not_hang(self) -> None:
        animations = AnimationSet(self.default, fallbacks={"a": "b", "b": "a"})
        self.assertIs(animations.get("a", Direction.DOWN), self.default)

    def test_has_and_states(self) -> None:
        self.animations.add("hide", self.animation(), Direction.LEFT)
        self.assertTrue(self.animations.has("hide", Direction.LEFT))
        self.assertFalse(self.animations.has("hide"))
        self.assertEqual(self.animations.states, {"hide"})

    def test_invalid_arguments_are_rejected(self) -> None:
        with self.assertRaises(AnimationError):
            AnimationSet(None)
        with self.assertRaises(AnimationError):
            self.animations.add("", self.animation())
        with self.assertRaises(AnimationError):
            self.animations.add(WALK, make_frames(2))
        with self.assertRaises(AnimationError):
            self.animations.add(WALK, self.animation(), "left")


class SpriteSheetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sheet_is_sliced_into_rows_and_columns(self) -> None:
        rows = slice_sheet(make_sheet(columns=4, rows=2), (16, 16))
        self.assertEqual(len(rows), 2)
        self.assertEqual([len(row) for row in rows], [4, 4])
        for row_index, row in enumerate(rows):
            for column_index, frame in enumerate(row):
                with self.subTest(row=row_index, column=column_index):
                    self.assertEqual(frame.get_size(), (16, 16))
                    self.assertEqual(tuple(frame.get_at((8, 8))), (column_index * 40, row_index * 40, 200, 255))

    def test_non_square_frames(self) -> None:
        rows = slice_sheet(make_sheet(columns=3, rows=1, frame_size=(16, 32)), (16, 32), columns=3, rows=1)
        self.assertEqual(len(rows[0]), 3)
        self.assertEqual(rows[0][2].get_size(), (16, 32))

    def test_frames_do_not_depend_on_sheet(self) -> None:
        sheet = make_sheet(columns=2, rows=1)
        frame = slice_sheet(sheet, (16, 16))[0][0]
        sheet.fill((0, 0, 0, 255))
        self.assertEqual(tuple(frame.get_at((8, 8))), (0, 0, 200, 255))

    def test_incompatible_sheet_size_is_rejected(self) -> None:
        sheet = pygame.Surface((50, 32))
        with self.assertRaisesRegex(SpriteSheetError, "50×32 не делится на кадры 16×16"):
            slice_sheet(sheet, (16, 16))

    def test_unexpected_grid_is_rejected(self) -> None:
        # Размер делится на кадры, но сетка не та, что ожидалась, — например, другой лист.
        with self.assertRaisesRegex(SpriteSheetError, "сетка 4×2"):
            slice_sheet(make_sheet(columns=4, rows=2), (16, 16), columns=3)
        with self.assertRaisesRegex(SpriteSheetError, "сетка 4×2"):
            slice_sheet(make_sheet(columns=4, rows=2), (16, 16), rows=4)

    def test_invalid_frame_size_and_grid_are_rejected(self) -> None:
        sheet = make_sheet(columns=2, rows=2)
        for frame_size in ((0, 16), (16, -1), (16,), (16.0, 16)):
            with self.subTest(frame_size=frame_size), self.assertRaises(SpriteSheetError):
                slice_sheet(sheet, frame_size)
        with self.assertRaises(SpriteSheetError):
            slice_sheet(sheet, (16, 16), columns=0)
        with self.assertRaises(SpriteSheetError):
            slice_sheet("sheet.png", (16, 16))

    def test_png_is_loaded_with_transparency(self) -> None:
        pygame.image.save(make_sheet(columns=2, rows=1), str(self.tmp_dir / "sheet.png"))
        rows = load_sprite_sheet(self.tmp_dir / "sheet.png", (16, 16), columns=2, rows=1)
        self.assertEqual(rows[0][0].get_at((0, 0)).a, 0)  # прозрачный пиксель остался прозрачным
        self.assertEqual(rows[0][0].get_at((8, 8)).a, 255)
        self.assertEqual(tuple(rows[0][1].get_at((8, 8))), (40, 0, 200, 255))

    def test_relative_path_does_not_depend_on_working_directory(self) -> None:
        (self.tmp_dir / "characters").mkdir()
        pygame.image.save(make_sheet(columns=1, rows=1), str(self.tmp_dir / "characters" / "test.png"))
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as other_dir:
            os.chdir(other_dir)
            try:
                image = load_image("characters/test.png", base_dir=self.tmp_dir)
            finally:
                os.chdir(previous)
        self.assertEqual(image.get_size(), (16, 16))

    def test_relative_paths_are_resolved_from_project_dir(self) -> None:
        self.assertEqual(resolve_path("assets/x.png"), config.PROJECT_DIR / "assets" / "x.png")
        absolute = self.tmp_dir / "x.png"
        self.assertEqual(resolve_path(absolute), absolute)
        self.assertTrue((config.PROJECT_DIR / "main.py").is_file())

    def test_missing_file_gives_clear_error(self) -> None:
        missing = self.tmp_dir / "нет_такого.png"
        with self.assertRaisesRegex(FileNotFoundError, "файл изображения не найден") as context:
            load_sprite_sheet(missing, (16, 16))
        self.assertIn(str(missing), str(context.exception))
        with self.assertRaises(FileNotFoundError):
            load_image(self.tmp_dir)  # папка, а не файл

    def test_broken_image_gives_clear_error(self) -> None:
        broken = self.tmp_dir / "broken.png"
        broken.write_bytes(b"this is not a png")
        with self.assertRaisesRegex(SpriteSheetError, "не удалось загрузить изображение"):
            load_image(broken)


if __name__ == "__main__":
    unittest.main()
