"""Проверки импортированных спрайтов персонажей в assets/characters и исходников в art/characters."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json  # noqa: E402
import unittest  # noqa: E402

import config  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, character_dirs, load_character_sprites  # noqa: E402

ART_DIR = config.PROJECT_DIR / "art" / "characters"
# Персонаж → (столбцы, строки) атласа и число отдельных кадров.
EXPECTED = {
    "alice": ((4, 8), 28),
    "chuchmek": ((4, 4), 16),
    "leo": ((4, 4), 16),
    "white_rabbit": ((4, 4), 16),
    "cat_chef": ((4, 4), 16),
    "goose_inspector": ((4, 3), 12),
    "hamster_official": ((4, 4), 16),
}
# Группы, непрерывность которых не подтверждена (по README и заметкам из архивов).
EXPECTED_DRAFTS = {
    "alice": {"walk_down", "walk_up"},
    "chuchmek": {"talk", "run_right"},
    "leo": set(),
    "white_rabbit": {"check_watch", "talk_or_point", "panic", "run_right", "rest"},
    "cat_chef": {"idle", "greet", "prepare_sushi", "serve_sushi", "react_angry", "move_with_tray"},
    "goose_inspector": set(),
    "hamster_official": {"review", "carry_papers", "walk_side_papers"},
}


class CharacterAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sprites = {path.name: load_character_sprites(path) for path in character_dirs(CHARACTERS_DIR)}

    def test_all_characters_are_imported(self) -> None:
        self.assertEqual(set(self.sprites), set(EXPECTED))

    def test_grid_and_frame_count(self) -> None:
        for char_id, ((columns, rows), count) in EXPECTED.items():
            sprites = self.sprites[char_id]
            with self.subTest(character=char_id):
                self.assertEqual((sprites.columns, sprites.rows), (columns, rows))
                self.assertEqual(sprites.atlas.get_size(), (columns * 64, rows * 64))
                self.assertEqual(len(sprites.frames), count)
                for frame in sprites.frames:
                    self.assertEqual(frame.image.get_size(), (64, 64), frame.id)

    def test_frames_stand_on_bottom_of_cell(self) -> None:
        # Кадры выровнены по нижней точке: ноги персонажа у нижнего края ячейки.
        for char_id, sprites in self.sprites.items():
            for frame in sprites.frames:
                with self.subTest(character=char_id, frame=frame.id):
                    self.assertGreaterEqual(frame.image.get_bounding_rect().bottom, 58)

    def test_draft_groups(self) -> None:
        for char_id, sprites in self.sprites.items():
            drafts = {name for name, group in sprites.groups.items() if group.draft}
            with self.subTest(character=char_id):
                self.assertEqual(drafts, EXPECTED_DRAFTS[char_id])

    def test_single_frame_groups_are_not_drafts(self) -> None:
        for char_id, sprites in self.sprites.items():
            for group in sprites.groups.values():
                if len(group.frame_ids) == 1:
                    self.assertFalse(group.draft, f"{char_id}.{group.name}")

    def test_files_follow_naming_rules(self) -> None:
        for char_id, sprites in self.sprites.items():
            folder = CHARACTERS_DIR / char_id
            expected = {f"{char_id}.json", "README.md", f"{char_id}_atlas_64px.png"}
            expected |= {f"frames/{frame.index:02d}_{frame.id}.png" for frame in sprites.frames}
            with self.subTest(character=char_id):
                for frame in sprites.frames:
                    self.assertEqual(frame.file, f"frames/{frame.index:02d}_{frame.id}.png")
                actual = {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}
                self.assertEqual(actual, expected)  # ни лишних, ни потерянных файлов

    def test_previews_and_sources_are_not_game_assets(self) -> None:
        for path in CHARACTERS_DIR.rglob("*"):
            for word in ("preview", "source", "checkerboard", "clerk"):
                self.assertNotIn(word, path.name, path)

    def test_hamster_uses_project_identifier(self) -> None:
        path = CHARACTERS_DIR / "hamster_official" / "hamster_official.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "hamster_official")
        self.assertEqual(manifest["source"]["id"], "hamster_clerk")  # откуда импортирован

    def test_original_descriptions_are_preserved(self) -> None:
        for char_id in EXPECTED:
            manifest = json.loads((CHARACTERS_DIR / char_id / f"{char_id}.json").read_text(encoding="utf-8"))
            original = config.PROJECT_DIR / manifest["source"]["manifest"]
            with self.subTest(character=char_id):
                self.assertEqual(original.parent, ART_DIR / char_id / "original")
                json.loads(original.read_text(encoding="utf-8"))
                self.assertTrue((original.parent / "README.md").is_file())
                self.assertTrue((CHARACTERS_DIR / char_id / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
