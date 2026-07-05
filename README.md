# credits_sutdio

Генератор видео с титрами: название -> прокрутка ролей и имён -> финальная надпись. gui на `customtkinter`.

## Демонстрация.

![Демонстрация](https://raw.githubusercontent.com/s4msepi0lroot/credits_sutdio/refs/heads/main/demo.mp4)

## Установка

```bash
pip install opencv-python numpy pillow customtkinter
```

`ffmpeg` - опционально, только для экспорта с прозрачным фоном (.mov).

## Запуск

```bash
python sutdio.py            # GUI
python sutdio.py --nogui    # тестовый рендер в CLI
```

## Использование без gui

```python
from sutdio import CreditsRenderer

renderer = CreditsRenderer(
    title="Название проекта",
    blocks=[
        {"role": "режиссёр", "names": ["123"], "bar": True},
        {"role": "разработка", "names": ["321", "231"], "bar": True},
    ],
    scheme="dark",
    width=1920, height=1080, fps=30,
    end_text="спасибо за игру",
)
renderer.render("credits.mp4")
```

## Настройки

тайминги (`title_fade_in`, `title_hold`, `title_fade_out`, `scroll_speed`, `tail_seconds`, `end_fade_in`, `end_hold`), размеры шрифтов (`title_size`, `role_size`, `name_size`, `end_size`), полоска-разделитель (`bar_w`, `bar_h`, `bar_dot`), отступы (`block_gap`, `bar_gap`, `role_gap`, `name_gap`).
