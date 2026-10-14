"""Основные настройки игры «Алиса и Чучмек»."""

from pathlib import Path

Size = tuple[int, int]
Color = tuple[int, int, int]

GAME_TITLE = "Алиса и Чучмек"

# Папка проекта: относительно неё загружаются изображения, поэтому игра находит их
# при запуске из любого текущего каталога терминала.
PROJECT_DIR = Path(__file__).resolve().parent

# --- Окно и масштабирование ---
# Вся графика рисуется в логическом разрешении и потом увеличивается до размера окна.
LOGICAL_SIZE: Size = (320, 180)
WINDOW_SIZE: Size = (960, 540)  # стартовый размер окна — ровно ×3
# Целый масштаб (×3, ×4, ×6…) даёт одинаковые по размеру игровые пиксели,
# но оставляет поля шире. False — дробный масштаб на всё доступное место.
INTEGER_SCALING = True

# --- Время ---
FPS = 60
# Верхняя граница dt в секундах: после подвисания окна (перетаскивание, отладчик)
# объекты не должны «телепортироваться» одним огромным шагом.
MAX_FRAME_TIME = 0.1

# --- Цвета ---
LETTERBOX_COLOR: Color = (0, 0, 0)  # поля вокруг картинки
BACKGROUND_COLOR: Color = (22, 24, 36)
TITLE_COLOR: Color = (232, 196, 120)
TEXT_COLOR: Color = (176, 182, 204)
HINT_COLOR: Color = (112, 120, 148)
FPS_COLOR: Color = (110, 170, 120)

# --- Диалоги ---
DIALOGUE_CHARS_PER_SECOND = 40  # скорость печати реплик, символов в секунду
DIALOGUE_BOX_COLOR: Color = (14, 18, 42)
DIALOGUE_BORDER_COLOR: Color = (206, 210, 230)
DIALOGUE_NAME_COLOR: Color = TITLE_COLOR
DIALOGUE_TEXT_COLOR: Color = (238, 238, 246)
DIALOGUE_CHOICE_COLOR: Color = (150, 158, 188)
DIALOGUE_SELECTED_COLOR: Color = (255, 224, 150)
DIALOGUE_SELECTED_BG_COLOR: Color = (44, 54, 104)

# --- Персонажи ---
CHARACTER_WALK_SPEED = 60  # скорость ходьбы, логических пикселей в секунду

# --- Шрифты ---
# Системные моноширинные шрифты с кириллицей в порядке предпочтения (имена для
# pygame.font.match_font). DejaVu Sans Mono есть в Linux Mint по умолчанию.
# Если не найден ни один, используется встроенный шрифт Pygame (в нём тоже есть кириллица).
FONT_CANDIDATES: tuple[str, ...] = (
    "dejavusansmono",
    "liberationmono",
    "notosansmono",
    "ubuntumono",
    "freemono",
)
# Текст высокого разрешения (персонажи и надписи в разрешении окна, game/graphics/hires.py):
# системные шрифты без засечек с кириллицей в порядке предпочтения. DejaVu Sans — шрифт
# интерфейса Linux Mint по умолчанию. Если не найден ни один — встроенный шрифт Pygame.
TEXT_FONT_CANDIDATES: tuple[str, ...] = (
    "dejavusans",
    "notosans",
    "liberationsans",
    "freesans",
)
