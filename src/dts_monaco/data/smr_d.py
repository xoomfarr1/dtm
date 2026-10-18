"""SMR-D / ODX data file parser.

The SMR-D file format is built on ODX (ISO 22901) and is used by the
DTS Monaco to describe each ECU's capabilities, coding tables, and
diagnostic services.

Two container formats are supported:

1. **ODX-embed (SMR-D)** - the file carries the ODX XML directly, either
   as a raw XML document or with a small binary header.  ``parse_smr_d``
   parses this format.
2. **CBFF (Caesar Binary Format)** - a binary container that holds one
   or more *sections*.  The most common sections are:
     - ODX (XML with the ``<ecuid>`` document)
     - ECUC   (binary list of ECU instance records)
     - CODING (binary list of coding table records)
   ``parse_cbf`` parses this format.

A typical CBFF file looks like this:

    [CBFF header]             20 bytes
      magic   (4)  "CBFF"
      version (4)  e.g. 2000
      file_size (4)
      file_type (4)  0 = normal, 1 = ODX/XML
      section_count (4)
    [Section header]          24 bytes each
      section_type (4)
      offset       (8)  absolute file offset of the section data
      size         (8)
      flags        (4)
    [Section data]

The ODX section is an XML document with this general shape:

  <ecuid>
    <general>
      < ecuTypeDescription>...</ecuTypeDescription>
      < ecuSubTypeDescription>...</ecuSubTypeDescription>
      < ecuSteeringNumber>123</ecuSteeringNumber>
      < vehicleIdentificationNumber>...
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

Public API
----------
- :func:`parse_smr_d`   -- parse an ODX-embed/smr file (or a CBFF container)
- :func:`parse_cbf`     -- parse a CBFF container file
- :class:`SmrDFile`     -- parsed result object
- :class:`EcucInstance` -- one ECU instance
- :class:`CodingTable`  -- one variant coding table
"""

from __future__ import annotations

import logging
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- ODX magic identifiers (the header declares the section type) ---
ODX_SECTION_MAGIC = b"ODX"
CBF_HEADER_MAGIC = b"CBF"
CBF_SECTION_MAGIC = b"CS0"

# --- Magic header bytes for a CBFF file ---
CBF_FILE_MAGIC_1 = b"CBF"      # v1 container
CBF_FILE_MAGIC_2 = b"CBFF"     # v2000+ container
CBF_FILE_MAGIC_3 = b"CBFV"     # v2000+ with variant

# --- File type codes ---
CBF_FILE_TYPE_NORMAL = 0x00000000
CBF_FILE_TYPE_ODX = 0x00000001

# --- CBFF section types ---
CBF_SECTION_TYPE_ODX = 0x00000001
CBF_SECTION_TYPE_ECUC = 0x00000002
CBF_SECTION_TYPE_CODING = 0x00000003

# --- Coding table binary record data type codes ---
CBF_DT_U8 = 0x01
CBF_DT_U16 = 0x02
CBF_DT_S16 = 0x03
CBF_DT_S32 = 0x04
CBF_DT_F32 = 0x05
CBF_DT_ASCII = 0x06
CBF_DT_STRING = 0x07
CBF_DT_BITMAP = 0x08


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
    data_type: str = "U8"
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
        return (f"CodeTable({self.table_id}, off=0x{self.offset:x}, size={self.size}, "
                f"type={self.data_type}, {self.description[:40]}...)")


@dataclass
class CbffHeader:
    """The CBFF container header (magic, version, file size, file type)."""
    magic: bytes
    version: int
    file_size: int
    file_type: int
    section_count: int

    def __str__(self) -> str:
        return (f"CBFFHeader(magic={self.magic!r}, version={self.version}, "
                f"type={self.file_type}, sections={self.section_count})")


