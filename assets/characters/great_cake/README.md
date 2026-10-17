# Тортище (`great_cake`) — спрайты

- Источник: архив `great_cake_sprite_assets.zip`.
  Исходные описание и README без изменений: `art/characters/great_cake/original/`.
- Атлас `great_cake_atlas_64px.png`: 256×256 px, сетка 4×4, ячейка 64×64, PNG RGBA с прозрачностью.
- Отдельные кадры: 16 файлов `frames/NN_<id>.png` 64×64 RGBA. NN — номер ячейки атласа
  (слева направо, сверху вниз); каждый кадр совпадает со своей ячейкой пиксель в пиксель.
- Описание кадров и групп: `great_cake.json` (формат 1, см. `assets/README.md`).
- Пиксели не изменялись: PNG скопированы из архива байт в байт, имена файлов те же
  (поле `source_file`). Кадры не отражены: скипетр и накидка делают персонажа несимметричным,
  поэтому для взгляда влево и вправо есть свои кадры. Отражать их в игре нельзя.
- Исходные кропы высокого разрешения (до уменьшения в 64×64) лежат
  в `art/characters/great_cake/original/source_frames/`. Полный исходный лист
  `great_cake_source_sheet.png` (2 МБ) хранится только локально, в Git не попадает.
- Края проверены: тело непрозрачно (альфа 250–255, как у Чучмека). Цветная кайма из исходной
  генерации осталась только в почти прозрачных краевых пикселях, на тёмном и на светлом фоне
  её не видно. Отдельные пятнышки вне силуэта — с альфой не больше 5 из 255, то есть невидимы.

## Группы кадров

| Группа | Кадры | Кадр/с | В игре | Статус |
|---|---|---|---|---|
| `idle_down` | idle_front | 2 | цикл | одиночная поза |
| `wink_down` | wink_front | 2 | один раз | одиночная поза |
| `idle_up` | back_cape | 2 | цикл | одиночная поза |
| `idle_right` | profile_right | 2 | цикл | одиночная поза |
| `reaction` | angry_shout, unimpressed, angry_scepter, crossed_arms | 4 | один раз | **черновик**: четыре разные эмоции, а не фазы одного движения |
| `walk_right` | walk_right_01 … walk_right_04 | 6 | цикл | **черновик**: варианты позы, подряд дёргаются |
| `walk_left` | walk_left_01 … walk_left_04 | 6 | цикл | **черновик**: варианты позы, подряд дёргаются |

Почему ходьба черновая. В каждом кадре корона, свечи и скипетр нарисованы заново,
а верхняя часть силуэта сдвигается по горизонтали на 2,5–2,6 px. У утверждённой ходьбы
Алисы этот сдвиг не больше 0,9 px. Ноги шагают правдоподобно, но корпус при проигрывании
дрожит. `animation_set()` эти группы пропускает. Если такой персонаж пойдёт, он будет
показан стоящим, а не ходящим дёргано.

## Как использовать в сцене

Тортище пока статичный персонаж: позы и эмоции — отдельные кадры.

- Поза по псевдониму или по id кадра: `sprites.pose("angry").image`. Исходный кадр 64×64
  передаётся в `hires.sprite()`, на холсте — он же, уменьшенный ближайшим соседом
  (так рисуется Майкл-повар в испытании суши).
- Для `Character` подходит `animation_set(size)`: ожидание лицом вниз, вверх и вправо.
  Своего кадра «стоит влево» нет: смотрящий влево Тортище показывается лицом к зрителю.
  Для взгляда влево есть только шаги `walk_left_*`.

## Кадры

| Ячейка | id | Описание |
|---|---|---|
| 0 | `idle_front` | Величественно стоит лицом к зрителю, скипетр в руке |
| 1 | `wink_front` | Подмигивает, стоя лицом к зрителю |
| 2 | `back_cape` | Вид сзади: королевская накидка с меховой окантовкой |
| 3 | `profile_right` | Стоит в профиль, смотрит вправо, скипетр впереди |
| 4 | `angry_shout` | Гневно кричит |
| 5 | `unimpressed` | Самодовольно смотрит из-под прикрытых век |
| 6 | `angry_scepter` | Грозит кулаком, в другой руке скипетр |
| 7 | `crossed_arms` | Скрестил руки и сурово смотрит |
| 8–11 | `walk_right_01` … `walk_right_04` | Шагает вправо, позы 1–4 |
| 12–15 | `walk_left_01` … `walk_left_04` | Шагает влево, позы 1–4 |

## Псевдонимы поз

- `idle` → `idle_front`
- `wink` → `wink_front`
- `back` → `back_cape`
- `facing_right` → `profile_right`
- `angry` → `angry_shout`
- `smug` → `unimpressed`
- `threaten` → `angry_scepter`
- `stern` → `crossed_arms`

## Заметки из исходников

- Runtime frames and atlas are normalized to 64x64, matching the existing character asset convention.
- High-resolution isolated crops are preserved in source_frames/ and the original full sheet is preserved as great_cake_source_sheet.png.
- The four row-2 and row-3 poses are directional pose variants; review them in the animation preview before using them as continuous walk cycles.
- The sprite was approved as the crowned, strawberry-topped cake king with a royal burgundy cape and a dessert scepter. Do not mirror horizontally.
- Some source edge pixels contain a generated colored fringe. Original crops are preserved for review; runtime frames are normalized with premultiplied-alpha downsampling.
