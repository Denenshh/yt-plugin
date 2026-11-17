---
description: Загрузить видео на YouTube (с подтверждением)
argument-hint: "<путь к видео> [папка с meta.md] [public|unlisted|private] [дата публикации]"
allowed-tools: Bash, Read, Write
---
Загрузи видео по скиллу youtube-channel. Аргументы: $ARGUMENTS

1. Найди файл видео и `meta.md` (выбранное название, описание, теги). Если метаданных
   нет — сначала сделай их как в /yt-meta.
2. Уточни приватность и время публикации, если не указаны (по умолчанию private).
   Время переведи в UTC формата RFC3339.
3. Пробный прогон: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/yt.py" upload <файл> --title ... --description ... --tags ... --privacy ... [--publish-at ...] [--thumbnail ...]`
   (без `--yes`). Покажи пользователю итоговые метаданные.
4. **Только после явного подтверждения** повтори команду с `--yes`.
5. Сохрани результат в `upload.json` в папке видео и дай ссылки на видео и Studio.