@dataclass
class CbffSection:
    """One section of a CBFF file: its type, file offset and size."""
    section_type: int
    offset: int
    size: int
    flags: int = 0

    @property
    def kind(self) -> str:
        return {
            CBF_SECTION_TYPE_ODX: "ODX",
            CBF_SECTION_TYPE_ECUC: "ECUC",
            CBF_SECTION_TYPE_CODING: "CODING",
        }.get(self.section_type, "unknown")

    def __str__(self) -> str:
        return (f"Section(type=0x{self.section_type:08x}, offset={self.offset}, "
                f"size={self.size}, flags=0x{self.flags:08x})")


@dataclass
class SmrDFile:
    """The parsed contents of one SMR-D / CBFF file."""
    filename: str
    version: str = ""
    odx_xml: str = ""
    ecuc_instances: list[EcucInstance] = field(default_factory=list)
    coding_tables: list[CodingTable] = field(default_factory=list)
    file_path: Path = None
    # CBFF-specific metadata (populated when parse_cbf() is used)
    header: CbffHeader | None = None
    sections: list[CbffSection] = field(default_factory=list)

    def __post_init__(self):
        if self.file_path is None:
            self.file_path = Path(self.filename) if self.filename else None

    def __str__(self) -> str:
        return (f"SMR-D({self.filename}, {len(self.ecuc_instances)} ECUs, "
                f"{len(self.coding_tables)} code tables)")


def parse_smr_d(filepath: str | Path) -> SmrDFile:
    """Parse an SMR-D file and extract the ODX section plus ECU meta-data.

    If the file is a CBFF container, it is parsed as a CBFF file instead.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"SMR-D file not found: {path}")

    raw = path.read_bytes()
    logger.info(f"Parsing SMR-D file: {path} ({len(raw)} bytes)")

    if raw[:4] in (CBF_FILE_MAGIC_2, CBF_FILE_MAGIC_3):
        # CBFF container -> use the section parser
        return parse_cbf(filepath)

    result = _parse_plain_odx_embed(raw, path)
    result.version = "SMR-D"
    return result


def parse_cbf(filepath: str | Path) -> SmrDFile:
    """Parse a CBF (Caesar Binary Format) file.

    A CBF file is a binary container of sections.  We extract the ODX XML
    and ECU instance list, then parse the coding table definitions
    (offsets, data types, sizes) from the binary sections and the XML.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CBF file not found: {path}")

    raw = path.read_bytes()
    logger.info(f"Parsing CBF file: {path} ({len(raw)} bytes)")

    header = _parse_cbf_header(raw)
    sections = _parse_cbf_sections(raw, header)

    odx_data = _extract_cbf_section(raw, sections, CBF_SECTION_TYPE_ODX)
    ecuc_data = _extract_cbf_section(raw, sections, CBF_SECTION_TYPE_ECUC)
    coding_data = _extract_cbf_section(raw, sections, CBF_SECTION_TYPE_CODING)

    result = SmrDFile(filename=path.name, file_path=path)
    result.header = header
    result.sections = sections

    if odx_data:
        result.odx_xml = odx_data.decode("utf-8", errors="replace")
        _parse_odx_xml(result, odx_data)

    # --- Enrichment from the binary ECUC section ---
    _enrich_ecuc_from_binary(result, ecuc_data)

    # --- Enrichment from the binary CODING section ---
    _enrich_coding_from_binary(result, coding_data)

    return result


# ---------------------------------------------------------------------------
# CBFF container parsing
# ---------------------------------------------------------------------------
def _parse_cbf_header(raw: bytes) -> CbffHeader:
    """Parse the 20-byte CBFF container header."""
    if len(raw) < 20:
        raise ValueError(
            f"CBF header truncated: file is {len(raw)} bytes, need 20"
        )
    magic = raw[0:4]
    version, file_size, file_type, section_count = struct.unpack_from("<IIII", raw, 4)
    return CbffHeader(
        magic=magic,
        version=version,
        file_size=file_size,
        file_type=file_type,
        section_count=section_count,
    )


