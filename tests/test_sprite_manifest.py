"""Проверки манифеста спрайтов персонажа: загрузка и понятные ошибки."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

from game.graphics.sprite_manifest import ManifestError, character_dirs, load_character_sprites  # noqa: E402

FRAME = 8
COLUMNS, ROWS = 2, 2


def build_character(root: Path, mutate=None, name: str = "hero") -> Path:
    """Персонаж 2×2 кадра 8×8: атлас, отдельные кадры (копии ячеек) и манифест.

    mutate(manifest, folder) может испортить манифест или файлы перед записью.
    """
    folder = root / name
    (folder / "frames").mkdir(parents=True)
    atlas = pygame.Surface((COLUMNS * FRAME, ROWS * FRAME), pygame.SRCALPHA)
    frames = []
    for index in range(COLUMNS * ROWS):
        rect = pygame.Rect((index % COLUMNS) * FRAME, (index // COLUMNS) * FRAME, FRAME, FRAME)
        atlas.fill((40 * index, 100, 200, 255), rect)
        atlas.set_at(rect.topleft, (0, 0, 0, 0))  # у каждого кадра есть прозрачный пиксель
        file = f"frames/{index:02d}_f{index}.png"
        pygame.image.save(atlas.subsurface(rect).copy(), str(folder / file))
        frames.append({"id": f"f{index}", "index": index, "file": file, "description": f"Кадр {index}"})
    pygame.image.save(atlas, str(folder / f"{name}_atlas.png"))
    manifest = {
        "format": 1,
        "id": name,
        "display_name": "Герой",
        "frame_size": [FRAME, FRAME],
        "atlas": {"file": f"{name}_atlas.png", "columns": COLUMNS, "rows": ROWS},
        "frames": frames,
        "animations": {
            "walk": {"frames": ["f0", "f1"], "fps": 4, "loop": True, "draft": False},
            "wave": {
                "frames": ["f2", "f3", "f2"], "fps": 2, "loop": False, "draft": True, "draft_reason": "не проверено",
            },
        },
        "poses": {"hello": "f2"},
        "notes": ["тестовый персонаж"],
    }
    if mutate is not None:
        mutate(manifest, folder)
    (folder / f"{name}.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return folder


class ManifestTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assert_error(self, mutate, pattern: str, error=ManifestError) -> None:
        folder = build_character(self.root, mutate)
        with self.assertRaisesRegex(error, pattern):
            load_character_sprites(folder)


class LoadTest(ManifestTestCase):
    def test_valid_manifest_is_loaded(self) -> None:
        sprites = load_character_sprites(build_character(self.root))
        self.assertEqual((sprites.id, sprites.display_name), ("hero", "Герой"))
        self.assertEqual((sprites.columns, sprites.rows, sprites.frame_size), (2, 2, (8, 8)))
        self.assertEqual([frame.id for frame in sprites.frames], ["f0", "f1", "f2", "f3"])
        self.assertEqual(sprites.frame("f3").description, "Кадр 3")
        self.assertEqual(tuple(sprites.frame("f1").image.get_at((4, 4))), (40, 100, 200, 255))
        self.assertEqual(sprites.frame("f1").image.get_at((0, 0)).a, 0)
        self.assertEqual(sprites.poses, {"hello": "f2"})
        self.assertEqual(sprites.notes, ("тестовый персонаж",))

    def test_groups_keep_draft_mark_and_build_animations(self) -> None:
        sprites = load_character_sprites(build_character(self.root))
        self.assertFalse(sprites.groups["walk"].draft)
        wave = sprites.groups["wave"]
        self.assertEqual((wave.frame_ids, wave.fps, wave.loop), (("f2", "f3", "f2"), 2, False))
        self.assertTrue(wave.draft)
        self.assertEqual(wave.draft_reason, "не проверено")
        animation = sprites.animation("wave")
        self.assertEqual(len(animation.frames), 3)
        self.assertIs(animation.frames[0], sprites.frame("f2").image)
        self.assertFalse(animation.loop)
        self.assertTrue(sprites.animation("wave", loop=True).loop)

    def test_character_without_groups_is_valid(self) -> None:
        def no_groups(manifest, folder):
            manifest["animations"] = {}
            del manifest["poses"]

        sprites = load_character_sprites(build_character(self.root, no_groups))
        self.assertEqual(sprites.groups, {})

    def test_character_dirs(self) -> None:
        for name in ("zeta", "alpha", ".hidden"):
            (self.root / name).mkdir()
        (self.root / "file.txt").write_text("не папка")
        self.assertEqual([path.name for path in character_dirs(self.root)], ["alpha", "zeta"])
        self.assertEqual(character_dirs(self.root / "нет"), [])


class FileErrorsTest(ManifestTestCase):
    def test_missing_manifest(self) -> None:
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(FileNotFoundError, "нет файла описания"):
            load_character_sprites(self.root / "empty")

    def test_broken_json(self) -> None:
        folder = build_character(self.root)
        (folder / "hero.json").write_text("{ не json", encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "некорректный JSON"):
            load_character_sprites(folder)

    def test_missing_frame_file(self) -> None:
        self.assert_error(lambda m, f: (f / "frames/02_f2.png").unlink(), "файл не найден", FileNotFoundError)

    def test_path_outside_character_folder(self) -> None:
        def escape(manifest, folder):
            manifest["frames"][0]["file"] = "../outside.png"

        self.assert_error(escape, "внутрь папки персонажа")

    def test_frame_without_alpha_channel(self) -> None:
        def opaque_rgb(manifest, folder):
            frame = pygame.Surface((FRAME, FRAME))  # RGB без альфа-канала
            pygame.image.save(frame, str(folder / "frames/01_f1.png"))

        self.assert_error(opaque_rgb, "RGBA")

    def test_image_without_transparent_pixels(self) -> None:
        def opaque_atlas(manifest, folder):
            atlas = pygame.Surface((COLUMNS * FRAME, ROWS * FRAME), pygame.SRCALPHA)
            atlas.fill((10, 20, 30, 255))
            pygame.image.save(atlas, str(folder / "hero_atlas.png"))

        self.assert_error(opaque_atlas, "нет прозрачных пикселей")

    def test_fully_transparent_frame(self) -> None:
        def empty_frame(manifest, folder):
            pygame.image.save(pygame.Surface((FRAME, FRAME), pygame.SRCALPHA), str(folder / "frames/03_f3.png"))

        self.assert_error(empty_frame, "полностью прозрачное")


class GridErrorsTest(ManifestTestCase):
    def test_atlas_size_must_match_grid(self) -> None:
        def wrong_grid(manifest, folder):
            manifest["atlas"]["rows"] = 3

        self.assert_error(wrong_grid, "атлас 16×16, а для сетки 2×3")

    def test_frame_size_must_match(self) -> None:
        def big_frame(manifest, folder):
            frame = pygame.Surface((FRAME + 1, FRAME), pygame.SRCALPHA)
            frame.fill((1, 2, 3, 255))
            frame.set_at((0, 0), (0, 0, 0, 0))
            pygame.image.save(frame, str(folder / "frames/00_f0.png"))

        self.assert_error(big_frame, "размером 9×8")

    def test_frame_must_equal_atlas_cell(self) -> None:
        def changed_pixel(manifest, folder):
            frame = pygame.image.load(str(folder / "frames/01_f1.png"))
            frame.set_at((5, 5), (255, 0, 0, 255))
            pygame.image.save(frame, str(folder / "frames/01_f1.png"))

        self.assert_error(changed_pixel, "не совпадает с ячейкой 1")

    def test_index_outside_grid(self) -> None:
        def outside(manifest, folder):
            manifest["frames"][3]["index"] = 4

        self.assert_error(outside, "ячейки 4 нет в сетке")

    def test_invalid_frame_size(self) -> None:
        for value in ([8], [0, 8], [8.0, 8], "8x8", [True, 8]):
            with self.subTest(frame_size=value):
                folder_root = Path(tempfile.mkdtemp(dir=self.root))

                def bad_size(manifest, folder, value=value):
                    manifest["frame_size"] = value

                with self.assertRaisesRegex(ManifestError, "frame_size"):
                    load_character_sprites(build_character(folder_root, bad_size))


class IdentifierErrorsTest(ManifestTestCase):
    def test_unknown_format(self) -> None:
        self.assert_error(lambda m, f: m.update(format=2), "версия формата 2")

    def test_id_must_match_folder(self) -> None:
        self.assert_error(lambda m, f: m.update(id="villain"), "не совпадает с папкой")

    def test_id_must_be_snake_case(self) -> None:
        def upper(manifest, folder):
            manifest["frames"][0]["id"] = "Idle"

        self.assert_error(upper, "латинские буквы в нижнем регистре")

    def test_duplicate_frame_id(self) -> None:
        def duplicate(manifest, folder):
            manifest["frames"][1]["id"] = "f0"

        self.assert_error(duplicate, "«f0» повторяется")

    def test_duplicate_cell(self) -> None:
        def duplicate(manifest, folder):
            manifest["frames"][1]["index"] = 0

        self.assert_error(duplicate, "ячейка атласа 0 занята")

    def test_missing_field(self) -> None:
        self.assert_error(lambda m, f: m.pop("frames"), "нет поля «frames»")
        folder = build_character(Path(tempfile.mkdtemp(dir=self.root)), lambda m, f: m["frames"][2].pop("description"))
        with self.assertRaisesRegex(ManifestError, "нет поля «description» у кадра №2"):
            load_character_sprites(folder)


class GroupErrorsTest(ManifestTestCase):
    def test_group_with_unknown_frame(self) -> None:
        self.assert_error(lambda m, f: m["animations"]["walk"]["frames"].append("f9"), "несуществующий кадр 'f9'")

    def test_empty_group(self) -> None:
        self.assert_error(lambda m, f: m["animations"]["walk"].update(frames=[]), "без кадров")

    def test_invalid_fps(self) -> None:
        for fps in (0, -1, True, "8"):
            with self.subTest(fps=fps):
                root = Path(tempfile.mkdtemp(dir=self.root))
                folder = build_character(root, lambda m, f, fps=fps: m["animations"]["walk"].update(fps=fps))
                with self.assertRaises(ManifestError):
                    load_character_sprites(folder)

    def test_draft_must_be_bool_and_explained(self) -> None:
        self.assert_error(lambda m, f: m["animations"]["walk"].update(draft="yes"), "«draft» в группе «walk»")
        root = Path(tempfile.mkdtemp(dir=self.root))
        folder = build_character(root, lambda m, f: m["animations"]["wave"].pop("draft_reason"))
        with self.assertRaisesRegex(ManifestError, "нужна причина draft_reason"):
            load_character_sprites(folder)

    def test_pose_with_unknown_frame(self) -> None:
        self.assert_error(lambda m, f: m.update(poses={"hello": "nobody"}), "poses")


if __name__ == "__main__":
    unittest.main()
