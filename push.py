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
  python3 push.py --list                      # what's on the network + what each is doing
  python3 push.py out/crackle_A_*.gcode       # upload to the K2 Plus (default)
  python3 push.py FILE --printer k1c          # or another machine
"""
import argparse, json, os, sys, urllib.request, uuid

PRINTERS = {            # discovered from Creality Print's own deviceInfo on this laptop
    "k2plus": "192.168.3.140",
    "k1c":    "192.168.3.117",
    "f022":   "192.168.3.138",
}

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
    a = ap.parse_args()
    if a.list or not a.files:
        for k, ip in PRINTERS.items():
            st = status(ip)
            print(f"  {k:<7} {ip:<15} {info(ip):<14} {st['state']:<10} {st.get('pct',0):>3}%  {str(st.get('file'))[:44]}")
        sys.exit(0)
    ip = PRINTERS[a.printer]
    # THE FILE MUST MATCH THE MACHINE. push knows both facts and never compared them: a K2 file
    # started on the K1C runs 130mm past the plate. The stamp is written by every generator.
    for _f in a.files:
        if remote_differs(ip, _f):
            print(f"   note: {os.path.basename(_f)} on {a.printer} has a DIFFERENT command stamp "
                  f"than the local file — overwriting with the local one.")
        _built = printer_of(_f)
        if _built and _built != a.printer:
            raise SystemExit(f"{os.path.basename(_f)} was built for {_built}, but you are sending "
                             f"it to {a.printer}. Regenerate with --printer {a.printer}.")
    ok = all(upload(ip, f, a.force, a.skip_validate) for f in a.files)
    if ok and not a.no_start:
        if len(a.files) > 1:
            print("   multiple files uploaded — not auto-starting; name one file to start it")
        else:
            ok = start(ip, os.path.basename(a.files[0]), src=a.files[0])
    sys.exit(0 if ok else 1)
