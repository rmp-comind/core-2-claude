# Anthropic Admin API: usage, cost and Claude Code analytics, reduced to what the screens draw.
import time, gc
import net

HOST = "api.anthropic.com"
TOKEN_TYPES = (
    "uncached_input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation.ephemeral_5m_input_tokens",
    "cache_creation.ephemeral_1h_input_tokens",
)
# List prices in $/MTok (input, output, cache read). Only used until real cost
# history has been fetched to calibrate effective per-token rates.
_LIST = {
    "claude-fable-5-1": (10, 50, 0.25),
    "claude-opus-5-5": (4, 20, 0.2),
    "claude-opus-5": (5, 25, 0.5),
    "claude-sonnet-5-5": (2, 10, 0.2),
    "claude-sonnet-5": (2, 10, 0.2),
    "claude-haiku-4-5": (1, 5, 0.1),
}


def iso(epoch):
    t = time.gmtime(epoch)
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % t[:6]


def ymd(epoch):
    return iso(epoch)[:10]


def parse_iso(s):
    return time.mktime((int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), int(s[17:19]), 0, 0))


def _list_rate(model, tt):
    i, o, cr = _LIST.get(model, _LIST["claude-opus-5-5"])
    usd = {"uncached_input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
           "cache_creation.ephemeral_5m_input_tokens": i * 1.25,
           "cache_creation.ephemeral_1h_input_tokens": i * 2}[tt]
    return usd / 1e4  # cents per token


def _tokens(r):
    cc = r.get("cache_creation") or {}
    return {
        "uncached_input_tokens": r.get("uncached_input_tokens", 0),
        "output_tokens": r.get("output_tokens", 0),
        "cache_read_input_tokens": r.get("cache_read_input_tokens", 0),
        "cache_creation.ephemeral_5m_input_tokens": cc.get("ephemeral_5m_input_tokens", 0),
        "cache_creation.ephemeral_1h_input_tokens": cc.get("ephemeral_1h_input_tokens", 0),
    }


class Client:
    def __init__(self, admin_key):
        self.headers = {"x-api-key": admin_key, "anthropic-version": "2023-06-01",
                        "User-Agent": "core2-claude-dash/1.0"}
        self.rates = {}  # (model, token_type) -> cents/token, calibrated from cost_report

    def _get(self, path, params):
        out, page = [], None
        while True:
            q = "&".join("%s=%s" % (k.replace("[]", "%5B%5D"), v) for k, v in params)
            if page:
                q += "&page=" + page
            try:
                d = net.get_json(HOST, path + "?" + q, self.headers)
            except OSError:  # dropped link / reset connection: one retry
                time.sleep(2)
                d = net.get_json(HOST, path + "?" + q, self.headers)
            out.extend(d.get("data", []))
            page = d.get("next_page")
            if not d.get("has_more") or not page:
                return out

    def rate(self, model, tt):
        r = self.rates.get((model, tt))
        return r if r is not None else _list_rate(model, tt)

    def est_cents(self, model, toks):
        return sum(self.rate(model, tt) * n for tt, n in toks.items() if n)

    # --- token usage -> estimated cost series -------------------------------
    def usage_series(self, start, end, width, limit):
        """[(bucket_start_epoch, est_cents, total_tokens, {model: cents})]."""
        rows = self._get("/v1/organizations/usage_report/messages", (
            ("starting_at", iso(start)), ("ending_at", iso(end)), ("bucket_width", width),
            ("limit", limit), ("group_by[]", "model")))
        series = []
        for b in rows:
            cents, toks, per = 0.0, 0, {}
            for r in b["results"]:
                t = _tokens(r)
                c = self.est_cents(r.get("model"), t)
                cents += c
                toks += sum(t.values())
                per[r.get("model") or "?"] = per.get(r.get("model") or "?", 0) + c
            series.append((parse_iso(b["starting_at"]), cents, toks, per))
        gc.collect()
        return series

    # --- daily cost (actuals) + per-token rate calibration -------------------
    def costs(self, now):
        """Returns {ymd: cents} of actual billed cost for completed UTC days."""
        today0 = now - now % 86400
        t = time.gmtime(now)
        month0 = time.mktime((t[0], t[1], 1, 0, 0, 0, 0, 0))
        start = min(month0, today0 - 7 * 86400)
        rows = self._get("/v1/organizations/cost_report", (
            ("starting_at", iso(start)), ("ending_at", iso(today0)), ("limit", 31),
            ("group_by[]", "description")))
        daily, billed = {}, {}
        cal0 = today0 - 7 * 86400
        for b in rows:
            day = parse_iso(b["starting_at"])
            for r in b["results"]:
                amt = float(r["amount"])
                daily[ymd(day)] = daily.get(ymd(day), 0) + amt
                if day >= cal0 and r.get("model") and r.get("token_type"):
                    k = (r["model"], r["token_type"])
                    billed[k] = billed.get(k, 0) + amt
        del rows
        gc.collect()
        # Same 7 days of token counts, so effective rate = billed cents / tokens.
        used = {}
        for b in self._get("/v1/organizations/usage_report/messages", (
                ("starting_at", iso(cal0)), ("ending_at", iso(today0)), ("bucket_width", "1d"),
                ("limit", 7), ("group_by[]", "model"))):
            for r in b["results"]:
                for tt, n in _tokens(r).items():
                    k = (r.get("model"), tt)
                    used[k] = used.get(k, 0) + n
        for k, cents in billed.items():
            if used.get(k):
                self.rates[k] = cents / used[k]
        gc.collect()
        return daily

    # --- Claude Code per-actor analytics (daily, ~1h lag) --------------------
    def claude_code(self, now, days=7):
        """{actor: {sessions, added, removed, commits, prs, cents, tokens, by_day{ymd: cents}}}."""
        actors = {}
        for i in range(days):
            day = ymd(now - i * 86400)
            for r in self._get("/v1/organizations/usage_report/claude_code",
                               (("starting_at", day), ("limit", 1000))):
                a = r["actor"]
                who = a.get("email_address") or a.get("api_key_name") or "?"
                s = actors.get(who)
                if s is None:
                    s = actors[who] = {"sessions": 0, "added": 0, "removed": 0, "commits": 0,
                                       "prs": 0, "cents": 0.0, "tokens": 0, "by_day": {}}
                cm = r["core_metrics"]
                s["sessions"] += cm.get("num_sessions", 0)
                s["added"] += cm["lines_of_code"]["added"]
                s["removed"] += cm["lines_of_code"]["removed"]
                s["commits"] += cm.get("commits_by_claude_code", 0)
                s["prs"] += cm.get("pull_requests_by_claude_code", 0)
                c = 0
                for m in r.get("model_breakdown", []):
                    c += m["estimated_cost"]["amount"]
                    s["tokens"] += sum(m["tokens"].values())
                s["cents"] += c
                s["by_day"][day] = s["by_day"].get(day, 0) + c
            gc.collect()
        return actors
