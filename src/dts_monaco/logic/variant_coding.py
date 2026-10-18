"""Variant coding data model + seed/key computing.

Variant coding is where the tool writes SA codes (Mercedes) or other
configuration values to an ECU. The raw data is in the SMR-D/Odex file;
this module turns it into a structured model and provides helpers for
compute the secure seed/key used for write access.

This is a *design* module: the seed compute is vehicle-specific and
requires reverse-engineering the ECU's secure-message algorithm. We
provide the framework and let the user plug in their implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from ..data.smr_d import CodingTable


class CodingDataType(Enum):
    U8 = "U8"
    U16 = "U16"
    U32 = "U32"
    S8 = "S8"
    S16 = "S16"
    S32 = "S32"
    ASCII = "ASCII"
    STRING = "STRING"
    BITMAP = "BITMAP"
    ARRAY = "ARRAY"
    ENUM = "ENUM"


@dataclass
class VariantCode:
    """One individual coding value (one SA code, one parameter)."""
    table_id: int
    offset: int
    name: str = ""
    data_type: CodingDataType = CodingDataType.U8
    value: int = 0
    description: str = ""

    def __str__(self) -> str:
        return f"{self.name} (0x{self.value & 0xFFFFFFFF:08x})"


@dataclass
class CodingTableModel:
    """A variant coding table after parsing the SMR-D."""
    table_id: int
    name: str = ""
    offset: int = 0
    size: int = 0
    data_type: CodingDataType = CodingDataType.U8
    description: str = ""
    min_value: int = 0
    max_value: int = 0
    default_value: int = 0
    is_variant: bool = False
    codes: list[VariantCode] = field(default_factory=list)

    def __str__(self) -> str:
        return f"Coding table {self.table_id} ({self.size} bytes, {self.data_type})"


class SeedComputer:
    """Computes the secure seed/key for writing to an ECU.

    The seed/key algorithm is *vehicle-specific*. An ECU's secure message
    unit (SMU) uses a proprietary algorithm to generate a key from a seed
    and the ECU's unique secret key (which is burned into the ECU at
    manufacturing and can't be read out). This means the open-source
    tool can't compute the key without the ECU's algorithm. The solution:

      1. The user implements a *callback* (a small function) for their
         specific vehicle family.
      2. The callback takes the seed and returns the key.
      3. The tool handles the secure session and calls the callback.

    We provide the framework and a dummy implementation for testing.
    """

    def __init__(self, algorithm: Callable[[bytes], bytes]):
        """
        algorithm : takes the seed bytes and returns the key bytes.
                    Example: lambda seed: some_hash + seed
        """
        self.algorithm = algorithm

    def compute_key(self, seed: bytes) -> bytes:
        """Compute the security key from a seed."""
        if not seed:
            return b""
        return self.algorithm(seed)

    # --- Dummy implementation for testing ---
    @staticmethod
    def _dummy_algorithm(seed: bytes) -> bytes:
        """A simple test algorithm: seed + 0x55."""
        return seed + b"\x55"


def build_table_models(smr_d: SmrDFile) -> list[CodingTableModel]:
    """Turn a parsed SmrDFile into a list of CodingTableModel objects."""
    models = []
    for ct in smr_d.coding_tables:
        model = CodingTableModel(
            table_id=ct.table_id,
            name=ct.description or f"Table {ct.table_id}",
            offset=0,  # offset comes from the ECUC instance
            size=ct.size,
            data_type=ct.data_type,
            description=ct.description,
            min_value=ct.min_value,
            max_value=ct.max_value,
            default_value=ct.default_value,
            is_variant=ct.is_variant,
        )
        models.append(model)
    return models


def extract_variant_codes(models: list[CodingTableModel]) -> list[VariantCode]:
    """Turn a list of CodingTableModel into flat VariantCode entries."""
    codes = []
    for m in models:
        for i in range(m.size):
            codes.append(VariantCode(
                table_id=m.table_id,
                offset=m.offset + i,
                name=f"{m.name}[{i}]",
                data_type=m.data_type,
                value=0,
                description=m.description,
            ))
    return codes
