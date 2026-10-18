"""Unified Diagnostic Services (UDS, ISO 14229) — client side.

This is how the tool talks to the car's computers. The client sends a
service request (e.g. "read the fault codes"), the ECU replies
(positive or negative response).

Services we implement:
  0x10  DiagnosticSessionControl    change mode
  0x11  ECUReset                    reset the ECU
  0x14  ClearDiagnosticInformation  erase logged fault codes
  0x19  ReadDTCInformation          list stored fault codes
  0x22  ReadDataByIdentifier        read ECU data (sensor values, PIDs)
  0x23  ReadMemoryByAddress           read a chunk of memory
  0x2e  ReadDataByPeriodicIdentifier
  0x2f  ReadScalingDataByIdentifier
  0x31  DiagnosticCommunicationControl (start/stop bus monitor)
  0x33  SecurityAccess              unlock the ECU (seed/key)
  0x34  DiagnosticRecord                access DTCs
  0x35  RequestUpload              ask ECU to send a file
  0x36  TransferData             relay chunked file data
  0x37  TransferExit             stop an ongoing upload
  0x3b  ReadDataByIdentifierN
  0x3c  ReadMemoryByAddressN
  0x3e  ReadScalingDataByIdentifierN
  0x3f  ReadDataByPeriodicIdentifierN
  0x42  WriteDataByIdentifier      write a single value to the ECU
  0x50  ReadDTCByStoredName
  0x51  ClearDiagnosticInformationN
  0x5d  WriteMemoryByAddress
  0x67  RoutineControl             start/stop a diagnostic routine (test)
  0x70  RequestUploadN          ask ECU to send a file by name
  0x71  TransferDataN          relay chunked file data (by name)
  0x77  RoutineControlByKey
  0x78  RoutineControlForTransfer
  0x7a  ClearDiagnosticInformationN
  0x7b  UploadRequestN
  0x7c  TransferDataN
  0x7d  TransferExitN

The implementation is deliberately *rule-based* (simple and transparent),
not a big state machine. Each service is a small function that takes
a request bytearray and returns a (response, comment) pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple
from enum import IntEnum

# --- negative response codes (NRC)
class Nrc(IntEnum):
    NO_ERROR = 0x00
    PENDING = 0x01
    SERVICE_NOT_SUPPORTED = 0x10
    SUB_FUNCTION_NOT_SUPPORTED = 0x11
    INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE = 0x21
    SENDING_OF_NRC_IS_NOT_PERMITTED = 0x22
    BUSY = 0x23
    NEGATIVE_RESPONSE = 0x24
    REQUEST_PENDING = 0x25
    CRITERIA_NOT_CORRESPONDING = 0x26
    REQUEST_OUT_OF_RANGE = 0x31
    CONDITIONS_NOT_CORRECT = 0x33
    REQUEST_SEMANTIC_ERROR = 0x35
    UNAVAILABLE = 0x36
    SECURITY_TOO_LOW = 0x38
    SECURITY_NOT_ACCEPTED = 0x39
    CORRUPTED_DATA = 0x3C
    FAILED_TO_EXECUTE = 0x3D
    VENDOR_OR_BYPASS = 0x3E
    WRONG_BLOCK_SEQUENCE = 0x7E
    INVALID_BLOCK = 0x7F

# --- service numbers
class ServiceId(IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECURESET = 0x11
    CLEAR_DIAGNOSTIC_INFO = 0x14
    READ_DTC_INFO = 0x19
    READ_DATA_BY_ID = 0x22
    READ_MEMORY_BY_ADDR = 0x23
    READ_DATA_BY_PERIODIC_ID = 0x2e
    READ_SCALING_DATA = 0x2f
    DIAG_COMMUNICATION_CONTROL = 0x31
    SECURITY_ACCESS = 0x33
    DIAGNOSTIC_RECORD = 0x34
    REQUEST_UPLOAD = 0x35
    TRANSFER_DATA = 0x36
    TRANSFER_EXIT = 0x37
    READ_DATA_BY_ID_N = 0x3b
    READ_MEMORY_BY_ADDR_N = 0x3c
    READ_SCALING_DATA_N = 0x3e
    READ_DATA_BY_PERIODIC_ID_N = 0x3f
    WRITE_DATA_BY_ID = 0x42
    READ_DTC_BY_STORED_NAME = 0x50
    CLEAR_DTC_INFO_N = 0x51
    WRITE_MEMORY_BY_ADDR = 0x5d
    ROUTINE_CONTROL = 0x67
    UPLOAD_REQUEST_N = 0x70
    TRANSFER_DATA_N = 0x71
    ROUTINE_CONTROL_BY_KEY = 0x77
    ROUTINE_CONTROL_FOR_TRANSFER = 0x78
    CLEAR_DTC_INFO_N2 = 0x7a
    UPLOAD_REQUEST_BY_NAME = 0x7b
    TRANSFER_DATA_BY_NAME = 0x7c
    TRANSFER_EXIT_N = 0x7d


# --- service handler table: sid -> handler(request, context) -> response
#    each handler returns (response_bytes, comment_str). The comment is
#    the "smart" part: human-friendly explanation of what is happening.
Handler = Callable[[bytes, dict], Tuple[bytes, str]]


@dataclass
class SessionContext:
    """Shared state for a conversation with one ECU."""
    ecu_name: str = "unknown ECU"
    ecu_address: int = 0x100   # CAN address (for CAN FD or functional)
    session: int = 0x01        # 0x01 = default, 0x02 = extended
    secure_data: Optional[bytes] = None
    upload_state: dict = None

    def __post_init__(self):
        if self.upload_state is None:
            self.upload_state = {}


class UdsClient:
    """A UDS conversation with one ECU.

    The *transport* (CAN / CAN FD / KWP2000) is injected from outside.
    This class only knows the UDS protocol and how to turn a service
    request into a smart, ELI5-friendly response.
    """

    def __init__(self, transport, ecu_name: str = "unknown ECU"):
        """
        transport : an object with:
            send(frame: CanFrame) -> bytes   # send a CAN frame, return raw bytes
            recv(timeout_ms: int) -> bytes   # receive one response
        """
        self.transport = transport
        self.ecu_name = ecu_name
        self.context = SessionContext(ecu_name=ecu_name)

        # Service handlers: sid -> (handler function)
        self._handlers: dict[int, Handler] = {
            ServiceId.DIAGNOSTIC_SESSION_CONTROL: self._handle_session_control,
            ServiceId.ECURESET: self._handle_ecu_reset,
            ServiceId.CLEAR_DIAGNOSTIC_INFO: self._handle_clear_dtc,
            ServiceId.READ_DTC_INFO: self._handle_read_dtc,
            ServiceId.READ_DATA_BY_ID: self._handle_read_data,
            ServiceId.READ_MEMORY_BY_ADDR: self._handle_read_memory,
            ServiceId.WRITE_DATA_BY_ID: self._handle_write_data,
            ServiceId.ROUTINE_CONTROL: self._handle_routine_control,
            ServiceId.SECURITY_ACCESS: self._handle_security_access,
            ServiceId.REQUEST_UPLOAD: self._handle_request_upload,
            ServiceId.TRANSFER_DATA: self._handle_transfer_data,
            ServiceId.TRANSFER_EXIT: self._handle_transfer_exit,
            ServiceId.READ_DATA_BY_PERIODIC_ID: self._handle_read_periodic_id,
            ServiceId.READ_SCALING_DATA: self._handle_read_scaling_data,
            ServiceId.DIAG_COMMUNICATION_CONTROL: self._handle_diag_comm_control,
            ServiceId.DIAGNOSTIC_RECORD: self._handle_diag_record,
            ServiceId.READ_DATA_BY_ID_N: self._handle_read_data_n,
            ServiceId.READ_MEMORY_BY_ADDR_N: self._handle_read_memory_n,
            ServiceId.READ_SCALING_DATA_N: self._handle_read_scaling_data_n,
            ServiceId.READ_DATA_BY_PERIODIC_ID_N: self._handle_read_periodic_id_n,
            ServiceId.CLEAR_DTC_INFO_N: self._handle_clear_dtc_n,
            ServiceId.WRITE_MEMORY_BY_ADDR: self._handle_write_memory,
            ServiceId.TRANSFER_DATA_N: self._handle_transfer_data_n,
            ServiceId.ROUTINE_CONTROL_BY_KEY: self._handle_routine_control_by_key,
            ServiceId.ROUTINE_CONTROL_FOR_TRANSFER: self._handle_routine_control_for_transfer,
            ServiceId.CLEAR_DTC_INFO_N2: self._handle_clear_dtc_n2,
            ServiceId.UPLOAD_REQUEST_N: self._handle_upload_request_n,
            ServiceId.TRANSFER_DATA_BY_NAME: self._handle_transfer_data_by_name,
            ServiceId.TRANSFER_EXIT_N: self._handle_transfer_exit_n,
        }

    # ------------------------------------------------------------------
    #  public API
    # ------------------------------------------------------------------
    def call(self, sid: int, sub_func: int, data: bytes = b"", timeout_ms: int = 500) -> Tuple[bytes, str]:
        """Send one UDS request and return (response_bytes, smart_explanation).

        This is the *only* method the GUI or CLI needs to call. It takes
        a service ID, a sub-function, and optional payload, and returns
        the raw response plus a plain-English comment.
        """
        # Build the request: SID + sub-function + payload
        request = bytes([sid, sub_func]) + data
        handler = self._handlers.get(sid)
        if handler is None:
            return self._negative_response(Nrc.SERVICE_NOT_SUPPORTED), \
                   f"Sorry, this tool doesn't support service {sid:#04x}."

        response, comment = handler(request, self.context)
        # If the ECU answered with a negative response (0x7F), wrap it.
        if response and response[0] == 0x7F:
            return response, comment
        return response, comment

    # ------------------------------------------------------------------
    #  smart explanation helper
    # ------------------------------------------------------------------
    def explain_unsupported(self, sid: int) -> str:
        """Return a friendly 'I can't do that yet' message."""
        return (f"Service {sid:#04x} isn't in this tool's toolbox yet. "
                f"Think of it like a door we haven't built a key for. "
                f"Tell the tool's builder or send the ECU's manual, and we can add it.")

    # ------------------------------------------------------------------
    #  individual service handlers
    # ------------------------------------------------------------------
    # Each handler returns (response_bytes, human_friendly_comment)

    def _handle_session_control(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "The message is missing a sub-function. Please tell me which mode to use."
        mode = req[1]
        if mode == 0x01:
            ctx.session = 0x01
            return bytes([0x10, 0x00]), "Good news — we are now in the 'default' diagnostic mode. This is like turning the ignition to 'ON' and getting ready to talk."
        elif mode == 0x02:
            ctx.session = 0x02
            return bytes([0x10, 0x00]), "We switched to 'extended' diagnostic mode. This unlocks more powerful features, like reading permanently stored fault codes."
        elif mode == 0x03:
            ctx.session = 0x03
            return bytes([0x10, 0x00]), "Extended diagnostic mode +programming (security access) enabled. Very powerful — everything is unlocked. Be careful."
        elif mode == 0x04:
            ctx.session = 0x04
            return bytes([0x10, 0x00]), "Programming mode for ECU firmware uploads. Only use on funded work and with a tester that supports it."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"That mode {mode:#04x} isn't understood yet. I can set the default or extended modes, but I haven't seen that sub-function before."

    def _handle_ecu_reset(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x11: sub-function 0x01 = hard reset, 0x02 = key-off/on, 0x03 = soft reset
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "Reset request needs a sub-function."
        mode = req[1]
        names = {0x01: "hard reset", 0x02: "key-off/on reset", 0x03: "soft reset"}
        name = names.get(mode, "unknown reset")
        if mode not in (0x01, 0x02, 0x03):
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"Reset mode {mode:#04x} not supported."
        # Note: we return a success response; the tool does NOT actually reset the ECU
        # unless the user explicitly picks a reset action in the GUI.
        return bytes([0x11, 0x00]), f"Ok — I will tell the {self.ecu_name} to do a {name}. The car should come back up. (Reset is only sent if you press the reset button in the GUI.)"

    def _handle_clear_dtc(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "Need sub-function (0x00 = clear all)."
        sub = req[1]
        if sub == 0x00:
            return bytes([0x14, 0x00]), f"Understood — we will erase all stored fault codes from the {self.ecu_name}. This wipes the 'check engine' light's memory. Only do this after fixing the problem."
        elif sub == 0x01:
            # 0x01 = clear DTCs with security access
            return bytes([0x14, 0x01, 0x00]), "Clearing with security access. This is the 'unlock before erasing' mode."
        elif sub == 0x07:
            return bytes([0x14, 0x07, 0x00]), "This sub-function clears DTCs but does not record that you did it. (Not recommended — keep a record.)"
        return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
               f"The clear sub-function {sub:#04x} isn't supported."

    def _handle_read_dtc(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "ReadDTC needs a sub-function to pick which DTC list you want."
        sub = req[1]
        if sub == 0x00:
            # No sub-function = return count of all DTCs
            return bytes([0x19, 0x00, 0x00]), f"Ok — I looked at the {self.ecu_name} and there are 0 stored fault codes in the system. Everything is clean. (00 00 means 'none')"
        elif sub == 0x01:
            return bytes([0x19, 0x01, 0x00, 0x00]), "Getting the count of all DTCs with any status. (00 00 = no faults)"
        elif sub == 0x02:
            return bytes([0x19, 0x02, 0x00, 0x00]), "Getting count of DTCs with status bit 0 set."
        elif sub == 0x03:
            return bytes([0x19, 0x03, 0x00, 0x00]), "Getting count of DTCs with status bit 0 and 1 set."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"DTC sub-function {sub:#04x} not supported."

    def _handle_read_data(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        if len(req) < 3:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "ReadDataByIdentifier needs a DataIdentifier (2 bytes)."
        did = int.from_bytes(req[1:3], "big")
        # Read the value — we return a sensible default in this example.
        value = self._read_did_dummy(did)
        payload = value.to_bytes(4, "big", signed=True)
        return bytes([0x22, 0x00]) + payload, \
               f"I asked the {self.ecu_name} to read data item {did:#06x} (ReadDataByIdentifier). It answered: {value}. This is a snapshot — values can change as the car runs."

    def _handle_read_memory(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x23: sub-func 0x01=count, 0x02=read, 0x03=read-back
        if len(req) < 4:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "ReadMemoryByAddress needs a sub-function, offset, and count."
        sub = req[1]
        offset = int.from_bytes(req[2:4], "big")
        count = int.from_bytes(req[4:6], "big")
        if sub == 0x02:
            data = bytes([offset, count])
            payload = self._read_memory_dummy(offset, count)
            return bytes([0x23, 0x00]) + payload, \
                   f"Reading {count} bytes at memory address {offset:#06x} in the {self.ecu_name}. This is like reading a page of a book from the ECU's notebook."
        elif sub == 0x03:
            return bytes([0x23, 0x00]), "Read-back is a second read of the same address to make sure the data is consistent and the ECU hasn't changed it."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"ReadMemory sub-function {sub:#04x} not supported."

    def _handle_write_data(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        if len(req) < 5:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "WriteDataByIdentifier needs a DataIdentifier and a value to write."
        did = int.from_bytes(req[1:3], "big")
        value = int.from_bytes(req[3:5], "big", signed=True)
        ok = True
        if did == 0x2001:  # example: VIN
            ok = False  # don't write a VIN
        comment = f"Writing value {value} (0x{value & 0xFFFFFFFF:08x}) to data item {did:#06x} in the {self.ecu_name}."
        if ok:
            return bytes([0x42, 0x00]), comment
        else:
            return self._negative_response(Nrc.CONDITIONS_NOT_CORRECT), \
                   comment + " (This data item can't be written — it is read-only or protected.)"

    def _handle_routine_control(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x67: sub-func 0x01=routine ON, 0x02=routine OFF, 0x03=confirm start
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "RoutineControl needs a sub-function."
        sub = req[1]
        if sub == 0x01:
            # Start a test/routine — request upload + transfer
            return bytes([0x67, 0x00]), f"Starting test routine. It's like pressing 'play' on a car diagnostic test. The ECU will run its self-test and let us know when it's done."
        elif sub == 0x02:
            return bytes([0x67, 0x00]), "Stopping the running routine. Like pressing 'stop' on a car test."
        elif sub == 0x03:
            return bytes([0x67, 0x00]), "Confirming we want the routine to start. This is a safety step — we only start the test after the user clicks 'Confirm'."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"RoutineControl sub-function {sub:#04x} not supported."

    def _handle_security_access(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x33
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "SecurityAccess needs sub-function 0x01 (request seed) or 0x02 (transmit key)."
        sub = req[1]
        if sub == 0x01:
            # Request a seed from the ECU
            seed = bytes([0x99, 0xAA])  # dummy seed
            return bytes([0x33, 0x00]) + seed, \
                   "The ECU asked for permission to let us write. I'm using a 'seed' — a temporary key — as a handshake. When the tool gets the seed and the ECU responds with a key, we can unlock the ecu to write."
        elif sub == 0x02:
            # Transmit the security key
            key = bytes([0x55, 0xCC])
            return bytes([0x33, 0x00]) + key, \
                   "Ok — here's the key the ECU asked for. With this and the seed, the ecu unlocks and we can use the final-write services."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"SecurityAccess sub-function {sub:#04x} not supported."

    def _handle_request_upload(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x35: sub-func 0x01 = count, 0x02 = start
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "RequestUpload needs a sub-function."
        sub = req[1]
        if sub == 0x01:
            return bytes([0x35, 0x00]), "Ok — the car is ready to send a file. Think of it as the ECU packing a suitcase of data and saying 'I'm ready to talk.'"
        elif sub == 0x02:
            return bytes([0x35, 0x00]), "Starting an ECU upload (file transfer). This is used for flashing firmware or reading large data blocks."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"RequestUpload sub-function {sub:#04x} not supported."

    def _handle_transfer_data(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x36: transfer data
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "TransferData needs a block count and sub-function."
        sub = req[1]
        if sub == 0x00:  # transfer data
            # Payload: req[2:]
            return bytes([0x36, 0x00, 0x00, 0x01]), "Sending chunk 0 of the file (block count 0). I'll keep sending the rest."
        elif sub == 0x01:  # flow control
            return bytes([0x36, 0x01, 0x00]), "Flow control — the ECU says 'send more' and gives a timeout."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"TransferData sub-function {sub:#04x} not supported."

    def _handle_transfer_exit(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x37: exit transfer
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "TransferExit needs a sub-function."
        sub = req[1]
        if sub == 0x00:
            return bytes([0x37, 0x00]), "Exiting the file transfer mode. The ECU knows we're done talking. Nice and clean."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"TransferExit sub-function {sub:#04x} not supported."

    def _handle_transfer_data_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x71: TransferData with security access
        if len(req) < 3:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "TransferDataN needs a block count and sub-function."
        block = req[1]
        sub = req[2]
        if sub == 0x00:  # transfer data
            return bytes([0x71, 0x00, 0x00, 0x01]), "Sending chunk 0 of the file (block count 0). I'll keep sending the rest."
        elif sub == 0x01:  # flow control
            return bytes([0x71, 0x01, 0x00]), "Flow control — the ECU says 'send more' and gives a timeout."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"TransferDataN sub-function {sub:#04x} not supported."

    def _handle_read_periodic_id(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x2e: read data by periodic identifier
        return bytes([0x2e, 0x00, 0x00]), "Reading data by periodic identifier. This is like reading a sensor value that gets updated quickly, such as engine RPM."

    def _handle_read_scaling_data(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x2f: read scaling data
        return bytes([0x2f, 0x00, 0x00]), "Reading scaling data. This is the 'fudge factor' data that converts raw sensor values into real units (like turning a raw number into degrees Celsius)."

    def _handle_diag_comm_control(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x31
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "DiagCommunicationControl needs a sub-function."
        sub = req[1]
        if sub == 0x00:  # start bus monitor
            return bytes([0x31, 0x00]), "Bus monitor started. Think of it as turning on a 'tape recorder' for the car's CAN bus. We'll log every message."
        elif sub == 0x01:  # end bus monitor
            return bytes([0x31, 0x00]), "Bus monitor stopped. The 'tape recorder' has been turned off."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"DiagCommunicationControl sub-function {sub:#04x} not supported."

    def _handle_diag_record(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x34
        return bytes([0x34, 0x00]), "DiagnosticRecord: accessing recorded DTCs, runs, and other diagnostic history. This is like reading a car's flight log."

    def _handle_read_data_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x3b: ReadDataByIdentifier with security access
        return bytes([0x3b, 0x00, 0x00]), "ReadDataByIdentifierN: the secure version of reading data. Needs security access first."

    def _handle_read_memory_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x3c
        return bytes([0x3c, 0x00, 0x00]), "ReadMemoryByAddressN: the secure version of reading memory."

    def _handle_read_scaling_data_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x3e
        return bytes([0x3e, 0x00, 0x00]), "ReadScalingDataByIdentifierN: secure scaling data read."

    def _handle_read_periodic_id_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x3f
        return bytes([0x3f, 0x00, 0x00]), "ReadDataByPeriodicIdentifierN: secure periodic identifier read."

    def _handle_clear_dtc_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x51: ClearDiagnosticInformationN
        return bytes([0x51, 0x00, 0x00]), "ClearDiagnosticInformationN: secure clear of fault codes."

    def _handle_write_memory(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x5d: WriteMemoryByAddress
        if len(req) < 4:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "WriteMemoryByAddress needs sub-function, offset, and count."
        sub = req[1]
        if sub == 0x02:
            offset = int.from_bytes(req[2:4], "big")
            count = int.from_bytes(req[4:6], "big")
            data = self._write_memory_dummy(offset, count)
            return bytes([0x5d, 0x00]) + data, \
                   f"Writing {count} bytes at memory address {offset:#06x} (WriteMemoryByAddress). This is a direct write to the ECU's memory. With great power comes great responsibility — double-check your offsets!"
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"WriteMemoryByAddress sub-function {sub:#04x} not supported."

        sub = req[1]
        if sub == 0x01:
            return bytes([0x7b, 0x00]), "UploadRequest by name is a secure way to ask the ECU to send a file. Yes, we're ready."
        # 0x71: TransferData with security access
        return bytes([0x71, 0x00, 0x00]), "TransferData with security access."

    def _handle_routine_control_by_key(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x77
        return bytes([0x77, 0x00, 0x00]), "RoutineControlByKey: start/stop a routine using security access."

    def _handle_routine_control_for_transfer(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x78
        return bytes([0x78, 0x00, 0x00]), "RoutineControlForTransfer: start a routine to transfer data."

    def _handle_clear_dtc_n2(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x7a
        return bytes([0x7a, 0x00, 0x00]), "ClearDiagnosticInformationN2: another form of secure clear."

    def _handle_upload_request_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x7b: RequestUpload by name
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "UploadRequestN needs a sub-function."
        sub = req[1]
        if sub == 0x01:
            return bytes([0x7b, 0x00]), "UploadRequest by name is a secure way to ask the ECU to send a file. Yes, we're ready."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"UploadRequestN sub-function {sub:#04x} not supported."

    def _handle_transfer_data_by_name(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x7c: TransferData by name
        return bytes([0x7c, 0x00, 0x00]), "TransferData by name."

    def _handle_transfer_exit_n(self, req: bytes, ctx: SessionContext) -> Tuple[bytes, str]:
        # 0x7d: TransferExit
        if len(req) < 2:
            return self._negative_response(Nrc.INCORRECT_MESSAGE_LENGTH_OR_MISSING_BYTE), \
                   "TransferExitN needs a sub-function."
        sub = req[1]
        if sub == 0x00:
            return bytes([0x7d, 0x00]), "Exiting the secure file transfer mode."
        else:
            return self._negative_response(Nrc.SUB_FUNCTION_NOT_SUPPORTED), \
                   f"TransferExitN sub-function {sub:#04x} not supported."

    # ------------------------------------------------------------------
    #  private dummy backends (used until real ECU access is wired)
    # ------------------------------------------------------------------
    def _read_did_dummy(self, did: int) -> int:
        """Return a plausible value for a given DataIdentifier."""
        # This is where you'd put a real lookup table from the vehicle data.
        if did == 0x2001:
            return 0x00000000            # VIN read-only
        if did == 0x2003:
            return 0x00000000            # ECU software version (dummy)
        if did == 0x2100:
            return 0x00000001            # readiness flags
        if did == 0x2110:
            return 0x00000000            # DTC count
        return 0x1234                # generic placeholder (small value)

    def _read_memory_dummy(self, offset: int, count: int) -> bytes:
        """Return a small chunk of fake memory at an offset."""
        return (offset.to_bytes(2, "big") + count.to_bytes(2, "big") + b"\x00" * count)

    def _write_memory_dummy(self, offset: int, count: int) -> bytes:
        return b"\x00" * count

    # ------------------------------------------------------------------
    #  negative response builder
    # ------------------------------------------------------------------
    def _negative_response(self, nrc: Nrc) -> bytes:
        """Build a UDS negative response frame (0x7F, NRC, code)."""
        return bytes([0x7F, nrc, 0x00])  # 0x00 as placeholder for the NRD length
