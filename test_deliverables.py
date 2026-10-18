"""Real test harness for the three hardware/data deliverables."""
import os
import struct
import sys
import tempfile
import traceback

sys.path.insert(0, "/root/dtm/src")

from dts_monaco.hardware.pt3gvci import (
    Pt3gVciAdapter,
    VirtualAdapter,
    find_pdua_dll,
    scan_pdua_devices,
    open_pt3g_vci,
)
from dts_monaco.hardware.base import HardwareError, HardwareType
from dts_monaco.data.smr_d import (
    parse_smr_d,
    parse_cbf,
    SmrDFile,
    CbffHeader,
    CbffSection,
    CBF_SECTION_TYPE_ODX,
    CBF_SECTION_TYPE_ECUC,
    CBF_SECTION_TYPE_CODING,
    CBF_FILE_MAGIC_2,
    CBF_FILE_MAGIC_3,
    CBF_FILE_TYPE_ODX,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def section_header(stype, offset, size, flags=0):
    return struct.pack("<IQQI", stype, offset, size, flags)


def build_cbff(xml_bytes, ecuc_records=(), coding_records=()):
    """Build a small CBFF container (24-byte section headers) and return bytes.

    One section per type (ODX / ECUC / CODING), regardless of how many
    records each section carries.
    """
    od_data = xml_bytes
    hdr = 20      # CBFF container header size
    sec_hdr = 24  # section header size (I QQ I)

    # One section per type: (section_type, data_size).
    types = []
    sizes = []
    if od_data:
        types.append(CBF_SECTION_TYPE_ODX)
        sizes.append(len(od_data))
    if ecuc_records:
        types.append(CBF_SECTION_TYPE_ECUC)
        sizes.append(len(ecuc_records) * 24)  # <I Q I I I> = 24 bytes
    if coding_records:
        types.append(CBF_SECTION_TYPE_CODING)
        sizes.append(len(coding_records) * 11)  # <I I B B B> = 11 bytes

    # Walk the file in order: container header -> section 0 header+data
    # -> section 1 header+data -> ... so each section header sits where
    # the parser expects it to be read from.
    header_offsets = []
    data_offsets = []
    cur = hdr
    for sz in sizes:
        header_offsets.append(cur)
        data_offsets.append(cur + sec_hdr)
        cur += sec_hdr + sz

    n = len(types)
    total = cur
    header = b"CBFF" + struct.pack("<IIII", 2000, total, CBF_FILE_TYPE_ODX, n)

    # Pre-allocate the whole file to `total` bytes (zero-filled).  Section
    # headers and payloads are written at their exact declared offsets.
    out = bytearray(total)
    out[0:20] = header

    for i, (stype, sz) in enumerate(zip(types, sizes)):
        out[header_offsets[i]:header_offsets[i] + sec_hdr] = section_header(stype, data_offsets[i], sz)

    payloads = []
    if od_data:
        payloads.append(od_data)
    if ecuc_records:
        payloads.append(b"".join(struct.pack("<I Q I I I", *rec) for rec in ecuc_records))
    if coding_records:
        payloads.append(b"".join(struct.pack("<I I B B B", *rec) for rec in coding_records))

    for i, payload in enumerate(payloads):
        out[data_offsets[i]:data_offsets[i] + len(payload)] = payload

    return bytes(out)


def main():
    print("=" * 60)
    print("1) PT3G-VCI driver: graceful Windows-only path (no driver on Linux)")
    print("=" * 60)
    try:
        adapter = Pt3gVciAdapter(serial_number="12345")
        adapter.open()
        check("open() raises HardwareError", False, "no exception raised")
    except HardwareError as exc:
        check("open() raises HardwareError", True)
        print(f"      message: {exc}")
        check("message mentions Windows", "Windows" in str(exc))
    except Exception as exc:  # noqa
        check("open() raises HardwareError", False, f"raised {type(exc).__name__}: {exc}")

    # module-level discovery helpers
    dll = find_pdua_dll()
    check("find_pdua_dll() returns None on non-Windows", dll is None)
    check("scan_pdua_devices() returns [] on non-Windows", scan_pdua_devices() == [])

    # virtual adapter works (headless test path)
    va = VirtualAdapter()
    va.open()
    check("VirtualAdapter.open()", va._opened)
    check("VirtualAdapter.read() before write() is None", va.read() is None)
    written = va.write(b"\x00\x00\x00\x10\x02\xAA\xBB")
    check("VirtualAdapter.write() returns byte count", written == 7)
    check("VirtualAdapter.read() after write() returns frame", va.read() == b"\x00\x00\x00\x10\x02\xAA\xBB")
    va.close()
    check("VirtualAdapter.close()", not va._opened)

    print()
    print("=" * 60)
    print("2) USB dongle adapter - python-can import wiring")
    print("=" * 60)
    import dts_monaco.hardware.usb_dongle as usb_mod
    check("module imports", True)
    check("'Bus' exported from can.interface", hasattr(usb_mod, "Bus"))
    check("Bus is can.interface.Bus", usb_mod.Bus.__module__ == "can.interface")
    check("Message / BusABC importable", "Message" in dir(usb_mod) and "BusABC" in dir(usb_mod))

    print()
    print("=" * 60)
    print("3) CBF parser: build + parse a container file")
    print("=" * 60)
    xml = b'''<ecuid><general>
      <ecuTypeDescription>Petrol</ecuTypeDescription>
      <ecuSubTypeDescription>TFSI</ecuSubTypeDescription>
      <ecuSteeringNumber>210</ecuSteeringNumber>
      <vehicleIdentificationNumber>WDD21W...</vehicleIdentificationNumber>
    </general>
    <supportedApplicationData></supportedApplicationData>
    <ecucInstances><ecucInstance id="7">
      <general>
        <ecuTypeDescription>Petrol</ecuTypeDescription>
        <ecuSubTypeDescription>TFSI</ecuSubTypeDescription>
        <ecuSteeringNumber>210</ecuSteeringNumber>
        <vehicleIdentificationNumber>WDD21W...</vehicleIdentificationNumber>
      </general>
      <config><description>Fuel injector ECU</description></config>
    </ecucInstance></ecucInstances>
    <dataIdentifier id="100" offset="256" size="2">
      <description>Engine coolant temperature</description>
      <dataType>S16</dataType>
      <minValue>-40</minValue>
      <maxValue>125</maxValue>
      <defaultValue>0</defaultValue>
    </dataIdentifier>
    <dataIdentifier id="101" offset="264" size="1">
      <description>RPM</description>
      <dataType>U8</dataType>
    </dataIdentifier>
    </ecuid>'''
    ecuc_records = [(7, 0x200, 0x200, 20, 0)]
    coding_records = [
        (100, 0x100, 2, 0x03, 0),  # S16
        (101, 0x104, 1, 0x01, 0),  # U8
    ]
    cbff = build_cbff(xml, ecuc_records, coding_records)

    with tempfile.NamedTemporaryFile(suffix=".cbf", delete=False) as f:
        f.write(cbff)
        cbf_path = f.name

    try:
        f = parse_cbf(cbf_path)
        check("parse_cbf() returns SmrDFile", isinstance(f, SmrDFile))
        check("header.magic == CBFF", f.header is not None and f.header.magic == b"CBFF")
        check("header.version == 2000", f.header is not None and f.header.version == 2000)
        check("header.file_type == ODX", f.header is not None and f.header.file_type == CBF_FILE_TYPE_ODX)
        check("header.section_count == 3", f.header is not None and f.header.section_count == 3)
        check("section table has 3 sections", len(f.sections) == 3)
        kinds = [s.kind for s in f.sections]
        check("sections: ODX, ECUC, CODING", kinds == ["ODX", "ECUC", "CODING"], str(kinds))
        check("ODX XML extracted", "<ecuid>" in f.odx_xml)
        check("ECU instance parsed", len(f.ecuc_instances) == 1)
        check("ecu_steering_number == 210", f.ecuc_instances[0].ecu_steering_number == 210)
        check("ecu_type_description parsed", "Petrol" in f.ecuc_instances[0].ecu_type_description)
        check("description parsed from config", "Fuel injector ECU" in f.ecuc_instances[0].description)
        check("code_data_addresses parsed", f.ecuc_instances[0].code_data_addresses == [0x200])
        check("coding tables parsed", len(f.coding_tables) >= 3)
        ct_ids = [c.table_id for c in f.coding_tables]
        check("table ids 100 and 101 present", 100 in ct_ids and 101 in ct_ids)
        # find the XML-derived S16 table
        s16 = [c for c in f.coding_tables if c.table_id == 100]
        if s16:
            check("S16 table offset 0x100", s16[0].offset == 0x100)
            check("S16 table size 2", s16[0].size == 2)
            check("S16 table data_type S16", s16[0].data_type == "S16")
        # binary-derived coding tables
        binaries = [c for c in f.coding_tables if c.description == "Coding table 100 (binary section)"]
        check("binary coding table added", len(binaries) >= 1)
        if binaries:
            check("binary offset", binaries[0].offset == 0x100)
            check("binary size", binaries[0].size == 2)
            check("binary data_type S16", binaries[0].data_type == "S16")
        check("total coding tables >= 3", len(f.coding_tables) >= 3)
    finally:
        os.unlink(cbf_path)

    print()
    print("=" * 60)
    print("4) SMR-D parser: plain ODX-embed file")
    print("=" * 60)
    plain_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<ecuid>
  <general>
    <ecuTypeDescription>Diesel</ecuTypeDescription>
    <ecuSubTypeDescription>CDI</ecuSubTypeDescription>
    <ecuSteeringNumber>211</ecuSteeringNumber>
    <vehicleIdentificationNumber>WDD21W...</vehicleIdentificationNumber>
  </general>
  <supportedApplicationData></supportedApplicationData>
  <ecucInstances>
    <ecucInstance id="3">
      <general>
        <ecuTypeDescription>Diesel</ecuTypeDescription>
        <ecuSubTypeDescription>CDI</ecuSubTypeDescription>
        <ecuSteeringNumber>211</ecuSteeringNumber>
        <vehicleIdentificationNumber>WDD21W...</vehicleIdentificationNumber>
      </general>
      <config><description>Injection ECU</description></config>
    </ecucInstance>
  </ecucInstances>
  <dataIdentifier id="200" offset="512" size="1">
    <description>Cylinder pressure</description>
    <dataType>U8</dataType>
  </dataIdentifier>
</ecuid>'''
    with tempfile.NamedTemporaryFile(suffix=".smr", delete=False) as f:
        f.write(plain_xml)
        plain_path = f.name
    try:
        s = parse_smr_d(plain_path)
        check("parse_smr_d() returns SmrDFile", isinstance(s, SmrDFile))
        check("version == SMR-D", s.version == "SMR-D")
        check("ODX XML extracted", "<ecuid>" in s.odx_xml)
        check("1 ECU parsed", len(s.ecuc_instances) == 1)
        check("ecu_steering_number == 211", s.ecuc_instances[0].ecu_steering_number == 211)
        check("description parsed", "Injection ECU" in s.ecuc_instances[0].description)
        check("coding table parsed", len(s.coding_tables) >= 1)
        ct = s.coding_tables[0]
        check("coding table id 200", ct.table_id == 200)
        check("coding table offset 512", ct.offset == 512)
        check("coding table size 1", ct.size == 1)
        check("coding table data_type U8", ct.data_type == "U8")
    finally:
        os.unlink(plain_path)

    print()
    print("=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
