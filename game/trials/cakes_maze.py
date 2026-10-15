"""Вторая часть испытания тортов: захламлённая кладовая-библиотека, где носится клубника.

Только данные и расчёты, без отрисовки. Одна модель на всё: PantryLayout — список предметов
(стеллажи, стопки книг, коробки) с прямоугольниками оснований. По этим же прямоугольникам
сцена рисует кладовую, CollisionMap не пускает сквозь них Алису и клубнику, а NavGrid ищет
путь для клубники. Плоские бумаги на полу — отдельный список decor: по ним ходят.

Раскладка случайная, но ограниченная (generate_layout): предметы ставятся вразброс по сетке
в 2 px, каждый новый — не ближе MIN_GAP_X / MIN_GAP_Y к остальным и к стенам (или вплотную
к задней стене), а вход у двери (START_ZONE) и место, где появляется клубника (SPAWN_ZONE),
остаются пустыми.
Готовая раскладка проверяется: вся свободная часть комнаты связна для ног Алисы, предметов
достаточно и они не выстроились в ряд. Не получилось за ATTEMPTS попыток — берётся проверенный
запасной вариант FALLBACK_ITEMS. Одинаковый seed — одинаковая раскладка (для тестов).
"""

from __future__ import annotations

import heapq
import math
import random
from collections import deque
from dataclasses import dataclass, field

import pygame

from game.world.collision import FOOT_SIZE, CollisionMap

# Где могут стоять ноги Алисы и клубники. Сверху — задняя стена кладовой, снизу — полоса
# подсказок, слева — дверь из кондитерской, в которой стоит Чучмек.
MAZE_BOUNDS = pygame.Rect(40, 50, 270, 114)
MAZE_START = (58, 66)  # Алиса входит у двери
STRAWBERRY_SPAWN = (270, 124)  # клубника вбежала первой — в дальнюю часть комнаты
START_ZONE = pygame.Rect(MAZE_BOUNDS.left, MAZE_BOUNDS.top, 56, 54)  # у двери ничего не стоит
SPAWN_ZONE = pygame.Rect(0, 0, 44, 34)
SPAWN_ZONE.midbottom = (STRAWBERRY_SPAWN[0], STRAWBERRY_SPAWN[1] + 8)

# Самые узкие проходы между предметами и от предмета до стены: между соседями слева и справа
# (ноги Алисы шириной 12 px) и между соседями сверху и снизу (ноги высотой 6 px). Так она
# проходит с запасом, а не протискивается.
MIN_GAP_X = 20
MIN_GAP_Y = 14
NAV_STEP = 4  # шаг сетки, по которой клубника ищет путь, px
ATTEMPTS = 30  # попыток собрать раскладку, потом — запасной вариант
PLACE_TRIES = 60  # попыток поставить один предмет
MIN_ITEMS = 9
COVERAGE = (0.15, 0.32)  # доля пола под предметами

# Размеры оснований (ширина, высота) — диапазоны в логических пикселях, шаг 2 px.
SIZES = {
    "bookcase": ((42, 64), (14, 16)),  # широкий книжный стеллаж, видны корешки
    "tall_bookcase": ((14, 16), (40, 56)),  # стеллаж боком: длинный в глубину
    "books": ((14, 18), (12, 14)),  # стопка книг
    "cookbooks": ((14, 16), (12, 12)),  # стопка кулинарных книг
    "boxes": ((16, 20), (14, 16)),  # коробки
}
WALL_KINDS = {"bookcase"}  # что может стоять вплотную к задней стене
DECOR_KINDS = ("papers", "recipe")  # плоские листы на полу — по ним ходят


@dataclass(frozen=True)
class PantryItem:
    kind: str  # что нарисовать: см. SIZES и DECOR_KINDS
    rect: pygame.Rect  # основание предмета — им же проверяются столкновения


@dataclass(frozen=True)
class PantryLayout:
    """Раскладка кладовой: предметы-препятствия, плоский мусор на полу и откуда она взялась."""

    items: tuple[PantryItem, ...]
    decor: tuple[PantryItem, ...] = ()
    seed: int | None = None
    fallback: bool = False  # запасной вариант вместо случайной раскладки
    attempts: int = 0  # сколько попыток понадобилось
    _nav: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def obstacles(self) -> list[pygame.Rect]:
        return [item.rect for item in self.items]

    def collision(self, foot_size: tuple[int, int] = FOOT_SIZE) -> CollisionMap:
        """Столкновения кладовой. foot_size крупнее настоящего — чтобы проверить запас в проходах."""
        return CollisionMap(MAZE_BOUNDS, self.obstacles, foot_size)

    def nav(self, foot_size: tuple[int, int] = FOOT_SIZE) -> NavGrid:
        """Сетка проходимости для ног foot_size (считается один раз на раскладку)."""
        if foot_size not in self._nav:
            self._nav[foot_size] = NavGrid(self.collision(foot_size))
        return self._nav[foot_size]


