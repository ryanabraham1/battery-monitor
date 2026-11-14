#!/usr/bin/env python3
"""A fake IR node speaking the same CAN protocol as the firmware.

Lets you try the hub before any boards exist:
    on the Pi:   sudo modprobe vcan && sudo ip link add vcan0 type vcan && sudo ip link set vcan0 up
                 python3 irhub.py --channel vcan0 &
                 python3 sim_node.py --channel vcan0 --id 3
"""
import argparse
import random
import struct
import threading
import time

import can

ID_CMD, ID_STATUS, ID_RESULT = 0x080, 0x100, 0x200


class SimNode:
    def __init__(self, bus, node_id, ir=13.2, uid=b""):
        self.bus, self.id, self.ir, self.uid = bus, node_id, ir, uid   # uid: bytes of an NFC tag, if any
        self.seq = 0
        self.running = True

    def send(self, base, data):
        self.bus.send(can.Message(arbitration_id=base + self.id, data=data, is_extended_id=False))

    def status(self, state=2):
        self.send(ID_STATUS, struct.pack("<BBHhbb", state, 0x1A, 13150, -420, -128, 27))
        if self.uid:
            self.send(0x180, bytes([len(self.uid)]) + self.uid.ljust(7, b"\0"))

    def result(self):
        self.seq = (self.seq + 1) & 0xFF
        ir = self.ir + random.uniform(-0.2, 0.2)
        i = 12.3
        vo = 12.92
        d = struct.pack("<HHHBB", round(ir * 100), round(vo * 1000), round((vo - ir / 1000 * i) * 1000), round(i * 10), self.seq)
        for _ in range(3):
            self.send(ID_RESULT, d)

    def run(self):
        t_status = 0
        while self.running:
            now = time.time()
            if now - t_status > 1:
                t_status = now
                self.status()
            msg = self.bus.recv(0.1)
            if msg is not None and msg.arbitration_id in (ID_CMD, ID_CMD + self.id) and msg.data and msg.data[0] == 1:
                self.status(state=4)
                self.result()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--interface", default="socketcan")
    ap.add_argument("--channel", default="vcan0")
    ap.add_argument("--id", type=int, default=1)
    a = ap.parse_args()
    node = SimNode(can.Bus(interface=a.interface, channel=a.channel), a.id)
    threading.Thread(target=node.run, daemon=True).start()
    print("simulated node %d running; Ctrl-C to stop" % a.id)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
