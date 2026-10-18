"""PT3G-VCI driver (ACTIA PDU API).

The PT3G-VCI is the interface that Porsche's PIWIS III diagnostic software
uses. On Windows it is driven by the Actia PDU API, a native Windows DLL
called XS_D_PDU_API.

How this works:
  1. The user installs the official PT3G Device Manager (which installs the
     Actia PDU API driver).
  2. Our tool finds and loads that DLL.
  3. We open the adapter by product ID (the serial number shown in the
     Device Manager).
  4. We create a CAN channel through the PDU API.
  5. Send/receive CAN frames via the PDU API functions.

This module is written with ctypes, so it requires nothing beyond the
Windows API and the official PDU API driver on the user's machine.

The PDU API function signatures (standard layout):
    uint16_t  XS_D_PDU_API_Init(void);
    uint16_t  XS_D_PDU_API_Exit(void);
    uint16_t  XS_D_PDU_API_Open(uint16_t idProduct, uint32_t timeout_ms);
    uint16_t  XS_D_PDU_API_Close(uint16_t handle);
    uint16_t  XS_D_PDU_API_OpenChannel(uint16_t handle, uint32_t baud, uint16_t hwOption);
    uint16_t  XS_D_PDU_API_CloseChannel(uint16_t handle, uint16_t channel);
    uint16_t  XS_D_PDU_API_ReadData(uint16_t handle, uint16_t channel,
                                    PDU_RX_FRAME *frame, uint32_t timeout_ms);
    uint16_t  XS_D_PDU_API_WriteData(uint16_t handle, uint16_t channel,
                                     PDU_TX_FRAME *frame);
    uint16_t  XS_D_PDU_API_GetDeviceList(PDU_DEVICE *list, uint32_t maxDevices,
                                         uint32_t *count);
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from ..hardware.base import CanHardwareAdapter, HardwareError, HardwareInfo, HardwareType

__all__ = [
    "Pt3gVciAdapter",
    "VirtualAdapter",
    "PduApiWrapper",
    "PduDevice",
    "PduRxFrame",
    "PduTxFrame",
    "find_pdua_dll",
    "scan_pdua_devices",
    "open_pt3g_vci",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The Actia PDU API DLL name
# ---------------------------------------------------------------------------
# On 64-bit Windows, the driver installs as either:
#   XS_D_PDU_API_64.dll      (64-bit build)
#   XS_D_PDU_API.dll         (32-bit build, older)
# The "Device Manager" installer places it in the system folder.
PDU_DLL_NAMES = ["XS_D_PDU_API_64.dll", "XS_D_PDU_API.dll"]

# Registry key paths that hint at the ACTIA PDU API install location.
PDU_API_REG_KEYS = [
    r"SOFTWARE\ACTIA\PDUAPI",
    r"SOFTWARE\WOW642\ACTIA\PDUAPI",
    r"SOFTWARE\Wow6432Node\ACTIA\PDUAPI",
    r"SYSTEM\CurrentControlSet\Services\PDUAPI",
]

# ---------------------------------------------------------------------------
# The actual PDU frame structures.  The PDU API treats a CAN frame as:
#     uint32_t  id;      // 32-bit CAN identifier
#     uint8_t   dlc;     // data length code  (0..8)
#     uint8_t   data[8]; // payload
#     uint8_t   rtr;     // remote transmission request (1 = RTR frame)
# For ctypes the struct is laid out as: 4-byte id, then 3 bytes of padding
# so the 8-byte data field starts on a 4-byte boundary, then RTR.
# ---------------------------------------------------------------------------
class PduDevice(ctypes.Structure):
    """One entry in the PDU API device list."""
    _fields_ = [
        ("productId", ctypes.c_uint16),
        ("instanceHandle", ctypes.c_uint16),
        ("serialNumber", ctypes.c_char * 64),
    ]


class PduRxFrame(ctypes.Structure):
    """A received CAN frame as the PDU API fills in."""
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("dlc", ctypes.c_uint8),
        ("data", ctypes.c_uint8 * 8),
        ("rtr", ctypes.c_uint8),
    ]


class PduTxFrame(ctypes.Structure):
    """A transmit CAN frame as the PDU API expects it."""
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("dlc", ctypes.c_uint8),
        ("data", ctypes.c_uint8 * 8),
        ("rtr", ctypes.c_uint8),
    ]


class PduApiWrapper:
    """Thin ctypes wrapper over the Actia PDU API DLL."""

    def __init__(self, dll_path: str):
        self.dll_path = dll_path
        try:
            self.lib = ctypes.WinDLL(dll_path)
        except OSError as exc:
            raise HardwareError(
                f"Could not load Actia PDU API DLL {dll_path!r}: {exc}. "
                "Is the official PT3G Device Manager installed?"
            ) from exc
        self._load_functions()

    def _load_functions(self) -> None:
        # --- Init / Exit ---
        self.lib.XS_D_PDU_API_Init.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_Init.argtypes = []

        # --- Open / Close (handle) ---
        self.lib.XS_D_PDU_API_Open.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_Open.argtypes = [ctypes.c_uint16, ctypes.c_uint32]  # idProduct, timeout

        self.lib.XS_D_PDU_API_Close.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_Close.argtypes = [ctypes.c_uint16]  # handle

        # --- Open / Close channel ---
        self.lib.XS_D_PDU_API_OpenChannel.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_OpenChannel.argtypes = [
            ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint16
        ]  # handle, baud, hwOption

        self.lib.XS_D_PDU_API_CloseChannel.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_CloseChannel.argtypes = [ctypes.c_uint16, ctypes.c_uint16]  # handle, channel

        # --- Read / Write data ---
        self.lib.XS_D_PDU_API_ReadData.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_ReadData.argtypes = [
            ctypes.c_uint16, ctypes.c_uint16,
            ctypes.POINTER(PduRxFrame), ctypes.c_uint32,
        ]

        self.lib.XS_D_PDU_API_WriteData.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_WriteData.argtypes = [
            ctypes.c_uint16, ctypes.c_uint16,
            ctypes.POINTER(PduTxFrame),
        ]

        # --- Get device list ---
        self.lib.XS_D_PDU_API_GetDeviceList.restype = ctypes.c_uint16
        self.lib.XS_D_PDU_API_GetDeviceList.argtypes = [
            ctypes.POINTER(PduDevice), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
        ]

    # --- Plain helpers for the adapter --- 

    def init(self) -> int:
        return self.lib.XS_D_PDU_API_Init()

    def open(self, id_product: int, timeout_ms: int = 5000) -> int:
        return self.lib.XS_D_PDU_API_Open(id_product, timeout_ms)

    def close(self, handle: int) -> int:
        return self.lib.XS_D_PDU_API_Close(handle)

    def open_channel(self, handle: int, baud: int = 500000, hw_option: int = 0) -> int:
        return self.lib.XS_D_PDU_API_OpenChannel(handle, baud, hw_option)

    def close_channel(self, handle: int, channel: int) -> int:
        return self.lib.XS_D_PDU_API_CloseChannel(handle, channel)

    def read_data(self, handle: int, channel: int, timeout_ms: int = 100) -> Optional[bytes]:
        """Read one raw CAN frame (id 4 bytes + dlc + data)."""
        frame = PduRxFrame()
        res = self.lib.XS_D_PDU_API_ReadData(handle, channel, ctypes.byref(frame), timeout_ms)
        if res != 0:
            logger.warning(f"PDU API ReadData failed with code {res}")
            return None
        return self._frame_to_bytes(frame)

    def write_data(self, handle: int, channel: int, frame: bytes) -> int:
        """Transmit one raw CAN frame (id 4 bytes + dlc + data)."""
        if len(frame) < 5:
            logger.warning(f"PDU API WriteData: frame too short ({len(frame)} bytes)")
            return 0
        tx = PduTxFrame()
        tx.id = int.from_bytes(frame[0:4], "big", signed=False)
        tx.dlc = frame[4] & 0xFF
        data = frame[5:5 + tx.dlc]
        for i, b in enumerate(data):
            tx.data[i] = b
        res = self.lib.XS_D_PDU_API_WriteData(handle, channel, ctypes.byref(tx))
        return res

    def _frame_to_bytes(self, frame: PduRxFrame) -> bytes:
        data = bytes(frame.data[: frame.dlc])
        return frame.id.to_bytes(4, "big", signed=False) + bytes([frame.dlc]) + data

    def get_device_list(self, max_devices: int = 32) -> list[dict]:
        """Query the hardware for connected devices and their serial numbers."""
        buf = (PduDevice * max_devices)()
        count = ctypes.c_uint32(0)
        res = self.lib.XS_D_PDU_API_GetDeviceList(
            buf, ctypes.sizeof(buf), ctypes.byref(count)
        )
        if res != 0:
            logger.warning(f"PDU API GetDeviceList failed with code {res}")
            return []
        devices = []
        for i in range(count.value):
            dev = buf[i]
            serial = dev.serialNumber.decode("utf-8", errors="replace").strip()
            devices.append({
                "product_id": dev.productId,
                "instance_handle": dev.instanceHandle,
                "serial_number": serial,
            })
        return devices


# --- A simple virtual adapter for development and testing ---
class VirtualAdapter(CanHardwareAdapter):
    """A software CAN channel that needs no hardware.

    Great for development, testing, and for the user to check that the
    tool's *logic* works before plugging in hardware.
    """

    def __init__(self, name: str = "virtual"):
        self.name = name
        self._opened = False
        self._queue: list[bytes] = []

    def open(self) -> None:
        self._queue = []
        self._opened = True

    def close(self) -> None:
        self._opened = False
        self._queue.clear()

    def read(self, timeout_ms: int = 100) -> bytes | None:
        if not self._opened or not self._queue:
            return None
        return self._queue.pop(0)  # FIFO

    def write(self, frame: bytes) -> int:
        if not self._opened:
            return 0
        self._queue.append(frame)
        return len(frame)

    def get_info(self) -> HardwareInfo:
        return HardwareInfo(kind=HardwareType.VIRTUAL, port=self.name, channels=1)

    def test(self) -> bool:
        return self._opened


# --- The actual hardware adapter class ---
class Pt3gVciAdapter(CanHardwareAdapter):
    """Adapt the PT3G-VCI (ACTIA PDU API) to our clean hardware contract.

    This is the only module the rest of the tool must import when using
    an actual PT3G-VCI. If the driver is not installed, we fail clearly
    and tell the user what to do.
    """

    def __init__(self, serial_number: str = "", baud: int = 500000):
        self.serial_number = serial_number
        self.baud = baud
        self.handle: int = 0
        self.channel: int = 0
        self._api: Optional[PduApiWrapper] = None
        self._opened = False

    # ------------------------------------------------------------------
    def open(self) -> None:
        """Find the driver and open the PT3G-VCI adapter."""
        # 1) Find the DLL (Windows only)
        if sys.platform != "win32":
            raise HardwareError(
                "PT3G-VCI support requires Windows. The adapter is driven "
                "by the Actia PDU API, which is only available on Windows. "
                "Please run DTS Monaco on a Windows machine and install the "
                "official PT3G Device Manager (or the PIWIS III setup media)."
            )
        dll_path = self._find_dll()
        if not dll_path:
            raise HardwareError(
                "Actia PDU API driver not found. Install the official PT3G "
                "Device Manager from the PIWIS III setup media. The driver "
                "installs as XS_D_PDU_API_64.dll in the system folder. "
                "Confirm the adapter appears in Device Manager > ACTIA PDU API."
            )
        self._api = PduApiWrapper(dll_path)

        # 2) Initialise the PDU API
        init_result = self._api.init()
        if init_result != 0:
            raise HardwareError(f"PDU API init failed with code {init_result}")

        # 3) Resolve the product ID for our device (by serial number if set)
        id_product = self._resolve_device_id()
        if id_product == 0:
            found = self._query_device_list()
            if found:
                raise HardwareError(
                    f"Could not match the requested PT3G-VCI. Connected "
                    f"devices: {found!r}"
                )
            raise HardwareError(
                "No PT3G-VCI devices found. Check Device Manager > ACTIA PDU "
                "API that the adapter is listed and the driver is running."
            )

        # 4) Open the device
        self.handle = self._api.open(id_product)
        if self.handle == 0:
            raise HardwareError("Failed to open the PT3G-VCI device.")

        # 5) Open a CAN channel (default 500 kbps)
        self.channel = self._api.open_channel(self.handle, self.baud)
        if self.channel == 0:
            raise HardwareError("Failed to open a CAN channel on the PT3G-VCI.")

        self._opened = True

    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._opened:
            if self.channel:
                try:
                    self._api.close_channel(self.handle, self.channel)
                except Exception:
                    pass
            if self.handle:
                try:
                    self._api.close(self.handle)
                except Exception:
                    pass
            self._opened = False

    # ------------------------------------------------------------------
    def read(self, timeout_ms: int = 100) -> bytes | None:
        """Return one raw CAN frame (id 4 bytes + dlc + data), or None."""
        if not self._opened:
            return None
        return self._api.read_data(self.handle, self.channel, timeout_ms)

    # ------------------------------------------------------------------
    def write(self, frame: bytes) -> int:
        """Transmit a raw CAN frame (id 4 bytes + dlc + data)."""
        if not self._opened:
            return 0
        return self._api.write_data(self.handle, self.channel, frame)

    # ------------------------------------------------------------------
    def get_info(self) -> HardwareInfo:
        return HardwareInfo(
            kind=HardwareType.PT3G_VCI,
            port="COM:? (Actia PDU API)",
            vendor_id="ACTIA / Porsche",
            product_id="PT3G-VCI",
            serial=self.serial_number or "unknown",
            channels=1,
        )

    # ------------------------------------------------------------------
    def test(self) -> bool:
        """Send a heartbeat and check the adapter is alive."""
        try:
            if not self._opened:
                return False
            # Probe the channel with a short read. On a quiet bus nothing
            # may arrive, but a successfully opened handle means the
            # adapter is alive and responsive.
            self._api.read_data(self.handle, self.channel, timeout_ms=100)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------
    def _find_dll(self) -> str | None:
        """Probe the filesystem for the PDU API DLL."""
        if sys.platform != "win32":
            return None

        candidates: list[str] = []

        # 1) Known system folders (%WINDIR%\\System32 / \\SysWOW64)
        windir = os.environ.get("WINDIR")
        if windir:
            for subsystem in ("System32", "SysWOW64"):
                for name in PDU_DLL_NAMES:
                    candidates.append(os.path.join(windir, subsystem, name))

        # 2) Registry hints from the ACTIA install keys
        candidates.extend(self._read_registry_paths())

        # 3) Common install locations
        for base in (
            r"C:\ACTIA",
            r"D:\ACTIA",
            r"C:\Program Files\ACTIA",
            r"C:\Program Files (x86)\ACTIA",
            r"C:\Program Files\ACTIA\PT3G",
            r"C:\Program Files (x86)\ACTIA\PT3G",
        ):
            for name in PDU_DLL_NAMES:
                candidates.append(os.path.join(base, name))

        seen: set[str] = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            if os.path.isfile(path):
                logger.info(f"Actia PDU API DLL found: {path}")
                return path
        return None

    def _read_registry_paths(self) -> list[str]:
        """Return install directory strings from the ACTIA registry keys."""
        paths: list[str] = []
        try:
            import winreg
        except ImportError:
            return paths

        try:
            keys = PDU_API_REG_KEYS
        except NameError:
            return paths

        for key in keys:
            try:
                handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key)
            except OSError:
                continue
            with handle:
                try:
                    num_values = winreg.QueryInfoKey(handle)[1]
                except OSError:
                    continue
                for i in range(num_values):
                    try:
                        _, value, _ = winreg.EnumValue(handle, i)
                    except OSError:
                        continue
                    if isinstance(value, str) and value.strip():
                        paths.append(value.strip())
        return paths

    def _query_device_list(self) -> list[dict]:
        """Ask the PDU API for connected devices (best effort)."""
        if self._api is None:
            return []
        try:
            return self._api.get_device_list()
        except Exception as exc:
            logger.warning(f"Device discovery failed: {exc}")
            return []

    def _resolve_device_id(self) -> int:
        """Resolve the Windows product ID for a serial number (or the first device)."""
        target = self.serial_number.strip()
        devices = self._query_device_list()

        if not target:
            # No serial given: open the first connected device we can find.
            if devices:
                return int(devices[0].get("product_id") or 0)
            return 0

        for dev in devices:
            if dev.get("serial_number", "").strip().lower() == target.lower():
                return int(dev.get("product_id") or 0)
        return 0


# --- Convenience module-level functions ---
def find_pdua_dll() -> str | None:
    """Locate the Actia PDU API DLL without opening a device."""
    adapter = Pt3gVciAdapter()
    return adapter._find_dll()


def scan_pdua_devices() -> list[dict]:
    """List connected PT3G-VCI devices through the PDU API."""
    adapter = Pt3gVciAdapter()
    return adapter._query_device_list()


def open_pt3g_vci(serial_number: str = "", baud: int = 500000) -> Pt3gVciAdapter:
    """Open a PT3G-VCI adapter by serial number (Windows only)."""
    adapter = Pt3gVciAdapter(serial_number=serial_number, baud=baud)
    adapter.open()
    return adapter
