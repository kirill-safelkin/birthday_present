"""Проверки центральной площади: движение Алисы, столкновения, порталы, Чучмек, переходы."""

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
from game.core.app import App  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.animation import IDLE, WALK, Direction  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story.hub_dialogue import (  # noqa: E402
    CHUCHMEK_TALK,
    CHUCHMEK_TALK_AGAIN,
    HUB_CHOICE_ID,
    HUB_JOIN_ID,
    LEO_LINES,
    PORTAL_NOT_READY,
    all_scripts,
)
from game.story.intro_dialogue import CHUCHMEK  # noqa: E402
from game.story.intro_scene import IntroScene  # noqa: E402
from game.world.hub import (  # noqa: E402
    CHUCHMEK_POSITION,
    CHUCHMEK_RADIUS,
    FLOWER_BEDS,
    GRASS_COLOR,
    GRASS_DARK_COLOR,
    HUB_SCENE,
    HUD_HEIGHT,
    LEO_FRAME,
    LEO_POINT,
    LEO_POSITION,
    LEO_RADIUS,
    MOSAIC_CENTER,
    MOSAIC_RADIUS,
    TREES,
    PORTALS,
    SPAWN,
    SPRITE_SIZE,
    STATUS_TOP,
    TRIAL_SCENES,
    WALK_BOUNDS,
    WALK_SPEED,
    HubScene,
)
from game.world.progress import GameProgress  # noqa: E402

DT = 1 / 60
PORTAL = {portal.id: portal for portal in PORTALS}


def key(key_code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=key_code, mod=0, unicode="", scancode=scancode)


def hold(hub: HubScene, keys, seconds: float, dt: float = DT) -> None:
    """Держит клавиши seconds секунд и отпускает. keys — коды или пары (код, скан-код)."""
    pairs = [k if isinstance(k, tuple) else (k, 0) for k in keys]
    for code, scancode in pairs:
        hub.handle_event(key(code, scancode))
    for _ in range(round(seconds / dt)):
        hub.update(dt)
    for code, scancode in pairs:
        hub.handle_event(key(code, scancode, pygame.KEYUP))


def press(hub: HubScene, code: int, scancode: int = 0) -> None:
    hub.handle_event(key(code, scancode))
    hub.handle_event(key(code, scancode, pygame.KEYUP))


def walk_to_portal(hub: HubScene, trial_id: str) -> None:
    """Доводит Алису от точки появления до портала клавишами, как игрок."""
    if trial_id == "forms":
        hold(hub, [pygame.K_UP], 3.0)
        return
    hold(hub, [pygame.K_UP], (SPAWN[1] - 95) / WALK_SPEED)
    hold(hub, [pygame.K_LEFT if trial_id == "sushi" else pygame.K_RIGHT], 3.0)


def walk_to_chuchmek(hub: HubScene) -> None:
    hold(hub, [pygame.K_UP], (SPAWN[1] - 100) / WALK_SPEED)
    hold(hub, [pygame.K_RIGHT], (CHUCHMEK_POSITION[0] - SPAWN[0]) / WALK_SPEED)


class HubTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.progress = GameProgress()
        self.hub = HubScene(self.progress)

    def tearDown(self) -> None:
        pygame.quit()


class CreationTest(HubTestCase):
    def test_alice_spawns_at_the_bottom_ready_to_walk(self) -> None:
        alice = self.hub.alice
        self.assertEqual((alice.x, alice.y), SPAWN)
        self.assertEqual(alice.direction, Direction.UP)
        self.assertEqual(alice.state, IDLE)
        self.assertGreater(SPAWN[1], WALK_BOUNDS.centery)  # внизу площади
        self.assertTrue(self.hub.collision.is_free(*SPAWN))
        self.assertEqual(alice.player.frame.get_size(), (SPRITE_SIZE, SPRITE_SIZE))
        self.assertIsNone(self.hub.dialogue)

    def test_alice_uses_manifest_frames_scaled_by_nearest_neighbour(self) -> None:
        sprites = load_character_sprites(CHARACTERS_DIR / "alice")
        source = sprites.frame("idle_up").image
        before = pygame.image.tobytes(source, "RGBA")
        frame = self.hub.alice.animations.get(IDLE, Direction.UP).frames[0]
        expected = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
        self.assertEqual(pygame.image.tobytes(frame, "RGBA"), pygame.image.tobytes(expected, "RGBA"))
        self.assertEqual(pygame.image.tobytes(source, "RGBA"), before)  # исходник не тронут

    def test_draft_walks_are_not_used(self) -> None:
        animations = self.hub.alice.animations
        # Ходьба вверх и вниз черновая: вместо неё — кадр ожидания того же направления.
        self.assertIs(animations.get(WALK, Direction.UP), animations.get(IDLE, Direction.UP))
        self.assertIs(animations.get(WALK, Direction.DOWN), animations.get(IDLE, Direction.DOWN))
        # Ходьба влево и вправо не черновая — настоящий цикл из четырёх кадров.
        self.assertEqual(len(animations.get(WALK, Direction.LEFT).frames), 4)
        self.assertEqual(len(animations.get(WALK, Direction.RIGHT).frames), 4)

    def test_chuchmek_stands_still_and_is_not_mirrored(self) -> None:
        chuchmek = self.hub.chuchmek
        self.assertEqual((chuchmek.x, chuchmek.y), CHUCHMEK_POSITION)
        source = load_character_sprites(CHARACTERS_DIR / "chuchmek").frame("idle").image
        expected = pygame.transform.scale(source, (SPRITE_SIZE, SPRITE_SIZE))
        self.assertEqual(pygame.image.tobytes(chuchmek.player.frame, "RGBA"), pygame.image.tobytes(expected, "RGBA"))
        self.hub.update(5.0)
        self.assertEqual((chuchmek.x, chuchmek.y), CHUCHMEK_POSITION)

    def test_missing_sprites_fall_back_to_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            hub = HubScene(characters_dir=Path(empty))
            hold(hub, [pygame.K_UP], 0.5)
            hub.draw(self.canvas)
            self.assertLess(hub.alice.y, SPAWN[1])

    def test_fragment_counter_shows_progress(self) -> None:
        self.assertEqual(self.hub.fragments_text(), "Фрагменты праздника: 0/3")
        self.progress.complete("forms")  # прямой вызов из теста: в игре фрагменты пока не выдаются
        self.assertEqual(self.hub.fragments_text(), "Фрагменты праздника: 1/3")


