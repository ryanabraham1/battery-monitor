#!/usr/bin/env python3
"""Pit hub for the FRC battery IR monitor nodes.

Listens on CAN, logs every IR test to SQLite keyed by the battery's NFC tag, and serves a
small web page (http://<pi>:8080) showing live nodes, every battery's history, and buttons
to trigger a test. Only dependency: python-can.

    python3 irhub.py                         # Raspberry Pi with a CAN HAT on can0
    python3 irhub.py --interface virtual     # no hardware (used by test_hub.py)
"""
import argparse
import json
import os
import sqlite3
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import can

# CAN protocol - must match firmware/include/config.h
ID_CMD, ID_STATUS, ID_UID, ID_RESULT = 0x080, 0x100, 0x180, 0x200
CMD_TEST, CMD_CHARGER, CMD_IDENTIFY, CMD_CLEAR_FAULT = 1, 2, 3, 4
STATES = {0: "no battery", 1: "idle", 2: "charging", 3: "settling", 4: "testing", 0x80: "FAULT: load stuck on"}
ERRORS = {1: "battery voltage too low", 2: "MOSFET too hot", 3: "gate driver never turned on",
          4: "pulse current too low (load resistor / thermostat open?)", 5: "pulse current too high",
          6: "no data from INA226", 7: "load current did not stop"}

GOOD_BELOW, WARN_BELOW = 15.0, 20.0   # mOhm; same defaults as the node LED
NODE_TIMEOUT = 5.0                    # seconds without a status frame before a node shows offline


def verdict(ir):
    if ir is None:
        return ""
    return "good" if ir < GOOD_BELOW else "marginal" if ir < WARN_BELOW else "bad"


def charge_percent(v_open):
    """Rough state of charge from rested open-circuit voltage (12 V AGM). Reads high right after charging."""
    pts = [(11.8, 0), (12.0, 25), (12.2, 50), (12.5, 75), (12.8, 100)]
    if v_open <= pts[0][0]:
        return 0
    for (v0, p0), (v1, p1) in zip(pts, pts[1:]):
        if v_open <= v1:
            return round(p0 + (p1 - p0) * (v_open - v0) / (v1 - v0))
    return 100


