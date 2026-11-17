#!/usr/bin/env python3
"""
short.py — сборка вертикального шортса (1080x1920) из сценария.

    python short.py build  <папка_видео>/short.json
    python short.py check  — проверить, что всё установлено

short.json:
{
  "title": "5 пасхалок в GTA, которые нашли спустя годы",
  "voice": "ru-RU-DmitryNeural",          // или ru-RU-SvetlanaNeural
  "rate": "+10%",                         // скорость речи
  "banner": "ПАСХАЛКИ GTA",               // необязательно: плашка сверху
  "music": "music/track.mp3",             // необязательно: фон (тихо)
  "segments": [
    {"text": "Хук — первая фраза ролика.", "visual": "gaming setup neon"},
    {"text": "Факт номер один...",        "clip": "clips/gta_01.mp4"},
    {"text": "...",                       "image": "images/frame.png"}
  ]
}

Источник картинки для сегмента (по приоритету):
  "clip"   — свой видеофайл (запись геймплея и т.п.)
  "image"  — своя картинка (будет медленный наезд камеры)
  "visual" — поисковый запрос к стокам Pexels (нужен PEXELS_API_KEY)
  иначе    — тёмный градиентный фон
Пути относительные — от папки, где лежит short.json.

Результат: short.mp4, voice.mp3, subs.ass и build.json рядом с short.json.
Нужно: ffmpeg в PATH, pip install edge-tts.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

W, H, FPS = 1080, 1920, 30
FONT = os.environ.get("YT_SHORT_FONT", "Arial Black")


def out(d):
    print(json.dumps(d, ensure_ascii=False, indent=2))


def fail(msg, **kw):
    out({"error": msg, **kw})
    sys.exit(1)


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        fail("ffmpeg error", cmd=" ".join(map(str, cmd))[:400], stderr=r.stderr[-1500:])
    return r.stdout


def duration(path):
    s = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(s.strip())


# ------------------------------------------------------------------ TTS

async def _tts(text, voice, rate, mp3_path):
    import edge_tts
    try:
        com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:  # старые версии edge-tts
        com = edge_tts.Communicate(text, voice, rate=rate)
    words = []
    with open(mp3_path, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"w": ch["text"], "s": ch["offset"] / 1e7,
                              "e": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def tts(text, voice, rate, mp3_path):
    """Возвращает список слов с таймингами (сек) относительно начала фразы."""
    words = asyncio.run(_tts(text, voice, rate, mp3_path))
    if not words:  # нет таймингов — раскидываем слова равномерно по длине
        d = duration(mp3_path)
        toks = text.split()
        total = sum(len(t) for t in toks) or 1
        t = 0.0
        for tok in toks:
            dt = d * len(tok) / total
            words.append({"w": tok, "s": t, "e": t + dt})
            t += dt
    return words


# ------------------------------------------------------------------ visuals

def pexels_clip(query, cache, used):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": 15})
    req = urllib.request.Request(f"https://api.pexels.com/videos/search?{q}",
                                 headers={"Authorization": key, "User-Agent": "yt-short/1.0"})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        print(f"pexels: {e}", file=sys.stderr)
        return None
    for v in data.get("videos", []):
        if v["id"] in used:
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("height") and f.get("width") and f["height"] >= f["width"]
                 and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
        if not files:
            continue
        best = min(files, key=lambda f: abs(f["height"] - H))
        dst = cache / f"pexels_{v['id']}.mp4"
        if not dst.exists():
            try:
                rq = urllib.request.Request(best["link"], headers={"User-Agent": "yt-short/1.0"})
                with urllib.request.urlopen(rq, timeout=120) as r, open(dst, "wb") as f:
                    shutil.copyfileobj(r, f)
            except Exception as e:
                print(f"pexels download: {e}", file=sys.stderr)
                continue
        used.add(v["id"])
        return dst
    return None


COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an"]


def make_segment(i, seg, dur, base, work, used):
    dst = work / f"seg_{i:02d}.mp4"
    clip = seg.get("clip")
    image = seg.get("image")
    if clip and (base / clip).exists():
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-ss", str(seg.get("start", 0)),
             "-i", str(base / clip), "-t", f"{dur:.3f}", "-vf", COVER, *ENC, str(dst)])
        return dst, f"clip:{clip}"
    if image and (base / image).exists():
        frames = int(dur * FPS) + 1
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},setsar=1")
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(base / image), "-t", f"{dur:.3f}",
             "-vf", vf, *ENC, str(dst)])
        return dst, f"image:{image}"
    if seg.get("visual"):
        p = pexels_clip(seg["visual"], work, used)
        if p:
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(p), "-t", f"{dur:.3f}",
                 "-vf", COVER, *ENC, str(dst)])
            return dst, f"pexels:{p.name}"
    # запасной вариант — градиент
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"gradients=s={W}x{H}:c0=0x0f0c29:c1=0x302b63:c2=0x24243e:nb_colors=3:speed=0.01:r={FPS}",
         "-t", f"{dur:.3f}", "-vf", "setsar=1", *ENC, str(dst)])
    return dst, "gradient"


# ------------------------------------------------------------------ subtitles

def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, total, banner=None):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,80,80,0,204
Style: Banner,{FONT},70,&H00FFFFFF,&H00FFFFFF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,18,0,8,60,60,170,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if banner:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(total)},Banner,,0,0,0,,{esc(banner.upper())}")
    # группы по 3 слова (или до знака препинания)
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or w["w"][-1:] in ".,!?:;—":
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    for gi, g in enumerate(groups):
        g_end = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else total
        for wi, w in enumerate(g):
            start = w["s"]
            end = g[wi + 1]["s"] if wi + 1 < len(g) else g_end
            parts = []
            for k, x in enumerate(g):
                t = esc(x["w"].upper())
                parts.append("{\\c&H00E5FF&}" + t + "{\\c&HFFFFFF&}" if k == wi else t)
            pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Sub,,0,0,0,,{pop}{' '.join(parts)}")
    return head + "\n".join(lines) + "\n"


# ------------------------------------------------------------------ build

def build(spec_path):
    spec_path = Path(spec_path).resolve()
    base = spec_path.parent
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    segs = spec.get("segments") or fail("В short.json нет segments")
    voice = spec.get("voice", "ru-RU-DmitryNeural")
    rate = spec.get("rate", "+10%")
    work = base / "_work"
    work.mkdir(exist_ok=True)

    # 1. озвучка по сегментам
    all_words, offset, parts, durs = [], 0.0, [], []
    for i, s in enumerate(segs):
        mp3 = work / f"voice_{i:02d}.mp3"
        words = tts(s["text"], voice, rate, mp3)
        d = duration(mp3) + 0.12  # маленькая пауза между фразами
        for w in words:
            all_words.append({"w": w["w"], "s": w["s"] + offset, "e": w["e"] + offset})
        parts.append(mp3); durs.append(d); offset += d
    total = offset

    # склеиваем голос: каждый кусок дополняем тишиной до своей длительности
    with open(work / "voice.txt", "w", encoding="utf-8") as f:
        for i, (p, d) in enumerate(zip(parts, durs)):
            wav = work / f"voice_{i:02d}.wav"
            run(["ffmpeg", "-y", "-i", str(p), "-af", f"apad=whole_dur={d:.3f}",
                 "-t", f"{d:.3f}", "-ar", "44100", "-ac", "2", str(wav)])
            f.write(f"file '{wav.name}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "voice.txt",
         "-c:a", "libmp3lame", "-b:a", "192k", str(base / "voice.mp3")], cwd=work)

    # 2. видеоряд
    used, sources, seg_files = set(), [], []
    for i, (s, d) in enumerate(zip(segs, durs)):
        f, src = make_segment(i, s, d, base, work, used)
        seg_files.append(f); sources.append(src)
    with open(work / "video.txt", "w", encoding="utf-8") as f:
        for p in seg_files:
            f.write(f"file '{p.name}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "video.txt", "-c", "copy",
         "video.mp4"], cwd=work)

    # 3. субтитры
    (work / "subs.ass").write_text(build_ass(all_words, total, spec.get("banner")),
                                   encoding="utf-8")
    shutil.copy(work / "subs.ass", base / "subs.ass")

    # 4. финальная сборка (cwd=work, чтобы не экранировать пути Windows в фильтре)
    inputs = ["-i", "video.mp4", "-i", str(base / "voice.mp3")]
    music = spec.get("music")
    if music and (base / music).exists():
        inputs += ["-stream_loop", "-1", "-i", str(base / music)]
        af = (f"[2:a]volume={spec.get('music_volume', 0.12)}[m];"
              f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0,"
              f"afade=t=out:st={max(total-0.6,0):.2f}:d=0.6[a]")
        amap = ["-filter_complex", af, "-map", "0:v", "-map", "[a]"]
        vf = ["-vf", "ass=subs.ass"]
    else:
        amap = ["-map", "0:v", "-map", "1:a"]
        vf = ["-vf", "ass=subs.ass"]
    final = base / "short.mp4"
    run(["ffmpeg", "-y", *inputs, *vf, *amap, "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)], cwd=work)

    info = {"ok": True, "file": str(final), "duration_sec": round(total, 1),
            "segments": [{"text": s["text"][:60], "source": src}
                         for s, src in zip(segs, sources)]}
    if total > 60:
        info["warning"] = "Длиннее 60 с — лучше сократить текст (Shorts до 3 мин, но лучше 30–50 с)."
    (base / "build.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    if not spec.get("keep_work"):
        shutil.rmtree(work, ignore_errors=True)
    out(info)


def check():
    res = {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe"))}
    try:
        import edge_tts  # noqa
        res["edge_tts"] = True
    except ImportError:
        res["edge_tts"] = False
    res["PEXELS_API_KEY"] = bool(os.environ.get("PEXELS_API_KEY"))
    hints = []
    if not res["ffmpeg"]:
        hints.append("winget install Gyan.FFmpeg  (потом перезапустить терминал)")
    if not res["edge_tts"]:
        hints.append("pip install edge-tts")
    if not res["PEXELS_API_KEY"]:
        hints.append("Необязательно: бесплатный ключ на pexels.com/api → setx PEXELS_API_KEY \"ключ\"")
    res["hints"] = hints
    out(res)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(sys.argv[2])
    else:
        print(__doc__)
