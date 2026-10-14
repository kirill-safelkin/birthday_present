# Чучмек (`chuchmek`) — спрайты

- Источник: архив `chuchmek_sprite_assets.zip`.
  Исходные описание и README без изменений: `art/characters/chuchmek/original/`.
- Атлас `chuchmek_atlas_64px.png`: 256×256 px, сетка 4×4, ячейка 64×64, PNG RGBA с прозрачностью.
- Отдельные кадры: 16 файлов `frames/NN_<id>.png` 64×64 RGBA. NN — номер ячейки атласа
  (слева направо, сверху вниз); каждый кадр совпадает со своей ячейкой пиксель в пиксель.
- Описание кадров и групп: `chuchmek.json` (формат 1, см. `assets/README.md`).
- Пиксели не изменялись: PNG скопированы из архива байт в байт, изменены только имена файлов
  (исходное имя каждого кадра — в поле `source_file`).
- Описания кадров составлены по разделу «Порядок сетки» исходного README (в `chuchmek.json` описаний нет).

## Группы кадров

| Группа | Кадры | Кадр/с | В игре | Статус |
|---|---|---|---|---|
| `idle` | idle | 1 | цикл | одиночная поза |
| `talk` | talk_01, talk_02, talk_gesture, talk_excited | 5 | цикл | **черновик**: README: последовательность нужно проверить в игре — позы могут быть вариантами, а не промежуточными кадрами |
| `run_right` | run_right_01, run_right_02, run_right_03, run_right_04 | 8 | цикл | **черновик**: README: последовательность нужно проверить в игре — позы могут быть вариантами, а не промежуточными кадрами |

## Кадры

| Ячейка | id | Описание |
|---|---|---|
| 0 | `idle` | Спокойная поза |
| 1 | `wink` | Подмигивание |
| 2 | `curious_glance` | Любопытный взгляд |
| 3 | `clipboard_confident` | Уверенность с планшетом |
| 4 | `talk_01` | Разговор, поза 1 |
| 5 | `talk_02` | Разговор, поза 2 |
| 6 | `talk_gesture` | Разговор с жестом |
| 7 | `talk_excited` | Оживлённый разговор |
| 8 | `confused` | Растерянность |
| 9 | `panicked` | Паника |
| 10 | `arms_up_panic` | Паника, руки вверх |
| 11 | `smug_wink` | Самодовольное подмигивание |
| 12 | `run_right_01` | Бег вправо, поза 1 |
| 13 | `run_right_02` | Бег вправо, поза 2 |
| 14 | `run_right_03` | Бег вправо, поза 3 |
| 15 | `run_right_04` | Бег вправо, поза 4 |

## Псевдонимы поз

- `wink` → `wink`
- `curious` → `curious_glance`
- `confident` → `clipboard_confident`
- `confused` → `confused`
- `panic` → `panicked`
- `panic_arms_up` → `arms_up_panic`
- `smug` → `smug_wink`

## Заметки из исходников

- Frames have been extracted from the generated 4x4 reference sheet and normalized to 64x64.
- Disconnected decorative specks/effects outside the main character silhouette were removed when possible.
- Review the talk and run sequences before using them as continuous loops; some generated frames are pose variants rather than true animation in-betweens.
