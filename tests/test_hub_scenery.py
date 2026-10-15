"""Оформление площади: три дерева-входа, стол мозаики, земля, столкновения и анимации по времени."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import itertools  # noqa: E402
import math  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from collections import deque  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.graphics.hires import HiResLayer, SpriteCommand, TextCommand  # noqa: E402
from game.graphics.pixel_art import SCALE, Piece  # noqa: E402
from game.world import hub_ground, hub_scenery  # noqa: E402
from game.world.collision import FOOT_SIZE  # noqa: E402
from game.world.hub import (  # noqa: E402
    CHUCHMEK_AREA,
    GRASS_COLOR,
    GRASS_DARK_COLOR,
    LEO_AREA,
    LEO_POINT,
    MOSAIC_CENTER,
    MOSAIC_RADIUS,
    PORTALS,
    SIGN_STYLE,
    SPAWN,
    TRIAL_SCENES,
    HubScene,
)
from game.world.progress import TRIALS, GameProgress  # noqa: E402

DT = 1 / 60
PORTAL = {portal.id: portal for portal in PORTALS}
# Маршруты от точки появления: пешком, клавишами, вокруг препятствий (точки поворота).
ROUTES = {
    "sushi": [(44, 160), (44, 97)],
    "cakes": [(276, 160), (276, 97)],
    "forms": [(86, 160), (86, 85), (160, 85)],
}
TREE_ART = {"sushi": hub_scenery.sushi_tree, "forms": hub_scenery.forms_tree, "cakes": hub_scenery.cakes_tree}


def key(code: int, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=0)


def walk(hub: HubScene, waypoints: list[tuple[int, int]]) -> None:
    """Ведёт Алису по точкам поворота клавишами, как игрок: по одной оси за раз."""
    for target in waypoints:
        for axis in (0, 1):
            start = (hub.alice.x, hub.alice.y)[axis]
            goal = target[axis]
            if abs(goal - start) < 0.5:
                continue
            forward = goal > start
            code = (pygame.K_RIGHT if forward else pygame.K_LEFT) if axis == 0 else (pygame.K_DOWN if forward else pygame.K_UP)
            hub.handle_event(key(code))
            for _ in range(3000):
                before = (hub.alice.x, hub.alice.y)[axis]
                hub.update(DT)
                now = (hub.alice.x, hub.alice.y)[axis]
                if (now >= goal) if forward else (now <= goal):
                    break
                if now == before:
                    break  # упёрлась в препятствие
            hub.handle_event(key(code, pygame.KEYUP))
    hub.alice.release_controls()


def press_e(hub: HubScene) -> None:
    hub.handle_event(key(pygame.K_e))
    hub.handle_event(key(pygame.K_e, pygame.KEYUP))


class SceneryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def tearDown(self) -> None:
        pygame.quit()

    def hub(self, *done: str) -> HubScene:
        progress = GameProgress()
        for trial_id in done:
            progress.complete(trial_id)
        return HubScene(progress)

    def draw(self, hub: HubScene) -> HiResLayer:
        layer = HiResLayer(strict=True)
        hub.draw(self.canvas, layer)
        return layer

    @staticmethod
    def images(layer: HiResLayer) -> list[pygame.Surface]:
        return [command.image for command in layer.commands if isinstance(command, SpriteCommand)]


class TreeGeometryTest(SceneryTestCase):
    def test_every_tree_has_a_door_in_the_lower_trunk_under_its_sign(self) -> None:
        for trial_id, spec in hub_scenery.TREE_SPECS.items():
            with self.subTest(tree=trial_id):
                art = TREE_ART[trial_id]()
                self.assertTrue(art.piece.rect.contains(spec.door), "дверца вне картинки дерева")
                self.assertTrue(art.piece.rect.contains(spec.sign), "табличка вне картинки дерева")
                self.assertEqual(spec.door.bottom, spec.ground)  # дверца стоит на земле, а не висит
                self.assertLess(spec.sign.bottom, spec.door.top + 4)  # табличка над входом
                self.assertGreaterEqual(spec.door.height, 14)  # дверь — заметная, а не щель
                self.assertLessEqual(abs(spec.door.centerx - spec.cx), 1)
                self.assertGreaterEqual(spec.sign.top, 12)  # не заходит под верхнюю полосу
                self.assertGreaterEqual(art.piece.rect.top, 12)

    def test_trees_are_big_and_differ_in_silhouette(self) -> None:
        profiles = {}
        for trial_id in TRIALS:
            art = TREE_ART[trial_id]()
            image = art.piece.image
            self.assertGreaterEqual(image.get_width() // SCALE, 64)
            self.assertGreaterEqual(image.get_height() // SCALE, 56)
            mask = pygame.mask.from_surface(image, 100)
            self.assertGreater(mask.count(), 5000)
            # Ширина дерева на каждой высоте — это и есть силуэт.
            rows = []
            for y in range(20, 70, 2):
                row = round((y - art.piece.rect.top) * SCALE)
                rows.append(sum(mask.get_at((x, row)) for x in range(image.get_width())) / SCALE if row < image.get_height() else 0)
            profiles[trial_id] = rows
        for a, b in itertools.combinations(TRIALS, 2):
            gap = sum(abs(x - y) for x, y in zip(profiles[a], profiles[b])) / len(profiles[a])
            self.assertGreater(gap, 5.0, (a, b))  # по ширине на одной высоте различаются в среднем на 5+ пикселей

    def test_portals_come_from_the_tree_specs(self) -> None:
        self.assertEqual({portal.id for portal in PORTALS}, set(TRIALS))
        for portal in PORTALS:
            spec = hub_scenery.TREE_SPECS[portal.id]
            self.assertEqual((portal.rect, portal.door, portal.point), (spec.block, spec.door, spec.stand))
            self.assertEqual(portal.sign, spec.sign_text)
        self.assertEqual({portal.sign for portal in PORTALS}, {"СУШИ", "ФОРМУЛЯРЫ", "ТОРТИКИ"})

    def test_the_entrance_is_right_under_the_hole(self) -> None:
        for portal in PORTALS:
            with self.subTest(tree=portal.id):
                hub = self.hub()
                x, y = portal.point
                self.assertTrue(hub.collision.is_free(x, y))  # подойти можно
                feet_top = y - FOOT_SIZE[1]
                self.assertGreaterEqual(feet_top, portal.rect.bottom)  # ноги — вплотную под стволом
                self.assertLessEqual(feet_top - portal.rect.bottom, 2)
                self.assertLessEqual(abs(x - portal.door.centerx), 3)  # и под самим отверстием
                self.assertLessEqual(portal.point[1] - portal.door.bottom, 10)  # а не у невидимой точки вдали
                self.assertLessEqual(portal.radius, 14)


SUSHI_COLORS = {hub_scenery.NORI, hub_scenery.RICE, hub_scenery.RICE_SHADE, hub_scenery.SALMON, hub_scenery.TUNA,
                hub_scenery.CUCUMBER, hub_scenery.TAMAGO}


def tree_pixel(piece: Piece, x: float, y: float) -> tuple[int, int, int, int]:
    """Пиксель картинки дерева в точке холста (x, y)."""
    return tuple(piece.image.get_at((round((x - piece.rect.x) * SCALE), round((y - piece.rect.y) * SCALE))))


def colors_in(piece: Piece, rect: pygame.Rect) -> set[tuple[int, int, int]]:
    area = pygame.Rect((rect.x - piece.rect.x) * SCALE, (rect.y - piece.rect.y) * SCALE, rect.w * SCALE, rect.h * SCALE)
    image = piece.image.subsurface(area)
    return {tuple(image.get_at((x, y)))[:3] for x in range(area.w) for y in range(area.h) if image.get_at((x, y)).a}


class SushiTreeTest(SceneryTestCase):
    """Дерево суши украшено суши: роллы и нигири в кроне, гирлянда из маки, фонарики-рыбки."""

    def test_geometry_and_lights_stay_as_they_were(self) -> None:
        spec = hub_scenery.TREE_SPECS["sushi"]
        self.assertEqual((spec.cx, spec.ground, spec.door_size), (44, 90, (14, 16)))
        self.assertEqual((spec.sign, spec.block, spec.stand, spec.radius),
                         (pygame.Rect(25, 54, 38, 10), pygame.Rect(12, 44, 64, 46), (44, 97), 12))
        self.assertEqual(spec.sign_text, "СУШИ")
        art = hub_scenery.sushi_tree()
        self.assertEqual([(x, y) for x, y, _, _ in art.lights], [(spec.cx - 33, 62), (spec.cx + 33, 59)])
        self.assertTrue(art.piece.rect.contains(spec.sign) and art.piece.rect.contains(spec.door))

    def test_crown_bears_rolls_and_nigiri_on_top_of_the_leaves(self) -> None:
        art, cx = hub_scenery.sushi_tree(), hub_scenery.TREE_SPECS["sushi"].cx
        kinds = [kind for kind, *_ in hub_scenery.SUSHI_FRUITS]
        self.assertGreaterEqual(kinds.count("maki"), 3)
        self.assertGreaterEqual(kinds.count("nigiri"), 2)
        for kind, dx, y, color, _ in hub_scenery.SUSHI_FRUITS:
            with self.subTest(kind=kind, dx=dx):
                # Начинка ролла или ломтик нигири (слева от полоски нори) видны: украшение лежит
                # поверх листвы, а не под ней.
                x = cx + dx - (0.1 if kind == "maki" else 1.1)
                self.assertEqual(tree_pixel(art.piece, x, y - 0.3)[:3], color)
                around = colors_in(art.piece, pygame.Rect(round(cx + dx) - 3, round(y) - 2, 6, 5))
                self.assertIn(hub_scenery.RICE, around)
                self.assertIn(hub_scenery.NORI, around)

    def test_old_red_balls_are_gone_and_sushi_colours_are_plentiful(self) -> None:
        piece = hub_scenery.sushi_tree().piece
        crown = pygame.Rect(piece.rect.x, piece.rect.y, piece.rect.w, 62 - piece.rect.y)
        crown_colors = colors_in(piece, crown)
        self.assertNotIn(hub_scenery.palette_from((196, 60, 60))[1], crown_colors)  # красно-белых бутонов нет
        mask = pygame.mask.from_surface(piece.image)
        counts = {color: 0 for color in SUSHI_COLORS}
        for x in range(piece.image.get_width()):
            for y in range(piece.image.get_height()):
                if mask.get_at((x, y)):
                    color = tuple(piece.image.get_at((x, y)))[:3]
                    if color in counts:
                        counts[color] += 1
        for color in (hub_scenery.RICE, hub_scenery.NORI, hub_scenery.SALMON, hub_scenery.CUCUMBER, hub_scenery.TAMAGO):
            self.assertGreater(counts[color], 12, color)  # различимо, а не пара случайных точек

    def test_sign_and_door_stay_clear(self) -> None:
        spec, piece = hub_scenery.TREE_SPECS["sushi"], hub_scenery.sushi_tree().piece
        self.assertFalse(colors_in(piece, spec.sign) & SUSHI_COLORS)  # украшения не лежат поверх таблички
        self.assertFalse(colors_in(piece, spec.door.inflate(-2, -2)) & SUSHI_COLORS)  # и не висят в дупле
        cx = spec.cx
        for _, dx, y, _, _ in hub_scenery.SUSHI_FRUITS:
            fruit = pygame.Rect(round(cx + dx) - 4, round(y) - 4, 8, 8)
            self.assertFalse(fruit.colliderect(spec.sign), dx)
            self.assertLess(fruit.bottom, spec.door.top - 8, dx)

    def test_decorated_tree_draws_at_window_and_fullscreen_sizes(self) -> None:
        from game.core.display import fit_viewport
        from game.graphics.hires import ViewTransform
        hub = self.hub()
        spec = hub_scenery.TREE_SPECS["sushi"]
        for size in ((960, 540), (1920, 1200)):
            with self.subTest(size=size):
                layer = HiResLayer()
                hub.draw(self.canvas, layer)
                screen = pygame.Surface(size)
                transform = ViewTransform(fit_viewport(size, config.LOGICAL_SIZE, config.INTEGER_SCALING))
                pygame.transform.scale(self.canvas, transform.viewport.size, screen.subsurface(transform.viewport))
                layer.render(screen, transform)
                # Середина ролла в кроне — цвет начинки и в окне, и на весь экран.
                kind, dx, y, color, _ = hub_scenery.SUSHI_FRUITS[2]
                self.assertEqual(tuple(screen.get_at(transform.point((spec.cx + dx - 0.1, y - 0.1))))[:3], color)


class ReachabilityTest(SceneryTestCase):
    def reachable(self, hub: HubScene) -> set[tuple[int, int]]:
        start = (int(SPAWN[0]), int(SPAWN[1]))
        seen, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cell = (x + dx, y + dy)
                if cell not in seen and hub.collision.is_free(*cell):
                    seen.add(cell)
                    queue.append(cell)
        return seen

    def test_all_entrances_and_targets_are_reachable(self) -> None:
        hub = self.hub()
        seen = self.reachable(hub)
        for portal in PORTALS:
            self.assertIn(portal.point, seen, portal.id)
            in_range = [cell for cell in seen if math.dist(cell, portal.point) <= portal.radius]
            self.assertGreater(len(in_range), 100, portal.id)  # у входа есть где встать
        self.assertIn(tuple(MOSAIC_CENTER), seen)
        self.assertIn(tuple(LEO_POINT), seen)
        chuchmek = [cell for cell in seen if hub.alice.set_position(*cell) is None and hub.nearby() is not None
                    and hub.nearby().kind == "chuchmek"]
        self.assertGreater(len(chuchmek), 100)

    def test_big_obstacles_cannot_be_entered(self) -> None:
        hub = self.hub()
        seen = self.reachable(hub)
        for portal in PORTALS:
            self.assertFalse([cell for cell in seen if portal.rect.collidepoint(cell)], portal.id)
        for rect in hub_scenery.table().footprint:
            self.assertFalse([cell for cell in seen if rect.inflate(-2, -2).collidepoint(cell)], rect)

    def test_walking_into_a_tree_or_the_table_stops_alice(self) -> None:
        hub = self.hub()
        for portal in PORTALS:
            hub.alice.set_position(portal.point[0] - 18, portal.point[1])
            hub.handle_event(key(pygame.K_RIGHT))
            hub.handle_event(key(pygame.K_UP))
            for _ in range(240):
                hub.update(DT)
            hub.handle_event(key(pygame.K_RIGHT, pygame.KEYUP))
            hub.handle_event(key(pygame.K_UP, pygame.KEYUP))
            self.assertTrue(hub.collision.is_free(hub.alice.x, hub.alice.y), portal.id)
            self.assertFalse(portal.rect.collidepoint(hub.alice.x, hub.alice.y - 1), portal.id)
        hub.alice.set_position(*MOSAIC_CENTER)
        hub.handle_event(key(pygame.K_UP))
        for _ in range(240):
            hub.update(DT)
        hub.handle_event(key(pygame.K_UP, pygame.KEYUP))
        table_bottom = max(rect.bottom for rect in hub_scenery.table().footprint)
        self.assertGreaterEqual(hub.alice.y - FOOT_SIZE[1], table_bottom - 1)  # упёрлась в основание стола

    def test_alice_walks_from_the_spawn_to_each_door_and_opens_the_right_trial(self) -> None:
        for trial_id, route in ROUTES.items():
            with self.subTest(trial=trial_id):
                manager = SceneManager()
                manager.push(Scene())
                scenes = {}
                for name in TRIAL_SCENES.values():
                    manager.register(name, lambda name=name: scenes.setdefault(name, Scene()))
                hub = manager.push(HubScene())
                walk(hub, route)
                target = hub.nearby()
                self.assertEqual((target.kind, target.target), ("portal", trial_id))
                self.assertEqual(hub.status_text(), f"{PORTAL[trial_id].name}   E — войти")
                press_e(hub)
                self.assertIs(manager.current, scenes[TRIAL_SCENES[trial_id]])  # то самое испытание
                self.assertEqual(len(scenes), 1)

    def test_interaction_far_from_the_hole_does_nothing(self) -> None:
        for portal in PORTALS:
            hub = self.hub()
            x, y = portal.point
            hub.alice.set_position(x + portal.radius + 4, y + 3)
            self.assertIsNone(hub.nearby(), portal.id)
            hub.alice.set_position(x, y)
            self.assertEqual(hub.nearby().target, portal.id)


class TableTest(SceneryTestCase):
    @staticmethod
    def drawn(layer: HiResLayer, piece: Piece) -> int:
        """Сколько раз картинка piece (или её ступень прозрачности) выведена слоем за кадр."""
        mine = [piece.image, *piece._levels.values()]
        return sum(any(image is own for own in mine) for image in SceneryTestCase.images(layer))

    def fragment_images(self, layer: HiResLayer) -> set[str]:
        art = hub_scenery.table()
        return {trial_id for trial_id, piece in art.fragments.items() if self.drawn(layer, piece)}

    def test_fragments_follow_progress_and_nothing_else(self) -> None:
        for count in range(len(TRIALS) + 1):
            for done in itertools.combinations(TRIALS, count):
                with self.subTest(done=done):
                    hub = self.hub(*done)
                    hub.update(0.2)
                    layer = self.draw(hub)
                    self.assertEqual(self.fragment_images(layer), set(done))
                    inlay = hub_scenery.table().inlay
                    self.assertEqual(self.drawn(layer, inlay), int(count == len(TRIALS)))

    def test_fragment_is_drawn_once_per_frame_and_never_stacks(self) -> None:
        hub = self.hub("sushi", "forms", "cakes")
        for _ in range(30):
            hub.update(DT)
            layer = self.draw(hub)
            for piece in hub_scenery.table().fragments.values():
                self.assertEqual(self.drawn(layer, piece), 1)
        self.assertEqual(hub.progress.completed, ("sushi", "forms", "cakes"))  # рисование прогресс не трогает

    def test_fragments_are_big_square_tiles_that_fit_the_table_and_differ(self) -> None:
        art = hub_scenery.table()
        slots = hub_scenery.MOSAIC_SLOTS
        images = []
        for trial_id, piece in art.fragments.items():
            self.assertEqual(piece.rect.size, (hub_scenery.SLOT_SIZE,) * 2)
            self.assertGreaterEqual(piece.rect.width, 10)
            self.assertEqual(piece.rect.center, tuple(slots[trial_id]))
            self.assertTrue(art.body.rect.contains(piece.rect))
            images.append(pygame.image.tobytes(piece.image, "RGBA"))
            # Внутри — настоящий рисунок: много разных цветов и непрозрачные углы плитки.
            colors = {tuple(piece.image.get_at((x, y))) for x in range(piece.image.get_width()) for y in range(piece.image.get_height())}
            self.assertGreaterEqual(len(colors), 8, trial_id)
            self.assertEqual(piece.image.get_at((piece.image.get_width() // 2, piece.image.get_height() // 2)).a, 255)
        self.assertEqual(len(set(images)), 3)
        for a, b in itertools.combinations(art.fragments.values(), 2):
            self.assertFalse(a.rect.inflate(2, 2).colliderect(b.rect), "плитки налезают друг на друга")
        # Плитки лежат на столешнице: центры внутри её эллипса.
        cx, cy = hub_scenery.TABLE_CENTER
        for x, y in slots.values():
            half = hub_scenery.SLOT_SIZE / 2
            for dx, dy in ((-half, -half), (half, -half), (-half, half), (half, half)):
                self.assertLess(((x + dx - cx) / hub_scenery.TABLE_RX) ** 2 + ((y + dy - cy) / hub_scenery.TABLE_RY) ** 2, 1.0)

    def test_complete_table_differs_clearly_from_incomplete(self) -> None:
        def render(*done: str) -> bytes:
            hub = self.hub(*done)
            hub.update(0.3)
            canvas = pygame.Surface(config.LOGICAL_SIZE)
            hub.draw(canvas)  # без слоя окна: всё на холсте
            area = hub_scenery.table().body.rect
            return pygame.image.tobytes(canvas.subsurface(area), "RGB")

        empty, two, three = render(), render("sushi", "forms"), render(*TRIALS)
        self.assertNotEqual(empty, two)
        self.assertNotEqual(two, three)
        differing = sum(a != b for a, b in zip(two, three))
        self.assertGreater(differing, 200)  # золотая вставка и новая плитка — заметная разница

    def test_new_fragment_sparkles_briefly_once(self) -> None:
        hub = self.hub()
        hub.update(1.0)
        self.assertEqual(hub._placed_at, {})
        hub.progress.complete("forms")
        hub.update(DT)
        self.assertEqual(set(hub._placed_at), {"forms"})
        placed = hub._placed_at["forms"]
        hub.update(3.0)
        self.assertEqual(hub._placed_at, {"forms": placed})  # время искр не обновляется заново
        early = HubScene(hub.progress)  # уже собранные при входе искр не дают
        early.update(0.5)
        self.assertEqual(early._placed_at, {})

    def test_mosaic_still_opens_only_with_all_fragments(self) -> None:
        for done in ((), ("sushi",), ("sushi", "forms"), ("forms", "cakes")):
            manager = SceneManager()
            manager.push(Scene())
            manager.register("finale", Scene)
            hub = manager.push(self.hub(*done))
            hub.alice.set_position(*MOSAIC_CENTER)
            press_e(hub)
            self.assertIs(manager.current, hub, done)
        manager = SceneManager()
        manager.push(Scene())
        manager.register("finale", Scene)
        hub = manager.push(self.hub(*TRIALS))
        hub.alice.set_position(*MOSAIC_CENTER)
        press_e(hub)
        self.assertIsNot(manager.current, hub)
        self.assertEqual(MOSAIC_RADIUS, 12)


class DrawingTest(SceneryTestCase):
    def test_signs_are_window_text_with_the_names_from_the_task(self) -> None:
        hub = self.hub()
        layer = self.draw(hub)
        texts = {c.text: c for c in layer.commands if isinstance(c, TextCommand)}
        for name in ("СУШИ", "ФОРМУЛЯРЫ", "ТОРТИКИ"):
            self.assertIn(name, texts)
            self.assertEqual(texts[name].style, SIGN_STYLE)
        for portal in PORTALS:
            plaque = hub.plaque_rect(portal, hires=True)
            width = layer.text_metrics(SIGN_STYLE).width(portal.sign)
            self.assertLessEqual(width + 6, plaque.width, portal.sign)  # надпись помещается на табличке с полями
            self.assertTrue(pygame.Rect((0, 0), config.LOGICAL_SIZE).contains(plaque))
            self.assertGreaterEqual(SIGN_STYLE.size, 8)  # не мелкий текст

    def test_sign_text_survives_without_the_window_layer(self) -> None:
        hub = self.hub()
        hub.draw(self.canvas)
        for portal in PORTALS:
            plaque = portal.sign_rect
            before = pygame.image.tobytes(hub._background.subsurface(plaque), "RGB")
            self.assertNotEqual(pygame.image.tobytes(self.canvas.subsurface(plaque), "RGB"), before)

    def test_effects_depend_on_time_not_on_frame_rate(self) -> None:
        first, second = self.hub(), self.hub()
        first.update(2.0)
        for _ in range(240):
            second.update(1 / 120)
        self.assertAlmostEqual(first.time, second.time)
        for index, spot in enumerate(__import__("game.world.hub", fromlist=["FIREFLIES"]).FIREFLIES):
            self.assertEqual(first._firefly(index, spot), second._firefly(index, spot))

    def test_fireflies_stay_on_the_clearing_and_blink_slowly(self) -> None:
        from game.world.hub import FIREFLIES, HUD_HEIGHT, STATUS_TOP, WIDTH

        hub = self.hub()
        levels = set()
        for index, spot in enumerate(FIREFLIES):
            previous = None
            for step in range(0, 600):
                hub.time = step / 30
                x, y, level = hub._firefly(index, spot)
                self.assertTrue(4 <= x <= WIDTH - 4 and HUD_HEIGHT + 4 <= y <= STATUS_TOP - 4, (index, x, y))
                levels.add(level)
                if previous is not None:
                    self.assertLessEqual(abs(level - previous), 1, "мерцание слишком резкое")
                    self.assertLessEqual(math.dist((x, y), previous_position), 2.5)
                previous, previous_position = level, (x, y)
        self.assertGreater(len(levels), 2)

    def test_scene_draws_in_all_states_with_and_without_the_layer(self) -> None:
        for done in ((), ("forms",), TRIALS):
            hub = self.hub(*done)
            for step in range(40):
                hub.update(0.05)
                hub.draw(self.canvas)
                self.draw(hub)
        with tempfile.TemporaryDirectory() as empty:
            hub = HubScene(characters_dir=Path(empty))
            hub.update(0.1)
            self.draw(hub)

    def test_hires_pieces_are_reused_between_frames(self) -> None:
        hub = self.hub(*TRIALS)
        hub.update(0.2)
        first = {id(image) for image in self.images(self.draw(hub))}
        hub.update(0.7)
        second = {id(image) for image in self.images(self.draw(hub))}
        self.assertLess(len(first | second), len(first) + 12)  # новые картинки — лишь ступени свечения

    def test_alice_is_not_lost_against_the_scenery_at_her_doors(self) -> None:
        for portal in PORTALS:
            hub = self.hub()
            hub.alice.set_position(*portal.point)
            layer = self.draw(hub)
            commands = layer.commands
            alice = next(i for i, c in enumerate(commands) if isinstance(c, SpriteCommand) and c.rect == hub.alice.rect)
            tree = TREE_ART[portal.id]().piece.image
            # Алиса стоит поверх дерева, а не за ним: дерево (в фоне, он идёт первым) поверх неё не перерисовывается.
            self.assertFalse([c for c in commands if isinstance(c, SpriteCommand) and c.image is tree], portal.id)
            self.assertTrue(commands[0].opaque)
            sign = portal.sign_rect
            self.assertLessEqual(sign.bottom, hub.alice.rect.top + 8, portal.id)  # и почти не закрывает табличку


class GroundTest(SceneryTestCase):
    def test_ground_is_deterministic_and_cached(self) -> None:
        first = hub_ground.render_ground()
        second = hub_ground.render_ground()
        self.assertEqual(pygame.image.tobytes(first, "RGB"), pygame.image.tobytes(second, "RGB"))
        self.assertIs(self.hub()._background, self.hub()._background)

    def test_reserved_places_stay_plain_grass(self) -> None:
        hub = self.hub()
        for area in (LEO_AREA, CHUCHMEK_AREA):
            for x in range(area.left, area.right):
                for y in range(area.top, area.bottom):
                    self.assertIn(tuple(hub._background.get_at((x, y)))[:3], (GRASS_COLOR, GRASS_DARK_COLOR), (x, y))

    def test_each_door_has_a_mat_and_a_path_to_it(self) -> None:
        background = self._background()
        for portal in PORTALS:
            color = tuple(background.get_at((portal.point[0], portal.point[1] - 2)))[:3]
            self.assertNotIn(color, (GRASS_COLOR, GRASS_DARK_COLOR), portal.id)

    def _background(self) -> pygame.Surface:
        return self.hub()._background


if __name__ == "__main__":
    unittest.main()
