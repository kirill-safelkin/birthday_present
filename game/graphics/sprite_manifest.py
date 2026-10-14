"""Спрайты персонажей: загрузка и проверка манифеста assets/characters/<id>/<id>.json.

Манифест (format 1) описывает атлас, отдельные кадры и группы кадров:

    {
      "format": 1,
      "id": "alice",                         — совпадает с именем папки
      "display_name": "Алиса",
      "frame_size": [64, 64],
      "atlas": {"file": "alice_atlas_64px.png", "columns": 4, "rows": 8},
      "frames": [{"id": "idle_down", "index": 0, "file": "frames/00_idle_down.png",
                  "description": "Стоит, смотрит вниз"}, ...],
      "animations": {"walk_down": {"frames": ["walk_down_1", ...], "fps": 8, "loop": true,
                                   "draft": true, "draft_reason": "…"}, ...},
      "poses": {"wink": "wink"},             — необязательно: псевдоним → кадр
      "source": {...}, "notes": [...]        — необязательно: откуда ресурсы и заметки
    }

index — номер ячейки атласа слева направо, сверху вниз. Каждый кадр обязан совпадать
со своей ячейкой пиксель в пиксель. draft=true означает, что непрерывность группы
не подтверждена: в игре её пока нельзя считать готовой анимацией.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pygame

import config
from game.graphics.animation import IDLE, Animation, AnimationSet, Direction, resolve_path

MANIFEST_FORMAT = 1
CHARACTERS_DIR = config.PROJECT_DIR / "assets" / "characters"
_ID = re.compile(r"[a-z][a-z0-9_]*")


class ManifestError(ValueError):
    """Ошибка в манифесте спрайтов или в файлах, на которые он ссылается."""


@dataclass(frozen=True, eq=False)
class SpriteFrame:
    id: str
    index: int  # ячейка атласа
    file: str
    description: str
    image: pygame.Surface


@dataclass(frozen=True)
class SpriteGroup:
    """Группа кадров: возможная анимация или набор поз одного действия."""

    name: str
    frame_ids: tuple[str, ...]
    fps: float
    loop: bool
    draft: bool
    draft_reason: str = ""


@dataclass(eq=False)
class CharacterSprites:
    id: str
    display_name: str
    frame_size: config.Size
    columns: int
    rows: int
    atlas: pygame.Surface
    frames: tuple[SpriteFrame, ...]
    groups: dict[str, SpriteGroup]
    poses: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def frame(self, frame_id: str) -> SpriteFrame:
        for frame in self.frames:
            if frame.id == frame_id:
                return frame
        raise KeyError(frame_id)

    def animation(self, group_name: str, loop: bool | None = None) -> Animation:
        """Анимация из группы кадров; loop переопределяет цикличность (например, для просмотра)."""
        group = self.groups[group_name]
        images = [self.frame(frame_id).image for frame_id in group.frame_ids]
        return Animation(images, group.fps, group.loop if loop is None else loop)

    def animation_set(self, size: int | None = None, include_draft: bool = False) -> AnimationSet:
        """Набор анимаций для Character: группа «<состояние>_<направление>» (например, walk_left)
        становится состоянием walk для направления LEFT, группа без направления (idle) — общей.

        size — размер кадра на холсте; кадры масштабируются ближайшим соседом в новые
        поверхности, исходные не меняются. Черновые группы по умолчанию пропускаются:
        вместо них AnimationSet подберёт замену (например, ходьба вверх — ожидание вверх).
        """
        scaled: dict[str, pygame.Surface] = {}

        def image(frame_id: str) -> pygame.Surface:
            if frame_id not in scaled:
                source = self.frame(frame_id).image
                if size is None:
                    scaled[frame_id] = source
                else:
                    width, height = source.get_size()
                    scaled[frame_id] = pygame.transform.scale(source, (size, max(1, height * size // width)))
            return scaled[frame_id]

        entries: list[tuple[str, Animation, Direction | None]] = []
        for name, group in self.groups.items():
            if group.draft and not include_draft:
                continue
            state, _, suffix = name.rpartition("_")
            direction = _DIRECTIONS.get(suffix)
            if direction is None or not state:
                state, direction = name, None
            animation = Animation([image(frame_id) for frame_id in group.frame_ids], group.fps, group.loop)
            entries.append((state, animation, direction))

        # Запасная анимация на крайний случай: ожидание лицом вниз, иначе первый кадр персонажа.
        default = next((a for s, a, d in entries if s == IDLE and d is Direction.DOWN), None)
        default = default or next((a for s, a, d in entries if s == IDLE), None)
        default = default or Animation([image(self.frames[0].id)], 1)
        animations = AnimationSet(default)
        for state, animation, direction in entries:
            animations.add(state, animation, direction)
        return animations


_DIRECTIONS = {"down": Direction.DOWN, "up": Direction.UP, "left": Direction.LEFT, "right": Direction.RIGHT}


def character_dirs(root: str | Path = CHARACTERS_DIR) -> list[Path]:
    """Папки персонажей в root (скрытые пропускаются). Пустой список, если root нет."""
    root = resolve_path(root)
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def load_character_sprites(directory: str | Path) -> CharacterSprites:
    """Загружает и проверяет спрайты персонажа. Ошибки — ManifestError или FileNotFoundError."""
    directory = resolve_path(directory)
    manifest_path = directory / f"{directory.name}.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"нет файла описания спрайтов: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{manifest_path.name}: некорректный JSON: {exc}") from exc
    return _Parser(directory, manifest_path.name).parse(data)


class _Parser:
    def __init__(self, directory: Path, name: str) -> None:
        self.directory = directory
        self.name = name

    def error(self, message: str) -> ManifestError:
        return ManifestError(f"{self.name}: {message}")

    def get(self, data: dict, key: str, kind: type | tuple[type, ...], where: str = "") -> object:
        if not isinstance(data, dict) or key not in data:
            raise self.error(f"нет поля «{key}»{where}")
        value = data[key]
        # bool — подкласс int, но числом в манифесте он быть не должен.
        if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
            raise self.error(f"поле «{key}»{where} имеет неверный тип")
        return value

    def identifier(self, value: object, what: str) -> str:
        if not isinstance(value, str) or not _ID.fullmatch(value):
            raise self.error(f"{what} {value!r}: нужны латинские буквы в нижнем регистре, цифры и «_»")
        return value

    def size(self, value: object, what: str) -> tuple[int, int]:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(side, int) and not isinstance(side, bool) and side > 0 for side in value)
        ):
            raise self.error(f"{what} должен быть парой положительных целых чисел")
        return value[0], value[1]

    def parse(self, data: object) -> CharacterSprites:
        if not isinstance(data, dict):
            raise self.error("ожидался объект JSON")
        if data.get("format") != MANIFEST_FORMAT:
            raise self.error(f"неизвестная версия формата {data.get('format')!r}, ожидалась {MANIFEST_FORMAT}")
        char_id = self.identifier(self.get(data, "id", str), "идентификатор персонажа")
        if char_id != self.directory.name:
            raise self.error(f"идентификатор «{char_id}» не совпадает с папкой «{self.directory.name}»")
        display_name = self.get(data, "display_name", str)
        if not display_name.strip():
            raise self.error("пустое display_name")
        frame_w, frame_h = self.size(data.get("frame_size"), "frame_size")

        atlas_info = self.get(data, "atlas", dict)
        columns = self.get(atlas_info, "columns", int, " атласа")
        rows = self.get(atlas_info, "rows", int, " атласа")
        if columns <= 0 or rows <= 0:
            raise self.error("сетка атласа должна быть положительной")
        atlas_raw = self.image(self.get(atlas_info, "file", str, " атласа"))
        expected = (columns * frame_w, rows * frame_h)
        if atlas_raw.get_size() != expected:
            size = atlas_raw.get_size()
            raise self.error(
                f"атлас {size[0]}×{size[1]}, а для сетки {columns}×{rows} кадров "
                f"{frame_w}×{frame_h} нужен {expected[0]}×{expected[1]}"
            )

        frames: list[SpriteFrame] = []
        seen_ids: set[str] = set()
        seen_indexes: set[int] = set()
        frame_list = self.get(data, "frames", list)
        if not frame_list:
            raise self.error("список кадров пуст")
        for number, item in enumerate(frame_list):
            where = f" у кадра №{number}"
            frame_id = self.identifier(self.get(item, "id", str, where), "идентификатор кадра")
            index = self.get(item, "index", int, where)
            file = self.get(item, "file", str, where)
            description = self.get(item, "description", str, where)
            if frame_id in seen_ids:
                raise self.error(f"идентификатор кадра «{frame_id}» повторяется")
            if index in seen_indexes:
                raise self.error(f"ячейка атласа {index} занята двумя кадрами")
            if not 0 <= index < columns * rows:
                raise self.error(f"кадр «{frame_id}»: ячейки {index} нет в сетке {columns}×{rows}")
            seen_ids.add(frame_id)
            seen_indexes.add(index)
            raw = self.image(file)
            if raw.get_size() != (frame_w, frame_h):
                width, height = raw.get_size()
                raise self.error(f"кадр «{frame_id}» размером {width}×{height}, а не {frame_w}×{frame_h}")
            cell = atlas_raw.subsurface(((index % columns) * frame_w, (index // columns) * frame_h, frame_w, frame_h))
            if pygame.image.tobytes(raw, "RGBA") != pygame.image.tobytes(cell, "RGBA"):
                raise self.error(f"кадр «{frame_id}» не совпадает с ячейкой {index} атласа")
            frames.append(SpriteFrame(frame_id, index, file, description, _for_screen(raw)))

        groups: dict[str, SpriteGroup] = {}
        for name, item in self.get(data, "animations", dict).items():
            self.identifier(name, "имя группы")
            where = f" в группе «{name}»"
            frame_ids = self.get(item, "frames", list, where)
            if not frame_ids:
                raise self.error(f"группа «{name}» без кадров")
            for frame_id in frame_ids:
                if frame_id not in seen_ids:
                    raise self.error(f"группа «{name}» ссылается на несуществующий кадр {frame_id!r}")
            fps = self.get(item, "fps", (int, float), where)
            if not 0 < fps < math.inf:
                raise self.error(f"скорость группы «{name}» должна быть положительной")
            loop = self.get(item, "loop", bool, where)
            draft = self.get(item, "draft", bool, where)
            reason = item.get("draft_reason", "")
            if not isinstance(reason, str) or (draft and not reason.strip()):
                raise self.error(f"у черновой группы «{name}» нужна причина draft_reason")
            groups[name] = SpriteGroup(name, tuple(frame_ids), fps, loop, draft, reason)

        poses = data.get("poses", {})
        if not isinstance(poses, dict) or not all(target in seen_ids for target in poses.values()):
            raise self.error("poses должен сопоставлять псевдонимы существующим кадрам")
        notes = data.get("notes", [])
        if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
            raise self.error("notes должен быть списком строк")

        return CharacterSprites(
            char_id, display_name, (frame_w, frame_h), columns, rows, _for_screen(atlas_raw),
            tuple(frames), groups, dict(poses), tuple(notes),
        )

    def image(self, file: str) -> pygame.Surface:
        """PNG с настоящим альфа-каналом, в исходном формате (до convert_alpha)."""
        relative = PurePosixPath(file)
        if relative.is_absolute() or ".." in relative.parts:
            raise self.error(f"путь {file!r} должен вести внутрь папки персонажа")
        path = self.directory / relative
        if not path.is_file():
            raise FileNotFoundError(f"{self.name}: файл не найден: {path}")
        try:
            image = pygame.image.load(str(path))
        except pygame.error as exc:
            raise self.error(f"не удалось загрузить {file}: {exc}") from exc
        if image.get_bitsize() != 32 or not image.get_flags() & pygame.SRCALPHA:
            raise self.error(f"{file}: нужен PNG RGBA с альфа-каналом")
        alpha = pygame.image.tobytes(image, "RGBA")[3::4]
        if min(alpha) == 255:
            raise self.error(f"{file}: в изображении нет прозрачных пикселей")
        if max(alpha) == 0:
            raise self.error(f"{file}: изображение полностью прозрачное")
        return image


def _for_screen(image: pygame.Surface) -> pygame.Surface:
    # convert_alpha() ускоряет вывод, но доступен только после создания окна.
    return image.convert_alpha() if pygame.display.get_surface() is not None else image
