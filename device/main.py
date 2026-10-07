# Claude usage dashboard for M5Stack Core2 (UIFlow2 MicroPython).
# BtnA/B/C (the touch strip under the screen) switch between Org / Team / Me.
import M5, time, gc, sys
import secrets, net, api, ui

TZ = getattr(secrets, "TZ_OFFSET_MIN", 0) * 60
MY_IDS = getattr(secrets, "MY_IDS", ())
CYCLE_MS = int(getattr(secrets, "CYCLE_S", 15) * 1000)  # auto-advance screens; 0 disables
SLEEP_MS = int(getattr(secrets, "SLEEP_S", 600) * 1000)  # blank after this long untouched; 0 disables
# seconds between refreshes; the Admin API asks for <= ~1 req/min sustained
EVERY = {"costs": 6 * 3600, "hours": 300, "mins": 90, "cc": 1800}
RETRY = 60


def local_midnight_utc(now):
    lnow = now + TZ
    return lnow - lnow % 86400 - TZ


class App:
    def __init__(self):
        self.client = api.Client(secrets.ADMIN_KEY)
        self.st = {"my_ids": MY_IDS, "err": None}
        self.due = {k: 0 for k in EVERY}
        self.daily = None
        self.tab = 0
        self.blanked = False
        self.updated = None
        self.ntp_at = 0

    # --- data ---------------------------------------------------------------
    def fetch(self, what, now):
        c, st = self.client, self.st
        if what == "costs":
            self.daily = c.costs(now)
            self.due["hours"] = self.due["mins"] = 0  # re-estimate with calibrated rates
        elif what == "hours":
            h0 = now - now % 3600
            st["hours"] = c.usage_series(h0 - 23 * 3600, now, "1h", 24)
        elif what == "mins":
            m0 = now - now % 60
            st["mins"] = c.usage_series(m0 - 59 * 60, now, "1m", 60)
            self.updated = now
        elif what == "cc":
            st["cc"] = c.claude_code(now, 7)
            st["cc_days"] = [api.ymd(now - i * 86400) for i in range(6, -1, -1)]
        self.derive(now)

    def derive(self, now):
        st = self.st
        hours, mins = st.get("hours"), st.get("mins")
        if hours is None or mins is None:
            return
        lm, um = local_midnight_utc(now), now - now % 86400
        # The API only returns completed buckets, so the hour in progress is
        # rebuilt from the minute series and appended as a partial hour.
        hour_end = hours[-1][0] + 3600 if hours else now - now % 3600
        partial = [m for m in mins if m[0] >= hour_end]
        cur = (hour_end, sum(m[1] for m in partial), sum(m[2] for m in partial), {})
        for m in partial:
            for k, v in m[3].items():
                cur[3][k] = cur[3].get(k, 0) + v
        hours = st["hours_plus"] = hours[-23:] + [cur]
        st["today_cents"] = sum(h[1] for h in hours if h[0] >= lm)
        models = {}
        for h in hours:
            if h[0] >= lm:
                for m, v in h[3].items():
                    models[m] = models.get(m, 0) + v
        st["today_models"] = models
        st["hour_cents"] = sum(m[1] for m in mins)
        st["hour_tokens"] = sum(m[2] for m in mins)
        if self.daily is not None:
            month = api.ymd(now)[:7]
            utc_today_est = sum(h[1] for h in hours if h[0] >= um)
            st["mtd_cents"] = sum(v for d, v in self.daily.items() if d.startswith(month)) + utc_today_est
            st["yday_cents"] = self.daily.get(api.ymd(um - 86400))

    def tick_network(self):
        now = time.time()
        if not net.wifi_ok():
            self.draw("reconnecting Wi-Fi...")
            if not net.wifi_connect(secrets.WIFI_SSID, secrets.WIFI_PASS):
                self.st["err"] = "Wi-Fi unavailable"
                return
        if now - self.ntp_at > 86400 and net.ntp_sync():
            self.ntp_at = now = time.time()
        for what in ("costs", "hours", "mins", "cc"):
            if now >= self.due[what]:
                self.draw("refreshing %s..." % what)
                try:
                    self.fetch(what, now)
                    print("fetched", what, "today", self.st.get("today_cents"), "60m", self.st.get("hour_cents"),
                          "mtd", self.st.get("mtd_cents"), "free", gc.mem_free())
                    self.due[what] = now + EVERY[what]
                    self.st["err"] = None
                except Exception as e:
                    sys.print_exception(e)
                    self.st["err"] = "%s: %s" % (what, e)
                    self.due[what] = now + RETRY
                gc.collect()
                return  # one request per loop pass keeps the buttons responsive

    # --- UI -----------------------------------------------------------------
    def status(self):
        if self.st.get("err"):
            return self.st["err"][:46]
        if self.updated is None:
            return "loading..."
        t = time.gmtime(self.updated + TZ)
        return "live data as of %02d:%02d  (API lag ~5 min)" % (t[3], t[4])

    def draw(self, status=None):
        if self.blanked:
            return
        try:
            batt = M5.Power.getBatteryLevel()
        except Exception:
            batt = None
        ui.render(self.tab, self.st, time.time() + TZ, status or self.status(), net.wifi_rssi(), batt)

    def poll_input(self):
        """Returns (touched, tab): any touch/press at all, and the button tab pressed if any."""
        M5.update()
        for i, b in enumerate((M5.BtnA, M5.BtnB, M5.BtnC)):
            if b.wasPressed():
                return True, i
        try:
            return M5.Touch.getCount() > 0, None
        except Exception:
            return False, None

    def run(self):
        last = shown = touched_at = time.ticks_ms()
        while True:
            touched, tab = self.poll_input()
            changed = False
            if touched:
                touched_at = time.ticks_ms()
                if self.blanked:  # the waking touch only wakes; it doesn't switch screens
                    self.blanked = False
                    self.draw()  # paint before the backlight comes on
                    ui.wake()
                    print("screen woke")
                    shown = last = touched_at
                elif tab is not None:
                    self.tab = tab
                    shown = touched_at  # a button press restarts the cycle from that screen
                    changed = True
            elif SLEEP_MS and not self.blanked and time.ticks_diff(time.ticks_ms(), touched_at) >= SLEEP_MS:
                self.blanked = True
                ui.blank()
                print("screen blanked after %ds idle" % (SLEEP_MS // 1000))
            # while blank: no cycling or redraws (draw() is a no-op), but data keeps refreshing
            if not self.blanked and not changed and CYCLE_MS and time.ticks_diff(time.ticks_ms(), shown) >= CYCLE_MS:
                self.tab = (self.tab + 1) % len(ui.TABS)
                shown = time.ticks_ms()
                changed = True
            try:
                self.tick_network()
            except Exception as e:  # never let a network hiccup kill the dashboard
                sys.print_exception(e)
                self.st["err"] = "net: %s" % e
            if changed or time.ticks_diff(time.ticks_ms(), last) > 1000:
                self.draw()
                last = time.ticks_ms()
            time.sleep_ms(30)


def boot():
    M5.begin()
    ui.init()
    ui.splash("Connecting to Wi-Fi", secrets.WIFI_SSID)
    while not net.wifi_connect(secrets.WIFI_SSID, secrets.WIFI_PASS):
        ui.splash("Wi-Fi failed, retrying", secrets.WIFI_SSID)
    ui.splash("Syncing clock")
    while not net.ntp_sync():
        time.sleep(2)
    app = App()
    app.ntp_at = time.time()
    app.run()


boot()
