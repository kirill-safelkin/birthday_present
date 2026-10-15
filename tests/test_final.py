"""Проверки финала: мозаика на площади, последняя страница, письмо, секрет подарка, титры, выход."""

import os

# Тестам не нужно настоящее окно: SDL рисует в память. Задаём до импорта Pygame,
# чтобы это работало при любом способе запуска, в том числе discover -s tests.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

import config  # noqa: E402
from game.core.app import App  # noqa: E402
from game.core.scenes import Scene, SceneManager  # noqa: E402
from game.dialogue.box import DialogueBox  # noqa: E402
from game.graphics.sprite_manifest import CHARACTERS_DIR, load_character_sprites  # noqa: E402
from game.story import final_dialogue as text  # noqa: E402
from game.story.final_scene import (  # noqa: E402
    ALICE_POSITION,
    ARRIVAL,
    ARRIVAL_SECONDS,
    CHUCHMEK_POSITION,
    CREDITS,
    CREDITS_SECONDS,
    CREDITS_SKIP_DELAY,
    DONE,
    END_INPUT_DELAY,
    GIFT,
    GIFT_REACTION,
    LETTER,
    PAUSE,
    PAUSE_SECONDS,
    SPRITE_SIZE,
    TALK,
    THE_END,
    FinalScene,
)
from game.story.intro_dialogue import ALICE, CHUCHMEK  # noqa: E402
from game.trials.cakes_maze import MAZE_ROUTE  # noqa: E402
from game.trials.cakes_scene import CHECK_ROW, ESCAPE_SECONDS  # noqa: E402
from game.trials.forms_scene import CABINETS, GOOSE_POSITION, SLOT_XS, SLOT_Y  # noqa: E402
from game.trials.sushi_orders import RECIPES  # noqa: E402
from game.trials.sushi_scene import STATIONS, TABLE as SUSHI_TABLE  # noqa: E402
from game.world.hub import (  # noqa: E402
    FINALE_SCENE,
    MOSAIC_CENTER,
    MOSAIC_RADIUS,
    PORTALS,
    SPAWN,
    WALK_SPEED,
    HubScene,
)
from game.world.progress import TRIALS, GameProgress  # noqa: E402

DT = 1 / 60
WIDTH, HEIGHT = config.LOGICAL_SIZE
PORTAL = {portal.id: portal.point for portal in PORTALS}


