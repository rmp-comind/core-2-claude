# Screen rendering for the 320x240 Core2 display. Everything draws into one
# off-screen canvas which is pushed in a single blit, so redraws don't flicker.
import M5, time

W, H = 320, 240
BG, PANEL, TEXT, MUTED, LABEL, DIM = 0x141413, 0x262624, 0xFAF9F5, 0x9C9A92, 0x75736C, 0x3D3D3A
ACCENT, BLUE, GREEN, RED = 0xD97757, 0x6A9BCC, 0x8FA876, 0xE5484D
MODEL_COLORS = (ACCENT, BLUE, GREEN, 0xC2A25E, 0xB07CC6)
TABS = ("Org", "Team", "Me")

F = M5.Lcd.FONTS
_c = None


def init():
    global _c
    M5.Lcd.setBrightness(110)
    _c = M5.Lcd.newCanvas(W, H, 16, True)


def money(cents):
    d = cents / 100
    if d >= 10000:
        return "$%.1fk" % (d / 1000)
    if d >= 1000:
        s = "%d" % round(d)
        return "$" + s[:-3] + "," + s[-3:]
    return "$%.2f" % d


def tokens(n):
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if n >= div:
            return ("%.1f" % (n / div)).replace(".0", "") + suf
    return "%d" % n


def short_model(m):
    return (m or "?").replace("claude-", "")


def _text(s, x, y, font, color, align="l", bg=None):
    _c.setFont(font)
    _c.setTextColor(color, BG if bg is None else bg)
    (_c.drawString if align == "l" else _c.drawRightString if align == "r" else _c.drawCenterString)(s, x, y)


def _bars(vals, x, y, w, h, color, gap=1, hi=None, hi_color=None):
    """Bar chart of vals scaled to the max in a w x h box (baseline at y+h)."""
    n = len(vals)
    if not n:
        return
    top = max(vals) or 1
    bw = w / n
    _c.drawLine(x, y + h, x + w - 1, y + h, DIM)
    for i, v in enumerate(vals):
        bh = int(v / top * h + 0.5) if v > 0 else 0
        if v > 0 and bh == 0:
            bh = 1
        if bh:
            bx = int(x + i * bw)
            _c.fillRect(bx, y + h - bh, max(1, int(bw) - gap), bh, hi_color if i == hi else color)


def _chrome(tab, local_now, status, wifi_rssi, batt, err):
    _c.fillScreen(BG)
    _text("CLAUDE", 8, 5, F.Montserrat14, ACCENT)
    _text("usage", 72, 5, F.Montserrat14, MUTED)
    t = time.gmtime(local_now)
    _text("%02d:%02d" % (t[3], t[4]), 312, 5, F.Montserrat14, TEXT, "r")
    # wifi strength: 3 bars
    lvl = 0 if wifi_rssi is None else 3 if wifi_rssi > -60 else 2 if wifi_rssi > -72 else 1
    for i in range(3):
        _c.fillRect(250 + i * 5, 15 - i * 4, 3, 4 + i * 4, TEXT if i < lvl else DIM)
    if batt is not None and batt >= 0:
        _c.drawRect(222, 6, 20, 11, MUTED)
        _c.fillRect(242, 9, 2, 5, MUTED)
        _c.fillRect(224, 8, max(1, int(16 * batt / 100)), 7, RED if batt < 20 else GREEN)
    _c.drawLine(0, 24, W, 24, PANEL)
    # bottom tabs line up with the Core2's three touch buttons
    for i, name in enumerate(TABS):
        cx = 53 + i * 107
        on = i == tab
        if on:
            _c.fillRoundRect(cx - 34, 222, 68, 18, 6, PANEL)
        _text(name, cx, 224, F.Montserrat14, ACCENT if on else MUTED, "c", PANEL if on else BG)
    _text(status, 160, 205, F.Montserrat12, RED if err else LABEL, "c")


def _empty(msg, sub=None):
    _text(msg, 160, 95, F.Montserrat18, MUTED, "c")
    if sub:
        _text(sub, 160, 122, F.Montserrat12, LABEL, "c")


