"""SMR-D / ODX data file parser.

The SMR-D file format is built on ODX (ISO 22901) and is used by the
DTS Monaco to describe each ECU's capabilities, coding tables, and
diagnostic services. A typical SMR-D file looks like this:

  [Header]                    16 bytes
  [Section count]             1 byte
  [ODX XML section]           starts with "ODX" magic + size
  [Binary sections...]        arbitrary

The ODX section is an XML document with this general shape:

  <ecuid>
    <general>
      <ecuTypeDescription>...</ecuTypeDescription>
      <ecuSubTypeDescription>...</ecuSubTypeDescription>
      <ecuSteeringNumber>123</ecuSteeringNumber>
      <vehicleIdentificationNumber>...
    </general>
    <supportedApplicationData>
      <!-- lists of services, coding tables, etc. -->
    </supportedApplicationData>
    <ecucInstances>
      <!-- ECU-specific instances with offsets for coding tables -->
    </ecucInstances>
  </ecuid>

This module parses the ODX XML into plain Python structures so the rest
of the tool can read the coding tables, service lists, and ECU metadata
without knowing the XML format.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# --- ODX magic identifiers (the header declares the section type)
ODX_SECTION_MAGIC = b"ODX"
CBF_HEADER_MAGIC = b"CBF"
CBF_SECTION_MAGIC = b"CS0"

# --- Magic header bytes for a CBFF file
CBF_FILE_MAGIC_1 = b"CBF"
CBF_FILE_MAGIC_2 = b"CBFF"  # version 2000+
CBF_FILE_MAGIC_3 = b"CBFV"  # version 2000+ with variant

# --- File type codes
CBF_FILE_TYPE_NORMAL = 0x00000000
CBF_FILE_TYPE_ODX = 0x00000001


@dataclass
class EcucInstance:
    """One ECU instance in an SMR-D file."""
    ecuc_instance_id: int
    ecu_type_description: str = ""
    ecu_subtype_description: str = ""
    ecu_steering_number: int = 0
    vehicle_id_number: str = ""
    code_data_addresses: list[int] = field(default_factory=list)
    service_list: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def __str__(self) -> str:
        return (f"ECU({self.ecu_steering_number}, {self.ecu_type_description}, "
                f"{self.ecu_subtype_description})")


@dataclass
class CodingTable:
    """One variant coding table (a set of SA codes or ECU parameters)."""
    table_id: int
    table_name: str = ""
    offset: int = 0
    size: int = 0
    data_type: str = ""          # U8, U16, S32, ASCII, etc.
    description: str = ""
    min_value: int = 0
    max_value: int = 0
    default_value: int = 0
    is_variant: bool = False

    @classmethod
    def from_data(cls, table_id: int, offset: int, size: int,
                  data_type: str, description: str,
                  min_value: int = 0, max_value: int = 0,
                  default_value: int = 0, is_variant: bool = False) -> "CodingTable":
        return cls(
            table_id=table_id,
            offset=offset,
            size=size,
            data_type=data_type,
            description=description,
            min_value=min_value,
            max_value=max_value,
            default_value=default_value,
            is_variant=is_variant,
        )

    def __str__(self) -> str:
        return (f"CodeTable({self.table_id}, size={self.size}, type={self.data_type}, "
                f"{self.description[:40]}...)")


@dataclass
class SmrDFile:
    """The parsed contents of one SMR-D file."""
    filename: str
    version: str = ""
    odx_xml: str = ""
    ecuc_instances: list[EcucInstance] = field(default_factory=list)
    coding_tables: list[CodingTable] = field(default_factory=list)
    file_path: Path = None

    def __post_init__(self):
        if self.file_path is None:
            self.file_path = Path(self.filename) if self.filename else None

    def __str__(self) -> str:
        return f"SMR-D({self.filename}, {len(self.ecuc_instances)} ECUs, {len(self.coding_tables)} code tables)"


def parse_smr_d(filepath: str | Path) -> SmrDFile:
    """Parse an SMR-D file and extract the ODX section plus ECU meta-data.

    This is a *documenting* parser. The actual parsing of the ODX XML
    into structured data is done by the caller. This function:
      1. Checks the file header (CBF / CBFF / CBFV).
      2. Locates the ODX XML section.
      3. Parses the XML and extracts the ECU instances.
      4. Extracts coding table information (offsets, data types, etc.)
      5. Returns a clean SmrDFile object.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"SMR-D file not found: {path}")

    raw = path.read_bytes()
    logger.info(f"Parsing SMR-D file: {path} ({len(raw)} bytes)")

    # --- Identify the file type
    if raw[:4] == CBF_FILE_MAGIC_3:
        file_type = CBF_FILE_TYPE_ODX
        version = "CBFV"
    elif raw[:4] == CBF_FILE_MAGIC_2:
        file_type = CBF_FILE_TYPE_ODX
        version = "CBFF"
    elif raw[:4] == CBF_FILE_MAGIC_1:
        file_type = CBF_FILE_TYPE_NORMAL
        version = "CBF"
    else:
        raise ValueError(f"Unknown file type: {raw[:4]!r} (expected CBF/CBFF/CBFV)")

    result = SmrDFile(filename=path.name, version=version, file_path=path)

    # --- Look for the ODX section
    odx_data = _extract_odx_section(raw)
    if odx_data:
        result.odx_xml = odx_data.decode("utf-8", errors="replace")
        _parse_odx_xml(result, odx_data)

    return result


