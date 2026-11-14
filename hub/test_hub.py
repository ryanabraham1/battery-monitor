#!/usr/bin/env python3
"""End-to-end check of the hub against a simulated node on python-can's in-process virtual bus.
Runs anywhere (no CAN hardware):  python test_hub.py
"""
import json
import os
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import can

import irhub
from sim_node import SimNode

PORT = 18080


def get(path):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=5).read())


def post(path, body):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def main():
    db = os.path.join(tempfile.mkdtemp(), "t.db")
    hub = irhub.Hub(can.Bus(interface="virtual", channel="t"), db)
    threading.Thread(target=hub.rx_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), irhub.make_handler(hub))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    node = SimNode(can.Bus(interface="virtual", channel="t"), 3)
    threading.Thread(target=node.run, daemon=True).start()

    time.sleep(1.5)
    st = get("/api/state")
    assert len(st["nodes"]) == 1 and st["nodes"][0]["id"] == 3, st
    n = st["nodes"][0]
    assert n["online"] and n["state"] == "charging" and abs(n["volts"] - 13.15) < 1e-6 and abs(n["amps"] + 4.2) < 1e-6, n
    assert n["uid"] == "04A1B2C3D4E5F6" and n["t_batt"] == 24, n

    post("/api/name", {"uid": "04A1B2C3D4E5F6", "name": "Battery 7"})
    post("/api/cmd", {"node": 3, "cmd": "test"})
    time.sleep(1.0)
    st = get("/api/state")
    b = st["batteries"][0]
    assert b["name"] == "Battery 7" and b["tests"] == 1, b          # three copies of the result -> one row
    assert 12.9 < b["ir"] < 13.5 and b["verdict"] == "good" and b["charge"] == 100, b
    assert st["nodes"][0]["name"] == "Battery 7" and st["nodes"][0]["last_verdict"] == "good"

    post("/api/cmd", {"node": 3, "cmd": "test"})
    time.sleep(1.0)
    hist = get("/api/history?uid=04A1B2C3D4E5F6")
    assert len(hist) == 2 and hist[0]["node"] == 3 and abs(hist[0]["i_pulse"] - 12.3) < 1e-6, hist

    # a failed test is logged with its error but does not count as a result
    node.seq += 1
    node.send(irhub.ID_RESULT, bytes([0xFF, 0xFF, 0, 0, 0, 0, 4, node.seq]))
    time.sleep(0.6)
    st = get("/api/state")
    assert st["batteries"][0]["tests"] == 2 and "load resistor" in st["nodes"][0]["last_error"], st

    csv = urllib.request.urlopen("http://127.0.0.1:%d/api/export.csv" % PORT).read().decode()
    assert csv.count("\n") == 4 and "Battery 7" in csv, csv
    try:
        post("/api/cmd", {"node": 99, "cmd": "test"})
        raise AssertionError("bad node id accepted")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    assert irhub.charge_percent(12.2) == 50 and irhub.charge_percent(11.0) == 0
    print("hub test passed")


if __name__ == "__main__":
    main()