def draw_org(st):
    hours, mins = st.get("hours_plus"), st.get("mins")
    if hours is None or mins is None:
        _empty("Fetching org usage..." if not st.get("err") else "No data yet")
        return
    _text("TODAY  est.", 10, 32, F.Montserrat12, MUTED)
    _text(money(st["today_cents"]), 8, 46, F.Montserrat40, ACCENT)
    # stacked model split under today's figure
    split = sorted(st["today_models"].items(), key=lambda kv: -kv[1])
    tot = sum(v for _, v in split) or 1
    x = 10
    for i, (m, v) in enumerate(split):
        w = int(180 * v / tot)
        if w:
            _c.fillRect(x, 90, w, 4, MODEL_COLORS[i % len(MODEL_COLORS)])
            x += w
    if split:
        _text("%s %d%%" % (short_model(split[0][0]), round(100 * split[0][1] / tot)), 10, 98, F.Montserrat12, MUTED)

    _text("LAST 60 MIN", 312, 32, F.Montserrat12, MUTED, "r")
    _text(money(st["hour_cents"]), 312, 46, F.Montserrat24, TEXT, "r")
    _text(tokens(st["hour_tokens"]) + " tok", 312, 72, F.Montserrat12, MUTED, "r")
    if st.get("mtd_cents") is not None:
        _text("MTD " + money(st["mtd_cents"]), 312, 88, F.Montserrat14, TEXT, "r")
    if st.get("yday_cents") is not None:
        _text("yday " + money(st["yday_cents"]), 312, 104, F.Montserrat12, MUTED, "r")

    _text("per minute", 10, 118, F.Montserrat12, LABEL)
    _bars([m[1] for m in mins], 10, 132, 300, 22, ACCENT, gap=1)
    _text("per hour, 24h", 10, 158, F.Montserrat12, LABEL)
    _bars([h[1] for h in hours], 10, 170, 300, 24, BLUE, gap=2, hi=len(hours) - 1, hi_color=ACCENT)


def draw_team(st):
    cc = st.get("cc")
    _text("CLAUDE CODE  last 7 days", 10, 32, F.Montserrat12, MUTED)
    if cc is None:
        _empty("Fetching Claude Code stats...")
        return
    if not cc:
        _empty("No Claude Code activity", "in this org over the last 7 days")
        return
    rows = sorted(cc.items(), key=lambda kv: -kv[1]["cents"])[:6]
    top = rows[0][1]["cents"] or 1
    mine = st["my_ids"]
    _text("sess", 196, 32, F.Montserrat12, LABEL, "r")
    _text("+lines", 252, 32, F.Montserrat12, LABEL, "r")
    for i, (who, s) in enumerate(rows):
        y = 50 + i * 25
        me = who in mine
        _c.fillRect(10, y + 17, max(2, int(300 * s["cents"] / top)), 3, ACCENT if me else DIM)
        name = who.split("@")[0]
        _text(name[:15], 10, y, F.Montserrat14, ACCENT if me else TEXT)
        _text(str(s["sessions"]), 196, y, F.Montserrat14, MUTED, "r")
        _text(tokens(s["added"]), 252, y, F.Montserrat14, MUTED, "r")
        _text(money(s["cents"]), 312, y, F.Montserrat14, TEXT, "r")
    total = sum(s["cents"] for s in cc.values())
    _text("%d people/keys  total %s" % (len(cc), money(total)), 10, 190, F.Montserrat12, LABEL)


def draw_me(st):
    cc = st.get("cc")
    ids = st["my_ids"]
    _text(", ".join(ids)[:40], 10, 32, F.Montserrat12, MUTED)
    if cc is None:
        _empty("Fetching Claude Code stats...")
        return
    mine = [s for who, s in cc.items() if who in ids]
    if not mine:
        _empty("No Claude Code usage for you", "in this org's analytics (last 7 days)")
        return
    agg = {"sessions": 0, "added": 0, "removed": 0, "commits": 0, "prs": 0, "cents": 0.0, "tokens": 0}
    by_day = {}
    for s in mine:
        for k in agg:
            agg[k] += s[k]
        for d, c in s["by_day"].items():
            by_day[d] = by_day.get(d, 0) + c
    org = sum(s["cents"] for s in cc.values()) or 1
    _text("LAST 7 DAYS  est.", 10, 48, F.Montserrat12, MUTED)
    _text(money(agg["cents"]), 8, 62, F.Montserrat40, ACCENT)
    _text("%d%% of org CC spend" % round(100 * agg["cents"] / org), 10, 106, F.Montserrat12, MUTED)
    stats = (("sessions", str(agg["sessions"])), ("lines", "+%s -%s" % (tokens(agg["added"]), tokens(agg["removed"]))),
             ("commits", str(agg["commits"])), ("PRs", str(agg["prs"])), ("tokens", tokens(agg["tokens"])))
    for i, (k, v) in enumerate(stats):
        y = 48 + i * 19
        _text(k, 214, y, F.Montserrat12, LABEL, "r")
        _text(v, 312, y, F.Montserrat14, TEXT, "r")
    days = st["cc_days"]  # oldest -> newest
    _bars([by_day.get(d, 0) for d in days], 10, 140, 300, 44, ACCENT, gap=6)
    for i, d in enumerate(days):
        _text(d[8:10], int(10 + (i + 0.5) * 300 / len(days)), 188, F.Montserrat12, LABEL, "c")


def render(tab, st, local_now, status, wifi_rssi, batt):
    _chrome(tab, local_now, status, wifi_rssi, batt, bool(st.get("err")))
    (draw_org, draw_team, draw_me)[tab](st)
    _c.push(0, 0)


def splash(msg, sub=""):
    _c.fillScreen(BG)
    _text("CLAUDE", 160, 80, F.Montserrat40, ACCENT, "c")
    _text(msg, 160, 140, F.Montserrat14, TEXT, "c")
    _text(sub, 160, 162, F.Montserrat12, MUTED, "c")
    _c.push(0, 0)
