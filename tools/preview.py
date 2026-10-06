#!/usr/bin/env python3
# /// script
# dependencies = ["pillow"]
# ///
"""Render the three dashboard screens to PNGs on the Mac using live Admin API data.

    preview.py OUT_DIR FONT_DIR

Runs the real device/ui.py + main.py logic against a Pillow stand-in for the M5
canvas; HTTP goes through curl. Reads .env like deploy.py. Layout check only:
fonts are approximated with Montserrat TTFs.
"""
import os, sys, types, json, time, calendar, subprocess
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, FONTS = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(ROOT, 'device'))
time.mktime = calendar.timegm
def rgb(c): return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
class Fonts: pass
F = Fonts()
for n in (12, 14, 16, 18, 24, 40, 44, 48): setattr(F, 'Montserrat%d' % n, n)
class Canvas:
    def __init__(s): s.im = Image.new('RGB', (320, 240)); s.d = ImageDraw.Draw(s.im); s.f = 14; s.fg = (255,)*3
    def font(s): return ImageFont.truetype(FONTS + '/Montserrat-%s.ttf' % ('SemiBold' if s.f >= 24 else 'Regular'), int(s.f * 0.93))
    def fillScreen(s, c): s.d.rectangle((0, 0, 319, 239), fill=rgb(c))
    def fillRect(s, x, y, w, h, c): s.d.rectangle((x, y, x + w - 1, y + h - 1), fill=rgb(c))
    def drawRect(s, x, y, w, h, c): s.d.rectangle((x, y, x + w - 1, y + h - 1), outline=rgb(c))
    def fillRoundRect(s, x, y, w, h, r, c): s.d.rounded_rectangle((x, y, x + w - 1, y + h - 1), r, fill=rgb(c))
    def drawLine(s, a, b, c2, d, c): s.d.line((a, b, c2, d), fill=rgb(c))
    def setFont(s, f): s.f = f
    def setTextColor(s, fg, bg=None): s.fg = rgb(fg)
    def _w(s, t): return s.d.textlength(t, font=s.font())
    def drawString(s, t, x, y): s.d.text((x, y), t, font=s.font(), fill=s.fg)
    def drawRightString(s, t, x, y): s.drawString(t, x - s._w(t), y)
    def drawCenterString(s, t, x, y): s.drawString(t, x - s._w(t) / 2, y)
    def push(s, x, y): pass
M5 = types.ModuleType('M5'); M5.Lcd = types.SimpleNamespace(FONTS=F, setBrightness=lambda b: None, newCanvas=lambda *a: Canvas())
sys.modules['M5'] = M5
net = types.ModuleType('net')
def get_json(host, path, headers, cafile=None):
    a = ['curl', '-sf', '--max-time', '30', 'https://' + host + path]
    for k, v in headers.items(): a += ['-H', '%s: %s' % (k, v)]
    return json.loads(subprocess.run(a, capture_output=True, check=True).stdout)
net.get_json = get_json; net.wifi_rssi = lambda: -68; sys.modules['net'] = net
env = dict(l.strip().split('=', 1) for l in open(os.path.join(ROOT, '.env')) if '=' in l and not l.startswith('#'))
sec = types.ModuleType('secrets'); sec.ADMIN_KEY = env['CLAUDE_APIKEY']; sec.MY_IDS = tuple(s.strip() for s in env.get('MY_IDS', '').split(',') if s.strip()); sec.TZ_OFFSET_MIN = int(env.get('TZ_OFFSET_MIN', 0))
sys.modules['secrets'] = sec
src = open(os.path.join(ROOT, 'device', 'main.py')).read().rsplit('\nboot()', 1)[0]
g = {'__name__': 'm'}; exec(src, g)
import ui; ui.init(); app = g['App'](); now = int(time.time())
for w in ('costs', 'hours', 'mins', 'cc'): app.fetch(w, now); app.updated = now
for tab in range(3):
    app.tab = tab; ui.render(tab, app.st, now + g['TZ'], app.status(), -68, 82)
    ui._c.im.resize((640, 480), Image.NEAREST).save('%s/screen%d-%s.png' % (OUT, tab, ui.TABS[tab].lower()))
print('wrote', OUT, {k: round(v) for k, v in app.st.items() if k.endswith('cents') and v is not None})
