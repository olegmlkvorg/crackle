#!/usr/bin/env python3
"""Push gcode straight to a Creality printer over Moonraker. Upload only — never auto-starts.

The K2/K1 run Klipper + Moonraker, so the file API is open on :7125. This uploads; you press
Print on the touchscreen.

WHY IT WILL NOT START THE PRINT FOR YOU (deliberate, and I'd keep it this way):
  1. There is a known bug where a job *started* remotely on recent firmware can crash the head into
     an unhomed axis. Starting from the screen avoids it entirely.
  2. Starting a print is a physical action on a hot machine in a room I can't see. Uploading is
     reversible; starting is not.
  3. All three of your printers are usually busy — this refuses to upload to a printer that is
     mid-print unless you pass --force, so a stray command can't touch a running job.

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

def upload(ip, path, force=False):
    st = status(ip)
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
        print("   now press Print on the touchscreen and pick it. (I don't start prints; see the docstring.)")
        return True
    except Exception as e:
        print(f"upload FAILED to {ip}: {e}")
        return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--printer", default="k2plus", choices=list(PRINTERS))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="upload even if that printer is mid-print")
    a = ap.parse_args()
    if a.list or not a.files:
        for k, ip in PRINTERS.items():
            st = status(ip)
            print(f"  {k:<7} {ip:<15} {info(ip):<14} {st['state']:<10} {st.get('pct',0):>3}%  {str(st.get('file'))[:44]}")
        sys.exit(0)
    ip = PRINTERS[a.printer]
    ok = all(upload(ip, f, a.force) for f in a.files)
    sys.exit(0 if ok else 1)
