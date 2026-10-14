"""Прогресс игры: какие из трёх испытаний пройдены (за каждое — фрагмент праздника)."""

from __future__ import annotations

# Идентификаторы испытаний в порядке на площади: слева направо.
TRIALS = ("sushi", "forms", "cakes")
TRIAL_NAMES = {"sushi": "Суши", "forms": "Формуляры", "cakes": "Торты"}


class GameProgress:
    """Пройденные испытания без повторов. Финал открывается, когда пройдены все три."""

    def __init__(self) -> None:
        self._completed: list[str] = []

    @property
    def completed(self) -> tuple[str, ...]:
        """Пройденные испытания в порядке прохождения."""
        return tuple(self._completed)

    @property
    def fragments(self) -> int:
        return len(self._completed)

    @property
    def total(self) -> int:
        return len(TRIALS)

    @property
    def has_all_fragments(self) -> bool:
        """Можно ли открыть финальную локацию."""
        return set(self._completed) == set(TRIALS)

    def is_completed(self, trial_id: str) -> bool:
        return trial_id in self._completed

    def complete(self, trial_id: str) -> bool:
        """Отмечает испытание пройденным. Возвращает False, если оно уже было пройдено."""
        if trial_id not in TRIALS:
            raise ValueError(f"неизвестное испытание {trial_id!r}, допустимы: {', '.join(TRIALS)}")
        if trial_id in self._completed:
            return False
        self._completed.append(trial_id)
        return True
