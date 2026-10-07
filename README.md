# Core2 Claude usage dashboard

MicroPython (UIFlow2 2.5.3) dashboard for an M5Stack Core2. It polls the Anthropic Admin API directly over Wi-Fi; no laptop needed once deployed.

**Screens** (they auto-cycle every `CYCLE_S` seconds; tap a touch button under the display to jump to one, which restarts the timer):
- **Org**: today's estimated spend, last 60 min, month-to-date, yesterday's actual cost, per-minute and 24h charts.
- **Team**: Claude Code per-person/per-key spend, sessions and lines over the last 7 days.
- **Me**: the same stats for the identities in `MY_IDS`.

**Deploy:** `make deploy` (or `uv run deploy.py`). Run `make` to list the other targets: `logs`, `repl`, `reset`, `ls`, `preview` (renders the screens to `build/preview/` with live data), `backup`, `restore`, `flash-firmware`. Settings come from `.env`: `CLAUDE_APIKEY` (admin key), `WIFI_SSID`, `WIFI_PASS`, `MY_IDS` (comma-separated emails or API-key names), `TZ_OFFSET_MIN` (set to 0 when BST ends), `CYCLE_S` (seconds per screen when auto-cycling, default 15; 0 disables).

**Notes**
- Today's spend is estimated: today's token counts × effective per-token rates calibrated from the last 7 days of real billed cost (backtest: $10.85 est. vs $10.90 actual). Usage data lags ~5 min; Claude Code analytics lag ~1 h and are daily.
- TLS certificates are verified against the GTS roots in `device/ca.pem`. This firmware's mbedtls checks validity 30 years ahead of the clock, so `net.py` winds the RTC back for each handshake.
- `firmware/factory-backup-16mb.bin` restores the original firmware: `uvx esptool --port <port> write-flash 0 firmware/factory-backup-16mb.bin`.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 CoMind.

`device/ca.pem` contains Google Trust Services' public root certificates. Firmware images and fonts are downloaded at build time and are not part of this repository. UIFlow2 and MicroPython are MIT-licensed, and Montserrat is under the SIL Open Font License.