class MovementTest(HubTestCase):
    def test_four_directions_with_arrows_and_wasd_in_both_layouts(self) -> None:
        cases = [
            ((pygame.K_UP, 0), Direction.UP, (0, -1)),
            ((ord("ц"), pygame.KSCAN_W), Direction.UP, (0, -1)),
            ((pygame.K_LEFT, 0), Direction.LEFT, (-1, 0)),
            ((ord("ф"), pygame.KSCAN_A), Direction.LEFT, (-1, 0)),
            ((pygame.K_d, pygame.KSCAN_D), Direction.RIGHT, (1, 0)),
            ((pygame.K_DOWN, 0), Direction.DOWN, (0, 1)),
        ]
        for (code, scancode), direction, (sx, sy) in cases:
            with self.subTest(key=code):
                hub = HubScene()
                hub.alice.set_position(160, 106)  # середина площади: вокруг свободно
                hub.handle_event(key(code, scancode))
                self.assertEqual(hub.alice.direction, direction)
                self.assertEqual(hub.alice.state, WALK)
                for _ in range(15):
                    hub.update(DT)
                moved = (hub.alice.x - 160, hub.alice.y - 106)
                self.assertAlmostEqual(moved[0], sx * WALK_SPEED * 0.25)
                self.assertAlmostEqual(moved[1], sy * WALK_SPEED * 0.25)
                hub.handle_event(key(code, scancode, pygame.KEYUP))
                self.assertEqual(hub.alice.state, IDLE)  # отпустила — стоит и смотрит туда же
                self.assertEqual(hub.alice.direction, direction)
                position = (hub.alice.x, hub.alice.y)
                hub.update(1.0)
                self.assertEqual((hub.alice.x, hub.alice.y), position)

    def test_diagonal_speed_is_the_same(self) -> None:
        self.hub.alice.set_position(160, 106)
        self.hub.handle_event(key(pygame.K_UP))
        self.hub.handle_event(key(pygame.K_RIGHT))
        for _ in range(30):
            self.hub.update(DT)
        self.assertAlmostEqual(math.dist((160, 106), (self.hub.alice.x, self.hub.alice.y)), WALK_SPEED * 0.5)

    def test_movement_does_not_depend_on_frame_rate(self) -> None:
        results = []
        for dt in (1 / 144, 1 / 60, 1 / 30, 0.1):
            hub = HubScene()
            hold(hub, [pygame.K_UP, pygame.K_LEFT], 3.0, dt)  # упрётся в клумбу/портал и проскользит
            results.append((hub.alice.x, hub.alice.y))
        for x, y in results:
            self.assertAlmostEqual(x, results[0][0], delta=1.0)
            self.assertAlmostEqual(y, results[0][1], delta=1.0)

    def test_alice_never_leaves_the_square(self) -> None:
        for keys in ([pygame.K_LEFT], [pygame.K_RIGHT], [pygame.K_DOWN], [pygame.K_UP, pygame.K_LEFT],
                     [pygame.K_DOWN, pygame.K_RIGHT]):
            with self.subTest(keys=keys):
                hub = HubScene()
                for code in keys:
                    hub.handle_event(key(code))
                for _ in range(600):
                    hub.update(DT)
                    left, top, right, bottom = hub.collision.foot_box(hub.alice.x, hub.alice.y)
                    self.assertGreaterEqual(left, WALK_BOUNDS.left - 1e-6)
                    self.assertLessEqual(right, WALK_BOUNDS.right + 1e-6)
                    self.assertGreaterEqual(top, WALK_BOUNDS.top - 1e-6)
                    self.assertLessEqual(bottom, WALK_BOUNDS.bottom + 1e-6)
                    self.assertTrue(hub.collision.is_free(hub.alice.x, hub.alice.y))
                    rect = hub.alice.rect  # кадр целиком между полосами интерфейса
                    self.assertGreaterEqual(rect.top, HUD_HEIGHT)
                    self.assertLessEqual(rect.bottom, STATUS_TOP)
                    self.assertGreaterEqual(rect.left, 0)
                    self.assertLessEqual(rect.right, config.LOGICAL_SIZE[0])

    def test_obstacles_stop_alice(self) -> None:
        self.hub.alice.set_position(80, 92)
        hold(self.hub, [pygame.K_LEFT], 3.0)
        self.assertAlmostEqual(self.hub.alice.x, PORTAL["sushi"].rect.right + 6)  # уперлась в портал
        self.hub.alice.set_position(71, 170 - 40)  # над клумбой
        hold(self.hub, [pygame.K_DOWN], 3.0)
        self.assertAlmostEqual(self.hub.alice.y, 138)  # ноги на верхнем крае клумбы
        self.hub.alice.set_position(214, 110)  # под Чучмеком
        hold(self.hub, [pygame.K_UP], 3.0)
        self.assertGreaterEqual(self.hub.alice.y - 6, 81 - 1e-6)  # сквозь Чучмека не проходит

    def test_diagonal_against_a_wall_slides_instead_of_sticking(self) -> None:
        # Сбоку от портала суши: влево упирается, вверх скользит вдоль боковой грани.
        self.hub.alice.set_position(46, 98)
        hold(self.hub, [pygame.K_LEFT, pygame.K_UP], 0.5)
        self.assertEqual(self.hub.alice.x, PORTAL["sushi"].rect.right + 6)
        self.assertLess(self.hub.alice.y, 98 - 15)  # за полсекунды заметно поднялась вдоль грани
        # Под порталом: вверх упирается, влево скользит вдоль нижней грани.
        self.hub.alice.set_position(46, 120)
        hold(self.hub, [pygame.K_LEFT, pygame.K_UP], 1.5)
        self.assertEqual(self.hub.alice.y, PORTAL["sushi"].rect.bottom + 6)
        self.assertLess(self.hub.alice.x, 30)
        self.assertTrue(self.hub.collision.is_free(self.hub.alice.x, self.hub.alice.y))

    def test_keys_released_stop_movement(self) -> None:
        hold(self.hub, [pygame.K_UP], 0.5)
        y = self.hub.alice.y
        self.hub.update(2.0)
        self.assertEqual(self.hub.alice.y, y)
        self.assertFalse(self.hub.alice.is_moving)


