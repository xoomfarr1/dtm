"""Clean end-to-end verification for UDS service surface + ISO-TP multi-frame."""
import sys
import py_compile

sys.path.insert(0, "/root/dtm/src")

for p in (
    "/root/dtm/src/dts_monaco/protocols/uds.py",
    "/root/dtm/src/dts_monaco/protocols/iso_tp.py",
):
    py_compile.compile(p, doraise=True)
print("PASS compile")

from dts_monaco.protocols.uds import UdsClient, ServiceId, Nrc
from dts_monaco.protocols.iso_tp import (
    encode_iso_tp, decode_iso_tp_frames,
    pack_iso_tp_first_frame, pack_iso_tp_cons_sec_frame, pack_iso_tp_flow_control,
)

class StubTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
    def send(self, frame):
        self.sent.append(frame)
        return self.responses.pop(0) if self.responses else b""
    def recv(self, timeout_ms=500):
        return b""

results = []

def call(sid, sub=0x00, data=b""):
    resp, comment = c.call(sid, sub, data)
    results.append((sid, resp))
    return resp, comment

c = UdsClient(StubTransport([]), ecu_name="simECU")

# --- required services (raw handler response, before 0x40 re-tag) ---
# (sid, expected raw bytes, description)
cases = [
    (ServiceId.READ_DATA_BY_PERIODIC_ID,      b"\x2e\x00\x00\x00\x01", "0x2E read periodic id + dummy payload"),
    (ServiceId.READ_SCALING_DATA,             b"\x2f\x00\x00",         "0x2F read scaling"),
    (ServiceId.READ_SCALING_DATA_SEC,         b"\x24\x00\x00",         "0x24 read scaling N (security)"),
    (ServiceId.READ_DATA_BY_PERIODIC_ID_SEC,  b"\x2a\x00\x00\x00\x01", "0x2A read periodic N (security)"),
    (ServiceId.DYNAMICALLY_DEFINE_DATA_IDENTIFIER, b"\x2c\x00\x00",   "0x2C dynamically define data id"),
    (ServiceId.DIAGNOSTIC_RECORD,             b"\x34\x00",             "0x34 diagnostic record (comment: Reading diagnostic record...)"),
    (ServiceId.CONTROL_DTC_SETTING,           b"\x38\x00\x00",         "0x38 control DTC setting"),
    (ServiceId.READ_DATA_BY_ID_N,             b"\x3b\x00\x00",         "0x3B read data N"),
    (ServiceId.READ_MEMORY_BY_ADDR_N,         b"\x3c\x00\x00",         "0x3C read memory N"),
    (ServiceId.READ_SCALING_DATA_N,           b"\x3e\x00\x00",         "0x3E read scaling N"),
    (ServiceId.READ_DATA_BY_PERIODIC_ID_N,    b"\x3f\x00\x00",         "0x3F read periodic N"),
    (ServiceId.READ_DTC_BY_STORED_NAME,       b"\x50\x00\x00\x00\x01", "0x50 read DTC by stored name"),
    (ServiceId.CLEAR_DTC_INFO_N,              b"\x51\x00\x00",         "0x51 clear DTC info N"),
    (ServiceId.WRITE_MEMORY_BY_ADDR,          b"\x5d\x00\x00\x00\x00\x00\x00", "0x5d write memory"),
]

for sid, expected, desc in cases:
    resp, comment = c.call(sid, 0x00, b"" if b"\x00" not in expected else b"\x00\x01")
    ok = resp == expected
    results.append((0x600 + sid, ok, resp.hex(" "), expected.hex(" "), desc))
    if not ok:
        print(f"  FAIL {desc}: got {resp.hex(' ')} want {expected.hex(' ')}")

# 0x99 unsupported -> negative response
resp, _ = c.call(0x99, 0x00)
results.append((0x699, resp[0] == 0x7F, resp.hex(" "), "", "unsupported service -> 0x7F 0x10"))

# --- SID -> 0x40 translation for positive responses ---
transport = StubTransport([bytes([0x22, 0x00])])
c2 = UdsClient(transport, ecu_name="sim")
tresp, _ = c2.call(ServiceId.READ_DATA_BY_ID, 0x00, b"\x00\x01")
results.append((0x640, tresp == b"\x40\x00", tresp.hex(" "), "", "positive response re-tagged to 0x40"))

# --- ISO-TP multi-frame encode/decode ---
payload = bytes(range(256)) * 3  # 768 bytes
frames = encode_iso_tp(payload)
reassembled = decode_iso_tp_frames(frames)
results.append((0x650, len(reassembled) == 768, str(len(reassembled)), "", "roundtrip length"))
results.append((0x651, reassembled == payload, "", "", "roundtrip data equality"))
results.append((0x652, all(len(f) - 1 <= 7 for f in frames), "", "", "all frame payloads <= 7"))
single = encode_iso_tp(b"\x01\x02")
results.append((0x653, len(single) == 1, str(len(single)), "", "small payload = 1 frame"))
fc = pack_iso_tp_flow_control(0x80, 0x07, 500)
results.append((0x654, fc == b"\xb0\x07\x05\xc8", fc.hex(" "), "", "flow control frame"))

# --- report ---
all_ok = True
for sid, ok, *rest in results:
    all_ok = all_ok and ok
    if not ok:
        print(f"  FAIL {sid:#04x}: {rest}")

print("\nALL_OK" if all_ok else "\nFAILURES_PRESENT")
sys.exit(0 if all_ok else 1)
