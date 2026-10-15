"""Лео в корзинке на площади: спокойная смена поз младенца. Логика без Pygame.

Лео не ходит, не ползает и не переходит с места на место: у него только позы «лёжа» и «сидя»
из манифеста assets/characters/leo/leo.json. Кадр «пробует ползти» (crawl_try) — почти ходьба,
а «плачет», «трёт глаза» и «сердится» не для праздника: их на площади нет.

Каждая поза относится к одному из настроений: спит, смеётся или просто не спит. Поза длится
случайное время из своего промежутка, потом Лео переходит к другой — без резких скачков:
спящий сначала просыпается, а смеющийся не засыпает посреди смеха. Таймер считает секунды (dt),
а не кадры, остаток переходит в следующую позу: смена поз от частоты кадров не зависит.
Случайность — через random.Random, который можно задать (в тестах — с постоянным зерном).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

SLEEP = "sleep"  # спит или дремлет
LAUGH = "laugh"  # смеётся, радуется
AWAKE = "awake"  # не спит: сидит, играет, смотрит по сторонам
MOODS = (SLEEP, LAUGH, AWAKE)


@dataclass(frozen=True)
class LeoPose:
    """Поза Лео: кадр манифеста, настроение и сколько секунд она длится (от и до)."""

    frame: str
    mood: str
    seconds: tuple[float, float]

    def __post_init__(self) -> None:
        if self.mood not in MOODS:
            raise ValueError(f"неизвестное настроение Лео {self.mood!r}")
        low, high = self.seconds
        if not 0 < low <= high < math.inf:
            raise ValueError(f"у позы {self.frame!r} неверная длительность {self.seconds!r}")


POSES = (
    LeoPose("sleep_blanket", SLEEP, (8.0, 13.0)),
    LeoPose("sleep_teddy", SLEEP, (7.0, 11.0)),
    LeoPose("nap_pillow", SLEEP, (6.0, 10.0)),
    LeoPose("sit_idle", AWAKE, (4.0, 7.0)),
    LeoPose("cuddle_teddy", AWAKE, (4.0, 7.0)),
    LeoPose("drink_bottle", AWAKE, (3.5, 6.0)),
    LeoPose("tummy_time", AWAKE, (3.5, 6.0)),
    LeoPose("reach", AWAKE, (2.5, 4.5)),
    LeoPose("surprised", AWAKE, (2.0, 3.5)),
    LeoPose("laugh", LAUGH, (2.5, 4.5)),
    LeoPose("arms_up", LAUGH, (2.0, 3.5)),
    LeoPose("play_rattle", LAUGH, (3.0, 5.5)),
)
POSE_BY_FRAME = {pose.frame: pose for pose in POSES}
START_POSE = "sleep_blanket"  # на площади Лео поначалу спит под одеялом
# Куда можно перейти из настроения и насколько охотно (вес): спящий только просыпается,
# смеющийся успокаивается или смеётся дальше, а проснувшийся может и заснуть снова.
NEXT_MOODS: dict[str, tuple[tuple[str, int], ...]] = {
    SLEEP: ((AWAKE, 1),),
    AWAKE: ((AWAKE, 2), (LAUGH, 2), (SLEEP, 1)),
    LAUGH: ((AWAKE, 2), (LAUGH, 1)),
}


class LeoIdle:
    """Какая поза у Лео сейчас и когда она сменится. update(dt) двигает время."""

    def __init__(self, rng: random.Random | None = None, start: str = START_POSE) -> None:
        if start not in POSE_BY_FRAME:
            raise ValueError(f"у Лео нет позы {start!r}")
        self.rng = rng if rng is not None else random.Random()
        self.pose = POSE_BY_FRAME[start]
        self.time_left = self._duration(self.pose)  # сколько секунд ещё длится текущая поза
        self.changes = 0  # сколько раз поза сменилась

    @property
    def frame(self) -> str:
        return self.pose.frame

    @property
    def mood(self) -> str:
        return self.pose.mood

    def update(self, dt: float) -> None:
        if not 0 <= dt < math.inf:
            raise ValueError(f"dt должен быть неотрицательным конечным числом, а не {dt!r}")
        self.time_left -= dt
        while self.time_left <= 0:  # долгий кадр — несколько смен подряд, остаток не теряется
            self._switch()

    def _switch(self) -> None:
        moods, weights = zip(*NEXT_MOODS[self.mood])
        mood = self.rng.choices(moods, weights)[0]
        # Всегда другая поза: та же самая подряд выглядела бы так, будто ничего не произошло.
        options = [pose for pose in POSES if pose.mood == mood and pose is not self.pose]
        self.pose = self.rng.choice(options)
        self.time_left += self._duration(self.pose)
        self.changes += 1

    def _duration(self, pose: LeoPose) -> float:
        return self.rng.uniform(*pose.seconds)