def key(code: int, scancode: int = 0, event_type: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(event_type, key=code, mod=0, unicode="", scancode=scancode)


def press(scene: Scene, code: int, scancode: int = 0) -> None:
    scene.handle_event(key(code, scancode))
    scene.handle_event(key(code, scancode, pygame.KEYUP))


def press_e(scene: Scene) -> None:
    press(scene, pygame.K_e, pygame.KSCAN_E)


def finish_dialogue(scene: Scene) -> list[str]:
    """Пролистывает текущий диалог клавишей Enter (только его, не следующий) и возвращает показанные реплики."""
    shown = []
    script = scene.dialogue.script if scene.dialogue is not None else None
    while scene.dialogue is not None and scene.dialogue.script is script:
        if len(shown) > 2 * len(script.nodes):  # сломанный диалог — провал теста, а не зависание
            raise AssertionError(f"диалог не заканчивается: {shown}")
        shown.append(scene.dialogue.node.id)
        press(scene, pygame.K_RETURN)  # дописать
        if scene.dialogue is not None and scene.dialogue.script is script:
            press(scene, pygame.K_RETURN)  # дальше
    return shown


def complete_progress(*trials: str) -> GameProgress:
    progress = GameProgress()
    for trial_id in trials:
        progress.complete(trial_id)
    return progress


def read_page(scene: FinalScene) -> None:
    """Одна страница письма: первое E проявляет её, второе — листает дальше."""
    press_e(scene)
    press_e(scene)


def to_letter(scene: FinalScene) -> None:
    press_e(scene)  # пропустить появление страницы
    finish_dialogue(scene)


def to_gift(scene: FinalScene) -> None:
    to_letter(scene)
    for _ in text.LETTER_PAGES:
        read_page(scene)
    scene.update(PAUSE_SECONDS + 0.01)


def to_credits(scene: FinalScene) -> None:
    to_gift(scene)
    read_page(scene)
    finish_dialogue(scene)


def to_the_end(scene: FinalScene) -> None:
    to_credits(scene)
    scene.update(CREDITS_SECONDS + 0.01)


def play_finale(scene: FinalScene) -> None:
    to_the_end(scene)
    scene.update(END_INPUT_DELAY + 0.01)
    press_e(scene)


class HubMosaicTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)

    def tearDown(self) -> None:
        pygame.quit()

    def hub_with(self, *trials: str, register: bool = True) -> tuple[SceneManager, HubScene]:
        progress = complete_progress(*trials)
        manager = SceneManager()
        manager.push(Scene())
        if register:
            manager.register(FINALE_SCENE, lambda: FinalScene(progress))
        hub = manager.push(HubScene(progress))
        return manager, hub

    def test_mosaic_is_closed_until_all_three_fragments(self) -> None:
        for trials in ((), ("sushi",), ("sushi", "forms"), ("forms", "cakes")):
            with self.subTest(trials=trials):
                manager, hub = self.hub_with(*trials)
                hub.alice.set_position(*MOSAIC_CENTER)
                target = hub.nearby()
                self.assertEqual((target.kind, target.target), ("mosaic", "finale"))
                self.assertEqual(hub.status_text(), f"Мозаика   нужны все фрагменты: {len(trials)}/3")
                for _ in range(3):  # и повторные нажатия ничего не открывают
                    press_e(hub)
                    self.assertIs(manager.current, hub)
                self.assertEqual(hub.toast, f"Мозаике не хватает фрагментов: {len(trials)}/3")
                self.assertEqual(hub.progress.completed, trials)

    def test_three_fragments_open_the_finale_only_by_the_players_hand(self) -> None:
        manager, hub = self.hub_with("sushi", "forms", "cakes")
        for _ in range(120):
            hub.update(DT)  # сам по себе финал не начинается
        self.assertIs(manager.current, hub)
        hub.alice.set_position(*MOSAIC_CENTER)
        self.assertEqual(hub.status_text(), "Мозаика   E — восстановить последнюю страницу")
        press(hub, pygame.K_RETURN)  # Enter — тоже interact
        finale = manager.current
        self.assertIsInstance(finale, FinalScene)
        self.assertIs(finale.progress, hub.progress)
        self.assertEqual(len(manager.stack), 3)

    def test_mosaic_is_reachable_on_foot_and_does_not_overlap_other_targets(self) -> None:
        _, hub = self.hub_with("sushi", "forms", "cakes")
        hub.handle_event(key(pygame.K_UP))
        for _ in range(round((SPAWN[1] - MOSAIC_CENTER[1]) / WALK_SPEED / DT)):
            hub.update(DT)
        hub.handle_event(key(pygame.K_UP, event_type=pygame.KEYUP))
        self.assertEqual(hub.nearby().kind, "mosaic")
        self.assertTrue(hub.collision.is_free(*MOSAIC_CENTER))
        for portal in PORTALS:
            self.assertGreater(abs(complex(*portal.point) - complex(*MOSAIC_CENTER)), portal.radius + MOSAIC_RADIUS)
        hub.alice.set_position(MOSAIC_CENTER[0], MOSAIC_CENTER[1] + MOSAIC_RADIUS + 1)
        self.assertIsNone(hub.nearby())

    def test_unregistered_finale_is_not_opened(self) -> None:
        manager, hub = self.hub_with("sushi", "forms", "cakes", register=False)
        hub.alice.set_position(*MOSAIC_CENTER)
        press_e(hub)
        self.assertIs(manager.current, hub)
        self.assertEqual(hub.toast, "Последняя страница пока не готова")

    def test_leaving_the_finale_keeps_progress_and_mosaic(self) -> None:
        manager, hub = self.hub_with("sushi", "forms", "cakes")
        hub.alice.set_position(*MOSAIC_CENTER)
        press_e(hub)
        to_letter(manager.current)
        press(manager.current, pygame.K_BACKSPACE)
        self.assertIs(manager.current, hub)
        self.assertEqual(hub.toast, "Последняя страница подождёт: E у мозаики")
        self.assertEqual(hub.progress.completed, ("sushi", "forms", "cakes"))
        press_e(hub)  # можно начать заново — и это снова один финал
        self.assertIsInstance(manager.current, FinalScene)
        self.assertEqual(manager.current.phase, ARRIVAL)
        self.assertEqual(sum(isinstance(scene, FinalScene) for scene in manager.stack), 1)

    def test_mosaic_shows_collected_fragments_and_glows(self) -> None:
        for trials in ((), ("forms",), ("sushi", "forms", "cakes")):
            _, hub = self.hub_with(*trials)
            hub.update(0.3)
            hub.draw(self.canvas)  # без ошибок при любом числе фрагментов
        x, y = MOSAIC_CENTER
        ring = {tuple(self.canvas.get_at((x + dx, y)))[:3] for dx in range(9, 14)}
        self.assertIn((250, 206, 108), ring)  # золотое кольцо при 3/3
        _, closed = self.hub_with("sushi", "forms")
        closed.draw(self.canvas)
        ring = {tuple(self.canvas.get_at((x + dx, y)))[:3] for dx in range(9, 14)}
        self.assertNotIn((250, 206, 108), ring)  # при 2/3 мозаика не светится


class FinaleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.canvas = pygame.Surface(config.LOGICAL_SIZE)
        self.progress = complete_progress("sushi", "forms", "cakes")
        self.manager = SceneManager()
        self.hub = self.manager.push(HubScene(self.progress))
        self.scene = self.manager.push(FinalScene(self.progress))

    def tearDown(self) -> None:
        pygame.quit()


class SequenceTest(FinaleTestCase):
    def test_page_restores_itself_then_chuchmek_speaks(self) -> None:
        self.assertEqual(self.scene.phase, ARRIVAL)
        self.assertIsNone(self.scene.dialogue)
        self.assertLess(self.scene.festive, 0.01)  # сначала пустая страница
        self.assertFalse(self.scene.symbols_assembled())
        self.scene.update(ARRIVAL_SECONDS * 0.8)
        self.assertTrue(self.scene.symbols_assembled())  # фрагменты стали символами
        self.assertGreater(self.scene.festive, 0.5)
        self.scene.update(ARRIVAL_SECONDS * 0.2 + 0.01)
        self.assertEqual(self.scene.phase, TALK)
        self.assertIs(self.scene.dialogue.script, text.FINALE_TALK)

    def test_chuchmek_does_not_know_how_fairy_tales_end(self) -> None:
        press_e(self.scene)  # появление можно не ждать
        shown = finish_dialogue(self.scene)
        said = [(text.FINALE_TALK.nodes[node_id].speaker, text.FINALE_TALK.nodes[node_id].text) for node_id in shown]
        self.assertEqual(said[:5], [
            (CHUCHMEK, "Поздравляю! Мы восстановили последнюю страницу."),
            (ALICE, "И чем заканчивается сказка?"),
            (CHUCHMEK, "Обычно свадьбой, королевством или моралью."),
            (ALICE, "А наша?"),
            (CHUCHMEK, "Я рассчитывал, что это будет прописано в документах."),
        ])
        self.assertEqual(self.scene.phase, LETTER)
        self.assertEqual(self.scene.page, 0)
        self.assertIsNone(self.scene.dialogue)  # письмо — не реплика персонажа

    def test_whole_order_of_screens(self) -> None:
        play_finale(self.scene)
        letter = [f"letter_{index}" for index in range(len(text.LETTER_PAGES))]
        # Enter на вопросе выбирает первый ответ; вторая ветка (f_upside_down) не показывается.
        talk = ["f_restored", "f_ending", "f_usually", "f_ours", "f_documents", "f_commission", "f_verdict",
                text.CREDIT_CHOICE_ID, "f_together", "f_backside"]
        self.assertEqual(self.scene.shown, [TALK, *talk, LETTER, *letter, PAUSE, GIFT, GIFT_REACTION, "g_appeal",
                                            CREDITS, THE_END, DONE])

    def test_letter_is_read_page_by_page_at_own_pace(self) -> None:
        to_letter(self.scene)
        for index in range(len(text.LETTER_PAGES)):
            with self.subTest(page=index):
                self.assertEqual(self.scene.phase, LETTER)
                self.assertEqual(self.scene.page, index)
                self.scene.update(60.0)  # время само страницы не листает
                self.assertEqual(self.scene.page, index)
                self.assertEqual(self.scene.hint(), "E — дальше")
                self.scene.draw(self.canvas)
                press_e(self.scene)
        self.assertEqual(self.scene.phase, PAUSE)

    def test_first_press_only_reveals_the_page(self) -> None:
        to_letter(self.scene)
        self.assertFalse(self.scene.page_revealed)
        self.assertEqual(self.scene.hint(), "")
        press(self.scene, pygame.K_SPACE)  # пробел — как в репликах
        self.assertTrue(self.scene.page_revealed)
        self.assertEqual(self.scene.page, 0)
        press(self.scene, pygame.K_SPACE)
        self.assertEqual(self.scene.page, 1)

    def test_pause_before_the_gift_cannot_be_skipped(self) -> None:
        to_letter(self.scene)
        for _ in text.LETTER_PAGES:
            read_page(self.scene)
        self.assertEqual(self.scene.phase, PAUSE)
        for code in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
            press(self.scene, code)
        self.scene.update(PAUSE_SECONDS - 0.1)
        self.assertEqual(self.scene.phase, PAUSE)  # тёплый момент успевает прозвучать
        self.assertEqual(self.scene.alice_pose, "happy_down_2")
        self.scene.update(0.2)
        self.assertEqual(self.scene.phase, GIFT)
        self.scene.update(100.0)  # и одним большим кадром не проскочить дальше
        self.assertEqual(self.scene.phase, GIFT)

    def test_credits_follow_the_gift_and_can_be_skipped_only_on_purpose(self) -> None:
        to_gift(self.scene)
        self.assertEqual(self.scene.phase, GIFT)
        read_page(self.scene)
        self.assertEqual(self.scene.phase, GIFT_REACTION)
        self.assertIn("F-17", self.scene.dialogue.node.text)
        finish_dialogue(self.scene)
        self.assertEqual(self.scene.phase, CREDITS)
        press_e(self.scene)  # сразу — нельзя: это могло быть «лишнее» нажатие
        self.assertEqual(self.scene.phase, CREDITS)
        self.scene.update(CREDITS_SKIP_DELAY)
        self.assertEqual(self.scene.hint(), "E — пропустить титры")
        press_e(self.scene)
        self.assertEqual(self.scene.phase, THE_END)

    def test_credits_end_by_themselves(self) -> None:
        to_credits(self.scene)
        self.scene.update(CREDITS_SECONDS - 0.1)
        self.assertEqual(self.scene.phase, CREDITS)
        self.scene.update(0.2)
        self.assertEqual(self.scene.phase, THE_END)

    def test_last_screen_closes_the_game_once(self) -> None:
        to_the_end(self.scene)
        self.assertEqual(self.scene.hint(), "")
        press_e(self.scene)  # подсказки ещё нет — и выход ещё не работает
        self.assertEqual(self.scene.phase, THE_END)
        self.assertFalse(self.manager.quit_requested)
        self.scene.update(END_INPUT_DELAY)
        self.assertEqual(self.scene.hint(), "Нажми E, чтобы выйти в реальный мир")
        press_e(self.scene)
        self.assertEqual(self.scene.phase, DONE)
        self.assertTrue(self.scene.completed)
        self.assertTrue(self.manager.quit_requested)
        shown = list(self.scene.shown)
        stack = self.manager.stack
        for code in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE, pygame.K_BACKSPACE):
            press(self.scene, code)  # больше ничего не запускается и не закрывается
        self.scene.update(10.0)
        self.assertEqual(self.scene.shown, shown)
        self.assertEqual(self.manager.stack, stack)
        self.assertEqual(self.scene.phase, DONE)

    def test_progress_is_only_shown_never_changed(self) -> None:
        before = self.progress.completed
        play_finale(self.scene)
        self.assertEqual(self.progress.completed, before)
        self.assertEqual(self.progress.fragments, 3)
        self.assertEqual(self.hub.fragments_text(), "Фрагменты праздника: 3/3")

    def test_backspace_returns_to_the_hub_at_any_stage(self) -> None:
        stages = {
            "появление": lambda scene: None,
            "разговор": lambda scene: press_e(scene),
            "письмо": to_letter,
            "пауза": lambda scene: (to_letter(scene), [read_page(scene) for _ in text.LETTER_PAGES]),
            "подарок": to_gift,
            "титры": to_credits,
            "последний экран": to_the_end,
        }
        for stage, prepare in stages.items():
            with self.subTest(stage=stage):
                progress = complete_progress(*TRIALS)
                manager = SceneManager()
                hub = manager.push(HubScene(progress))
                scene = manager.push(FinalScene(progress))
                prepare(scene)
                press(scene, pygame.K_BACKSPACE)
                self.assertIs(manager.current, hub)
                self.assertFalse(scene.completed)
                self.assertFalse(manager.quit_requested)
                self.assertEqual(progress.completed, TRIALS)


