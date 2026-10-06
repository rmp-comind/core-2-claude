# Wi-Fi, NTP and a small verified-TLS HTTPS GET client for the Admin API.
import network, time, socket, ssl, machine, ntptime, json, gc

# The mbedtls in UIFlow2 2.5.3 evaluates certificate validity 30 years ahead of
# the system clock (1970 vs 2000 epoch mix-up), so every cert looks expired.
# Verification stays on; we wind the RTC back by this much for the handshake only.
_MBEDTLS_EPOCH_SKEW = 946684800

_wlan = network.WLAN(network.STA_IF)
_ctx = None


def wifi_connect(ssid, password, timeout_s=30):
    _wlan.active(True)
    try:
        _wlan.config(pm=_wlan.PM_NONE)  # power-save makes a marginal link drop more often
    except Exception:
        pass
    if _wlan.isconnected():
        return True
    if _wlan.status() != network.STAT_CONNECTING:
        try:
            _wlan.disconnect()
        except OSError:
            pass
        try:
            _wlan.connect(ssid, password)
        except OSError:  # "Wifi Internal State Error": bounce the interface
            _wlan.active(False)
            time.sleep_ms(500)
            _wlan.active(True)
            _wlan.connect(ssid, password)
    t0 = time.time()
    while not _wlan.isconnected():
        if time.time() - t0 > timeout_s:
            return False
        time.sleep_ms(250)
    return True


def wifi_ok():
    return _wlan.isconnected()


def wifi_rssi():
    try:
        return _wlan.status("rssi")
    except Exception:
        return None


def ntp_sync():
    for host in ("pool.ntp.org", "time.google.com"):
        try:
            ntptime.host = host
            ntptime.settime()
            return True
        except Exception:
            pass
    return False


def _set_rtc(epoch):
    t = time.gmtime(epoch)
    machine.RTC().datetime((t[0], t[1], t[2], t[6] + 1, t[3], t[4], t[5], 0))


def _context(cafile):
    global _ctx
    if _ctx is None:
        _ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        _ctx.verify_mode = ssl.CERT_REQUIRED
        with open(cafile, "rb") as f:
            _ctx.load_verify_locations(cadata=f.read())  # PEM, so every root loads (DER takes only the first)
    return _ctx


def _tls_connect(host, cafile):
    addr = socket.getaddrinfo(host, 443, 0, socket.SOCK_STREAM)[0][-1]
    s = socket.socket()
    s.settimeout(20)
    s.connect(addr)
    now, t0 = time.time(), time.ticks_ms()
    _set_rtc(now - _MBEDTLS_EPOCH_SKEW)
    try:
        return _context(cafile).wrap_socket(s, server_hostname=host)
    except Exception:
        s.close()
        raise
    finally:
        _set_rtc(now + time.ticks_diff(time.ticks_ms(), t0) // 1000)


class HTTPError(Exception):
    def __init__(self, status, body):
        super().__init__("HTTP %d" % status)
        self.status = status
        self.body = body


def _dechunk(body):
    out, i = bytearray(), 0
    while True:
        j = body.index(b"\r\n", i)
        n = int(body[i:j].split(b";")[0], 16)
        if n == 0:
            return bytes(out)
        out += body[j + 2 : j + 2 + n]
        i = j + 2 + n + 2


def get_json(host, path, headers, cafile="/flash/ca.pem"):
    s = _tls_connect(host, cafile)
    try:
        req = "GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\nAccept: application/json\r\n" % (path, host)
        for k, v in headers.items():
            req += "%s: %s\r\n" % (k, v)
        s.write(req.encode() + b"\r\n")
        buf = bytearray()
        while True:
            chunk = s.read(4096)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    head, _, body = bytes(buf).partition(b"\r\n\r\n")
    del buf
    lines = head.split(b"\r\n")
    status = int(lines[0].split()[1])
    if any(l.lower().startswith(b"transfer-encoding:") and b"chunked" in l.lower() for l in lines[1:]):
        body = _dechunk(body)
    gc.collect()
    if status != 200:
        raise HTTPError(status, body[:300])
    return json.loads(body)