class PortalTest(HubTestCase):
    def test_each_portal_is_reachable_on_foot_and_shows_its_prompt(self) -> None:
        for trial_id, name in (("sushi", "Суши"), ("forms", "Формуляры"), ("cakes", "Торты")):
            with self.subTest(trial=trial_id):
                hub = HubScene()
                walk_to_portal(hub, trial_id)
                target = hub.nearby()
                self.assertIsNotNone(target)
                self.assertEqual((target.kind, target.target), ("portal", trial_id))
                self.assertEqual(hub.status_text(), f"{name}   E — войти")

    def test_nothing_happens_far_from_portals(self) -> None:
        self.assertIsNone(self.hub.nearby())
        press(self.hub, pygame.K_e, pygame.KSCAN_E)
        self.assertIsNone(self.hub.dialogue)
        self.assertIsNone(self.hub.active_trial)
        self.assertEqual(self.hub.status_text(), "Стрелки/WASD — идти   E — действие")

    def test_portal_works_from_any_side_it_can_be_touched(self) -> None:
        # Вплотную к порталу — сверху, снизу или сбоку — подсказка та же, что у дорожки.
        for portal in PORTALS:
            rect = portal.rect
            spots = [(rect.centerx, rect.top), (rect.centerx, rect.bottom + 6),
                     (rect.left - 6, rect.centery + 3), (rect.right + 6, rect.centery + 3)]
            touched = 0
            for x, y in spots:
                if not self.hub.collision.is_free(x, y):
                    continue  # с этой стороны к порталу не подойти (край площади или дорожка)
                with self.subTest(trial=portal.id, spot=(x, y)):
                    self.hub.alice.set_position(x, y)
                    target = self.hub.nearby()
                    self.assertIsNotNone(target)
                    self.assertEqual((target.kind, target.target), ("portal", portal.id))
                    touched += 1
            self.assertGreaterEqual(touched, 1)
        portal = PORTALS[0]  # а в паре шагов от портала — ничего
        self.hub.alice.set_position(portal.rect.centerx, portal.rect.top - 10)
        self.assertIsNone(self.hub.nearby())

    def test_interaction_radius(self) -> None:
        for portal in PORTALS:
            with self.subTest(trial=portal.id):
                hub = HubScene()
                x, y = portal.point
                hub.alice.set_position(x, y + portal.radius - 0.5)
                self.assertEqual(hub.nearby().target, portal.id)
                hub.alice.set_position(x, y + portal.radius + 1)
                self.assertIsNone(hub.nearby())

    def test_unready_portals_show_chuchmek_message_and_give_nothing(self) -> None:
        manager = SceneManager()
        base = manager.push(Scene())
        for trial_id in ("sushi", "forms", "cakes"):
            with self.subTest(trial=trial_id):
                hub = manager.push(HubScene(self.progress))
                walk_to_portal(hub, trial_id)
                press(hub, pygame.K_e, pygame.KSCAN_E)
                self.assertIs(manager.current, hub)  # переходить некуда — остаёмся на площади
                self.assertEqual(hub.active_trial, trial_id)
                self.assertIs(hub.dialogue.script, PORTAL_NOT_READY[trial_id])
                self.assertEqual(hub.dialogue.node.speaker, CHUCHMEK)
                self.assertIn("не готов", hub.dialogue.node.text)
                press(hub, pygame.K_RETURN)  # дописать
                press(hub, pygame.K_RETURN)  # закрыть
                self.assertIsNone(hub.dialogue)
                self.assertIn("пока не готов", hub.toast)  # испытание названо в сообщении интерфейса
                self.assertIn(PORTAL[trial_id].name, hub.toast)
                self.assertEqual(self.progress.completed, ())
                self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 0/3")
                manager.pop()
        self.assertIs(manager.current, base)

    def test_portal_messages_match_the_trials(self) -> None:
        self.assertIn("Кот-повар точит нож. Надеюсь, для суши", PORTAL_NOT_READY["sushi"].nodes["p_sushi"].text)
        self.assertIn("форму на разрешение входа", PORTAL_NOT_READY["forms"].nodes["p_forms"].text)
        self.assertIn("с тортами всё под контролем. Это тревожный знак", PORTAL_NOT_READY["cakes"].nodes["p_cakes"].text)

    def test_registered_trial_scene_will_be_opened(self) -> None:
        # Когда сцена испытания появится, портал откроет её через менеджер — без выдачи фрагмента.
        manager = SceneManager()
        manager.push(Scene())
        manager.register(TRIAL_SCENES["cakes"], Scene)
        hub = manager.push(HubScene(self.progress))
        walk_to_portal(hub, "cakes")
        press(hub, pygame.K_RETURN)  # Enter — тоже действие interact
        self.assertIsNot(manager.current, hub)
        self.assertIsNone(hub.dialogue)
        self.assertEqual(self.progress.completed, ())

    def test_repeated_interaction_does_not_break_state(self) -> None:
        walk_to_portal(self.hub, "forms")
        for _ in range(3):  # E открывает реплику, следующее E дописывает, ещё одно — закрывает
            press(self.hub, pygame.K_e, pygame.KSCAN_E)
        self.assertIsNone(self.hub.dialogue)
        for _ in range(4):
            press(self.hub, pygame.K_e, pygame.KSCAN_E)
        self.assertIsNotNone(self.hub.dialogue)  # можно открыть снова
        self.assertEqual(self.progress.completed, ())
        self.assertEqual(self.hub.active_trial, "forms")