class Hub:
    def __init__(self, bus, db_path):
        self.bus = bus
        self.db_path = db_path
        self.lock = threading.Lock()
        self.nodes = {}      # node id -> live dict
        self.seen_seq = {}   # node id -> last result seq
        self.running = True
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS batteries (uid TEXT PRIMARY KEY, name TEXT, first_seen REAL)")
            db.execute("""CREATE TABLE IF NOT EXISTS tests (id INTEGER PRIMARY KEY, ts REAL, uid TEXT, node INTEGER,
                          ir_mohm REAL, v_open REAL, v_load REAL, i_pulse REAL, err INTEGER)""")

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    # ---------------------------------------------------------------- CAN in
    def rx_loop(self):
        while self.running:
            try:
                msg = self.bus.recv(0.5)
            except can.CanError:
                time.sleep(1)
                continue
            if msg is None or msg.is_extended_id or msg.is_remote_frame or len(msg.data) < 8:
                continue
            base, node = msg.arbitration_id & 0x7E0, msg.arbitration_id & 0x1F
            if node == 0:
                continue
            try:
                self.handle(base, node, bytes(msg.data))
            except Exception as e:   # one bad frame must not kill the listener
                print("frame error:", e)

    def handle(self, base, node, d):
        now = time.time()
        with self.lock:
            n = self.nodes.setdefault(node, {"uid": "", "last": None})
            if base == ID_STATUS:
                state, flags, mv, ca, _, tf = struct.unpack("<BBHhbb", d)
                n.update(seen=now, state=state, flags=flags, volts=mv / 1000, amps=ca / 100,
                         t_fet=None if tf == -128 else tf)
            elif base == ID_UID:
                ln = min(d[0], 7)
                n["uid"] = d[1:1 + ln].hex().upper()
                if n["uid"]:
                    with self._db() as db:
                        db.execute("INSERT OR IGNORE INTO batteries (uid, name, first_seen) VALUES (?, '', ?)",
                                   (n["uid"], now))
            elif base == ID_RESULT:
                ir, vo, vl, b6, seq = struct.unpack("<HHHBB", d)
                if self.seen_seq.get(node) == seq:
                    return                       # each result is sent three times
                self.seen_seq[node] = seq
                ok = ir != 0xFFFF
                uid = n["uid"] or "untagged-node-%d" % node
                row = dict(ts=now, uid=uid, node=node, ir_mohm=ir / 100 if ok else None, v_open=vo / 1000,
                           v_load=vl / 1000, i_pulse=float(b6) if ok else None, err=0 if ok else b6)
                n["last"] = row
                with self._db() as db:
                    db.execute("INSERT OR IGNORE INTO batteries (uid, name, first_seen) VALUES (?, '', ?)", (uid, now))
                    db.execute("""INSERT INTO tests (ts, uid, node, ir_mohm, v_open, v_load, i_pulse, err)
                                  VALUES (:ts, :uid, :node, :ir_mohm, :v_open, :v_load, :i_pulse, :err)""", row)

    # ---------------------------------------------------------------- CAN out
    def command(self, node, cmd, arg=0):
        data = bytes([cmd, arg, 0, 0, 0, 0, 0, 0])
        self.bus.send(can.Message(arbitration_id=ID_CMD + node, data=data, is_extended_id=False))

    # ---------------------------------------------------------------- queries
    def snapshot(self):
        now = time.time()
        with self.lock:
            nodes = []
            for nid in sorted(self.nodes):
                n = self.nodes[nid]
                if "seen" not in n:
                    continue
                online = now - n["seen"] < NODE_TIMEOUT
                nodes.append(dict(id=nid, online=online, state=STATES.get(n["state"], "state %d" % n["state"]),
                                  fault=n["state"] >= 0x80, volts=n["volts"], amps=n["amps"],
                                  t_fet=n["t_fet"], uid=n["uid"], nfc_ok=bool(n["flags"] & 4),
                                  ina_ok=bool(n["flags"] & 8), charger_connected=bool(n["flags"] & 2)))
        with self._db() as db:
            names = {r["uid"]: r["name"] for r in db.execute("SELECT uid, name FROM batteries")}
            bats = []
            for r in db.execute("""SELECT b.uid, b.name, COUNT(t.id) AS n, MIN(t.ir_mohm) AS best, MAX(t.ts) AS last_ts
                                   FROM batteries b LEFT JOIN tests t ON t.uid = b.uid AND t.err = 0
                                   GROUP BY b.uid ORDER BY b.name = '', b.name, b.uid"""):
                last = db.execute("SELECT ir_mohm, v_open FROM tests WHERE uid = ? AND err = 0 ORDER BY ts DESC LIMIT 1",
                                  (r["uid"],)).fetchone()
                trend = [x["ir_mohm"] for x in db.execute(
                    "SELECT ir_mohm FROM tests WHERE uid = ? AND err = 0 ORDER BY ts DESC LIMIT 30", (r["uid"],))][::-1]
                bats.append(dict(uid=r["uid"], name=r["name"], tests=r["n"], best=r["best"], last_ts=r["last_ts"],
                                 ir=last["ir_mohm"] if last else None, verdict=verdict(last["ir_mohm"]) if last else "",
                                 charge=charge_percent(last["v_open"]) if last else None, trend=trend))
        for n in nodes:
            n["name"] = names.get(n["uid"], "")
            with self.lock:
                last = self.nodes[n["id"]]["last"]
            if last:
                n["last_ir"] = last["ir_mohm"]
                n["last_verdict"] = verdict(last["ir_mohm"])
                n["last_error"] = ERRORS.get(last["err"], "") if last["err"] else ""
        return dict(nodes=nodes, batteries=bats, good_below=GOOD_BELOW, warn_below=WARN_BELOW)

    def history(self, uid):
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM tests WHERE uid = ? ORDER BY ts DESC LIMIT 500", (uid,))]

    def rename(self, uid, name):
        with self._db() as db:
            db.execute("UPDATE batteries SET name = ? WHERE uid = ?", (name[:40], uid))

    def export_csv(self):
        out = ["time,battery,uid,node,ir_mohm,v_open,v_load,i_pulse,error"]
        with self._db() as db:
            for r in db.execute("""SELECT t.*, b.name FROM tests t LEFT JOIN batteries b ON b.uid = t.uid ORDER BY t.ts"""):
                out.append(",".join(str(x if x is not None else "") for x in (
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])), (r["name"] or "").replace(",", " "),
                    r["uid"], r["node"], r["ir_mohm"], r["v_open"], r["v_load"], r["i_pulse"],
                    ERRORS.get(r["err"], "") if r["err"] else "")))
        return "\n".join(out) + "\n"


def make_handler(hub):
    page = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), "rb").read()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                self._send(200, page, "text/html; charset=utf-8")
            elif u.path == "/api/state":
                self._send(200, hub.snapshot())
            elif u.path == "/api/history":
                self._send(200, hub.history(parse_qs(u.query).get("uid", [""])[0]))
            elif u.path == "/api/export.csv":
                self._send(200, hub.export_csv().encode(), "text/csv")
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/api/name":
                    hub.rename(str(body["uid"]), str(body["name"]).strip())
                elif self.path == "/api/cmd":
                    node = int(body["node"])
                    cmd = {"test": CMD_TEST, "identify": CMD_IDENTIFY, "clear": CMD_CLEAR_FAULT,
                           "charger_off": CMD_CHARGER, "charger_on": CMD_CHARGER}[body["cmd"]]
                    if not 0 <= node <= 31:
                        raise ValueError("node")
                    hub.command(node, cmd, 1 if body["cmd"] == "charger_off" else 0)
                else:
                    return self._send(404, {"error": "not found"})
                self._send(200, {"ok": True})
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                self._send(400, {"error": str(e)})
            except can.CanError as e:
                self._send(503, {"error": "CAN send failed: %s" % e})

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "irhub.db"))
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    bus = can.Bus(interface=a.interface, channel=a.channel)
    hub = Hub(bus, a.db)
    threading.Thread(target=hub.rx_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(hub))
    print("hub listening on %s/%s, web page on port %d" % (a.interface, a.channel, a.port))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.running = False
        bus.shutdown()


if __name__ == "__main__":
    main()