def _parse_cbf_sections(raw: bytes, header: CbffHeader) -> list[CbffSection]:
    """Parse the section table that follows the container header.

    Section headers are stored sequentially in the file in the order the
    sections appear.  Each header is followed by its section data, so the
    parser advances *size* bytes after each header.
    """
    sections = []
    n = header.section_count
    pos = 20  # container header is 20 bytes
    for i in range(n):
        if pos + 24 > len(raw):
            logger.warning(f"CBF section header {i} out of range")
            break
        section_type, offset, size, flags = struct.unpack_from("<IQQI", raw, pos)
        sections.append(CbffSection(
            section_type=section_type,
            offset=offset,
            size=size,
            flags=flags,
        ))
        pos += 24 + size  # section header + its data
    return sections


def _extract_cbf_section(raw: bytes, sections: list[CbffSection],
                         section_type: int) -> bytes:
    """Return the data bytes of the first section of *section_type*."""
    for s in sections:
        if s.section_type == section_type:
            start = s.offset
            end = min(start + s.size, len(raw))
            data = raw[start:end]
            if len(data) != s.size:
                logger.warning(
                    f"Section 0x{section_type:x} at 0x{start:x} is truncated "
                    f"({len(data)}/{s.size} bytes)"
                )
            return data
    return b""


def _coding_type_name(code: int) -> str:
    """Map a binary coding-table record data-type code to a string."""
    return {
        CBF_DT_U8: "U8",
        CBF_DT_U16: "U16",
        CBF_DT_S16: "S16",
        CBF_DT_S32: "S32",
        CBF_DT_F32: "F32",
        CBF_DT_ASCII: "ASCII",
        CBF_DT_STRING: "STRING",
        CBF_DT_BITMAP: "BITMAP",
    }.get(code, f"DT_{code}")


# ---------------------------------------------------------------------------
# ODX XML parsing (shared by the CBFF and plain-ODX paths)
# ---------------------------------------------------------------------------
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
    for inst in root.iter("ecucInstance"):
        try:
            instance_id = int(inst.get("id", 0))
        except ValueError:
            instance_id = 0

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

        code_data_addrs = _extract_code_data_addresses(inst)
        service_list = _extract_service_list(inst)
        description = _first_text(inst.find("config"), "description") if inst.find("config") is not None else ""

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


def _extract_code_data_addresses(inst) -> list[int]:
    """Read the coding-table offsets for one ECU instance."""
    addrs = []
    for addr in inst.findall(".//codeDataAddress"):
        val = _text_or_attr(addr, "offset", default=None)
        if val is None:
            val = _text_or_attr(addr, "id", default=None)
        try:
            addrs.append(int(val))
        except (ValueError, TypeError):
            pass
    return addrs


def _extract_service_list(inst) -> dict[str, str]:
    """Read the supported service identifiers for one ECU instance."""
    services = {}
    for svc in inst.findall(".//serviceIdentifier"):
        code = svc.get("code", "")
        desc = svc.get("description", "")
        if desc:
            services[code] = desc
    return services


def _extract_coding_tables(root, result: SmrDFile) -> None:
    """Extract coding table definitions from the XML.

    Look for ``dataIdentifier`` / ``codeDataIdentifier`` elements that
    carry the table id, offset, size, data type and bounds.
    """
    identifiers = list(root.iter("dataIdentifier")) + list(root.iter("codeDataIdentifier"))
    for identifier in identifiers:
        table_id = _attr_int(identifier, "id") or _attr_int(identifier, "tableId") or 0
        offset = _attr_int(identifier, "offset") or _attr_int(identifier, "codeOffset") or 0
        size = _attr_int(identifier, "size") or 1
        data_type = _first_text(identifier, "dataType") or "U8"
        description = _first_text(identifier, "description") or f"Table {table_id}"
        min_value = _attr_int(identifier, "minValue") or 0
        max_value = _attr_int(identifier, "maxValue") or 0
        default_value = _attr_int(identifier, "defaultValue") or 0
        is_variant = _first_text(identifier, "isVariant") in ("1", "true", "yes")

        result.coding_tables.append(CodingTable.from_data(
            table_id=table_id,
            offset=offset,
            size=size,
            data_type=data_type,
            description=description,
            min_value=min_value,
            max_value=max_value,
            default_value=default_value,
            is_variant=is_variant,
        ))