class ChuchmekTest(HubTestCase):
    def test_talk_prompt_dialogue_and_control_returns(self) -> None:
        walk_to_chuchmek(self.hub)
        self.assertEqual(self.hub.nearby().kind, "chuchmek")
        self.assertEqual(self.hub.status_text(), "Чучмек   E — поговорить")
        press(self.hub, pygame.K_e, pygame.KSCAN_E)
        dialogue = self.hub.dialogue
        self.assertIs(dialogue.script, CHUCHMEK_TALK)
        shown = []
        while self.hub.dialogue is not None:
            shown.append(self.hub.dialogue.node.id)
            press(self.hub, pygame.K_RETURN)
            press(self.hub, pygame.K_RETURN)
        # Enter на вопросе выбирает первый ответ — совет о порталах; дальше общая реплика про мозаику.
        self.assertEqual(shown, ["h_welcome", "h_why", "h_because", HUB_CHOICE_ID, "h_where", "h_hungry", HUB_JOIN_ID])
        x = self.hub.alice.x
        hold(self.hub, [pygame.K_LEFT], 0.5)  # управление вернулось
        self.assertLess(self.hub.alice.x, x)

    def test_dialogue_texts(self) -> None:
        texts = [CHUCHMEK_TALK.nodes[node_id].text for node_id in ("h_welcome", "h_why", "h_because")]
        self.assertEqual(texts, [
            "Добро пожаловать на центральную площадь!",
            "Почему она центральная?",
            "Потому что если бы она была боковой, её пришлось бы искать.",
        ])
        choices = [choice.text for choice in CHUCHMEK_TALK.nodes[HUB_CHOICE_ID].choices]
        self.assertEqual(choices, ["С какого испытания лучше начать?", "А что конкретно ты поручил Лео?"])
        self.assertIn("Слева суши, справа торты", CHUCHMEK_TALK.nodes["h_where"].text)
        self.assertIn("Если Лео улыбнётся — пункт плана утверждён", CHUCHMEK_TALK.nodes["h_leo"].text)
        self.assertIn("мозаике", CHUCHMEK_TALK.nodes[HUB_JOIN_ID].text)  # общая реплика — про финал

    def test_alice_does_not_walk_during_dialogue(self) -> None:
        walk_to_chuchmek(self.hub)
        self.hub.handle_event(key(pygame.K_RIGHT))  # шла и нажала E на ходу
        press(self.hub, pygame.K_e, pygame.KSCAN_E)
        self.assertFalse(self.hub.alice.is_moving)
        position = (self.hub.alice.x, self.hub.alice.y)
        hold(self.hub, [pygame.K_DOWN], 1.0)  # стрелки в диалоге не двигают Алису
        self.assertEqual((self.hub.alice.x, self.hub.alice.y), position)
        self.hub.handle_event(key(pygame.K_RIGHT, event_type=pygame.KEYUP))

    def test_backspace_closes_dialogue_but_not_the_square(self) -> None:
        manager = SceneManager()
        base = manager.push(Scene())
        hub = manager.push(HubScene())
        walk_to_chuchmek(hub)
        press(hub, pygame.K_e, pygame.KSCAN_E)
        press(hub, pygame.K_BACKSPACE)
        self.assertIsNone(hub.dialogue)
        self.assertIs(manager.current, hub)
        press(hub, pygame.K_BACKSPACE)  # без реплики — назад к предыдущей сцене
        self.assertIs(manager.current, base)

    def test_alice_stands_above_dialogue_box_wherever_she_can_talk(self) -> None:
        box = DialogueBox()
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in all_scripts() for node in script.nodes.values())
        lowest_feet = [portal.point[1] + portal.radius for portal in PORTALS]
        lowest_feet.append(CHUCHMEK_POSITION[1] + 6 + CHUCHMEK_RADIUS)
        for feet in lowest_feet:
            self.assertLessEqual(feet, lowest_box)  # окно реплики не закрывает Алису


