#!/usr/bin/env python3
"""Push gcode straight to a Creality printer over Moonraker — uploads AND starts it.

The K2/K1 run Klipper + Moonraker, so the file API is open on :7125. This uploads; you press
Print on the touchscreen.

It starts the job by default (2026-07-25: Oleg — "i have way higher risk tolerance then you").
Iteration speed is the point; a wasted coupon costs pennies and a minute. Pass --no-start to only
upload.

The ONE guard that stays and is NOT overridable: never overwrite the file Klipper is currently
streaming off disk. That isn't caution, it's corruption — Klipper reads the running job
progressively, so rewriting it mid-print garbles the remainder. Everything else is now opt-out.

Usage:
  python3 tools/push.py --list                # what's on the network + what each is doing
  python3 tools/push.py out/crackle_A_*.gcode # upload to the K2 Plus (default)
  python3 tools/push.py FILE --printer k1c    # or another machine
"""
import argparse, concurrent.futures, json, os, socket, sys, time, uuid
import urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import machine

# ADDRESSES MOVE. Every number below is a DHCP LEASE, not a fact — the K2 Plus took a new one on
# 2026-08-03 and read as "offline" for a day until somebody scanned the subnet by hand. So this
# table is only a first GUESS at where a machine was last seen. HOSTNAMES is what a machine IS,
# and nothing is ever pushed to an address that has not just identified itself by hostname.
PRINTERS = {            # last-known address; refreshed into CACHE as the leases move
    "k2plus": "192.168.3.140",
    "k1c":    "192.168.3.117",
    "f022":   "192.168.3.138",
}
HOSTNAMES = {           # Moonraker /printer/info `hostname` — the stable identity, confirmed on this fleet
    "k2plus": "K2Plus-22A0",
    "k1c":    "K1C-0517",
    "f022":   "F022-EAE2",
}

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".printers.json")
PROBE_TIMEOUT = 1.5     # one address. A printer on the LAN answers in ~30ms, so this is generous.
SWEEP_WORKERS = 64      # 253 addresses, 64 at a time, 1.5s each -> a whole-subnet sweep under 6s


def _probe(ip, timeout=PROBE_TIMEOUT):
    """What the Moonraker at `ip` calls itself.

    Three distinct answers, and collapsing them is how "unreachable" became meaningless: a hostname
    string (a printer, identified), "" (something IS listening on :7125 but would not name itself —
    Klipper down, or not a printer at all), and None (nothing is there)."""
    try:
        with urllib.request.urlopen(f"http://{ip}:7125/printer/info", timeout=timeout) as r:
            return json.load(r).get("result", {}).get("hostname") or ""
    except urllib.error.HTTPError:
        return ""
    except Exception:
        return None


