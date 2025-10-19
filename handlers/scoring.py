# scoring.py
import os

USE_SCORING_V2 = os.getenv("SCORING_V2") == "1"

# базові бали нової системи
def points_for_type(task_type: str, *, is_correct: bool, match_correct: int = 0, is_daily: bool = False) -> int:
    if is_daily:
        return 0  # за щоденні бали не даємо

    t = (task_type or "").lower()
    if t == "single":
        return 1 if is_correct else 0
    if t == "match":
        # 0..3 бали
        mc = max(0, min(3, int(match_correct or 0)))
        return mc
    if t == "open":
        return 2 if is_correct else 0
    if t == "boss":
        return 10 if is_correct else 0
    if t == "light":
        return 0
    # якщо тип невідомий -> 0 у V2
    return 0

def legacy_points() -> int:
    # стара логіка (у тебе було просто +10 за правильну відповідь)
    return 10

def calc_points(task: dict, *, is_correct: bool, match_correct: int = 0) -> int:
    """
    task: словник завдання з полями: task_type (може бути None), is_daily (0/1), level (старе)
    """
    if not USE_SCORING_V2:
        return legacy_points() if is_correct else 0

    task_type = task.get("task_type")
    is_daily = bool(task.get("is_daily"))

    # fallback: якщо task_type ще не заповнений у БД — мапимо зі старих рівнів, щоб нічого не впало
    if not task_type:
        lvl = (task.get("level") or "").lower()
        if lvl == "легкий":
            task_type = "single"
        elif lvl == "середній":
            task_type = "open"
        elif lvl == "важкий":
            task_type = "boss"
        else:
            task_type = "single"  # дефолт

    return points_for_type(task_type, is_correct=is_correct, match_correct=match_correct, is_daily=is_daily)
