"""Клубника в кладовой: маленький NPC, которым управляет логика сцены, без отрисовки.

Клубника бегает со скоростью Алисы (speed задаёт сцена), поэтому догоняют её не скоростью,
а маршрутом и пока она болтает. Цикл:
- бег (RUNNING): выбрать цель на свободном полу не ближе MIN_TRIP, проложить к ней путь по
  сетке кладовой (NavGrid) и бежать по нему; добежала — следующая цель. Если известно, где
  Алиса, цель берётся из «своей» части пола — куда клубника добежит раньше Алисы с запасом
  SAFE_MARGIN (два поиска в ширину по сетке): из нескольких случайных таких точек — дальняя от
  Алисы со случайной поправкой, поэтому клубника возвращается и туда, где уже была, и не всегда
  удаляется. Путь — кратчайший по той же сетке: все его точки тоже «свои», навстречу Алисе он
  не ведёт. Подбежала Алиса ближе SPOOK_RADIUS — новая цель, но не чаще раза в SPOOK_COOLDOWN.
  Ноги клубники того же размера, что у Алисы, и двигаются через тот же CollisionMap.move
  отрезками не длиннее 1 px: сквозь стеллажи не пройти даже при большом dt;
- через RUN_SECONDS (3–6 с) — остановка (TALKING). Если Алиса в этот миг ближе
  STOP_SAFE_DISTANCE по пути в обход стеллажей, клубника ещё бежит, но не дольше STOP_POSTPONE:
  остановка всё равно будет. Она стоит и говорит реплику из колоды (LineDeck: все по очереди
  в случайном порядке, без повторов подряд) и снова бежит к новой цели. Цели не нашлось или
  путь перегородило несколько раз подряд — тоже остановка, а потом новая цель;
- поймали (CAUGHT) — стоит, больше ничего не выбирает и не говорит.

Все случайности — из переданного random.Random: одинаковый seed — одинаковая погоня.
Работа за кадр ограничена (MAX_PHASES, MAX_PICKS_PER_STEP, предел A*): update не зацикливается.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from game.trials.cakes_maze import STRAWBERRY_SPAWN, PantryLayout

RUNNING = "running"
TALKING = "talking"
CAUGHT = "caught"

FIRST_RUN_SECONDS = (1.0, 1.8)  # первая реплика — пока Алиса ещё у двери
RUN_SECONDS = (3.0, 6.0)  # бег между остановками
TALK_SECONDS = (1.5, 2.0)  # сколько стоит и говорит (для коротких реплик)
TALK_PLAIN_CHARS = 26  # реплика длиннее — постоит чуть дольше, чтобы её успели прочитать
TALK_SECONDS_PER_CHAR = 0.03
STOP_SAFE_DISTANCE = 150  # останавливаться, когда путь Алисы до клубники длиннее, px
STOP_POSTPONE = 3.0  # дольше этого остановку не откладывает, с
SAFETY_CHECK_SECONDS = 0.2  # как часто проверять, можно ли уже остановиться
MIN_TRIP = 48  # цель не ближе, px: каждое решение даёт заметный пробег
SAFE_MARGIN = 4  # на сколько шагов сетки раньше Алисы клубника должна успеть к цели
TARGET_SAMPLES = 6  # случайных «своих» точек, из которых выбирается цель
TARGET_JITTER = 10  # случайная поправка к «дальности от Алисы», шагов сетки
MAX_TARGET_TRIES = 12  # без Алисы: случайных точек-кандидатов за раз
MAX_ROUTE_TRIES = 4  # без Алисы: из них — сколько раз прокладывать путь (A*)
SPOOK_RADIUS = 40  # Алиса ближе — клубника выбирает новую цель
SPOOK_COOLDOWN = 1.0  # но не чаще, с
MAX_PHASES = 8  # смен «бег ↔ остановка» за один update
MAX_PICKS_PER_STEP = 2  # новых маршрутов за один кусок бега
COLLISION_STEP = 1.0  # как у Character: отрезки не длиннее пикселя


class LineDeck:
    """Реплики в случайном порядке: пока не прозвучат все, ни одна не повторится, и одна и та же
    не звучит два раза подряд даже на стыке колод."""

    def __init__(self, lines: Sequence[str], rng: random.Random) -> None:
        if not lines:
            raise ValueError("клубнике нужна хотя бы одна реплика")
        self.lines = tuple(lines)
        self.rng = rng
        self._deck: list[str] = []
        self.last: str | None = None

    def next(self) -> str:
        if not self._deck:
            self._deck = list(self.lines)
            self.rng.shuffle(self._deck)
            if len(self._deck) > 1 and self._deck[-1] == self.last:
                self._deck[0], self._deck[-1] = self._deck[-1], self._deck[0]
        self.last = self._deck.pop()
        return self.last


class StrawberryChase:
    """Позиция, маршрут, таймеры и реплики клубники. (x, y) — точка под ногами, как у Character."""

    def __init__(
        self,
        layout: PantryLayout,
        speed: float,
        rng: random.Random,
        lines: Sequence[str],
        start: tuple[float, float] = STRAWBERRY_SPAWN,
        pursuer: tuple[float, float] | None = None,
    ) -> None:
        if not 0 < speed < math.inf:
            raise ValueError(f"скорость клубники должна быть положительной, а не {speed!r}")
        self.layout = layout
        self.collision = layout.collision()
        self.nav = layout.nav()
        if not self.collision.is_free(*start):
            raise ValueError(f"клубника не может появиться в {start}: там препятствие")
        self._cells = sorted(self.nav.free)  # порядок не зависит от устройства множества
        self.speed = float(speed)
        self.rng = rng
        self.x, self.y = float(start[0]), float(start[1])
        self.state = RUNNING
        self.path: list[tuple[float, float]] = []
        self.target: tuple[float, float] | None = None
        self.line: str | None = None
        self.deck = LineDeck(lines, rng)
        self.run_left = rng.uniform(*FIRST_RUN_SECONDS)
        self.talk_left = 0.0
        self.postponed = 0.0  # сколько уже откладывает остановку
        self.velocity = (0.0, 0.0)  # средняя скорость за последний update
        self.travelled = 0.0
        self.routes = 0  # сколько маршрутов проложено
        self.stops = 0
        self.lines_said: list[str] = []
        self.pursuer = pursuer  # где ноги Алисы (обновляется в update)
        self._spook_left = 0.0
        self._safety_check_left = 0.0
        self._choose_target()

    # --- Состояние ---

    @property
    def position(self) -> tuple[float, float]:
        return self.x, self.y

    @property
    def is_moving(self) -> bool:
        return self.state == RUNNING and bool(self.path)

    # --- Шаг времени ---

    def update(self, dt: float, pursuer: tuple[float, float] | None = None) -> None:
        """Шаг времени. pursuer — где ноги Алисы: от неё клубника и убегает."""
        if not 0 <= dt < math.inf:
            raise ValueError(f"dt должен быть неотрицательным конечным числом, а не {dt!r}")
        if pursuer is not None:
            self.pursuer = pursuer
        start = (self.x, self.y)
        remaining = dt
        for _ in range(MAX_PHASES):
            if remaining <= 1e-9 or self.state == CAUGHT:
                break
            if self.state == RUNNING and self.run_left > 1e-9:
                step = min(remaining, self.run_left)
                self._run(step)
                remaining -= step
                self.run_left -= step
            elif self.state == RUNNING:
                # Пора остановиться: сразу, если Алиса далеко, иначе ещё немного бежит.
                if self.postponed >= STOP_POSTPONE - 1e-9 or self._safe_to_stop():
                    self._start_talk()
                    continue
                step = min(remaining, SAFETY_CHECK_SECONDS, STOP_POSTPONE - self.postponed)
                self._run(step)
                remaining -= step
                self.postponed += step
                self._safety_check_left -= step
            else:
                step = min(remaining, self.talk_left)
                remaining -= step
                self.talk_left -= step
                if self.talk_left <= 1e-9:
                    self._end_talk()
        if dt > 0:
            self.velocity = ((self.x - start[0]) / dt, (self.y - start[1]) / dt)

    def catch(self) -> bool:
        """Поймали: True только в первый раз. Дальше клубника стоит и молчит."""
        if self.state == CAUGHT:
            return False
        self.state = CAUGHT
        self.path, self.target, self.line = [], None, None
        self.run_left = self.talk_left = self.postponed = 0.0
        self.velocity = (0.0, 0.0)
        return True

    def _run(self, seconds: float) -> None:
        """Бежит seconds секунд по маршруту; маршрут кончился — новая цель (ограниченное число раз)."""
        budget = self.speed * seconds
        picks = 0
        self._spook_left = max(0.0, self._spook_left - seconds)
        pursuer = self.pursuer
        if pursuer is not None and self._spook_left <= 0 and math.dist(pursuer, (self.x, self.y)) < SPOOK_RADIUS:
            self._spook_left = SPOOK_COOLDOWN
            self.path = []  # Алиса рядом — новая цель
        while budget > 1e-9 and self.state == RUNNING:
            if not self.path:
                if picks >= MAX_PICKS_PER_STEP or not self._choose_target():
                    self._start_talk()  # некуда бежать — постоит, поговорит и попробует снова
                    return
                picks += 1
            tx, ty = self.path[0]
            dx, dy = tx - self.x, ty - self.y
            distance = math.hypot(dx, dy)
            if distance < 1e-6:
                self.path.pop(0)
                continue
            step = min(distance, budget)
            moved = self._move(dx / distance * step, dy / distance * step)
            budget -= step
            if moved < step - 1e-3:
                self.path = []  # маршрут перегородило — следующий проложим заново
            elif step >= distance - 1e-9:
                self.path.pop(0)

    def _move(self, dx: float, dy: float) -> float:
        """Сдвиг через столкновения кладовой отрезками не длиннее пикселя. Возвращает пройденное."""
        x0, y0 = self.x, self.y
        steps = max(1, math.ceil(math.hypot(dx, dy) / COLLISION_STEP))
        for _ in range(steps):
            self.x, self.y = self.collision.move(self.x, self.y, dx / steps, dy / steps)
        moved = math.hypot(self.x - x0, self.y - y0)
        self.travelled += moved
        return moved

    # --- Выбор цели ---

    def _choose_target(self) -> bool:
        """Новая цель и путь к ней; False — цели нет. Работа ограничена: два поиска в ширину
        по сетке (если известно, где Алиса) или MAX_ROUTE_TRIES путей A* из MAX_TARGET_TRIES
        случайных точек."""
        here = (self.x, self.y)
        start = self.nav.cell(*here)
        hunter = self.nav.cell(*self.pursuer) if self.pursuer is not None else None
        if start is not None and hunter is not None:
            found = self._escape_target(here, start, hunter)
        else:
            found = self._random_target(here)
        if found is None:
            self.target, self.path = None, []
            return False
        self.target, self.path = found[0], list(found[1])
        self.routes += 1
        return True

    def _escape_target(self, here, start, hunter):
        """Цель в «своей» части пола: туда клубника успевает раньше Алисы (см. описание модуля)."""
        mine, came = self.nav.steps_from(start)
        theirs, _ = self.nav.steps_from(hunter)
        min_steps = MIN_TRIP / self.nav.step
        own = sorted(cell for cell, steps in mine.items()
                     if steps >= min_steps and steps + SAFE_MARGIN < theirs.get(cell, math.inf))
        if not own:  # загнали в угол: хотя бы туда, где выигрыш у Алисы наибольший
            own = sorted((cell for cell in mine if mine[cell] >= 2),
                         key=lambda cell: (mine[cell] - theirs.get(cell, 0), cell))[:TARGET_SAMPLES]
        if not own:
            return None
        samples = [self.rng.choice(own) for _ in range(TARGET_SAMPLES)]
        best = max(samples, key=lambda cell: theirs.get(cell, 0) + self.rng.uniform(0, TARGET_JITTER))
        return self.nav.point(best), self.nav.route(here, came, best)

    def _random_target(self, here):
        """Без Алисы — просто случайная достижимая точка не ближе MIN_TRIP (путь A*)."""
        draws = [self.nav.point(self.rng.choice(self._cells)) for _ in range(MAX_TARGET_TRIES)]
        candidates = [point for point in draws if math.dist(point, here) >= MIN_TRIP]
        for point in candidates[:MAX_ROUTE_TRIES]:
            path = self.nav.find_path(here, point)
            if path:
                return point, path
        return None

    # --- Остановки ---

    def _safe_to_stop(self) -> bool:
        """Можно ли остановиться: Алиса не ближе STOP_SAFE_DISTANCE по пути (путь считается
        не чаще раза в SAFETY_CHECK_SECONDS)."""
        pursuer = self.pursuer
        if pursuer is None or math.dist(pursuer, (self.x, self.y)) >= STOP_SAFE_DISTANCE:
            return True
        if self._safety_check_left > 1e-9:
            return False
        self._safety_check_left = SAFETY_CHECK_SECONDS
        path = self.nav.find_path((self.x, self.y), pursuer)
        if path is None:
            return True  # Алиса сюда не дойдёт — можно и поболтать
        length = sum(math.dist(a, b) for a, b in zip([(self.x, self.y), *path], path))
        return length >= STOP_SAFE_DISTANCE

    def _start_talk(self) -> None:
        self.state = TALKING
        self.path, self.target = [], None
        self.postponed = 0.0
        self._safety_check_left = 0.0
        self.line = self.deck.next()
        self.lines_said.append(self.line)
        self.stops += 1
        extra = max(0, len(self.line) - TALK_PLAIN_CHARS) * TALK_SECONDS_PER_CHAR
        self.talk_left = self.rng.uniform(*TALK_SECONDS) + extra

    def _end_talk(self) -> None:
        self.state = RUNNING
        self.line = None
        self.talk_left = 0.0
        self.run_left = self.rng.uniform(*RUN_SECONDS)
        self._choose_target()