class TextTest(FinaleTestCase):
    def test_letter_speaks_to_alice_and_is_complete(self) -> None:
        letter = " ".join(text.LETTER_PAGES)
        self.assertTrue(text.LETTER_PAGES[0].startswith("Алиса, с днём рождения"))
        for phrase in ("тебе не нужно быть идеальной", "Я люблю тебя", "С днём рождения!", "Лео", "суши", "торт",
                       "гриб с планшетом", "ответственным отделом"):
            self.assertIn(phrase, letter)
        self.assertEqual(letter.count("Лео"), 1)  # о сыне — бережно и один раз, праздник — её
        self.assertIn("твой день", text.LETTER_PAGES[-1])
        self.assertEqual(text.LETTER_SIGNATURE, "Твой муж")
        words = re.findall(r"\w+", letter.lower())
        to_her = sum(word in ("ты", "тебя", "тебе", "тобой", "твой") for word in words)
        self.assertGreaterEqual(to_her, 6)  # к ней на «ты»
        self.assertNotIn("алиса любит", letter.lower())  # с ней говорят, а не рассказывают о ней

    def test_every_letter_page_fits_and_nothing_is_cut(self) -> None:
        for index, page in enumerate(text.LETTER_PAGES):
            with self.subTest(page=index):
                lines = self.scene._page_lines[index]
                self.assertLessEqual(len(lines), self.scene.max_letter_lines())
                words = re.sub(r"\s+", " ", " ".join(lines)).strip()
                self.assertEqual(words, re.sub(r"\s+", " ", page).strip())  # всё до последнего слова
        self.assertLessEqual(len(self.scene._gift_lines), self.scene.max_letter_lines())

    def test_gift_stays_a_secret(self) -> None:
        self.assertEqual(text.GIFT_TEXT, (
            "Я приготовил для тебя ещё один подарок. Что это — пока секрет.\n\n"
            "Доиграй до конца, и сразу после титров я отдам его тебе лично. Подсказок не будет.\n\n"
            "Чучмек уже пытался меня допросить и получил отказ с формуляром F-17."
        ))
        everything = " ".join([text.GIFT_TEXT, text.GIFT_TITLE, *text.LETTER_PAGES,
                               *(node.text for script in text.all_scripts() for node in script.nodes.values()),
                               *(line for _, line in text.CREDITS), *text.THE_END_LINES]).lower()
        # Ни намёка на содержимое: ни упаковки, ни предметов, ни поездок, ни цены.
        for hint in ("коробк", "внутри", "кольц", "билет", "сертификат", "поездк", "путешеств", "украшени",
                     "цветы", "букет", "конверт", "рублей", "размер", "цвет "):
            self.assertNotIn(hint, everything, hint)

    def test_credits_and_last_screen(self) -> None:
        credits = [line for kind, line in text.CREDITS if kind != "gap"]
        self.assertEqual(credits[0], "Алиса в стране Чучмека?!")
        for line in ("Для Алисы. С любовью", "Спасибо, что прошла эту сказку до конца"):
            self.assertIn(line, credits)
        self.assertIn("временно ответственный по непредсказуемости", " ".join(credits))
        self.assertEqual(" ".join(text.THE_END_LINES), "Конец сказки. Начало настоящего праздника.")
        self.assertEqual(text.EXIT_HINT, "Нажми E, чтобы выйти в реальный мир")

    def test_texts_fit_on_screen(self) -> None:
        sizes = {"title": self.scene._title_font, "line": self.scene._letter_font, "small": self.scene._font}
        for kind, line in text.CREDITS:
            if line:
                self.assertLessEqual(sizes[kind].size(line)[0], WIDTH - 8, line)
        for line in text.THE_END_LINES:
            self.assertLessEqual(self.scene._end_font.size(line)[0], WIDTH - 16, line)
        for line in (text.EXIT_HINT, "E — пропустить титры", "Мозаика   E — восстановить последнюю страницу",
                     "Получен фрагмент праздника! Теперь 3/3. Мозаика засветилась"):
            self.assertLessEqual(self.scene._font.size(line)[0], WIDTH - 8, line)
        lines = self.scene.credit_lines()
        self.assertLessEqual(lines[-1][2] + 12, HEIGHT - 18)  # титры целиком помещаются над подсказкой

    def test_dialogue_box_never_covers_alice_or_chuchmek(self) -> None:
        box = DialogueBox()
        lowest_box = min((box.layout(node).name_tab or box.layout(node).box).top
                         for script in text.all_scripts() for node in script.nodes.values())
        self.assertLessEqual(ALICE_POSITION[1], lowest_box)
        self.assertLessEqual(CHUCHMEK_POSITION[1], lowest_box)