# --- Проходимость и поиск пути ---


class NavGrid:
    """Точки сетки с шагом NAV_STEP, где ноги помещаются (CollisionMap.is_free), и путь между ними.

    Соседние точки соединены по горизонтали, вертикали и диагонали; по диагонали — только если
    свободны обе соседние по осям (угол стеллажа не срезается). Отрезок между соседями свободен
    целиком: ноги в двух соседних точках перекрываются, а предметы толще шага сетки.
    """

    def __init__(self, collision: CollisionMap, step: int = NAV_STEP) -> None:
        self.collision = collision
        self.step = step
        bounds = collision.bounds
        self.origin = (bounds.left, bounds.top)
        self.columns = bounds.width // step + 1
        self.rows = bounds.height // step + 1
        self.free = {
            (i, j)
            for i in range(self.columns)
            for j in range(self.rows)
            if collision.is_free(*self.point((i, j)))
        }
        # Соседи каждой точки — один раз: поиск пути идёт часто, сетка не меняется.
        self._links = {cell: tuple(self._find_neighbours(cell)) for cell in self.free}
        # Запрещённые области для точки под ногами: предмет, расширенный на половину ног.
        hw, fh = collision.half_width, collision.foot_height
        self._forbidden = [(o.left - hw, o.top, o.right + hw, o.bottom + fh) for o in collision.obstacles]

    def point(self, cell: tuple[int, int]) -> tuple[float, float]:
        return self.origin[0] + cell[0] * self.step, self.origin[1] + cell[1] * self.step

    def cell(self, x: float, y: float) -> tuple[int, int] | None:
        """Ближайшая свободная точка сетки к (x, y), в пределах двух шагов (None — нет такой)."""
        ci = round((x - self.origin[0]) / self.step)
        cj = round((y - self.origin[1]) / self.step)
        best, best_distance = None, math.inf
        for i in range(ci - 2, ci + 3):
            for j in range(cj - 2, cj + 3):
                if (i, j) in self.free and self.segment_clear((x, y), self.point((i, j))):
                    distance = math.dist((x, y), self.point((i, j)))
                    if distance < best_distance:
                        best, best_distance = (i, j), distance
        return best

    def neighbours(self, cell: tuple[int, int]) -> tuple[tuple[tuple[int, int], float], ...]:
        """Соседние свободные точки и длина шага до них (в шагах сетки)."""
        return self._links.get(cell, ())

    def _find_neighbours(self, cell: tuple[int, int]):
        i, j = cell
        free = self.free
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (i + di, j + dj) in free:
                yield (i + di, j + dj), 1.0
        for di, dj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            if (i + di, j + dj) in free and (i + di, j) in free and (i, j + dj) in free:
                yield (i + di, j + dj), math.sqrt(2)

    def reachable(self, start: tuple[int, int]) -> set[tuple[int, int]]:
        """Все точки сетки, куда можно дойти от start (поиск в ширину)."""
        if start not in self.free:
            return set()
        seen = {start}
        queue = deque([start])
        while queue:
            for nxt, _ in self.neighbours(queue.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def steps_from(self, start: tuple[int, int]) -> tuple[dict, dict]:
        """Поиск в ширину от start: сколько шагов сетки до каждой точки и откуда в неё пришли."""
        steps = {start: 0}
        came: dict[tuple[int, int], tuple[int, int]] = {}
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            for nxt, _ in self.neighbours(cell):
                if nxt not in steps:
                    steps[nxt] = steps[cell] + 1
                    came[nxt] = cell
                    queue.append(nxt)
        return steps, came

    def route(self, start: tuple[float, float], came: dict, last: tuple[int, int]) -> list[tuple[float, float]]:
        """Путь от start до точки last по дереву поиска came (как из steps_from), спрямлённый."""
        cells = [last]
        while cells[-1] in came:
            cells.append(came[cells[-1]])
        points = [self.point(c) for c in reversed(cells)]
        return self.smooth([start, *points])[1:] or [self.point(last)]

    def find_path(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
        max_expanded: int = 6000,
    ) -> list[tuple[float, float]] | None:
        """Путь A* от start до goal — точки, по которым можно идти по прямой (без start).

        None — пути нет или goal не в свободной части. max_expanded ограничивает работу:
        сетка кладовой меньше 2000 точек, так что предел срабатывает только на сломанных данных.
        """
        first, last = self.cell(*start), self.cell(*goal)
        if first is None or last is None:
            return None
        goal_point = self.point(last)

        def estimate(cell: tuple[int, int]) -> float:
            dx, dy = abs(cell[0] - last[0]), abs(cell[1] - last[1])
            return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)

        queue = [(estimate(first), 0.0, first)]
        cost = {first: 0.0}
        came: dict[tuple[int, int], tuple[int, int]] = {}
        expanded = 0
        while queue and expanded < max_expanded:
            _, spent, cell = heapq.heappop(queue)
            if cell == last:
                cells = [cell]
                while cells[-1] in came:
                    cells.append(came[cells[-1]])
                points = [self.point(c) for c in reversed(cells)]
                return self.smooth([start, *points])[1:] or [goal_point]
            if spent > cost.get(cell, math.inf):
                continue
            expanded += 1
            for nxt, step in self.neighbours(cell):
                new = spent + step
                if new < cost.get(nxt, math.inf):
                    cost[nxt] = new
                    came[nxt] = cell
                    heapq.heappush(queue, (new + estimate(nxt), new, nxt))
        return None

    def smooth(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Спрямляет ломаную: от каждой точки — сразу к самой дальней, видной по прямой подряд."""
        if len(points) <= 2:
            return list(points)
        result = [points[0]]
        anchor = 0
        while anchor < len(points) - 1:
            reach = anchor + 1
            while reach + 1 < len(points) and self.segment_clear(points[anchor], points[reach + 1]):
                reach += 1
            result.append(points[reach])
            anchor = reach
        return result

    def segment_clear(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        """Можно ли пройти по прямой из a в b: ноги нигде не задевают предметы и стены."""
        if not (self.collision.is_free(*a) and self.collision.is_free(*b)):
            return False
        return not any(_crosses(box, a, b) for box in self._forbidden)


def line_of_sight(obstacles: list[pygame.Rect], a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Не перегорожен ли отрезок a–b каким-нибудь предметом (касание края не считается)."""
    return not any(_crosses((o.left, o.top, o.right, o.bottom), a, b) for o in obstacles)


def _crosses(box: tuple[float, float, float, float], a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Проходит ли отрезок a–b через внутренность прямоугольника box = (лево, верх, право, низ)."""
    left, top, right, bottom = box
    eps = 1e-6
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for delta, low, high, origin in ((dx, left, right, a[0]), (dy, top, bottom, a[1])):
        if abs(delta) < 1e-12:
            if not (low + eps < origin < high - eps):
                return False
            continue
        u0, u1 = (low + eps - origin) / delta, (high - eps - origin) / delta
        if u0 > u1:
            u0, u1 = u1, u0
        t0, t1 = max(t0, u0), min(t1, u1)
        if t0 >= t1:
            return False
    return True


# --- Раскладка ---


def gap(a: pygame.Rect, b: pygame.Rect) -> tuple[int, int]:
    """Зазор между прямоугольниками по x и по y (0 — перекрываются по этой оси)."""
    dx = max(b.left - a.right, a.left - b.right, 0)
    dy = max(b.top - a.bottom, a.top - b.bottom, 0)
    return dx, dy


def placement_problem(rect: pygame.Rect, kind: str, others: list[pygame.Rect]) -> str | None:
    """Почему предмет нельзя поставить в rect (None — можно): правила ограниченной случайности."""
    bounds = MAZE_BOUNDS
    if not bounds.contains(rect):
        return "выходит за комнату"
    if rect.colliderect(START_ZONE) or rect.colliderect(SPAWN_ZONE):
        return "загораживает вход или место клубники"
    top_gap = rect.top - bounds.top
    if not (top_gap >= MIN_GAP_Y or (top_gap == 0 and kind in WALL_KINDS)):
        return "щель у задней стены"
    if min(rect.left - bounds.left, bounds.right - rect.right) < MIN_GAP_X or bounds.bottom - rect.bottom < MIN_GAP_Y:
        return "щель у стены"
    for other in others:
        dx, dy = gap(rect, other)
        if dx < MIN_GAP_X and dy < MIN_GAP_Y:
            return "слишком близко к другому предмету"
    return None


def layout_problems(items: tuple[PantryItem, ...]) -> list[str]:
    """Что не так с готовой раскладкой (пустой список — она годится)."""
    problems = []
    rects = [item.rect for item in items]
    for index, item in enumerate(items):
        problem = placement_problem(item.rect, item.kind, rects[:index] + rects[index + 1:])
        if problem:
            problems.append(f"{item.kind} {tuple(item.rect)}: {problem}")
    if len(items) < MIN_ITEMS:
        problems.append(f"мало предметов: {len(items)}")
    coverage = sum(r.width * r.height for r in rects) / (MAZE_BOUNDS.width * MAZE_BOUNDS.height)
    if not COVERAGE[0] <= coverage <= COVERAGE[1]:
        problems.append(f"доля пола под предметами {coverage:.2f}")
    # Не ряд и не пустое поле: предметы заходят во все три трети комнаты по ширине и в обе половины по высоте.
    thirds = {min(2, (r.centerx - MAZE_BOUNDS.left) * 3 // MAZE_BOUNDS.width) for r in rects}
    halves = {(r.centery - MAZE_BOUNDS.top) * 2 // MAZE_BOUNDS.height for r in rects}
    if len(thirds) < 3 or len(halves) < 2:
        problems.append("предметы собрались в одной части комнаты")
    if problems:
        return problems  # связность дороже остального — её считаем последней
    layout = PantryLayout(items)
    nav = layout.nav()
    start, spawn = nav.cell(*MAZE_START), nav.cell(*STRAWBERRY_SPAWN)
    if start is None or spawn is None:
        problems.append("вход или место клубники заняты")
    elif nav.reachable(start) != nav.free:
        problems.append("есть недостижимые закутки")
    return problems


def _random_items(rng: random.Random) -> tuple[PantryItem, ...]:
    plan = (["tall_bookcase"] * rng.randint(2, 4) + ["bookcase"] * rng.randint(4, 6)
            + [rng.choice(("books", "cookbooks", "boxes")) for _ in range(rng.randint(4, 6))])
    items: list[PantryItem] = []
    for kind in plan:  # сначала крупные — им труднее найти место
        (w_min, w_max), (h_min, h_max) = SIZES[kind]
        for _ in range(PLACE_TRIES):
            width = rng.randrange(w_min, w_max + 1, 2)
            height = rng.randrange(h_min, h_max + 1, 2)
            x = rng.randrange(MAZE_BOUNDS.left, MAZE_BOUNDS.right - width + 1, 2)
            if kind in WALL_KINDS and rng.random() < 0.4:
                y = MAZE_BOUNDS.top  # вплотную к задней стене
            else:
                y = rng.randrange(MAZE_BOUNDS.top, MAZE_BOUNDS.bottom - height + 1, 2)
            rect = pygame.Rect(x, y, width, height)
            if placement_problem(rect, kind, [item.rect for item in items]) is None:
                items.append(PantryItem(kind, rect))
                break
    return tuple(items)


def _random_decor(rng: random.Random, items: tuple[PantryItem, ...]) -> tuple[PantryItem, ...]:
    """Несколько листов рецептов на полу — между предметами, не на них."""
    decor: list[PantryItem] = []
    for _ in range(40):
        if len(decor) >= 4:
            break
        rect = pygame.Rect(rng.randrange(MAZE_BOUNDS.left + 4, MAZE_BOUNDS.right - 12, 2),
                           rng.randrange(MAZE_BOUNDS.top + 4, MAZE_BOUNDS.bottom - 8, 2), 8, 6)
        if rect.collidelist([item.rect.inflate(4, 4) for item in items + tuple(decor)]) == -1:
            decor.append(PantryItem(rng.choice(DECOR_KINDS), rect))
    return tuple(decor)


# Запасная раскладка (одна из удачных случайных, закреплённая): тесты проверяют, что
# layout_problems для неё пуст.
FALLBACK_ITEMS = (
    PantryItem("tall_bookcase", pygame.Rect(208, 110, 16, 40)),
    PantryItem("tall_bookcase", pygame.Rect(98, 92, 14, 56)),
    PantryItem("bookcase", pygame.Rect(228, 82, 46, 14)),
    PantryItem("bookcase", pygame.Rect(132, 78, 52, 14)),
    PantryItem("bookcase", pygame.Rect(196, 50, 52, 14)),
    PantryItem("bookcase", pygame.Rect(114, 50, 54, 14)),
    PantryItem("books", pygame.Rect(164, 106, 18, 12)),
    PantryItem("books", pygame.Rect(258, 134, 14, 12)),
    PantryItem("books", pygame.Rect(166, 136, 16, 14)),
    PantryItem("cookbooks", pygame.Rect(60, 138, 16, 12)),
)


def generate_layout(seed: int | None = None, attempts: int = ATTEMPTS) -> PantryLayout:
    """Случайная, но проверенная раскладка кладовой; одинаковый seed — одинаковая раскладка.

    Не больше attempts попыток (каждая — быстрая), затем — запасной вариант FALLBACK_ITEMS.
    """
    rng = random.Random(seed)
    for attempt in range(1, attempts + 1):
        items = _random_items(rng)
        if not layout_problems(items):
            return PantryLayout(items, _random_decor(rng, items), seed, attempts=attempt)
    return fallback_layout(seed)


def fallback_layout(seed: int | None = None) -> PantryLayout:
    return PantryLayout(FALLBACK_ITEMS, _random_decor(random.Random(0), FALLBACK_ITEMS), seed, fallback=True)
