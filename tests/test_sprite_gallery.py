"""Проверки тестовой галереи спрайтов."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.debug.sprite_gallery import (  # noqa: E402
    CHARACTER_ORDER,
    DRAFT_COLOR,
    HINTS_TOP,
    INFO_TOP,
    INFO_WIDTH,
    PANEL_RECT,
    REPEAT_DELAY,
    REPEAT_INTERVAL,
    SpriteGallery,
)
from game.graphics.sprite_manifest import CHARACTERS_DIR  # noqa: E402


def key_event(key: int, scancode: int = 0, mod: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key, mod=mod, unicode="", scancode=scancode)


class GalleryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def tearDown(self) -> None:
        pygame.quit()

    def press(self, gallery: SpriteGallery, key: int, **kwargs) -> None:
        gallery.handle_event(key_event(key, **kwargs))

    def open_group(self, gallery: SpriteGallery, char_id: str, group_name: str) -> None:
        """Выбирает персонажа и группу так же, как пользователь: стрелками и Tab."""
        while gallery.entry.id != char_id:
            self.press(gallery, pygame.K_RIGHT)
        while gallery.group.name != group_name:
            self.press(gallery, pygame.K_TAB)


class NavigationTest(GalleryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gallery = SpriteGallery()

    def test_opens_on_first_frame_of_alice(self) -> None:
        self.assertEqual([entry.id for entry in self.gallery.entries], list(CHARACTER_ORDER))
        self.assertEqual(self.gallery.entry.id, "alice")
        self.assertEqual(self.gallery.current_frame.id, "idle_down")
        self.assertEqual(self.gallery.display_size, 64)
        self.assertFalse(self.gallery.is_playing)

    def test_left_and_right_switch_characters_in_a_circle(self) -> None:
        self.press(self.gallery, pygame.K_DOWN)
        self.press(self.gallery, pygame.K_RIGHT)
        self.assertEqual(self.gallery.entry.id, "chuchmek")
        self.assertEqual(self.gallery.frame_index, 0)  # у нового персонажа — с первого кадра
        self.press(self.gallery, pygame.K_LEFT)
        self.press(self.gallery, pygame.K_LEFT)
        self.assertEqual(self.gallery.entry.id, "great_cake")  # последний в списке

    def test_up_and_down_browse_every_frame(self) -> None:
        sprites = self.gallery.sprites
        seen = []
        for _ in range(len(sprites.frames)):
            seen.append(self.gallery.current_frame.id)
            self.press(self.gallery, pygame.K_DOWN)
        self.assertEqual(seen, [frame.id for frame in sprites.frames])
        self.assertEqual(self.gallery.frame_index, 0)  # по кругу
        self.press(self.gallery, pygame.K_UP)
        self.assertEqual(self.gallery.current_frame.id, "happy_down_3")

    def test_group_follows_browsed_frame(self) -> None:
        for _ in range(4):
            self.press(self.gallery, pygame.K_DOWN)
        self.assertEqual(self.gallery.current_frame.id, "walk_down_1")
        self.assertEqual(self.gallery.group.name, "walk_down")

    def test_frame_outside_groups_is_explained(self) -> None:
        self.open_group(self.gallery, "cat_chef", "idle")
        while self.gallery.current_frame.id != "stern_side_pose":  # кадр 11 не входит ни в одну группу
            self.press(self.gallery, pygame.K_DOWN)
        self.assertIn("Кадр не входит ни в одну группу", self.gallery.info_lines())

    def test_held_arrow_repeats(self) -> None:
        self.press(self.gallery, pygame.K_DOWN)
        self.gallery.update(REPEAT_DELAY / 2)
        self.assertEqual(self.gallery.frame_index, 1)
        self.gallery.update(REPEAT_DELAY / 2 + REPEAT_INTERVAL * 2.5)
        self.assertEqual(self.gallery.frame_index, 4)
        self.gallery.handle_event(key_event(pygame.K_DOWN, event_type=pygame.KEYUP))
        self.gallery.update(1.0)
        self.assertEqual(self.gallery.frame_index, 4)

    def test_tab_selects_groups_with_their_first_frame(self) -> None:
        self.press(self.gallery, pygame.K_TAB)
        self.assertEqual(self.gallery.group.name, "idle_right")
        self.assertEqual(self.gallery.current_frame.id, "idle_right")
        self.press(self.gallery, pygame.K_TAB, mod=pygame.KMOD_SHIFT)
        self.press(self.gallery, pygame.K_TAB, mod=pygame.KMOD_SHIFT)
        self.assertEqual(self.gallery.group.name, "happy_down")  # назад по кругу
        self.assertEqual(self.gallery.current_frame.id, "happy_down_1")

    def test_info_shows_frame_id_and_description(self) -> None:
        self.open_group(self.gallery, "hamster_official", "stamp")
        lines = self.gallery.info_lines()
        self.assertEqual(lines[0], "Кадр 7/16 · ячейка 6")
        self.assertEqual(lines[1], "stamp_documents")
        self.assertEqual(lines[2], "Ставит печать на документы")
        self.assertIn("Группа 7/13: stamp", lines)

    def test_backspace_finishes_gallery(self) -> None:
        self.press(self.gallery, pygame.K_BACKSPACE)
        self.assertTrue(self.gallery.is_finished)


class PlaybackTest(GalleryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gallery = SpriteGallery()

    def test_space_plays_group_in_a_loop_and_stops(self) -> None:
        self.open_group(self.gallery, "white_rabbit", "run_right")  # 4 кадра, 10 кадр/с
        self.press(self.gallery, pygame.K_SPACE)
        self.assertTrue(self.gallery.is_playing)
        self.assertEqual(self.gallery.current_frame.id, "run_right_1")
        self.gallery.update(0.25)
        self.assertEqual(self.gallery.current_frame.id, "run_right_3")
        self.gallery.update(0.2)
        self.assertEqual(self.gallery.current_frame.id, "run_right_1")  # по кругу
        self.gallery.update(0.1)
        self.press(self.gallery, pygame.K_SPACE)
        self.assertFalse(self.gallery.is_playing)
        self.assertEqual(self.gallery.current_frame.id, "run_right_2")  # остановка на показанном кадре

    def test_one_shot_group_repeats_for_review(self) -> None:
        self.open_group(self.gallery, "alice", "react_down")  # в игре — один раз
        self.press(self.gallery, pygame.K_SPACE)
        self.gallery.update(0.7)  # 3,5 кадра из 3 при 5 кадр/с
        self.assertTrue(self.gallery.is_playing)
        self.assertEqual(self.gallery.current_frame.id, "react_down_1")
        self.assertIn("5 кадр/с · в игре: один раз · кадров 3", self.gallery.info_lines())

    def test_arrow_stops_playback_on_shown_frame(self) -> None:
        self.open_group(self.gallery, "chuchmek", "talk")
        self.press(self.gallery, pygame.K_SPACE)
        self.gallery.update(0.2)  # второй кадр группы
        self.press(self.gallery, pygame.K_DOWN)
        self.assertFalse(self.gallery.is_playing)
        self.assertEqual(self.gallery.current_frame.id, "talk_gesture")

    def test_tab_during_playback_plays_new_group(self) -> None:
        self.open_group(self.gallery, "chuchmek", "talk")
        self.press(self.gallery, pygame.K_SPACE)
        self.press(self.gallery, pygame.K_TAB)
        self.assertEqual(self.gallery.group.name, "run_right")
        self.assertTrue(self.gallery.is_playing)
        self.assertEqual(self.gallery.current_frame.id, "run_right_01")

    def test_draft_group_is_marked(self) -> None:
        self.open_group(self.gallery, "alice", "walk_down")
        self.assertTrue(any(line.startswith("ЧЕРНОВИК: README") for line in self.gallery.info_lines()))
        self.press(self.gallery, pygame.K_SPACE)
        self.gallery.draw(self.canvas)
        self.assertEqual(tuple(self.canvas.get_at(PANEL_RECT.topleft))[:3], DRAFT_COLOR)

    def test_verified_group_is_not_marked(self) -> None:
        self.open_group(self.gallery, "alice", "walk_left")
        self.assertFalse(any("ЧЕРНОВИК" in line for line in self.gallery.info_lines()))
        self.press(self.gallery, pygame.K_SPACE)
        self.gallery.draw(self.canvas)
        self.assertNotEqual(tuple(self.canvas.get_at(PANEL_RECT.topleft))[:3], DRAFT_COLOR)

    def test_character_without_groups(self) -> None:
        while self.gallery.entry.id != "leo":
            self.press(self.gallery, pygame.K_RIGHT)
        self.press(self.gallery, pygame.K_TAB)
        self.press(self.gallery, pygame.K_SPACE)
        self.assertFalse(self.gallery.is_playing)
        self.assertIn("Групп анимации нет — только позы", self.gallery.info_lines())
        self.gallery.draw(self.canvas)


class ScalingTest(GalleryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gallery = SpriteGallery()

    def test_size_keys(self) -> None:
        expected = {pygame.K_1: 24, pygame.K_2: 32, pygame.K_KP3: 40, pygame.K_4: 48, pygame.K_5: 64}
        for key, size in expected.items():
            self.press(self.gallery, key)
            self.assertEqual(self.gallery.display_size, size)
            self.assertEqual(self.gallery.scaled_frame().get_size(), (size, size))
        self.press(self.gallery, 0, scancode=pygame.KSCAN_2)  # по физическому положению клавиши
        self.assertEqual(self.gallery.display_size, 32)

    def test_scaling_is_nearest_neighbour_and_keeps_source(self) -> None:
        frame = self.gallery.current_frame.image
        source_bytes = pygame.image.tobytes(frame, "RGBA")
        source_colors = set(zip(*[iter(source_bytes)] * 4))
        for key in (pygame.K_1, pygame.K_4):
            self.press(self.gallery, key)
            scaled = self.gallery.scaled_frame()
            scaled_bytes = pygame.image.tobytes(scaled, "RGBA")
            # Ближайший сосед не создаёт новых цветов, в отличие от сглаживающего smoothscale.
            self.assertLessEqual(set(zip(*[iter(scaled_bytes)] * 4)), source_colors)
            expected = pygame.transform.scale(frame, scaled.get_size())
            self.assertEqual(scaled_bytes, pygame.image.tobytes(expected, "RGBA"))
            self.gallery.draw(self.canvas)
        self.assertEqual(pygame.image.tobytes(frame, "RGBA"), source_bytes)

    def test_texts_fit_on_screen(self) -> None:
        screen = pygame.Rect((0, 0), config.LOGICAL_SIZE)
        for image, rect in self.gallery.labels:
            self.assertTrue(screen.contains(rect), rect)
        font_height = self.gallery._line_height
        for _ in self.gallery.entries:
            sprites = self.gallery.sprites
            for _ in range(max(1, len(sprites.groups))):
                for playing in (False, True):
                    if playing != self.gallery.is_playing:
                        self.press(self.gallery, pygame.K_SPACE)
                    lines = self.gallery.info_lines()
                    with self.subTest(character=sprites.id, group=getattr(self.gallery.group, "name", None)):
                        self.assertLessEqual(INFO_TOP + len(lines) * font_height, HINTS_TOP)
                        for line in lines:
                            self.assertLessEqual(self.gallery._font.size(line)[0], INFO_WIDTH, line)
                        self.gallery.draw(self.canvas)
                self.press(self.gallery, pygame.K_TAB)
            self.press(self.gallery, pygame.K_RIGHT)


class BrokenAssetsTest(GalleryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        super().tearDown()

    def test_broken_character_shows_message_and_others_still_work(self) -> None:
        for char_id in ("alice", "goose_inspector"):
            shutil.copytree(CHARACTERS_DIR / char_id, self.root / char_id)
        (self.root / "goose_inspector" / "frames" / "02_talk.png").unlink()
        (self.root / "notes").mkdir()  # папка без описания
        gallery = SpriteGallery(self.root)
        self.assertEqual([entry.id for entry in gallery.entries], ["alice", "goose_inspector", "notes"])
        broken = gallery.entries[1]
        self.assertIsNone(broken.sprites)
        self.assertIn("02_talk.png", broken.error)
        self.assertIn("нет файла описания", gallery.entries[2].error)
        self.press(gallery, pygame.K_RIGHT)
        for key in (pygame.K_DOWN, pygame.K_TAB, pygame.K_SPACE, pygame.K_1):
            self.press(gallery, key)  # ничего не ломается
        self.assertIsNone(gallery.current_frame)
        self.assertEqual(gallery.info_lines(), [])
        gallery.draw(self.canvas)
        self.press(gallery, pygame.K_LEFT)
        self.assertEqual(gallery.current_frame.id, "idle_down")

    def test_missing_characters_folder(self) -> None:
        gallery = SpriteGallery(self.root / "нет")
        self.assertEqual(gallery.entries, [])
        for key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_TAB, pygame.K_SPACE):
            self.press(gallery, key)
        gallery.update(1.0)
        gallery.draw(self.canvas)
        self.press(gallery, pygame.K_BACKSPACE)
        self.assertTrue(gallery.is_finished)


class GreatCakeGalleryTest(GalleryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.gallery = SpriteGallery()
        while self.gallery.entry.id != "great_cake":
            self.press(self.gallery, pygame.K_RIGHT)

    def test_listed_after_other_characters_with_its_name(self) -> None:
        self.assertEqual(CHARACTER_ORDER[-1], "great_cake")
        self.assertEqual(self.gallery.entries[-1].id, "great_cake")
        self.assertEqual([entry.id for entry in self.gallery.entries].count("great_cake"), 1)
        self.assertEqual(self.gallery.sprites.display_name, "Тортище")
        self.assertEqual(self.gallery.sprites.atlas.get_size(), (256, 256))
        self.gallery.draw(self.canvas)

    def test_every_frame_one_by_one_and_never_mirrored(self) -> None:
        sprites = self.gallery.sprites
        seen = []
        for _ in range(16):
            frame = self.gallery.current_frame
            seen.append(frame.id)
            for key, size in ((pygame.K_4, 48), (pygame.K_5, 64)):  # размер в сценах и исходный
                self.press(self.gallery, key)
                shown = pygame.image.tobytes(self.gallery.scaled_frame(), "RGBA")
                expected = pygame.transform.scale(frame.image, (size, size))
                mirrored = pygame.transform.flip(expected, True, False)
                with self.subTest(frame=frame.id, size=size):
                    self.assertEqual(shown, pygame.image.tobytes(expected, "RGBA"))
                    self.assertNotEqual(shown, pygame.image.tobytes(mirrored, "RGBA"))
                self.gallery.draw(self.canvas)
            self.press(self.gallery, pygame.K_DOWN)
        self.assertEqual(seen, [frame.id for frame in sprites.frames])
        self.assertEqual(len(set(seen)), 16)

    def test_draft_walk_plays_safely_and_is_marked(self) -> None:
        for name in ("walk_right", "walk_left", "reaction"):
            self.open_group(self.gallery, "great_cake", name)
            group = self.gallery.group
            self.assertTrue(any(line.startswith("ЧЕРНОВИК: ") for line in self.gallery.info_lines()))
            self.press(self.gallery, pygame.K_SPACE)
            shown = []
            for _ in range(len(group.frame_ids) * 2):
                shown.append(self.gallery.current_frame.id)
                self.gallery.update(1 / group.fps)
                self.gallery.draw(self.canvas)
                self.assertEqual(tuple(self.canvas.get_at(PANEL_RECT.topleft))[:3], DRAFT_COLOR)
            self.assertEqual(shown, list(group.frame_ids) * 2)  # по кругу, в порядке манифеста
            self.press(self.gallery, pygame.K_SPACE)
            self.assertFalse(self.gallery.is_playing)

    def test_single_poses_are_not_drafts(self) -> None:
        for name in ("idle_down", "wink_down", "idle_up", "idle_right"):
            self.open_group(self.gallery, "great_cake", name)
            self.assertFalse(any("ЧЕРНОВИК" in line for line in self.gallery.info_lines()))
            self.press(self.gallery, pygame.K_SPACE)
            self.gallery.update(1.0)
            self.gallery.draw(self.canvas)
            self.assertNotEqual(tuple(self.canvas.get_at(PANEL_RECT.topleft))[:3], DRAFT_COLOR)
            self.press(self.gallery, pygame.K_SPACE)

    def test_broken_great_cake_does_not_break_the_gallery(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for char_id in ("alice", "great_cake"):
                shutil.copytree(CHARACTERS_DIR / char_id, root / char_id)
            (root / "great_cake" / "great_cake_atlas_64px.png").unlink()
            gallery = SpriteGallery(root)
            self.assertEqual([entry.id for entry in gallery.entries], ["alice", "great_cake"])
            self.assertIn("great_cake_atlas_64px.png", gallery.entries[1].error)
            self.press(gallery, pygame.K_RIGHT)
            for key in (pygame.K_DOWN, pygame.K_TAB, pygame.K_SPACE, pygame.K_4):
                self.press(gallery, key)
            gallery.update(1.0)
            gallery.draw(self.canvas)
            self.assertIsNone(gallery.current_frame)
            self.press(gallery, pygame.K_RIGHT)
            self.assertEqual(gallery.current_frame.id, "idle_down")  # Алиса показывается как раньше


if __name__ == "__main__":
    unittest.main()