class LookTest(FinaleTestCase):
    def test_sprites_come_from_manifests_without_mirroring(self) -> None:
        for who, pose in (("alice", "idle_right"), ("chuchmek", "idle")):
            sprites = load_character_sprites(CHARACTERS_DIR / who)
            expected = pygame.transform.scale(sprites.frame(pose).image, (SPRITE_SIZE, SPRITE_SIZE))
            actual = self.scene._actor_image(who)
            self.assertEqual(pygame.image.tobytes(actual, "RGBA"), pygame.image.tobytes(expected, "RGBA"), who)
        alice = {frame.id for frame in load_character_sprites(CHARACTERS_DIR / "alice").frames}
        chuchmek = {frame.id for frame in load_character_sprites(CHARACTERS_DIR / "chuchmek").frames}
        self.assertLessEqual(set(text.ALICE_POSES.values()) | {"idle_right", "idle_down", "happy_down_2"}, alice)
        self.assertLessEqual(set(text.CHUCHMEK_POSES.values()) | {"idle", "wink"}, chuchmek)

    def test_draws_every_screen(self) -> None:
        scene = self.scene
        for step in (0.2, 1.0, 2.5):
            scene.update(step)
            scene.draw(self.canvas)
        press_e(scene)
        scene.draw(self.canvas)
        finish_dialogue(scene)
        for _ in text.LETTER_PAGES:
            scene.update(0.25)
            scene.draw(self.canvas)
            read_page(scene)
        scene.draw(self.canvas)
        scene.update(PAUSE_SECONDS)
        scene.draw(self.canvas)
        read_page(scene)
        scene.draw(self.canvas)
        finish_dialogue(scene)
        for _ in range(3):
            scene.update(CREDITS_SECONDS / 3)
            scene.draw(self.canvas)
        scene.update(END_INPUT_DELAY)
        scene.draw(self.canvas)
        press_e(scene)
        scene.draw(self.canvas)

    def test_missing_sprites_use_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            scene = FinalScene(self.progress, characters_dir=Path(empty))
            scene.draw(self.canvas)
            manager = SceneManager()
            manager.push(scene)
            play_finale(scene)
            self.assertTrue(scene.completed)


