"""Проверки импортированных спрайтов персонажей в assets/characters и исходников в art/characters."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import hashlib  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from collections import deque  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.display import fit_viewport  # noqa: E402
from game.graphics.animation import IDLE, WALK, Direction  # noqa: E402
from game.graphics.hires import HiResLayer, SpriteCommand, ViewTransform, scale_sprite  # noqa: E402
from game.graphics.sprite_manifest import (  # noqa: E402
    CHARACTERS_DIR,
    ManifestError,
    character_dirs,
    load_character_sprites,
    try_load_character_sprites,
)
from game.world.character import Character  # noqa: E402

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
    "great_cake": ((4, 4), 16),
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
    "great_cake": {"reaction", "walk_right", "walk_left"},
}
# Поля манифеста формата 1, которые понимает загрузчик (game/graphics/sprite_manifest.py).
MANIFEST_KEYS = {
    "format", "id", "display_name", "frame_size", "atlas", "frames", "animations", "poses", "source", "notes",
}
FRAME_KEYS = {"id", "index", "file", "description", "source_file"}
GROUP_KEYS = {"frames", "fps", "loop", "draft", "draft_reason"}


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

    def test_manifests_use_only_fields_the_loader_knows(self) -> None:
        for char_id in EXPECTED:
            manifest = json.loads((CHARACTERS_DIR / char_id / f"{char_id}.json").read_text(encoding="utf-8"))
            with self.subTest(character=char_id):
                self.assertLessEqual(set(manifest), MANIFEST_KEYS)
                self.assertEqual(set(manifest["atlas"]), {"file", "columns", "rows"})
                for frame in manifest["frames"]:
                    self.assertLessEqual(set(frame), FRAME_KEYS, frame["id"])
                for name, group in manifest["animations"].items():
                    self.assertLessEqual(set(group), GROUP_KEYS, name)


GREAT_CAKE = CHARACTERS_DIR / "great_cake"
# Кадры Тортища по ячейкам атласа, как в архиве: позы и эмоции, затем шаги вправо и влево.
GREAT_CAKE_FRAMES = (
    "idle_front", "wink_front", "back_cape", "profile_right",
    "angry_shout", "unimpressed", "angry_scepter", "crossed_arms",
    "walk_right_01", "walk_right_02", "walk_right_03", "walk_right_04",
    "walk_left_01", "walk_left_02", "walk_left_03", "walk_left_04",
)
# Отпечаток PNG Тортища (16 кадров и атлас): он совпадает с файлами архива great_cake_sprite_assets.zip.
GREAT_CAKE_PNG_DIGEST = "b62d04eeef93fffb2b28ebd77cf3afef248db2cbb205ed314818eb9d16c6f8e3"
# Отпечатки PNG и манифестов персонажей, импортированных раньше: импорт нового персонажа их не трогает,
# а пиксели утверждённых кадров вообще не меняются (assets/README.md).
APPROVED_DIGESTS = {
    "alice": "0e67311fdad00e1e654031c8784b57b2954568d8722f6fe27814e539118e641e",
    "cat_chef": "7108e1e2d95eb2f853938b0da4a5c36cde1641b3d11889afd88e6cdb7468c22e",
    "chuchmek": "9ed5e7332d20a565f79e70e28c0b3dd4422c4598c3461bda0c95ad624e7f01f5",
    "goose_inspector": "84d7cb51641fa0cf2c493a5a221329afe2680da2b424c06d609242d886638124",
    "hamster_official": "4cc1b281230218f26cf3c3c5e48da521fa69688bbf080904477496f7c3e9ac93",
    "leo": "b04f85d724315a7c56d2396ec54ca562f78b12cf27c3028338c637e0f295f40d",
    "white_rabbit": "f74fc750bfa2118fbf564ed1e902725d03afeb3df526f376dac376f8746b8aba",
}
# Пятнышко вне силуэта с такой альфой и меньше на экране не видно (3 % непрозрачности).
INVISIBLE_ALPHA = 8


def digest(folder: Path, files: list[Path]) -> str:
    """SHA-256 по относительным путям и содержимому файлов, в порядке путей."""
    result = hashlib.sha256()
    for file in sorted(files):
        result.update(file.relative_to(folder).as_posix().encode() + b"\0" + file.read_bytes() + b"\0")
    return result.hexdigest()


def raw_png(path: Path) -> pygame.Surface:
    """PNG как он лежит на диске: без convert_alpha() и без загрузчика манифеста."""
    return pygame.image.load(str(path))


def alpha_of(image: pygame.Surface) -> bytes:
    return pygame.image.tobytes(image, "RGBA")[3::4]


def components(alpha: bytes, width: int, height: int) -> list[tuple[int, int]]:
    """Связные (с диагоналями) области непрозрачных пикселей: (размер, наибольшая альфа), крупные первыми."""
    seen = bytearray(width * height)
    found = []
    for start in range(width * height):
        if not alpha[start] or seen[start]:
            continue
        seen[start] = 1
        queue, size, strongest = deque([start]), 0, 0
        while queue:
            index = queue.popleft()
            size += 1
            strongest = max(strongest, alpha[index])
            x, y = index % width, index // width
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    near = ny * width + nx
                    if 0 <= nx < width and 0 <= ny < height and alpha[near] and not seen[near]:
                        seen[near] = 1
                        queue.append(near)
        found.append((size, strongest))
    return sorted(found, reverse=True)


class ApprovedAssetsTest(unittest.TestCase):
    def test_earlier_characters_are_unchanged(self) -> None:
        for char_id, expected in APPROVED_DIGESTS.items():
            folder = CHARACTERS_DIR / char_id
            files = [*folder.rglob("*.png"), folder / f"{char_id}.json"]
            with self.subTest(character=char_id):
                self.assertEqual(digest(folder, files), expected)

    def test_great_cake_pixels_are_copied_from_the_archive(self) -> None:
        self.assertEqual(digest(GREAT_CAKE, list(GREAT_CAKE.rglob("*.png"))), GREAT_CAKE_PNG_DIGEST)


class GreatCakeTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        self.sprites = load_character_sprites(GREAT_CAKE)
        self.manifest = json.loads((GREAT_CAKE / "great_cake.json").read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        pygame.quit()

    def frame_files(self) -> list[Path]:
        folder = GREAT_CAKE / "frames"
        return [folder / f"{index:02d}_{frame_id}.png" for index, frame_id in enumerate(GREAT_CAKE_FRAMES)]

    def test_all_sixteen_frames_in_atlas_order(self) -> None:
        self.assertEqual([frame.id for frame in self.sprites.frames], list(GREAT_CAKE_FRAMES))
        self.assertEqual([frame.index for frame in self.sprites.frames], list(range(16)))
        self.assertEqual(sorted((GREAT_CAKE / "frames").glob("*.png")), self.frame_files())

    def test_runtime_frames_are_64_and_atlas_is_256(self) -> None:
        for path in self.frame_files():
            self.assertEqual(raw_png(path).get_size(), (64, 64), path.name)
        self.assertEqual(raw_png(GREAT_CAKE / "great_cake_atlas_64px.png").get_size(), (256, 256))
        self.assertEqual(self.sprites.frame_size, (64, 64))

    def test_frames_match_their_atlas_cells(self) -> None:
        atlas = raw_png(GREAT_CAKE / "great_cake_atlas_64px.png")
        for index, path in enumerate(self.frame_files()):
            cell = atlas.subsurface(((index % 4) * 64, (index // 4) * 64, 64, 64))
            self.assertEqual(pygame.image.tobytes(raw_png(path), "RGBA"), pygame.image.tobytes(cell, "RGBA"), path.name)

    def test_alpha_transparency(self) -> None:
        for path in [*self.frame_files(), GREAT_CAKE / "great_cake_atlas_64px.png"]:
            image = raw_png(path)
            with self.subTest(file=path.name):
                self.assertEqual(image.get_bitsize(), 32)
                self.assertTrue(image.get_flags() & pygame.SRCALPHA)
        for path in self.frame_files():
            image = raw_png(path)
            alpha = alpha_of(image)
            with self.subTest(frame=path.name):
                # Фон прозрачный, а корпус непрозрачный: торт не просвечивает.
                self.assertGreater(alpha.count(0), 64 * 64 * 0.3)
                self.assertGreater(sum(1 for value in alpha if value >= 250), 64 * 64 * 0.3)
                # Корона, накидка и скипетр не обрезаны краем ячейки.
                border = [alpha[i] for i in range(64)] + [alpha[63 * 64 + i] for i in range(64)]
                border += [alpha[row * 64] for row in range(64)] + [alpha[row * 64 + 63] for row in range(64)]
                self.assertEqual(max(border), 0)
                # Вне силуэта нет заметных случайных пятен: всё, что не связано с персонажем, невидимо.
                main, *specks = components(alpha, 64, 64)
                self.assertGreater(main[0], 1500)
                for size, strongest in specks:
                    self.assertLessEqual(strongest, INVISIBLE_ALPHA, f"пятно из {size} пикселей")

    def test_manifest_follows_project_schema(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest["format"], 1)
        self.assertEqual(manifest["id"], "great_cake")
        self.assertEqual(manifest["display_name"], "Тортище")
        self.assertEqual(manifest["frame_size"], [64, 64])
        self.assertEqual(manifest["atlas"], {"file": "great_cake_atlas_64px.png", "columns": 4, "rows": 4})
        self.assertEqual(manifest["source"]["archive"], "great_cake_sprite_assets.zip")
        for frame in manifest["frames"]:
            self.assertTrue(frame["description"].strip(), frame["id"])
            self.assertEqual(frame["source_file"], frame["file"])  # имена файлов из архива сохранены
        original = json.loads((config.PROJECT_DIR / manifest["source"]["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(original["character"], "great_cake")
        # Группы архива перенесены все, с номерами кадров вместо ячеек.
        self.assertEqual(set(manifest["animations"]), set(original["animations"]))
        for name, group in original["animations"].items():
            self.assertEqual(manifest["animations"][name]["frames"], [GREAT_CAKE_FRAMES[i] for i in group["frames"]])

    def test_existing_loader_reads_it(self) -> None:
        sprites = try_load_character_sprites(GREAT_CAKE)
        self.assertIsNotNone(sprites)
        self.assertEqual(sprites.display_name, "Тортище")
        self.assertEqual((sprites.columns, sprites.rows), (4, 4))
        self.assertEqual(sprites.atlas.get_size(), (256, 256))
        for frame in sprites.frames:
            on_disk = raw_png(GREAT_CAKE / frame.file)
            self.assertEqual(pygame.image.tobytes(frame.image, "RGBA"), pygame.image.tobytes(on_disk, "RGBA"))

    def test_frames_are_not_mirror_copies(self) -> None:
        # Скипетр и накидка делают Тортища несимметричным: шаги влево — свои кадры, а не отражение шагов вправо.
        masks = {frame.id: pygame.mask.from_surface(frame.image, 0) for frame in self.sprites.frames}
        for frame in self.sprites.frames:
            mirrored = pygame.mask.from_surface(pygame.transform.flip(frame.image, True, False), 0)
            for other_id, mask in masks.items():
                if other_id == frame.id:
                    continue
                different = mask.count() + mirrored.count() - 2 * mask.overlap_area(mirrored, (0, 0))
                with self.subTest(frame=frame.id, other=other_id):
                    self.assertGreater(different, 100)

    def test_animation_set_uses_original_frames_without_flipping(self) -> None:
        for include_draft in (False, True):
            animations = self.sprites.animation_set(48, include_draft=include_draft)
            images = {id(frame.image) for frame in self.sprites.frames}
            for state in animations.states:
                for direction in Direction:
                    animation = animations.get(state, direction)
                    with self.subTest(state=state, direction=direction.name, include_draft=include_draft):
                        self.assertTrue(all(id(source) in images for source in animation.sources))
        walk_left = self.sprites.animation_set(48, include_draft=True).get(WALK, Direction.LEFT)
        expected = [self.sprites.frame(f"walk_left_0{n}").image for n in range(1, 5)]
        self.assertEqual(list(walk_left.sources), expected)

    def test_ready_to_be_a_static_npc(self) -> None:
        poses = {
            "idle": "idle_front", "wink": "wink_front", "back": "back_cape", "facing_right": "profile_right",
            "angry": "angry_shout", "smug": "unimpressed", "threaten": "angry_scepter", "stern": "crossed_arms",
        }
        for alias, frame_id in poses.items():
            self.assertIs(self.sprites.pose(alias), self.sprites.frame(frame_id))
        self.assertEqual(self.sprites.pose("walk_left_02").id, "walk_left_02")  # или прямо по id кадра
        with self.assertRaises(KeyError):
            self.sprites.pose("dance")
        # В обычный набор попадают только проверенные позы; дёрганая ходьба — нет.
        animations = self.sprites.animation_set(48)
        self.assertEqual(animations.states, {"idle", "wink"})
        front, back, right = (self.sprites.frame(i).image for i in ("idle_front", "back_cape", "profile_right"))
        self.assertEqual(animations.get(IDLE, Direction.DOWN).sources, (front,))
        self.assertEqual(animations.get(IDLE, Direction.UP).sources, (back,))
        self.assertEqual(animations.get(IDLE, Direction.RIGHT).sources, (right,))
        # Своего кадра «стоит влево» нет: лицом к зрителю, а не отражённый профиль.
        self.assertEqual(animations.get(IDLE, Direction.LEFT).sources, (front,))
        self.assertIs(animations.get(WALK, Direction.RIGHT), animations.get(IDLE, Direction.RIGHT))

    def test_hires_draws_the_original_frame_like_other_characters(self) -> None:
        pygame.display.set_mode((960, 540))
        sprites = load_character_sprites(GREAT_CAKE)  # кадры после convert_alpha(), как в игре
        cake = Character("Тортище", sprites.animation_set(32), position=(200, 120))
        cake.face(Direction.RIGHT)
        layer, canvas = HiResLayer(), pygame.Surface(config.LOGICAL_SIZE)
        canvas.fill((1, 2, 3))
        cake.draw(canvas, layer)
        (command,) = layer.commands
        self.assertIsInstance(command, SpriteCommand)
        self.assertIs(command.image, sprites.frame("profile_right").image)
        self.assertEqual(command.rect, cake.rect)
        self.assertEqual(command.rect.size, (32, 32))
        self.assertEqual(set(pygame.image.tobytes(canvas, "RGB")), {1, 2, 3})  # на холсте его нет
        for window in ((960, 540), (1920, 1200)):
            transform = ViewTransform(fit_viewport(window, config.LOGICAL_SIZE, config.INTEGER_SCALING))
            screen = pygame.Surface(window)
            screen.fill((1, 2, 3))
            layer.render(screen, transform)
            place = transform.rect(cake.rect)
            expected = pygame.Surface(place.size)
            expected.fill((1, 2, 3))
            expected.blit(scale_sprite(command.image, place.size), (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
            with self.subTest(window=window):
                drawn = pygame.image.tobytes(screen.subsurface(place), "RGB")
                self.assertEqual(drawn, pygame.image.tobytes(expected, "RGB"))


class GreatCakeFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        self._tmp = tempfile.TemporaryDirectory()
        self.copy = Path(self._tmp.name) / "great_cake"
        shutil.copytree(GREAT_CAKE, self.copy)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        pygame.quit()

    def test_missing_frame_gives_placeholder_instead_of_crash(self) -> None:
        (self.copy / "frames" / "06_angry_scepter.png").unlink()
        with self.assertRaises(FileNotFoundError):
            load_character_sprites(self.copy)
        self.assertIsNone(try_load_character_sprites(self.copy))  # сцена покажет временный спрайт

    def test_mirrored_frame_is_rejected(self) -> None:
        path = self.copy / "frames" / "03_profile_right.png"
        pygame.image.save(pygame.transform.flip(raw_png(path), True, False), str(path))
        with self.assertRaisesRegex(ManifestError, "не совпадает с ячейкой 3"):
            load_character_sprites(self.copy)


if __name__ == "__main__":
    unittest.main()
