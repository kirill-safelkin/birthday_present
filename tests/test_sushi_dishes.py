"""Проверки тарелки и готовых блюд испытания суши: цвета, геометрия, состояния и слой высокого разрешения."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.scenes import SceneManager  # noqa: E402
from game.graphics.fonts import TextFonts  # noqa: E402
from game.core.display import fit_viewport  # noqa: E402
from game.graphics.hires import HiResLayer, SpriteCommand, ViewTransform  # noqa: E402
from game.trials import sushi_dishes as dishes  # noqa: E402
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import (  # noqa: E402
    COOKING,
    REACTION,
    STATIONS,
    TABLE,
    TABLE_AREA,
    SushiTrialScene,
    draw_ingredient,
)
from game.world.hub import HubScene  # noqa: E402
from game.world.progress import GameProgress  # noqa: E402

STATION = {station.ingredient: station for station in STATIONS}
PLATE_SPOT = (TABLE.centerx, TABLE.top - 2)
PLATE = dishes.plate_rect(TABLE)
DIALOGUE_STEPS = 200
RECIPE_IDS = tuple(recipe.id for recipe in RECIPES)


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press_e(scene: SushiTrialScene) -> None:
    scene.handle_event(key(pygame.K_e, pygame.KSCAN_E))
    scene.handle_event(key(pygame.K_e, pygame.KSCAN_E, pygame.KEYUP))


def finish_dialogue(scene: SushiTrialScene) -> None:
    script = scene.dialogue.script if scene.dialogue is not None else None
    for _ in range(DIALOGUE_STEPS):
        if scene.dialogue is None or scene.dialogue.script is not script:
            return
        scene.handle_event(key(pygame.K_RETURN))
        scene.handle_event(key(pygame.K_RETURN, event_type=pygame.KEYUP))
    raise AssertionError("диалог не заканчивается")


def take(scene: SushiTrialScene, ingredient: str) -> None:
    scene.alice.set_position(*STATION[ingredient].point)
    press_e(scene)


def place(scene: SushiTrialScene) -> None:
    scene.alice.set_position(*PLATE_SPOT)
    press_e(scene)


def bring(scene: SushiTrialScene, ingredient: str) -> None:
    take(scene, ingredient)
    place(scene)


def luminance(color) -> float:
    r, g, b = color[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def colors_in(surface: pygame.Surface, rect: pygame.Rect) -> set[tuple[int, int, int]]:
    return {tuple(surface.get_at((x, y)))[:3] for x in range(rect.left, rect.right) for y in range(rect.top, rect.bottom)}


def plate_bytes(canvas: pygame.Surface) -> bytes:
    return pygame.image.tobytes(canvas.subsurface(TABLE_AREA), "RGB")


class SushiDishCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.progress = GameProgress()
        self.manager = SceneManager()
        self.manager.push(HubScene(self.progress))
        self.scene = self.manager.push(SushiTrialScene(self.progress))
        finish_dialogue(self.scene)  # вступление
        self.assertEqual(self.scene.phase, COOKING)

    def tearDown(self) -> None:
        pygame.quit()

    def render(self) -> pygame.Surface:
        self.scene.alice.set_position(20, 100)  # подальше от стола: он не заслоняет тарелку
        self.scene.time = 0.0  # сияние готовой тарелки пульсирует от времени сцены; сравниваем в одной фазе
        self.canvas.fill((0, 0, 0))
        self.scene.draw(self.canvas)
        return self.canvas

    def table_bytes(self) -> bytes:
        return plate_bytes(self.render())

    def cook(self, count: int) -> None:
        """Кладёт на тарелку первые count ингредиентов текущего заказа."""
        for ingredient in self.scene.orders.current.ingredients[:count]:
            bring(self.scene, ingredient)


class PlateTest(SushiDishCase):
    def test_plate_is_light_blue_not_white(self) -> None:
        for color in (dishes.PLATE_COLOR, dishes.PLATE_RIM_COLOR):
            r, g, b = color
            self.assertGreater(b - r, 40, color)  # голубой: синего заметно больше красного
            self.assertGreater(b, g)
            self.assertLess(r, 230)  # не белая
            self.assertGreater(luminance(color), 150)  # но и не тёмная: «мягкий» цвет
        self.assertLess(luminance(dishes.PLATE_EDGE_COLOR), luminance(dishes.PLATE_COLOR))  # контур темнее
        self.assertGreater(dishes.PLATE_EDGE_COLOR[2] - dishes.PLATE_EDGE_COLOR[0], 80)  # и насыщеннее
        self.assertGreater(luminance(dishes.PLATE_INNER_RIM_COLOR), luminance(dishes.PLATE_COLOR))  # ободок светлее

    def test_empty_plate_is_drawn_light_blue(self) -> None:
        canvas = self.render()
        self.assertEqual(tuple(canvas.get_at(PLATE.center))[:3], dishes.PLATE_COLOR)
        self.assertIsNone(self.scene.plate_dish())

    def test_plate_keeps_its_place_and_size(self) -> None:
        self.assertEqual(PLATE.size, (36, 10))
        self.assertEqual(PLATE.center, (TABLE.centerx, TABLE.centery - 1))
        self.assertTrue(TABLE.contains(PLATE))
        self.assertTrue(TABLE_AREA.contains(PLATE.move(0, 2)))  # тень тоже внутри заявленной области

    def test_rim_is_drawn_over_the_surface_in_the_right_order(self) -> None:
        canvas = self.render()
        left, top = PLATE.left, PLATE.top
        self.assertEqual(tuple(canvas.get_at((left, PLATE.centery)))[:3], dishes.PLATE_EDGE_COLOR)  # контур сверху
        self.assertEqual(tuple(canvas.get_at((PLATE.centerx, top)))[:3], dishes.PLATE_EDGE_COLOR)
        self.assertEqual(tuple(canvas.get_at((PLATE.centerx, PLATE.bottom - 1)))[:3], dishes.PLATE_EDGE_COLOR)
        well_top = PLATE.inflate(-6, -4).top
        self.assertEqual(tuple(canvas.get_at((PLATE.centerx, well_top)))[:3], dishes.PLATE_INNER_RIM_COLOR)
        self.assertEqual(tuple(canvas.get_at((PLATE.centerx, well_top + 1)))[:3], dishes.PLATE_COLOR)
        # От края к центру: контур → край → светлый ободок → поверхность.
        row = [tuple(canvas.get_at((x, PLATE.centery)))[:3] for x in range(PLATE.left, PLATE.centerx)]
        order = [row.index(color) for color in (dishes.PLATE_EDGE_COLOR, dishes.PLATE_RIM_COLOR,
                                               dishes.PLATE_INNER_RIM_COLOR, dishes.PLATE_COLOR)]
        self.assertEqual(order, sorted(order))
        self.assertEqual(len(set(order)), 4)

    def test_shadow_lies_under_the_plate(self) -> None:
        canvas = self.render()
        self.assertEqual(tuple(canvas.get_at((PLATE.centerx, PLATE.bottom)))[:3], dishes.PLATE_SHADOW_COLOR)

    def test_rice_stands_out_against_the_plate(self) -> None:
        self.assertGreaterEqual(luminance(dishes.RICE_COLOR) - luminance(dishes.PLATE_COLOR), 25)
        bring(self.scene, "rice")
        canvas = self.render()
        center = (PLATE.centerx, PLATE.centery - 2)
        rice = tuple(canvas.get_at(center))[:3]
        self.assertIn(rice, {(250, 250, 246), dishes.RICE_COLOR})
        self.assertGreaterEqual(luminance(rice) - luminance(dishes.PLATE_COLOR), 25)
        self.assertIn(dishes.FOOD_SHADOW_COLOR, colors_in(canvas, PLATE))  # и тень отделяет рис от поверхности

    def test_rim_survives_items_and_dishes(self) -> None:
        empty = self.render()
        edge = [(x, y) for x in range(PLATE.left, PLATE.right) for y in range(PLATE.top, PLATE.bottom)
                if tuple(empty.get_at((x, y)))[:3] == dishes.PLATE_EDGE_COLOR]
        self.assertGreater(len(edge), 40)
        left_and_right = [point for point in edge if point[0] < PLATE.left + 3 or point[0] >= PLATE.right - 3]
        self.cook(2)  # нигири собрано
        canvas = self.render()
        for point in left_and_right:  # края тарелки не закрыты ни ингредиентами, ни блюдом
            self.assertEqual(tuple(canvas.get_at(point))[:3], dishes.PLATE_EDGE_COLOR, point)


class DishGeometryTest(unittest.TestCase):
    def draw(self, recipe_id: str) -> pygame.Surface:
        surface = pygame.Surface(config.LOGICAL_SIZE, pygame.SRCALPHA)
        dishes.draw_dish(surface, recipe_id, PLATE.center)
        return surface

    def test_every_recipe_has_a_dish_and_nothing_else(self) -> None:
        self.assertEqual(set(dishes.DISH_DRAWERS), set(RECIPE_IDS))

    def test_dish_is_compact_and_inside_the_drawn_area(self) -> None:
        for recipe_id in RECIPE_IDS:
            with self.subTest(recipe=recipe_id):
                bounds = self.draw(recipe_id).get_bounding_rect()
                self.assertTrue(TABLE_AREA.contains(bounds), bounds)
                self.assertLessEqual(bounds.width, PLATE.width)
                self.assertLessEqual(bounds.height, 14)
                self.assertLessEqual(bounds.bottom, PLATE.bottom)  # не свисает с тарелки вниз
                self.assertLessEqual(abs(bounds.centerx - PLATE.centerx), 1)  # по центру

    def test_nigiri_is_rice_with_salmon_on_top(self) -> None:
        surface = self.draw("nigiri_salmon")
        colors = colors_in(surface, surface.get_rect())
        self.assertTrue({dishes.SALMON_COLOR, dishes.SALMON_STREAK_COLOR, dishes.RICE_COLOR} <= colors)
        self.assertFalse({dishes.NORI_COLOR, dishes.CUCUMBER_COLOR, dishes.AVOCADO_COLOR} & colors)
        salmon = [y for y in range(surface.get_height()) for x in range(surface.get_width())
                  if tuple(surface.get_at((x, y)))[:3] == dishes.SALMON_COLOR]
        rice = [y for y in range(surface.get_height()) for x in range(surface.get_width())
                if tuple(surface.get_at((x, y)))[:3] == dishes.RICE_COLOR]
        self.assertLess(sum(salmon) / len(salmon), sum(rice) / len(rice))  # лосось выше риса
        self.assertGreaterEqual(len(salmon), 60)  # ломтик, а не точка
        streaks = [1 for x in range(surface.get_width()) for y in range(surface.get_height())
                   if tuple(surface.get_at((x, y)))[:3] == dishes.SALMON_STREAK_COLOR]
        self.assertGreaterEqual(len(streaks), 6)  # несколько светлых линий

    def test_maki_is_nori_rice_and_cucumber_without_fish(self) -> None:
        surface = self.draw("maki_cucumber")
        colors = colors_in(surface, surface.get_rect())
        self.assertTrue({dishes.NORI_COLOR, dishes.RICE_COLOR, dishes.CUCUMBER_COLOR} <= colors)
        self.assertFalse({dishes.SALMON_COLOR, dishes.AVOCADO_COLOR} & colors)

    def test_roll_has_nori_rice_salmon_and_avocado_apart(self) -> None:
        surface = self.draw("roll_salmon_avocado")
        colors = colors_in(surface, surface.get_rect())
        self.assertTrue({dishes.NORI_COLOR, dishes.RICE_COLOR, dishes.SALMON_COLOR, dishes.AVOCADO_COLOR} <= colors)
        self.assertNotIn(dishes.CUCUMBER_COLOR, colors)
        self.assertNotEqual(dishes.SALMON_COLOR, dishes.AVOCADO_COLOR)
        self.assertGreater(abs(dishes.SALMON_COLOR[0] - dishes.AVOCADO_COLOR[0]), 100)  # оранжевый и зелёный

    def test_three_dishes_look_different(self) -> None:
        images = {pygame.image.tobytes(self.draw(recipe_id), "RGBA") for recipe_id in RECIPE_IDS}
        self.assertEqual(len(images), 3)

    def test_maki_shows_cross_sections(self) -> None:
        surface = self.draw("maki_cucumber")
        # В центре каждого среза — огурец, вокруг него рис, а снаружи нори.
        for dx, dy in ((0, -3), (-7, 0), (7, 0)):
            x, y = PLATE.centerx + dx, PLATE.centery - 1 + dy
            self.assertEqual(tuple(surface.get_at((x, y)))[:3], dishes.CUCUMBER_CORE_COLOR)
            self.assertEqual(tuple(surface.get_at((x + 2, y)))[:3], dishes.RICE_COLOR)

    def test_sparks_live_for_the_effect_time_only(self) -> None:
        def sparks(progress: float) -> pygame.Rect:
            surface = pygame.Surface(config.LOGICAL_SIZE, pygame.SRCALPHA)
            dishes.draw_sparks(surface, PLATE.center, progress)
            return surface.get_bounding_rect()

        self.assertGreater(sparks(0.5).width, 0)
        self.assertEqual(sparks(0.0).width, 0)  # ещё не вспыхнули
        self.assertEqual(sparks(1.0).width, 0)  # уже погасли
        self.assertEqual(sparks(2.0).width, 0)
        self.assertTrue(TABLE_AREA.contains(sparks(0.5)))
        self.assertTrue(0.2 <= dishes.FINISH_EFFECT_SECONDS <= 0.4)


class DishStateTest(SushiDishCase):
    def test_partial_orders_show_loose_ingredients(self) -> None:
        for recipe in RECIPES:  # заказы идут подряд: каждый начинается с чистой тарелки
            with self.subTest(recipe=recipe.id):
                previous = self.table_bytes()
                for ingredient in recipe.ingredients[:-1]:
                    bring(self.scene, ingredient)
                    self.assertIsNone(self.scene.plate_dish())
                    self.assertFalse(self.scene.orders.order_complete)
                    now = self.table_bytes()
                    self.assertNotEqual(now, previous)  # каждый ингредиент виден отдельно
                    previous = now
                bring(self.scene, recipe.ingredients[-1])
                self.assertEqual(self.scene.plate_dish(), recipe.id)
                finish_dialogue(self.scene)

    def test_each_dish_appears_only_after_its_own_order_is_done(self) -> None:
        dish_images = {}
        for index, recipe in enumerate(RECIPES):
            self.assertIsNone(self.scene.plate_dish(), recipe.id)
            for ingredient in recipe.ingredients[:-1]:
                bring(self.scene, ingredient)
                self.assertIsNone(self.scene.plate_dish(), (recipe.id, ingredient))
            bring(self.scene, recipe.ingredients[-1])
            self.assertEqual(self.scene.plate_dish(), recipe.id)
            self.assertEqual(self.scene.phase, REACTION)
            dish_images[recipe.id] = self.table_bytes()
            self.scene.update(1.0)  # вспышка кончилась — картинка устойчива
            self.assertEqual(self.table_bytes(), dish_images[recipe.id])
            finish_dialogue(self.scene)
            self.assertIsNone(self.scene.plate_dish())
            self.assertEqual(self.scene.orders.index, index + 1)
        self.assertEqual(len(set(dish_images.values())), 3)

    def test_finished_dish_replaces_the_loose_ingredients(self) -> None:
        self.cook(1)  # только рис
        rice_only = self.render().copy()
        bring(self.scene, "salmon")
        self.scene.update(1.0)
        done = self.render().copy()
        self.assertNotEqual(plate_bytes(rice_only), plate_bytes(done))
        # В готовом блюде нет двух отдельных кусочков: ингредиент-значок лосося из руки не рисуется.
        loose = pygame.Surface(config.LOGICAL_SIZE, pygame.SRCALPHA)
        draw_ingredient(loose, "salmon", (PLATE.centerx, PLATE.centery - 2), small=True)
        loose_rect = loose.get_bounding_rect()
        self.assertNotEqual(pygame.image.tobytes(done.subsurface(loose_rect), "RGB"),
                            pygame.image.tobytes(loose.subsurface(loose_rect), "RGB"))
        self.assertIn(dishes.SALMON_STREAK_COLOR, colors_in(done, PLATE.inflate(0, 8)))

    def test_wrong_ingredient_never_makes_a_dish(self) -> None:
        before = self.table_bytes()
        for ingredient in ("cucumber", "nori", "avocado"):  # не для нигири
            bring(self.scene, ingredient)
            self.assertEqual(self.scene.orders.held, ingredient)  # остался в руках
            self.assertIn("не для этого заказа", self.scene.toast)
            self.assertIsNone(self.scene.plate_dish())
            self.assertEqual(self.table_bytes(), before)
            self.scene.orders.put_back()
        bring(self.scene, "rice")
        bring(self.scene, "rice")  # повтор — тоже не засчитывается
        self.assertIn("уже на тарелке", self.scene.toast)
        self.assertIsNone(self.scene.plate_dish())
        self.assertEqual(self.scene.orders.plate, ("rice",))

    def test_dish_follows_the_orders_model(self) -> None:
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                bring(self.scene, ingredient)
                expected = recipe.id if self.scene.orders.order_complete else None
                self.assertEqual(self.scene.plate_dish(), expected)
                self.assertEqual(self.scene.plate_dish() is not None, set(self.scene.orders.plate) == set(recipe.ingredients))
            finish_dialogue(self.scene)
            self.assertIsNone(self.scene.plate_dish())
        self.assertTrue(self.scene.orders.all_done)
        self.assertIsNone(self.scene.plate_dish())  # заказов больше нет — и блюда нет

    def test_scene_does_not_decide_success_by_count_alone(self) -> None:
        # Нужное число ингредиентов, но не те — модель заказа не засчитывает, блюда нет.
        self.scene.orders._plate.extend(["cucumber", "nori"])  # заведомо неверный состав для нигири
        self.assertFalse(self.scene.orders.order_complete)
        self.assertIsNone(self.scene.plate_dish())

    def test_repeated_interaction_does_not_restart_the_completion(self) -> None:
        self.cook(2)
        self.assertEqual(self.scene.phase, REACTION)
        self.scene.update(0.2)
        age = self.scene._dish_age
        self.assertAlmostEqual(age, 0.2)
        # Во время реакции повара E лишь листает реплику: до тарелки взаимодействие не доходит.
        self.assertFalse(self.scene.interact())
        self.assertEqual(self.scene._dish_age, age)
        # Прямой вызов тоже ничего не перезапускает: тарелка заперта моделью заказа.
        self.scene.orders.held = "rice"
        self.scene._use_plate()
        self.assertEqual(self.scene._dish_age, age)
        self.assertEqual(self.scene.phase, REACTION)
        self.assertEqual(self.scene.orders.plate, ("rice", "salmon"))
        self.assertEqual(self.progress.fragments, 0)

    def test_next_order_prepares_a_clean_plate(self) -> None:
        empty = self.table_bytes()
        self.cook(2)
        self.assertNotEqual(self.table_bytes(), empty)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, COOKING)
        self.assertEqual(self.scene.orders.plate, ())
        self.assertIsNone(self.scene._dish_age)
        self.assertEqual(self.table_bytes(), empty)  # новая тарелка пуста, без остатков вспышки и блюда
        self.assertIn("Новый заказ", self.scene.toast)

    def test_fragment_is_given_only_after_the_final_line_and_only_once(self) -> None:
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                bring(self.scene, ingredient)
                self.assertEqual(self.progress.fragments, 0)
            self.assertIsNotNone(self.scene.plate_dish())
            self.assertEqual(self.progress.fragments, 0)  # блюдо готово, но награды ещё нет
            finish_dialogue(self.scene)
            self.assertEqual(self.progress.fragments, 0)
        finish_dialogue(self.scene)  # финальная реплика
        self.assertEqual(self.progress.completed, ("sushi",))
        self.assertEqual(self.progress.fragments, 1)
        second = self.manager.push(SushiTrialScene(self.progress))
        finish_dialogue(second)
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                bring(second, ingredient)
            finish_dialogue(second)
        finish_dialogue(second)
        self.assertEqual(self.progress.fragments, 1)  # повторное прохождение не начисляет второй раз


class FinishEffectTest(SushiDishCase):
    def test_flash_runs_by_dt_and_goes_out(self) -> None:
        self.cook(2)
        self.scene.update(0.0)
        start = self.table_bytes()
        self.assertEqual(self.scene._dish_age, 0.0)
        self.scene.update(dishes.FINISH_EFFECT_SECONDS / 2)
        middle = self.table_bytes()
        self.assertNotEqual(start, middle)
        self.assertIn(dishes.SPARK_COLOR, colors_in(self.canvas, TABLE_AREA))
        self.scene.update(dishes.FINISH_EFFECT_SECONDS)
        end = self.table_bytes()
        self.assertNotIn(dishes.SPARK_COLOR, colors_in(self.canvas, TABLE_AREA))
        self.scene.update(5.0)
        self.assertEqual(end, self.table_bytes())  # дальше блюдо не меняется (кроме сияния тарелки)

    def test_flash_does_not_block_the_cat_reaction(self) -> None:
        self.cook(2)
        self.assertEqual(self.scene.phase, REACTION)
        self.assertIsNotNone(self.scene.dialogue)  # реплика повара открывается сразу, вспышка её не ждёт
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, COOKING)  # и не задерживает переход к следующему заказу

    def test_no_flash_for_loose_ingredients_and_wrong_items(self) -> None:
        bring(self.scene, "rice")
        bring(self.scene, "cucumber")
        self.assertIsNone(self.scene._dish_age)
        self.render()
        self.assertNotIn(dishes.SPARK_COLOR, colors_in(self.canvas, TABLE_AREA))


class HiresTest(SushiDishCase):
    def setUp(self) -> None:
        super().setUp()
        pygame.display.set_mode((960, 540))
        self.fonts = TextFonts()

    def draw_hires(self) -> tuple[HiResLayer, pygame.Surface]:
        self.scene.alice.set_position(20, 100)
        layer, canvas = HiResLayer(self.fonts, strict=True), pygame.Surface(config.LOGICAL_SIZE)
        self.scene.draw(canvas, layer)  # строгий слой падает, если логическая графика вышла за область
        return layer, canvas

    def sprites(self, layer: HiResLayer) -> list[SpriteCommand]:
        return [command for command in layer.commands if isinstance(command, SpriteCommand)]

    def test_every_state_draws_strictly_without_extra_sprites(self) -> None:
        _, canvas = self.draw_hires()
        base = len(self.sprites(self.draw_hires()[0]))
        for recipe in RECIPES:
            for ingredient in recipe.ingredients:
                bring(self.scene, ingredient)
                for age in (0.0, 0.1, 0.2, 0.3, 1.0):
                    if self.scene._dish_age is not None:
                        self.scene._dish_age = age
                    layer, canvas = self.draw_hires()
                    self.assertEqual(len(self.sprites(layer)), base)  # блюдо не добавляет спрайтов
            finish_dialogue(self.scene)

    def test_canvas_matches_the_plain_path_on_the_table(self) -> None:
        # Двойного рисования нет: на холсте стол с тарелкой такой же, как без слоя высокого разрешения.
        for ingredient in (None, *self.scene.orders.current.ingredients):  # пустая, рис, рис и лосось (блюдо)
            if ingredient is not None:
                bring(self.scene, ingredient)
            plain = self.render().copy()
            _, canvas = self.draw_hires()
            self.assertEqual(plate_bytes(canvas), plate_bytes(plain))

    def test_window_render_shows_the_dish_at_both_sizes(self) -> None:
        empty_layer, empty_canvas = self.draw_hires()
        self.cook(2)
        self.scene.update(1.0)
        layer, canvas = self.draw_hires()
        self.assertNotEqual(plate_bytes(empty_canvas), plate_bytes(canvas))
        for size in ((960, 540), (1920, 1080), (1920, 1200)):
            with self.subTest(size=size):
                transform = ViewTransform(fit_viewport(size, config.LOGICAL_SIZE, config.INTEGER_SCALING))
                window = pygame.Surface(size)
                window.fill((1, 2, 3))
                pygame.transform.scale(canvas, transform.viewport.size, window.subsurface(transform.viewport))
                layer.render(window, transform)
                # Блюдо видно в окне: лососёвый цвет есть в области тарелки.
                area = transform.rect(PLATE.inflate(0, 8))
                self.assertIn(dishes.SALMON_COLOR, colors_in(window, area))
                again = pygame.Surface(size)
                again.fill((1, 2, 3))
                pygame.transform.scale(canvas, transform.viewport.size, again.subsurface(transform.viewport))
                layer.render(again, transform)
                self.assertEqual(pygame.image.tobytes(window, "RGB"), pygame.image.tobytes(again, "RGB"))


if __name__ == "__main__":
    unittest.main()
