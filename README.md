# youtube-channel — плагин Claude Code для ведения YouTube-канала

## Установка

1. Распакуйте архив, например в `~/claude-plugins/yt-plugin`.
2. В Claude Code:
   ```
   /plugin marketplace add ~/claude-plugins/yt-plugin
   /plugin install youtube-channel@yt-tools
   ```
3. Перезапустите Claude Code и выполните `/yt-setup`. Команда поможет
   поставить библиотеки Google API, подключить OAuth и создать профиль канала `CHANNEL.md`.

Лучше работать из отдельной папки канала (например `~/youtube/my-channel`):
там будут лежать профиль, идеи, сценарии и отчёты.

## Команды

| Команда | Что делает |
|---|---|
| `/yt-setup` | первичная настройка и авторизация |
| `/yt-short [тема]` | AI-шортс под ключ: факты → сценарий → озвучка → видео с субтитрами → загрузка |
| `/yt-ideas [тема]` | идеи видео с оценкой → `ideas.md` |
| `/yt-script <тема> [shorts]` | сценарий → `videos/.../script.md` |
| `/yt-meta <видео>` | названия, описание, теги, таймкоды, превью → `meta.md` |
| `/yt-upload <файл>` | загрузка через API (сначала пробный прогон, потом подтверждение) |
| `/yt-analytics [дни] [ID]` | отчёт с выводами → `reports/` |
| `/yt-comments [ID]` | черновики ответов, отправка только одобренных |

Скилл `youtube-channel` подключается автоматически, когда вы просто пишете
о своём канале («что сейчас заходит?», «придумай шортс про…»).

## Настройка Google API (один раз)

1. https://console.cloud.google.com → новый проект.
2. APIs & Services → Library → включить **YouTube Data API v3** и **YouTube Analytics API**.
3. OAuth consent screen → External → добавьте свой аккаунт в *Test users*.
4. Credentials → Create credentials → OAuth client ID → **Desktop app** → скачать JSON.
5. Сохранить как `~/.config/yt-claude/client_secret.json`.
6. `pip install google-api-python-client google-auth-oauthlib google-auth-httplib2`
7. `python3 youtube-channel/scripts/yt.py auth` — вход через браузер.

Токен хранится в `~/.config/yt-claude/token.json` (путь меняется переменной `YT_CLAUDE_HOME`).

## AI-шортсы (Windows)

```
winget install Python.Python.3.12
winget install Gyan.FFmpeg
pip install edge-tts google-api-python-client google-auth-oauthlib google-auth-httplib2
setx PEXELS_API_KEY "ваш_ключ"      # необязательно, бесплатно на pexels.com/api
```
Перезапустите терминал после установки. Свои записи геймплея кладите в `clips/`
в папке канала, фоновую музыку (например из Фонотеки YouTube) — в `music/`.

## Ограничения

- Квота YouTube API — 10 000 единиц в день; одна загрузка видео ≈ 1600.
- Пока OAuth-приложение не прошло проверку Google, видео, загруженные через API,
  могут принудительно становиться *private*. Для личного канала обычно хватает
  режима тестирования; для публичной загрузки через API Google может потребовать аудит.
- В режиме Testing токен живёт 7 дней, после этого снова выполните `yt.py auth`
  (или переведите приложение в *In production*).
- Загрузка и ответы на комментарии всегда проходят через ваше подтверждение.