def _extract_odx_section(raw: bytes) -> bytes:
    """Find the ODX XML section and return its raw bytes."""
    idx = raw.find(ODX_SECTION_MAGIC)
    if idx == -1:
        # Some files put the ODX section right after the header with a
        # length prefix. Try to find a <ecuid> tag anywhere.
        marker = b"<ecuid"
        idx = raw.find(marker)
        if idx == -1:
            return b""
        # Just return from the marker onward
        return raw[idx:]

    # ODX section: magic "ODX" + 4-byte length + data
    if len(raw) < idx + 8:
        return b""
    section_length = int.from_bytes(raw[idx+4:idx+8], "big")
    start = idx + 8
    end = min(start + section_length, len(raw))
    return raw[start:end]


def _parse_odx_xml(result: SmrDFile, odx_bytes: bytes) -> None:
    """Parse the ODX XML and extract ECU instances and coding tables."""
    try:
        root = ET.fromstring(odx_bytes)
    except ET.ParseError as exc:
        logger.warning(f"ODX XML parse error: {exc}")
        return

    _extract_ecuc_instances(root, result)
    _extract_coding_tables(root, result)


def _extract_ecuc_instances(root, result: SmrDFile) -> None:
    """Walk the XML and collect ECU instances."""
    # Find all <ecucInstance> elements
    for inst in root.iter("ecucInstance"):
        try:
            instance_id = int(inst.get("id", 0))
        except ValueError:
            instance_id = 0

        # Read the general info
        general = inst.find("general")
        ecu_type_desc = _first_text(general, "ecuTypeDescription")
        ecu_subtype_desc = _first_text(general, "ecuSubTypeDescription")
        steering_number = 0
        for child in general.iter("ecuSteeringNumber"):
            try:
                steering_number = int(child.text)
            except (ValueError, TypeError):
                pass
        vehicle_id = _first_text(general, "vehicleIdentificationNumber")

        # Read the supported coding tables
        code_data_addrs = []
        service_list = {}

        # Look for code data address (offset) elements
        for addr in inst.findall(".//codeDataAddress"):
            try:
                code_data_addrs.append(int(addr.text))
            except (ValueError, TypeError):
                pass

        # Look for service list (supported service identifiers)
        for svc in inst.findall(".//serviceIdentifier"):
            code = svc.get("code", "")
            desc = svc.get("description", "")
            if desc:
                service_list[code] = desc

        config = inst.find("config")
        description = _first_text(config, "description") if config is not None else ""

        result.ecuc_instances.append(EcucInstance(
            ecuc_instance_id=instance_id,
            ecu_type_description=ecu_type_desc,
            ecu_subtype_description=ecu_subtype_desc,
            ecu_steering_number=steering_number,
            vehicle_id_number=vehicle_id,
            code_data_addresses=code_data_addrs,
            service_list=service_list,
            description=description,
        ))


def _extract_coding_tables(root, result: SmrDFile) -> None:
    """Extract coding table definitions from the XML (or the header)."""
    # In a real SMR-D, coding tables are defined inside <dataIdentifier> or
    # <codeDataIdentifier> elements. We'll look for those.
    for identifier in root.iter("dataIdentifier"):
        try:
            table_id = int(identifier.get("id", 0))
        except ValueError:
            table_id = 0
        desc = _first_text(identifier, "description") or "unknown"
        # Candidate data types
        data_type = "U8"
        size = 1
        # Look for type or size info
        for child in identifier:
            if child.tag.endswith("dataType"):
                data_type = child.text or "U8"
            if child.tag.endswith("size"):
                try:
                    size = int(child.text)
                except (ValueError, TypeError):
                    pass
        # Default value
        default_value = 0
        min_value = 0
        max_value = 0
        variant = False

        result.coding_tables.append(CodingTable.from_data(
            table_id=table_id,
            offset=0,          # offset comes from the ECUC instance
            size=size,
            data_type=data_type,
            description=desc,
            min_value=min_value,
            max_value=max_value,
            default_value=default_value,
            is_variant=variant,
        ))


def _first_text(parent, tag: str) -> str:
    """Return the first text of a child element or empty string."""
    if parent is None:
        return ""
    for child in parent.iter(tag):
        if child.text:
            return child.text.strip()
    return ""


def parse_cbf(filepath: str | Path) -> SmrDFile:
    """Parse a CBF (Caesar Binary Format) file.

    CBF files contain multiple sections, each with a type and data.
    The most common sections are:
      - General header (with file type)
      - ECUC header (ECU instance list with offsets)
      - ODX section (XML data)

    We extract the ODX XML and ECU instance list from the CBF the same
    way as the SMR-D (the CBF is just a container for the same data).
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CBF file not found: {path}")

    raw = path.read_bytes()
    logger.info(f"Parsing CBF file: {path} ({len(raw)} bytes)")

    result = SmrDFile(filename=path.name, version="CBF", file_path=path)

    # Extract the ODX section (same as SMR-D)
    odx_data = _extract_odx_section(raw)
    if odx_data:
        result.odx_xml = odx_data.decode("utf-8", errors="replace")
        _parse_odx_xml(result, odx_data)

    return result