def talk(hub: HubScene, answer: int) -> list[str]:
    """Разговор с Чучмеком целиком: E у Чучмека, Enter по репликам, на вопросе — ответ answer."""
    press(hub, pygame.K_e, pygame.KSCAN_E)
    shown = []
    for _ in range(100):
        dialogue = hub.dialogue
        if dialogue is None:
            return shown
        shown.append(dialogue.node.id)
        press(hub, pygame.K_RETURN)  # дописать
        for _ in range(answer if hub.dialogue is not None and hub.dialogue.choices else 0):
            press(hub, pygame.K_DOWN)
        press(hub, pygame.K_RETURN)  # дальше или ответ
    raise AssertionError(f"разговор не заканчивается: {shown}")


class ChuchmekChoiceTest(HubTestCase):
    def test_both_answers_have_own_lines_and_join(self) -> None:
        expected = {
            0: [HUB_CHOICE_ID, "h_where", "h_hungry", HUB_JOIN_ID],
            1: [HUB_CHOICE_ID, "h_leo", "h_yawn", "h_commission", HUB_JOIN_ID],
        }
        for answer, tail in expected.items():
            with self.subTest(answer=answer):
                hub = HubScene(GameProgress())
                walk_to_chuchmek(hub)
                self.assertEqual(talk(hub, answer), ["h_welcome", "h_why", "h_because", *tail])
                self.assertIsNone(hub.dialogue)

    def test_second_talk_skips_the_welcome(self) -> None:
        walk_to_chuchmek(self.hub)
        talk(self.hub, 0)
        press(self.hub, pygame.K_e, pygame.KSCAN_E)
        self.assertIs(self.hub.dialogue.script, CHUCHMEK_TALK_AGAIN)
        self.assertEqual(self.hub.dialogue.node.id, "h_again")
        press(self.hub, pygame.K_BACKSPACE)
        self.assertEqual(talk(self.hub, 1), ["h_again", "h_leo", "h_yawn", "h_commission", HUB_JOIN_ID])

    def test_answers_change_nothing_but_the_lines(self) -> None:
        manager = SceneManager()
        manager.register(HUB_SCENE, lambda: self.hub)
        manager.push(HUB_SCENE)
        for answer in (0, 1):
            walk_to_chuchmek(self.hub)
            talk(self.hub, answer)
            self.assertEqual(self.progress.completed, ())  # ни фрагментов, ни открытого финала
            self.assertIs(manager.current, self.hub)  # и никакого перехода в испытание
            self.assertEqual(list(manager.stack), [self.hub])

    def test_space_does_not_answer_and_held_enter_answers_once(self) -> None:
        walk_to_chuchmek(self.hub)
        press(self.hub, pygame.K_e, pygame.KSCAN_E)
        for _ in range(3):  # приветствие, «почему центральная», ответ: дописать и дальше
            press(self.hub, pygame.K_SPACE)
            press(self.hub, pygame.K_SPACE)
        dialogue = self.hub.dialogue
        press(self.hub, pygame.K_SPACE)  # дописать вопрос
        self.assertEqual(dialogue.node.id, HUB_CHOICE_ID)
        self.assertTrue(dialogue.choices)
        for _ in range(3):
            press(self.hub, pygame.K_SPACE)  # пробел листает реплики, но ответ не выбирает
        self.assertEqual(dialogue.node.id, HUB_CHOICE_ID)
        self.assertEqual(dialogue.answers, {})
        press(self.hub, pygame.K_DOWN)
        self.hub.handle_event(key(pygame.K_RETURN))  # зажатый Enter: первое нажатие — ответ…
        self.assertEqual(dialogue.node.id, "h_leo")
        self.assertTrue(dialogue.is_typing)  # …и новая реплика начата с нуля, а не пролистана