def play_sushi(sushi: Scene) -> None:
    finish_dialogue(sushi)
    stations = {station.ingredient: station for station in STATIONS}
    for recipe in RECIPES:
        for ingredient in recipe.ingredients:
            sushi.alice.set_position(*stations[ingredient].point)
            press_e(sushi)
            sushi.alice.set_position(SUSHI_TABLE.centerx, SUSHI_TABLE.top - 2)
            press_e(sushi)
        finish_dialogue(sushi)
    finish_dialogue(sushi)


def play_forms(forms: Scene) -> None:
    finish_dialogue(forms)
    cabinet = {cabinet.section.id: cabinet.point for cabinet in CABINETS}
    for section in ("holidays", "requests", "permits"):
        forms.alice.set_position(*cabinet[section])
        press_e(forms)
        finish_dialogue(forms)
    for slot in (2, 0, 2, 1):
        forms.alice.set_position(SLOT_XS[slot], SLOT_Y)
        press_e(forms)
    forms.alice.set_position(GOOSE_POSITION[0] - 22, GOOSE_POSITION[1])
    press_e(forms)
    finish_dialogue(forms)
    finish_dialogue(forms)


def play_cakes(cakes: Scene) -> None:
    finish_dialogue(cakes)
    for row in (0, 4, 1, 3, CHECK_ROW):
        cakes.cursor = row
        press_e(cakes)
    finish_dialogue(cakes)
    cakes.update(ESCAPE_SECONDS + 0.1)
    finish_dialogue(cakes)
    cakes.alice.set_position(*MAZE_ROUTE[-1])
    press_e(cakes)
    finish_dialogue(cakes)
    finish_dialogue(cakes)


class AppIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.display.init()
        pygame.font.init()
        self.app = App(dev_mode=True)  # экран проверки и его клавиши
        self.app.running = True

    def tearDown(self) -> None:
        pygame.quit()

    def send(self, *events: pygame.event.Event) -> None:
        for event in events:
            pygame.event.post(event)
        self.app._handle_events()

    def press(self, code: int, scancode: int = 0) -> None:
        self.send(key(code, scancode), key(code, scancode, pygame.KEYUP))

    def stack_names(self) -> list[str]:
        return [type(scene).__name__ for scene in self.app.scenes.stack]

    def open_hub(self) -> HubScene:
        self.press(pygame.K_h, pygame.KSCAN_H)
        return self.app.scenes.current

    def enter_portal(self, hub: HubScene, trial_id: str) -> Scene:
        hub.alice.set_position(*PORTAL[trial_id])
        self.press(pygame.K_e, pygame.KSCAN_E)
        return self.app.scenes.current

    def collect_all(self, hub: HubScene) -> None:
        play_sushi(self.enter_portal(hub, "sushi"))
        play_forms(self.enter_portal(hub, "forms"))
        play_cakes(self.enter_portal(hub, "cakes"))

    def press_through_finale(self) -> None:
        """Финал целиком через приложение: только E, Enter и пробел — как игрок."""
        finale = self.app.scenes.current
        for _ in range(400):
            if finale.phase == DONE:
                return
            code = (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE)[len(finale.shown) % 3]
            if code == pygame.K_SPACE and finale.dialogue is not None and finale.dialogue.choices:
                code = pygame.K_e  # пробел только листает реплики: ответ игрок выбирает E или Enter
            self.press(code, pygame.KSCAN_E if code == pygame.K_e else 0)
            self.app._update(0.4)
        raise AssertionError(f"финал не закончился: {finale.phase}")

    def test_finale_is_registered(self) -> None:
        self.assertEqual(FINALE_SCENE, "finale")
        self.assertTrue(self.app.scenes.is_registered(FINALE_SCENE))

    def test_two_fragments_do_not_open_the_finale(self) -> None:
        hub = self.open_hub()
        play_sushi(self.enter_portal(hub, "sushi"))
        play_forms(self.enter_portal(hub, "forms"))
        hub.alice.set_position(*MOSAIC_CENTER)
        self.press(pygame.K_e, pygame.KSCAN_E)
        self.assertEqual(self.stack_names(), ["DebugScreen", "HubScene"])
        self.assertIn("2/3", hub.toast)

    def test_whole_ending_from_three_trials_to_closing_the_game(self) -> None:
        hub = self.open_hub()
        self.collect_all(hub)
        self.assertEqual(hub.fragments_text(), "Фрагменты праздника: 3/3")
        self.assertEqual(hub.toast, "Получен фрагмент праздника! Теперь 3/3. Мозаика засветилась")
        for _ in range(10):
            self.app._update(0.5)  # третий фрагмент сам финал не запускает
        self.assertEqual(self.stack_names(), ["DebugScreen", "HubScene"])
        hub.alice.set_position(*MOSAIC_CENTER)
        self.press(ord("у"), pygame.KSCAN_E)  # русская раскладка
        self.assertEqual(self.stack_names(), ["DebugScreen", "HubScene", "FinalScene"])
        finale = self.app.scenes.current
        self.assertIs(finale.progress, self.app.progress)
        self.press_through_finale()
        self.assertTrue(finale.completed)
        self.assertFalse(self.app.running)  # игра закрывается штатно
        self.assertEqual(self.stack_names(), ["DebugScreen", "HubScene", "FinalScene"])  # ничего лишнего не открылось
        self.assertEqual(self.app.progress.completed, ("sushi", "forms", "cakes"))
        self.assertIn("letter_4", finale.shown)
        self.assertLess(finale.shown.index("letter_4"), finale.shown.index(GIFT))
        self.assertLess(finale.shown.index(GIFT), finale.shown.index(CREDITS))
        self.assertLess(finale.shown.index(CREDITS), finale.shown.index(THE_END))

    def test_escape_f11_and_window_close_in_the_finale(self) -> None:
        hub = self.open_hub()
        self.collect_all(hub)
        hub.alice.set_position(*MOSAIC_CENTER)
        self.press(pygame.K_e, pygame.KSCAN_E)
        self.press(pygame.K_F11)
        self.assertTrue(self.app.display.is_fullscreen)
        self.app._update(0.5)
        self.app._draw()
        self.press(pygame.K_F11)
        self.assertFalse(self.app.display.is_fullscreen)
        self.press(pygame.K_ESCAPE)  # ESC — выход из игры в любой момент
        self.assertFalse(self.app.running)
        self.app.running = True
        self.send(pygame.event.Event(pygame.QUIT))
        self.assertFalse(self.app.running)

    def test_held_e_on_the_last_screen_does_not_skip_it(self) -> None:
        hub = self.open_hub()
        self.collect_all(hub)
        hub.alice.set_position(*MOSAIC_CENTER)
        self.press(pygame.K_e, pygame.KSCAN_E)
        finale = self.app.scenes.current
        to_the_end(finale)
        self.app._update(END_INPUT_DELAY + 0.1)
        self.send(key(pygame.K_SPACE))  # зажатый пробел: первое нажатие закрывает…
        self.send(key(pygame.K_SPACE), key(pygame.K_SPACE))  # …автоповтор ничего не добавляет
        self.assertEqual(finale.phase, DONE)
        self.assertFalse(self.app.running)

    def test_debug_screen_still_works_after_leaving_the_finale(self) -> None:
        hub = self.open_hub()
        self.collect_all(hub)
        hub.alice.set_position(*MOSAIC_CENTER)
        self.press(pygame.K_e, pygame.KSCAN_E)
        self.press(pygame.K_BACKSPACE)  # из финала — на площадь
        self.assertIs(self.app.scenes.current, hub)
        self.press(pygame.K_BACKSPACE)  # с площади — на экран проверки
        self.assertIs(self.app.scenes.current, self.app.screen)
        self.assertTrue(self.app.running)
        self.assertFalse(self.app.scenes.quit_requested)


if __name__ == "__main__":
    unittest.main()
