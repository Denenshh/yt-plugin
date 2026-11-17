#!/usr/bin/env python3
"""
yt.py — CLI для работы с YouTube-каналом из Claude Code.

Подкоманды:
  auth                         — авторизация через OAuth (один раз)
  channel                      — сведения и статистика канала
  videos   [--limit N]         — последние загруженные видео
  analytics [--days N]         — сводка по каналу за период
  top      [--days N] [--limit N] — топ видео по просмотрам
  video-stats VIDEO_ID [--days N] — аналитика одного видео
  comments [--video ID] [--limit N] [--unanswered] — комментарии
  reply COMMENT_ID --text "..." --yes — ответить на комментарий
  upload FILE --title ... [--description ...] [--tags a,b] [--privacy private]
         [--publish-at 2026-12-01T15:00:00Z] [--thumbnail img.jpg]
         [--category 22] [--made-for-kids] [--yes]

Все ответы печатаются в JSON, чтобы Claude мог их разобрать.

Файлы конфигурации (по умолчанию в ~/.config/yt-claude/, можно сменить
переменной окружения YT_CLAUDE_HOME):
  client_secret.json — OAuth-клиент из Google Cloud Console (тип «Desktop app»)
  token.json         — создаётся после `yt.py auth`
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

HOME = Path(os.environ.get("YT_CLAUDE_HOME", Path.home() / ".config" / "yt-claude"))
CLIENT_SECRET = HOME / "client_secret.json"
TOKEN = HOME / "token.json"


# ---------------------------------------------------------------- helpers

def out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def fail(msg, code=1, **extra):
    out({"error": msg, **extra})
    sys.exit(code)


def _imports():
    try:
        from google.auth.transport.requests import Request  # noqa
        from google.oauth2.credentials import Credentials  # noqa
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa
        from googleapiclient.discovery import build  # noqa
    except ImportError:
        fail(
            "Не установлены библиотеки Google API.",
            hint="pip install google-api-python-client google-auth-oauthlib google-auth-httplib2",
        )


def get_credentials(interactive=False):
    _imports()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json())
            return creds
        except Exception as e:  # токен отозван и т.п.
            if not interactive:
                fail(f"Не удалось обновить токен: {e}", hint="Запустите: yt.py auth")
    if not interactive:
        fail("Нет авторизации.", hint="Запустите: yt.py auth")
    if not CLIENT_SECRET.exists():
        fail(
            f"Не найден {CLIENT_SECRET}",
            hint="Скачайте OAuth client (Desktop app) из Google Cloud Console и сохраните по этому пути.",
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    HOME.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json())
    try:
        os.chmod(TOKEN, 0o600)
    except OSError:
        pass
    return creds


def yt():
    creds = get_credentials()
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def yta():
    creds = get_credentials()
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def my_channel(service):
    r = service.channels().list(part="id,snippet,statistics,contentDetails", mine=True).execute()
    items = r.get("items", [])
    if not items:
        fail("У аккаунта нет YouTube-канала.")
    return items[0]


def date_range(days):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    return start.isoformat(), end.isoformat()


def rows_to_dicts(resp):
    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in resp.get("rows", []) or []]


# ---------------------------------------------------------------- commands

def cmd_auth(a):
    get_credentials(interactive=True)
    ch = my_channel(yt())
    out({"ok": True, "channel_id": ch["id"], "title": ch["snippet"]["title"], "token": str(TOKEN)})


def cmd_channel(a):
    ch = my_channel(yt())
    s = ch.get("statistics", {})
    out({
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "description": ch["snippet"].get("description", ""),
        "custom_url": ch["snippet"].get("customUrl"),
        "subscribers": s.get("subscriberCount"),
        "views": s.get("viewCount"),
        "videos": s.get("videoCount"),
    })


def _recent_videos(service, limit):
    ch = my_channel(service)
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while len(ids) < limit:
        r = service.playlistItems().list(
            part="contentDetails", playlistId=uploads,
            maxResults=min(50, limit - len(ids)), pageToken=token).execute()
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        token = r.get("nextPageToken")
        if not token:
            break
    vids = []
    for i in range(0, len(ids), 50):
        r = service.videos().list(part="snippet,statistics,status,contentDetails",
                                  id=",".join(ids[i:i + 50])).execute()
        for v in r.get("items", []):
            st = v.get("statistics", {})
            vids.append({
                "id": v["id"],
                "title": v["snippet"]["title"],
                "published": v["snippet"]["publishedAt"],
                "duration": v["contentDetails"]["duration"],
                "privacy": v["status"]["privacyStatus"],
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
                "url": f"https://youtu.be/{v['id']}",
            })
    return vids


def cmd_videos(a):
    out(_recent_videos(yt(), a.limit))


def cmd_analytics(a):
    start, end = date_range(a.days)
    metrics = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
               "subscribersGained,subscribersLost,likes,comments,shares")
    r = yta().reports().query(ids="channel==MINE", startDate=start, endDate=end,
                              metrics=metrics).execute()
    daily = yta().reports().query(ids="channel==MINE", startDate=start, endDate=end,
                                  metrics="views,estimatedMinutesWatched,subscribersGained",
                                  dimensions="day", sort="day").execute()
    sources = yta().reports().query(ids="channel==MINE", startDate=start, endDate=end,
                                    metrics="views", dimensions="insightTrafficSourceType",
                                    sort="-views").execute()
    out({
        "period": {"start": start, "end": end},
        "totals": (rows_to_dicts(r) or [{}])[0],
        "traffic_sources": rows_to_dicts(sources),
        "daily": rows_to_dicts(daily),
    })


def cmd_top(a):
    start, end = date_range(a.days)
    r = yta().reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained",
        dimensions="video", sort="-views", maxResults=a.limit).execute()
    rows = rows_to_dicts(r)
    if rows:
        ids = ",".join(x["video"] for x in rows)
        titles = {v["id"]: v["snippet"]["title"]
                  for v in yt().videos().list(part="snippet", id=ids).execute().get("items", [])}
        for x in rows:
            x["title"] = titles.get(x["video"], "")
    out({"period": {"start": start, "end": end}, "top": rows})


def cmd_video_stats(a):
    start, end = date_range(a.days)
    f = f"video=={a.video_id}"
    totals = yta().reports().query(
        ids="channel==MINE", startDate=start, endDate=end, filters=f,
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained").execute()
    retention = yta().reports().query(
        ids="channel==MINE", startDate=start, endDate=end, filters=f,
        metrics="audienceWatchRatio,relativeRetentionPerformance",
        dimensions="elapsedVideoTimeRatio").execute()
    out({
        "video": a.video_id,
        "period": {"start": start, "end": end},
        "totals": (rows_to_dicts(totals) or [{}])[0],
        "retention_curve": rows_to_dicts(retention),
    })


def cmd_comments(a):
    service = yt()
    ch = my_channel(service)
    kw = dict(part="snippet,replies", maxResults=min(100, a.limit), order="time",
              textFormat="plainText")
    if a.video:
        kw["videoId"] = a.video
    else:
        kw["allThreadsRelatedToChannelId"] = ch["id"]
    res, token = [], None
    while len(res) < a.limit:
        if token:
            kw["pageToken"] = token
        r = service.commentThreads().list(**kw).execute()
        for t in r.get("items", []):
            top = t["snippet"]["topLevelComment"]
            replies = t.get("replies", {}).get("comments", [])
            answered = any(c["snippet"].get("authorChannelId", {}).get("value") == ch["id"]
                           for c in replies)
            if a.unanswered and answered:
                continue
            res.append({
                "comment_id": top["id"],
                "video_id": t["snippet"].get("videoId"),
                "author": top["snippet"]["authorDisplayName"],
                "text": top["snippet"]["textDisplay"],
                "likes": top["snippet"].get("likeCount", 0),
                "published": top["snippet"]["publishedAt"],
                "reply_count": t["snippet"].get("totalReplyCount", 0),
                "answered_by_channel": answered,
            })
        token = r.get("nextPageToken")
        if not token:
            break
    out(res[: a.limit])


def cmd_reply(a):
    if not a.yes:
        fail("Ответ не отправлен: нужен флаг --yes (подтверждение пользователя).")
    r = yt().comments().insert(part="snippet", body={
        "snippet": {"parentId": a.comment_id, "textOriginal": a.text}}).execute()
    out({"ok": True, "reply_id": r["id"], "parent": a.comment_id})


def cmd_upload(a):
    _imports()
    from googleapiclient.http import MediaFileUpload
    path = Path(a.file)
    if not path.is_file():
        fail(f"Файл не найден: {path}")
    if len(a.title) > 100:
        fail("Название длиннее 100 символов.")
    if len(a.description or "") > 5000:
        fail("Описание длиннее 5000 символов.")
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": a.made_for_kids}
    if a.publish_at:
        status["privacyStatus"] = "private"  # YouTube требует private для отложенной публикации
        status["publishAt"] = a.publish_at
    body = {
        "snippet": {"title": a.title, "description": a.description or "", "tags": tags,
                    "categoryId": str(a.category)},
        "status": status,
    }
    if a.language:
        body["snippet"]["defaultLanguage"] = a.language
        body["snippet"]["defaultAudioLanguage"] = a.language
    if not a.yes:
        out({"dry_run": True, "file": str(path), "size_mb": round(path.stat().st_size / 1e6, 1),
             "metadata": body, "hint": "Добавьте --yes, чтобы загрузить."})
        return
    service = yt()
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    req = service.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print(f"progress {int(st.progress() * 100)}%", file=sys.stderr)
    vid = resp["id"]
    result = {"ok": True, "video_id": vid, "url": f"https://youtu.be/{vid}",
              "studio": f"https://studio.youtube.com/video/{vid}/edit",
              "privacy": status["privacyStatus"], "publish_at": a.publish_at}
    if a.thumbnail:
        try:
            service.thumbnails().set(videoId=vid, media_body=MediaFileUpload(a.thumbnail)).execute()
            result["thumbnail"] = "set"
        except Exception as e:
            result["thumbnail_error"] = str(e)
    if a.playlist:
        try:
            service.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": a.playlist,
                "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
            result["playlist"] = a.playlist
        except Exception as e:
            result["playlist_error"] = str(e)
    out(result)


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="YouTube channel CLI for Claude Code")
    sp = p.add_subparsers(dest="cmd", required=True)

    sp.add_parser("auth").set_defaults(fn=cmd_auth)
    sp.add_parser("channel").set_defaults(fn=cmd_channel)

    s = sp.add_parser("videos"); s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_videos)

    s = sp.add_parser("analytics"); s.add_argument("--days", type=int, default=28)
    s.set_defaults(fn=cmd_analytics)

    s = sp.add_parser("top"); s.add_argument("--days", type=int, default=28)
    s.add_argument("--limit", type=int, default=10); s.set_defaults(fn=cmd_top)

    s = sp.add_parser("video-stats"); s.add_argument("video_id")
    s.add_argument("--days", type=int, default=90); s.set_defaults(fn=cmd_video_stats)

    s = sp.add_parser("comments"); s.add_argument("--video")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--unanswered", action="store_true"); s.set_defaults(fn=cmd_comments)

    s = sp.add_parser("reply"); s.add_argument("comment_id"); s.add_argument("--text", required=True)
    s.add_argument("--yes", action="store_true"); s.set_defaults(fn=cmd_reply)

    s = sp.add_parser("upload"); s.add_argument("file"); s.add_argument("--title", required=True)
    s.add_argument("--description", default=""); s.add_argument("--tags", default="")
    s.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    s.add_argument("--publish-at", help="RFC3339, напр. 2026-12-01T15:00:00Z")
    s.add_argument("--thumbnail"); s.add_argument("--playlist")
    s.add_argument("--category", default="22", help="22 = People & Blogs, 27 = Education, 28 = Science & Tech, 20 = Gaming")
    s.add_argument("--language", help="напр. ru, en")
    s.add_argument("--made-for-kids", action="store_true")
    s.add_argument("--yes", action="store_true"); s.set_defaults(fn=cmd_upload)

    a = p.parse_args()
    try:
        a.fn(a)
    except SystemExit:
        raise
    except Exception as e:
        msg = str(e)
        hint = None
        if "quotaExceeded" in msg:
            hint = "Исчерпана дневная квота YouTube API (10 000 ед.; загрузка видео ≈ 1600). Попробуйте завтра."
        elif "insufficientPermissions" in msg or "invalid_grant" in msg:
            hint = "Переавторизуйтесь: yt.py auth"
        fail(msg, hint=hint)


if __name__ == "__main__":
    main()