class LeoTest(HubTestCase):
    def walk_to_leo(self, hub: HubScene) -> None:
        hold(hub, [pygame.K_UP], (SPAWN[1] - LEO_POINT[1]) / WALK_SPEED)
        hold(hub, [pygame.K_LEFT], (SPAWN[0] - LEO_POINT[0]) / WALK_SPEED)

    def test_sprite_is_the_manifest_frame_scaled_by_nearest_neighbour(self) -> None:
        frame = load_character_sprites(CHARACTERS_DIR / "leo").frame(LEO_FRAME).image
        source, image = self.hub.leo_frames()
        self.assertEqual(pygame.image.tobytes(source, "RGBA"), pygame.image.tobytes(frame, "RGBA"))
        expected = pygame.transform.scale(frame, (SPRITE_SIZE, SPRITE_SIZE))
        self.assertEqual(pygame.image.tobytes(image, "RGBA"), pygame.image.tobytes(expected, "RGBA"))
        self.assertEqual(self.hub.leo_rect().size, (SPRITE_SIZE, SPRITE_SIZE))

    def test_leo_is_drawn_in_his_basket(self) -> None:
        self.hub.draw(self.canvas)
        rect = self.hub.leo_rect()
        _, image = self.hub.leo_frames()
        # Пиксели спящего Лео над передней стенкой корзинки — его, а не фона.
        x, y = next((x, y) for y in range(SPRITE_SIZE) for x in range(SPRITE_SIZE)
                    if image.get_at((x, y)).a == 255 and rect.y + y < LEO_POSITION[1] - 8)
        point = (rect.x + x, rect.y + y)
        self.assertEqual(self.canvas.get_at(point)[:3], image.get_at((x, y))[:3])
        self.assertNotEqual(self.canvas.get_at(point), self.hub._background.get_at(point))

    def test_basket_does_not_change_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            root = Path(empty)
            for char_id in ("alice", "chuchmek"):  # всё, кроме Лео
                (root / char_id).symlink_to(CHARACTERS_DIR / char_id)
            without_leo = HubScene(characters_dir=root)
        self.assertIsNone(without_leo.leo_frames())
        self.assertEqual(self.hub.collision.bounds, without_leo.collision.bounds)
        self.assertEqual(self.hub.collision.obstacles, without_leo.collision.obstacles)
        self.assertTrue(self.hub.collision.is_free(*LEO_POSITION))  # корзинка — не препятствие
        self.assertTrue(self.hub.collision.is_free(*LEO_POINT))

    def test_basket_stays_off_paths_portals_beds_trees_and_mosaic(self) -> None:
        rect = self.hub.leo_rect().union(pygame.Rect(LEO_POSITION[0] - 17, LEO_POSITION[1] - 13, 34, 15))
        background = self.hub._background
        for x in range(rect.left, rect.right):
            for y in range(rect.top, rect.bottom):  # только трава: ни дорожек, ни мозаики, ни клумб
                self.assertIn(tuple(background.get_at((x, y)))[:3], (GRASS_COLOR, GRASS_DARK_COLOR), (x, y))
        for portal in PORTALS:
            self.assertFalse(rect.colliderect(portal.rect.inflate(8, 8)), portal.id)
            self.assertFalse(rect.colliderect(self.hub.plaque_rect(portal)), portal.id)
        for bed in FLOWER_BEDS:
            self.assertFalse(rect.colliderect(bed))
        for x, y in TREES:
            self.assertFalse(rect.colliderect(pygame.Rect(x - 10, y - 24, 21, 25)))
        self.assertGreater(math.dist(LEO_POSITION, MOSAIC_CENTER), 28 + 10)  # за краем мозаичного круга

    def test_leo_zone_does_not_steal_other_targets(self) -> None:
        points = [portal.point for portal in PORTALS]
        points += [MOSAIC_CENTER, (CHUCHMEK_POSITION[0], CHUCHMEK_POSITION[1] + 6)]
        for point in points:
            self.assertGreater(math.dist(point, LEO_POINT), LEO_RADIUS + MOSAIC_RADIUS, point)
        hub = HubScene()
        for point in points:
            hub.alice.set_position(*point)
            self.assertNotEqual(hub.nearby().kind, "leo", point)
        hub.alice.set_position(*LEO_POINT)
        self.assertEqual(hub.nearby().kind, "leo")
        self.assertEqual(hub.status_text(), "Лео   E — заглянуть в корзинку")

    def test_peek_shows_one_line_and_returns_control_without_progress(self) -> None:
        self.walk_to_leo(self.hub)
        self.assertEqual(self.hub.nearby().kind, "leo")
        seen = []
        for visit in range(len(LEO_LINES) + 1):
            press(self.hub, pygame.K_e, pygame.KSCAN_E)
            dialogue = self.hub.dialogue
            self.assertEqual(len(dialogue.script.nodes), 1)  # одна реплика, без выбора
            self.assertEqual(dialogue.node.speaker, "")  # говорит рассказчик, а не Лео
            seen.append(dialogue.node.text)
            press(self.hub, pygame.K_RETURN)  # дописать
            press(self.hub, pygame.K_RETURN)  # закрыть
            self.assertIsNone(self.hub.dialogue)
        self.assertEqual(seen, [*LEO_LINES, LEO_LINES[0]])  # по кругу, без повторов подряд
        self.assertEqual(self.progress.completed, ())
        self.assertEqual(self.hub.leo_visits, len(LEO_LINES) + 1)
        x = self.hub.alice.x
        hold(self.hub, [pygame.K_RIGHT], 0.3)  # управление вернулось
        self.assertGreater(self.hub.alice.x, x)

    def test_alice_walks_past_the_basket_and_leo_does_not_move(self) -> None:
        hub = HubScene()
        hub.alice.set_position(LEO_POSITION[0] - 30, LEO_POSITION[1] - 4)
        rect = hub.leo_rect()
        hold(hub, [pygame.K_RIGHT], 60 / WALK_SPEED)  # прямо сквозь место корзинки
        self.assertGreater(hub.alice.x, LEO_POSITION[0] + 20)
        self.assertEqual(hub.leo_rect(), rect)

    def test_missing_leo_sprites_leave_a_blanket_in_the_basket(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            hub = HubScene(characters_dir=Path(empty))
            self.assertIsNone(hub.leo_frames())
            hub.alice.set_position(*LEO_POINT)
            hub.draw(self.canvas)  # без падений
            press(hub, pygame.K_e, pygame.KSCAN_E)
            self.assertIsNotNone(hub.dialogue)


class DrawingTest(HubTestCase):
    def test_draws_everywhere_without_errors(self) -> None:
        for keys in ([pygame.K_UP], [pygame.K_UP, pygame.K_LEFT], [pygame.K_UP, pygame.K_RIGHT], [pygame.K_LEFT]):
            hub = HubScene()
            for code in keys:
                hub.handle_event(key(code))
            for _ in range(240):
                hub.update(DT)
                hub.draw(self.canvas)

    def test_texts_fit_on_screen(self) -> None:
        font = self.hub._font
        width = config.LOGICAL_SIZE[0]
        statuses = ["Стрелки/WASD — идти   E — действие", "Чучмек   E — поговорить"]
        statuses += [f"{portal.name}   E — войти" for portal in PORTALS]
        statuses += [f"Испытание «{portal.name}»: портал пока не готов" for portal in PORTALS]
        for text in statuses:
            self.assertLessEqual(font.size(text)[0], width - 8, text)
        self.assertLessEqual(font.size("Центральная площадь")[0] + font.size(self.hub.fragments_text())[0], width - 12)
        for portal in PORTALS:
            plaque = pygame.Rect((0, 0), font.size(portal.name)).inflate(6, 2)
            plaque.center = portal.sign_center
            self.assertTrue(pygame.Rect((0, 0), config.LOGICAL_SIZE).contains(plaque), portal.id)
            self.assertGreaterEqual(plaque.top, HUD_HEIGHT)


class Base(Scene):
    pass


class TransitionsTest(HubTestCase):
    def test_intro_leads_to_registered_hub(self) -> None:
        manager = SceneManager()
        base = manager.push(Base())
        manager.register(HUB_SCENE, lambda: HubScene(self.progress))
        intro = manager.push(IntroScene(next_scene=HUB_SCENE))
        intro.update(1000.0)  # заставки и паузы
        while not intro.completed:
            dialogue = intro.dialogue
            if dialogue is not None:
                intro.handle_event(key(pygame.K_RETURN))
            else:
                intro.update(0.5)
        hub = manager.current
        self.assertIsInstance(hub, HubScene)
        self.assertEqual(manager.stack, (base, hub))  # вступление заменено площадью, база под ней
        self.assertIs(hub.progress, self.progress)
        hold(hub, [pygame.K_UP], 0.5)  # управление сразу у Алисы
        self.assertLess(hub.alice.y, SPAWN[1])


class AppIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App(dev_mode=True)  # экран проверки и его клавиши

    def tearDown(self) -> None:
        pygame.quit()

    def send(self, *events: pygame.event.Event) -> None:
        for event in events:
            pygame.event.post(event)
        self.app._handle_events()

    def press(self, code: int, scancode: int = 0) -> None:
        self.send(key(code, scancode), key(code, scancode, pygame.KEYUP))

    def test_hub_is_registered_and_shares_progress(self) -> None:
        self.assertTrue(self.app.scenes.is_registered(HUB_SCENE))
        self.press(pygame.K_h, pygame.KSCAN_H)
        hub = self.app.scenes.current
        self.assertIsInstance(hub, HubScene)
        self.assertIs(hub.progress, self.app.progress)

    def test_h_works_in_russian_layout_and_backspace_returns(self) -> None:
        self.press(ord("р"), pygame.KSCAN_H)
        self.assertIsInstance(self.app.scenes.current, HubScene)
        self.assertIs(self.app.screen.hub, self.app.scenes.current)
        self.press(pygame.K_BACKSPACE)
        self.assertIs(self.app.scenes.current, self.app.screen)

    def test_debug_screen_is_frozen_and_hidden_while_hub_is_open(self) -> None:
        screen = self.app.screen
        self.press(pygame.K_h, pygame.KSCAN_H)
        timer = screen._fps_timer
        self.app.scenes.update(1.0)
        self.assertEqual(screen._fps_timer, timer)
        self.send(key(pygame.K_d, pygame.KSCAN_D))  # D на площади — шаг вправо, а не диалог
        self.assertIsNone(screen.dialogue)
        self.assertEqual(self.app.scenes.current.alice.direction, Direction.RIGHT)
        canvas = self.app.display.canvas
        self.app.scenes.draw(canvas)
        self.assertEqual(tuple(canvas.get_at((1, 1)))[:3], (44, 38, 58))  # полоса площади, не экран проверки

    def test_other_debug_keys_still_work_after_visiting_hub(self) -> None:
        self.press(pygame.K_h, pygame.KSCAN_H)
        self.press(pygame.K_BACKSPACE)
        screen = self.app.screen
        for code, scancode, kind in (
            (pygame.K_a, pygame.KSCAN_A, "animation_demo"),
            (pygame.K_d, pygame.KSCAN_D, "dialogue"),
            (pygame.K_p, pygame.KSCAN_P, "sprite_gallery"),
            (pygame.K_i, pygame.KSCAN_I, "intro"),
            (pygame.K_h, pygame.KSCAN_H, "hub"),
        ):
            with self.subTest(kind=kind):
                self.press(code, scancode)
                self.assertIsNotNone(getattr(screen, kind))
                self.press(pygame.K_BACKSPACE)
                self.assertIs(self.app.scenes.current, screen)

    def test_fullscreen_escape_and_window_close_on_hub(self) -> None:
        self.press(pygame.K_h, pygame.KSCAN_H)
        self.app.running = True
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.app.scenes.update(0.2)
        self.app.scenes.draw(self.app.display.canvas)
        self.app.display.present()
        self.press(pygame.K_F11)
        self.assertFalse(self.app.display.is_fullscreen)
        self.press(pygame.K_ESCAPE)
        self.assertFalse(self.app.running)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)

    def test_held_e_opens_portal_once(self) -> None:
        # Все порталы теперь ведут в испытания: зажатая E открывает одно испытание, и автоповтор
        # не пролистывает его первую реплику и не открывает портал повторно.
        self.press(pygame.K_h, pygame.KSCAN_H)
        hub = self.app.scenes.current
        walk_to_portal(hub, "cakes")
        depth = len(self.app.scenes.stack)
        self.send(key(pygame.K_e, pygame.KSCAN_E), key(pygame.K_e, pygame.KSCAN_E), key(pygame.K_e, pygame.KSCAN_E))
        self.assertEqual(len(self.app.scenes.stack), depth + 1)
        trial = self.app.scenes.current
        self.assertIsNotNone(trial.dialogue)
        self.assertTrue(trial.dialogue.is_typing)  # автоповтор не пролистал реплику


if __name__ == "__main__":
    unittest.main()