# ---------------------------------------------------------------------------
# Binary ECUC / CODING section enrichment
# ---------------------------------------------------------------------------
def _enrich_ecuc_from_binary(result: SmrDFile, data: bytes) -> None:
    """Parse the binary ECUC section and attach instance offsets."""
    if not data:
        return

    # ECUC record: instance_id(u32), general_offset(u64),
    #               coding_table_offset(u32), coding_table_size(u32), flags(u32)
    rec = struct.Struct("<I Q I I I")
    if len(data) % rec.size != 0:
        logger.warning(f"ECUC section has {len(data)} bytes (not a multiple of {rec.size})")

    for i in range(0, len(data), rec.size):
        chunk = data[i:i + rec.size]
        if len(chunk) < rec.size:
            break
        instance_id, general_offset, table_offset, table_size, flags = rec.unpack(chunk)
        # Attach the offsets to every matching ECU instance by id.
        # Only fill in fields that the XML parsing left empty.
        for inst in result.ecuc_instances:
            if inst.ecuc_instance_id == instance_id:
                if not inst.code_data_addresses:
                    inst.code_data_addresses = [table_offset]
                if not inst.description:
                    inst.description = (
                        f"ECUC instance {instance_id} (flags=0x{flags:08x})"
                    )
                break


def _enrich_coding_from_binary(result: SmrDFile, data: bytes) -> None:
    """Parse the binary CODING section and add coding table records."""
    if not data:
        return

    # Coding record: table_id(u32), offset(u32), size(u8), data_type(u8), flags(u8)
    rec = struct.Struct("<I I B B B")
    if len(data) % rec.size != 0:
        logger.warning(f"CODING section has {len(data)} bytes (not a multiple of {rec.size})")

    for i in range(0, len(data), rec.size):
        chunk = data[i:i + rec.size]
        if len(chunk) < rec.size:
            break
        table_id, offset, size, dtype_code, flags = rec.unpack(chunk)
        result.coding_tables.append(CodingTable.from_data(
            table_id=table_id,
            offset=offset,
            size=size,
            data_type=_coding_type_name(dtype_code),
            description=f"Coding table {table_id} (binary section)",
            min_value=0,
            max_value=0,
            default_value=0,
            is_variant=bool(flags & 0x01),
        ))


# ---------------------------------------------------------------------------
# Plain ODX-embed parsing (no container)
# ---------------------------------------------------------------------------
def _parse_plain_odx_embed(raw: bytes, path: Path) -> SmrDFile:
    """Parse an SMR-D file that embeds the ODX XML directly."""
    result = SmrDFile(filename=path.name, file_path=path)

    # Try the container format first (magic + 4-byte length), then fall back
    # to searching for an <ecuid> marker anywhere in the file.
    odx_data = b""
    if raw.find(ODX_SECTION_MAGIC) == 0 and len(raw) >= 8:
        section_length = int.from_bytes(raw[4:8], "big")
        start = 8
        end = min(start + section_length, len(raw))
        odx_data = raw[start:end]

    if not odx_data:
        marker = b"<ecuid"
        idx = raw.find(marker)
        if idx == -1:
            logger.warning("No ODX XML found in file")
            return result
        odx_data = raw[idx:]

    result.odx_xml = odx_data.decode("utf-8", errors="replace")
    _parse_odx_xml(result, odx_data)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _first_text(parent, tag: str) -> str:
    """Return the first text of a child element or empty string."""
    if parent is None:
        return ""
    for child in parent.iter(tag):
        if child.text:
            return child.text.strip()
    return ""


def _attr_int(element, name: str) -> Optional[int]:
    """Return an integer attribute of an element, or None."""
    if element is None:
        return None
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_attr(element, name: str, default: Optional[str] = None) -> Optional[str]:
    """Return an element's text, or an attribute if text is empty/absent."""
    if element is None:
        return default
    text = element.text
    if text and text.strip():
        return text.strip()
    return element.get(name, default)