def _subnet():
    """The /24 this laptop is on. Hardcoding 192.168.3 is the same bug as hardcoding .140."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))      # a UDP connect sends no packet; it only picks the route
        return s.getsockname()[0].rsplit(".", 1)[0]
    except Exception:
        return PRINTERS["f022"].rsplit(".", 1)[0]
    finally:
        s.close()


_SWEEP, _SWEEP_SECS = None, 0.0

def _sweep():
    """Every Moonraker on this /24 as {ip: hostname}. Swept concurrently, and once per process so
    that resolving all three printers costs at most one sweep."""
    global _SWEEP, _SWEEP_SECS
    if _SWEEP is not None:
        return _SWEEP
    net, t0 = _subnet(), time.time()
    addrs = [f"{net}.{n}" for n in range(2, 255)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=SWEEP_WORKERS) as ex:
        found = {ip: h for ip, h in zip(addrs, ex.map(_probe, addrs)) if h is not None}
    _SWEEP, _SWEEP_SECS = found, time.time() - t0
    return _SWEEP


def _cache_read():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def _cache_write(key, ip, host):
    c = _cache_read()
    c[key] = {"ip": ip, "hostname": host, "seen": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        with open(CACHE + ".tmp", "w") as f:
            json.dump(c, f, indent=2, sort_keys=True)
        os.replace(CACHE + ".tmp", CACHE)
    except Exception:
        pass                # a cache that will not write costs one sweep, never a wrong push


_RESOLVED = {}

def resolve(key, quiet=False):
    """Where `key` is RIGHT NOW, identified by HOSTNAME. None if it is not on the network.

    Order: the cached address, then the seed address, then a sweep of the whole /24. The first two
    are one request each, so the common case is instant and never sweeps; the sweep runs only when
    the machine is not where it was.

    An address is never accepted because it ANSWERED — only because the thing that answered calls
    itself the right name. A DHCP pool that hands .140 to the K1C tomorrow must not be able to send
    a K2 file there; that file runs 130mm past the K1C plate.

    "Unreachable" is two different facts and this says which: MOVED (on the network, new lease) or
    OFF (nothing anywhere answers to that name).
    """
    if key in _RESOLVED:
        return _RESOLVED[key]
    want = HOSTNAMES[key]
    say = (lambda *a: None) if quiet else print
    known, occupant = [], None
    for ip in (_cache_read().get(key, {}).get("ip"), PRINTERS[key]):
        if ip and ip not in known:
            known.append(ip)
    for ip in known:
        host = _probe(ip)
        if host and host.lower() == want.lower():
            _RESOLVED[key] = ip
            _cache_write(key, ip, host)
            return ip
        if host and occupant is None:
            occupant = (ip, host)       # somebody else holds that lease now — say so, don't push
    found = _sweep()
    hit = [ip for ip, h in found.items() if h.lower() == want.lower()]
    if not hit:
        # A re-flashed or renamed machine keeps its model prefix. Accept that only when it is the
        # ONLY such machine on the subnet, and say out loud that the table is now wrong.
        pre = want.split("-")[0].lower() + "-"
        near = [ip for ip, h in found.items() if h.lower().startswith(pre)]
        if len(near) == 1:
            say(f"{key}: hostname is {found[near[0]]!r}, not {want!r} — matched on the model prefix "
                f"and it is the only such machine here. Fix HOSTNAMES[{key!r}] in push.py.")
            hit = near
    occ = (f" A different machine, {occupant[1]!r}, holds {occupant[0]} now." if occupant else "")
    if hit:
        ip = hit[0]
        if ip in known:     # same address, different name: renamed or re-flashed, it never moved
            say(f"{key}: RENAMED — still at {ip}, but it now calls itself {found[ip]!r}. Using {ip}.")
        else:
            say(f"{key}: MOVED — {want} is no longer at {known[0]}; it now answers at {ip} "
                f"(new DHCP lease, found by sweeping {len(found)} live host(s) in "
                f"{_SWEEP_SECS:.1f}s).{occ} Using {ip}.")
        _RESOLVED[key] = ip
        _cache_write(key, ip, found[ip])
        return ip
    live = ", ".join(f"{ip} {h or '(listening, unidentified)'}" for ip, h in sorted(found.items()))
    say(f"{key}: OFF — no host on {_subnet()}.0/24 identifies as {want} (tried "
        f"{' then '.join(known)}, then swept 253 addresses in {_SWEEP_SECS:.1f}s). It is powered "
        f"off or on another network — it has NOT been re-addressed.{occ} "
        f"Moonrakers answering right now: {live or 'none'}.")
    _RESOLVED[key] = None
    return None


def api(ip, path, timeout=6):
    try:
        with urllib.request.urlopen(f"http://{ip}:7125{path}", timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": str(e)}

def status(ip):
    j = api(ip, "/printer/objects/query?print_stats&display_status")
    if "_error" in j: return {"state": "unreachable", "err": j["_error"]}
    s = j.get("result", {}).get("status", {})
    ps, ds = s.get("print_stats", {}), s.get("display_status", {})
    return {"state": ps.get("state", "?"), "file": ps.get("filename") or "-",
            "pct": round((ds.get("progress") or 0) * 100)}

def info(ip):
    j = api(ip, "/printer/info")
    return j.get("result", {}).get("hostname", "?") if "_error" not in j else "unreachable"

def gcode(ip, script, timeout=180):
    """Run a gcode command and BLOCK until the machine finishes it. Moonraker only responds when the
    command completes, so the long timeout is what makes 'home, then start' actually sequential."""
    req = urllib.request.Request(
        f"http://{ip}:7125/printer/gcode/script?script={urllib.parse.quote(script)}",
        data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.load(r)
        return True
    except Exception as e:
        print(f"   {script} FAILED: {e}")
        return False

def start(ip, name, src=None):
    # A "NO HOME" file started against an unhomed machine does NOT fail safely: Klipper accepts the
    # job, runs M190/M109, and only errors when the first move executes — so it heats the bed and
    # nozzle for minutes and dies at 0% with nothing on the plate. That is what happened to the K1C
    # honeycomb. --no-home is an optimisation for a machine already homed, never a statement about
    # the machine, so ASK the machine before trusting it.
    if src and "G28" not in open(src).read():
        st = api(ip, "/printer/objects/query?toolhead")
        axes = st.get("result", {}).get("status", {}).get("toolhead", {}).get("homed_axes", "")
        if axes != "xyz":
            print(f"   file has no G28 and {ip} reports homed_axes={axes!r} — homing first")
            gcode(ip, "G28")
    req = urllib.request.Request(f"http://{ip}:7125/printer/print/start?filename={name}",
                                 data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            json.load(r)
        # A 200 from Moonraker means the REQUEST was accepted, not that printing began. After a
        # firmware_restart the K2 answers "The motor parameters are initializing, please try again
        # later" and silently ignores both G28 and the print start -- and this used to report
        # "started" regardless. Confirm against the machine.
        for _ in range(20):
            st = api(ip, "/printer/objects/query?print_stats")
            state = st.get("result", {}).get("status", {}).get("print_stats", {}).get("state")
            if state in ("printing", "paused"):
                print(f"   ▶ started {name}")
                return True
            time.sleep(3)
        print(f"   start NOT CONFIRMED: {name} — machine still {state!r} after 60s "
              f"(motor params initializing after a restart? try again)")
        return False
    except Exception as e:
        print(f"   start FAILED: {e}")
        return False


def _validated(path):
    """Refuse to upload a file that fails validate.py.

    Every guard written today has been run BY HAND before pushing, which works until it does not:
    on 2026-07-25 a file that failed validation (Z descending below the layer floor) was uploaded
    and started anyway, because push.py never asked. A check that depends on remembering to run it
    is not a check."""
    import subprocess, sys as _s
    r = subprocess.run([_s.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "validate.py"), path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"BLOCKED: {os.path.basename(path)} fails validation —")
        for ln in r.stdout.split("\n"):
            if "FAIL" in ln:
                print("  " + ln.strip())
        print("  fix it, or pass --skip-validate if you know better than the validator.")
        return False
    return True


def printer_of(path):
    """The machine a file was BUILT for, from its own `; PRINTER=` stamp."""
    try:
        for ln in open(path):
            if ln.startswith('; PRINTER='):
                return ln.split('=', 1)[1].strip()
            if 'BODY_START' in ln:
                break
    except OSError:
        pass
    return None


def remote_differs(ip, path):
    """True if a file of this name on the printer differs from the local one.

    Regenerating a part with the same parameters produces the same FILENAME with different
    CONTENT — a hollowed spacer and a solid one are both spacer2_k1c_s6.35_c100_h14_T210.gcode.
    The printer then runs whichever was uploaded, and nothing on screen says which. Compare the
    ARGV stamp, which every generator now writes.
    """
    name = os.path.basename(path)
    try:
        req = urllib.request.Request(f"http://{ip}:7125/server/files/gcodes/{name}")
        with urllib.request.urlopen(req, timeout=15) as r:
            head = r.read(4096).decode("utf-8", "replace")
    except Exception:
        return False
    def argv_of(text):
        for ln in text.splitlines():
            if ln.startswith("; ARGV:"):
                return ln.strip()
            if "BODY_START" in ln:
                break
        return None
    return argv_of(head) != argv_of(open(path).read(4096))


def upload(ip, path, force=False, skip_validate=False):
    if not skip_validate and not _validated(path):
        return False
    st = status(ip)
    # HARD guard, not overridable: Klipper streams the running job progressively off disk.
    # Overwriting that file mid-print can corrupt the job. --force does NOT bypass this.
    if os.path.basename(path) == os.path.basename(st.get("file") or "") and st["state"] == "printing":
        print(f"BLOCKED: {os.path.basename(path)} is the file currently PRINTING on {ip}.")
        print("         Overwriting it mid-print can corrupt the job. Rename or wait.")
        return False
    if st["state"] == "printing" and not force:
        print(f"REFUSING: {ip} is PRINTING ({st['file'][:40]}, {st['pct']}%).")
        print("          Uploading is safe, but I won't touch a busy machine without --force.")
        return False
    data = open(path, "rb").read()
    name = os.path.basename(path)
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"root\"\r\n\r\ngcodes\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n".encode(),
        data, f"\r\n--{boundary}--\r\n".encode()])
    req = urllib.request.Request(f"http://{ip}:7125/server/files/upload", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            json.load(r)
        print(f"uploaded {name} ({len(data)/1024:.0f} KB) -> {ip}")
        return True
    except Exception as e:
        print(f"upload FAILED to {ip}: {e}")
        return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=list(PRINTERS))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="upload even if that printer is mid-print")
    ap.add_argument("--no-start", action="store_true", help="upload only, do not start")
    ap.add_argument("--skip-validate", action="store_true", help="push a file that fails validate.py")
    ap.add_argument("--refresh", action="store_true", help="ignore the address cache and re-resolve")
    a = ap.parse_args()
    if a.refresh:
        try: os.remove(CACHE)
        except OSError: pass
    if a.list or not a.files:
        for k in PRINTERS:
            ip = resolve(k)
            if not ip:
                print(f"  {k:<7} {'-':<15} {HOSTNAMES[k]:<14} off")
                continue
            st = status(ip)
            print(f"  {k:<7} {ip:<15} {info(ip):<14} {st['state']:<10} {st.get('pct',0):>3}%  {str(st.get('file'))[:44]}")
        sys.exit(0)
    # THE FILE MUST MATCH THE MACHINE. push knows both facts and never compared them: a K2 file
    # started on the K1C runs 130mm past the plate. The stamp is written by every generator.
    # This runs BEFORE resolution and before any socket opens, so a wrong-machine push dies offline
    # and no amount of address-hunting can route around it.
    for _f in a.files:
        _built = printer_of(_f)
        if _built and _built != a.printer:
            raise SystemExit(f"{os.path.basename(_f)} was built for {_built}, but you are sending "
                             f"it to {a.printer}. Regenerate with --printer {a.printer}.")
    ip = resolve(a.printer)
    if not ip:
        sys.exit(1)
    for _f in a.files:
        if remote_differs(ip, _f):
            print(f"   note: {os.path.basename(_f)} on {a.printer} has a DIFFERENT command stamp "
                  f"than the local file — overwriting with the local one.")
    ok = all(upload(ip, f, a.force, a.skip_validate) for f in a.files)
    if ok and not a.no_start:
        if len(a.files) > 1:
            print("   multiple files uploaded — not auto-starting; name one file to start it")
        else:
            ok = start(ip, os.path.basename(a.files[0]), src=a.files[0])
    sys.exit(0 if ok else 1)
