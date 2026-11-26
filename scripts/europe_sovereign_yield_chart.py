#!/usr/bin/env python3
"""Supplemental chart from the exact pending state; never trigger a new text alert.

No interpolation or mixing providers in the spread; no send without the existing
text ACK. Photo errors never invalidate a confirmed text delivery or cause its
retransmission. Store an independent receipt and do not retry uncertain sends.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import pathlib
import struct
import subprocess
import sys
import urllib.request
import uuid
import warnings

from scripts import europe_sovereign_yield_watch as base
from scripts.europe_sovereign_yield_telegram_html import verified_telegram_message_id

OUT = base.OUT
PNG = OUT / "europe_sovereign_yield_chart.png"
RECEIPT = OUT / "europe_sovereign_yield_photo_status.json"
MARKETS = ("uk_mkt", "fr_mkt", "it10", "de_mkt")
LABELS_KO = {"uk_mkt": "영국", "fr_mkt": "프랑스", "it10": "이탈리아", "de_mkt": "독일"}
# All modern Hangul syllables must be supported by the actual normal/bold faces.
HANGUL_GLYPHS = frozenset(range(0xAC00, 0xD7A4))
NANUM_DIR = pathlib.Path("/usr/share/fonts/truetype/nanum")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checked_date(state):
    stamp = dt.datetime.fromisoformat(state["last_checked_kst"])
    if stamp.tzinfo is None:
        raise ValueError("Missing offset-aware observation timestamp")
    return stamp.date()


def number(value):
    if isinstance(value, bool):
        raise ValueError("Not a numeric yield")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError("Non-finite yield")
    return v


def market_rows(state, key, *, days=35):
    """Retain actual dated observations only, limited to the stored as-of date."""
    end = checked_date(state)
    floor = end - dt.timedelta(days=days)
    by_date = {}
    for row in (state.get("history") or {}).get(key, []):
        try:
            day = dt.date.fromisoformat(row["date"])
            value = number(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        if floor <= day <= end:
            by_date[day] = value
    return sorted(by_date.items())


def same_date_spread(left, right):
    """Only shared dates, both from Trading Economics market series."""
    r = dict(right)
    return [(day, round((v-r[day])*100, 6)) for day, v in left if day in r]


def current(state, key):
    if key in (state.get("stale") or []):
        return None
    try:
        day = dt.date.fromisoformat(state["last_source_dates"][key])
        val = number(state["last_values"][key])
        if day <= checked_date(state):
            return day, val
    except (ValueError, TypeError, KeyError):
        pass
    return None


def live_spread(state, left, right):
    a, b = current(state, left), current(state, right)
    return round((a[1] - b[1])*100, 6) if a and b and a[0] == b[0] else None


def text_receipt(path, expected):
    if not path.is_file():
        return None
    ack = load(path)
    ids = ack.get("message_ids")
    if (ack.get("status") != "confirmed" or ack.get("lane") != "europe_sovereign_yields"
            or ack.get("chat_id_verified") is not True
            or str(ack.get("bot_username", "")).lower() != expected.lower()
            or not isinstance(ids, list) or not ids
            or any(type(mid) is not int or mid <= 0 for mid in ids)):
        raise ValueError("Missing valid existing text receipt")
    return ids[-1]


class KoreanFontUnavailable(RuntimeError):
    pass


def choose_font():
    """Select an actual Hangul-capable normal and bold font; never fall back to English."""
    from matplotlib import font_manager as fm
    from matplotlib.ft2font import FT2Font

    def covers(path):
        return HANGUL_GLYPHS.issubset(FT2Font(str(path)).get_charmap())

    # Ubuntu fonts-nanum ships distinct normal and bold TTFs. Register both
    # explicitly even if Matplotlib's cache was built before package install.
    preferred = [NANUM_DIR / "NanumGothic.ttf", NANUM_DIR / "NanumGothicBold.ttf",
                 NANUM_DIR / "NanumBarunGothic.ttf", NANUM_DIR / "NanumBarunGothicBold.ttf"]
    candidates = list(preferred)
    try:
        result = subprocess.run(["fc-list", ":lang=ko", "-f", "%{file}\n"],
                                capture_output=True, text=True, check=True, timeout=8)
        candidates += [pathlib.Path(p) for p in result.stdout.splitlines() if p]
    except (OSError, subprocess.SubprocessError):
        pass
    families = []
    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue
        try:
            if not covers(path):
                continue
            fm.fontManager.addfont(str(path))
            family = fm.FontProperties(fname=str(path)).get_name()
            if family not in families:
                families.append(family)
        except (OSError, ValueError, RuntimeError):
            continue

    for family in families:
        try:
            resolved = [fm.findfont(fm.FontProperties(family=[family], weight=w),
                                    fallback_to_default=False)
                        for w in ("normal", "bold")]
            if all(covers(path) for path in resolved):
                return family
        except (OSError, ValueError, RuntimeError):
            continue
    raise KoreanFontUnavailable("No validated Korean normal/bold font")


def ensure_korean_font():
    """Install the free Ubuntu Korean font only when the existing runner needs it."""
    try:
        return choose_font()
    except KoreanFontUnavailable:
        pass
    # This is the existing disposable GitHub-hosted Ubuntu runner; no external
    # credentials or new runner permissions. A failure is handled as photo-only.
    commands = (
        ["sudo", "-n", "apt-get", "-o", "Acquire::Retries=2",
         "-o", "Acquire::http::Timeout=20", "update", "-qq"],
        ["sudo", "-n", "apt-get", "-o", "Acquire::Retries=2",
         "-o", "Acquire::http::Timeout=20", "install", "-y", "--no-install-recommends", "fonts-nanum"],
    )
    try:
        for command in commands:
            subprocess.run(command, timeout=90, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise KoreanFontUnavailable("Korean font installation failed") from exc
    return choose_font()


def render(state, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    font = ensure_korean_font()
    plt.rcParams.update({"font.family": font, "axes.unicode_minus": False, "font.size": 12})
    labels = LABELS_KO
    data = {k: market_rows(state, k) for k in MARKETS}
    if not any(data.values()):
        raise ValueError("No actual market observations for chart")
    end = checked_date(state)
    start = min(day for series in data.values() for day, _ in series)
    if start == end:
        start -= dt.timedelta(days=1)
    fig = plt.figure(figsize=(10, 12), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.2, 1], left=.10, right=.78,
                          top=.76, bottom=.12, hspace=.32)
    ax, bx = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    title = "유럽 국채금리 경보"
    fig.text(.065, .963, title, fontsize=25, weight="bold", va="top")
    stamp = dt.datetime.fromisoformat(state["last_checked_kst"]).strftime("%Y.%m.%d %H:%M")
    fig.text(.065, .922, stamp+" 한국시간", fontsize=13, va="top")
    def official(k, label):
        point = current(state, k)
        if point:
            return f"{label} {point[1]:.3f}% ({point[0]:%m/%d})"
        return label + " 확인 불가/후행"
    f = official("fr10", "프랑스 공식 TEC10")
    g = official("de10", "독일 공식 10년")
    fig.text(.065, .881, f, fontsize=19, weight="bold", va="top")
    fig.text(.065, .844, g, fontsize=13, va="top")
    fd = live_spread(state, "fr_mkt", "de_mkt")
    it = live_spread(state, "it10", "de_mkt")
    missing = "확인 불가"
    fs = f"{fd:.1f}bp" if fd is not None else missing
    ins = f"{it:.1f}bp" if it is not None else missing
    fig.text(.065, .808, f"프랑스-독일 {fs}  |  이탈리아-독일 {ins}", fontsize=14, va="top")
    colors = dict(zip(MARKETS, plt.rcParams["axes.prop_cycle"].by_key()["color"]))
    for k, rows in data.items():
        if not rows:
            continue
        xs, ys = zip(*rows)
        ax.plot(xs, ys, marker="o", markersize=3.3, linewidth=2, color=colors[k])
        point = current(state, k)
        current_label = (f"{ys[-1]:.3f}%" if point and point[0] == xs[-1] and
                         math.isclose(point[1], ys[-1], abs_tol=1e-8)
                         else "후행/과거")
        ax.annotate(f"{labels[k]} {current_label}\n{xs[-1]:%m/%d}", (xs[-1], ys[-1]),
                    xytext=(8, 0), textcoords="offset points", va="center",
                    fontsize=11, weight="bold", color=colors[k], annotation_clip=False)
    ax.set_title("국가별 10년 시장수익률 (%)",
                 loc="left", weight="bold", fontsize=16, pad=10)
    ax.axhline(5.50, color="0.6", ls=":", lw=1)
    ax.text(start, 5.50, "영국 감시선 5.50%", fontsize=10, color="0.4", va="bottom")
    spread_series = (
        ("프랑스-독일", "fr_mkt", fd),
        ("이탈리아-독일", "it10", it),
    )
    has_spread = False
    for label, k, val in spread_series:
        rows = same_date_spread(data[k], data["de_mkt"])
        if not rows:
            continue
        has_spread = True
        xs, ys = zip(*rows)
        bx.plot(xs, ys, marker="o", markersize=3.3, linewidth=2, color=colors[k])
        current_label = f"{val:.1f}bp" if val is not None and math.isclose(val, ys[-1], abs_tol=1e-8) else "과거"
        bx.annotate(f"{label}\n{current_label}", (xs[-1], ys[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=colors[k],
                    fontsize=11, weight="bold", annotation_clip=False)
    if not has_spread:
        bx.text(.5, .3, "동일 기준일 자료 없음", transform=bx.transAxes, ha="center")
    for y in (150, 170):
        bx.axhline(y, color="0.55", ls="--", lw=.8)
        bx.text(start, y, f"감시선 {y}bp",
                fontsize=10, color="0.4", va="bottom")
    bx.set_title("독일 대비 금리차 (bp)",
                 loc="left", weight="bold", fontsize=16, pad=10)
    for panel in (ax, bx):
        panel.set_xlim(start-dt.timedelta(days=.5), end+dt.timedelta(days=.6))
        panel.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
        panel.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        panel.grid(axis="y", alpha=.2)
        panel.spines[["top", "right"]].set_visible(False)
        panel.tick_params(length=0, pad=7)
    footer = ("자료: 기존 알림과 동일한 Trading Economics 시장 관측값.\n"
              "금리차는 동일 기준일 자료만 계산. 장중 제공값은 확정 종가 아님.\n"
              "공식 중앙은행 수익률과 시장수익률은 별도 지표. 감시선은 내부 기준.")
    fig.text(.065, .075, footer, fontsize=11, va="top", linespacing=1.45)
    try:
        # A partially broken Hangul image is not an acceptable fallback.
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message=r"Glyph .* missing from font", category=UserWarning)
            fig.savefig(output, dpi=150, facecolor="white")
    except UserWarning as exc:
        output.unlink(missing_ok=True)
        raise KoreanFontUnavailable("Chart has missing glyphs") from exc
    finally:
        plt.close(fig)
    if not output.is_file() or output.stat().st_size > 10_000_000:
        raise ValueError("PNG missing or too large")
    with output.open("rb") as fobj:
        prefix = fobj.read(24)
    if prefix[:8] != b"\x89PNG\r\n\x1a\n" or len(prefix) != 24:
        raise ValueError("Invalid PNG")
    width, height = struct.unpack(">II", prefix[16:24])
    if not (width > 0 and height > 0 and width+height <= 10000 and max(width/height, height/width) <= 20):
        raise ValueError("PNG dimensions outside Telegram limits")
    return {"width": width, "height": height, "font_language": "ko"}


def multipart(fields, png):
    boundary = "europechart-" + uuid.uuid4().hex
    chunks = []
    for k, v in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="europe_yields.png"\r\nContent-Type: image/png\r\n\r\n'.encode("ascii"))
    chunks.extend([png, b"\r\n", f"--{boundary}--\r\n".encode("ascii")])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def send_photo(token, chat, expected, mid, png, caption):
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as r:
        ident = json.loads(r.read().decode("utf-8"))
    if ident.get("ok") is not True or str(ident.get("result", {}).get("username", "")).lower() != expected.lower():
        raise ValueError("Wrong Telegram bot")
    payload, content_type = multipart({
        "chat_id": chat, "caption": caption,
        "reply_parameters": json.dumps({"message_id": mid, "allow_sending_without_reply": False}),
    }, png)
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto",
                                     data=payload, headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(request, timeout=35) as r:
        reply = json.loads(r.read().decode("utf-8"))
    photo_id = verified_telegram_message_id(reply, chat)
    if not reply.get("result", {}).get("photo"):
        raise ValueError("Telegram reply lacks photo confirmation")
    return photo_id


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    state = load(base.PENDING)
    expected = os.environ.get("EXPECTED_TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    status = {"checked_at_kst": state["last_checked_kst"], "status": "render_pending"}
    try:
        mid = text_receipt(base.CONFIRMED, expected)
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                            "matplotlib==3.10.8"], timeout=150, check=True)
        status.update(render(state, PNG))
        if status.get("font_language") != "ko":
            raise KoreanFontUnavailable("Non-Korean chart blocked")
        print("europe_chart_font_language=ko")
        if mid is None:
            status["status"] = "preview_only_no_text_alert"
            save(RECEIPT, status)
            print("europe_photo_status=preview_only_no_text_alert")
            return 0
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat or not expected:
            raise ValueError("Missing existing Telegram configuration")
        caption = "유럽 국채금리·금리차 추세 (" + state["last_checked_kst"][:16].replace("T", " ") + " 한국시간)\n기존 텍스트 경보와 동일 관측값 · 시장 제공값은 확정 종가 아님"
        status["status"] = "send_unconfirmed"
        save(RECEIPT, status)
        photo_id = send_photo(token, chat, expected, mid, PNG.read_bytes(), caption)
        status.update(status="confirmed", chat_id_verified=True, message_id=photo_id)
        print("europe_photo_status=confirmed chat_id_verified=true positive_message_id=true")
    except Exception as exc:
        # Avoid logging the URL, token or any potentially private raw reply.
        status["status"] = "send_unconfirmed" if status["status"] == "send_unconfirmed" else "not_sent"
        status["error_type"] = type(exc).__name__
        print("europe_photo_status=" + status["status"] + " error_type=" + status["error_type"])
    save(RECEIPT, status)
    if base.CONFIRMED.is_file():
        # The text receipt is never removed or invalidated. The public state
        # stores only delivery status, not a private chat/message identifier.
        state["last_photo_delivery"] = {k:v for k,v in status.items() if k != "message_id"}
        save(base.PENDING, state)
    return 0 if status["status"] in ("confirmed", "preview_only_no_text_alert") else 1


if __name__ == "__main__":
    raise SystemExit(main())
