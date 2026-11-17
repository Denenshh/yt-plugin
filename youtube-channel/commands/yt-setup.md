---
description: Первичная настройка — библиотеки, OAuth-доступ к YouTube и профиль канала
allowed-tools: Bash, Read, Write
---
Помоги пользователю настроить плагин YouTube. Используй скилл youtube-channel.

1. Проверь Python (`python --version`; на Windows без него — `winget install Python.Python.3.12`,
   потом перезапустить терминал) и библиотеки. С согласия пользователя выполни:
   `pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 edge-tts`.
   Для шортсов нужен ffmpeg: `winget install Gyan.FFmpeg` (проверка — `python "${CLAUDE_PLUGIN_ROOT}/scripts/short.py" check`).
   Необязательно: бесплатный ключ Pexels (pexels.com/api) → `setx PEXELS_API_KEY "ключ"`.
2. Проверь наличие `~/.config/yt-claude/client_secret.json` (или `$YT_CLAUDE_HOME`).
   Если нет — объясни по шагам:
   - console.cloud.google.com → создать проект;
   - «APIs & Services → Library» → включить **YouTube Data API v3** и **YouTube Analytics API**;
   - «OAuth consent screen» → External, добавить свой Google-аккаунт в Test users;
   - «Credentials → Create credentials → OAuth client ID → Desktop app» → скачать JSON;
   - сохранить как `~/.config/yt-claude/client_secret.json`.
3. Запусти `python "${CLAUDE_PLUGIN_ROOT}/scripts/yt.py" auth` — откроется браузер для входа.
4. Запусти `channel` и покажи название и статистику канала.
5. Если в проекте нет `CHANNEL.md` — задай вопросы из шаблона скилла и создай его.
