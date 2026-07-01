from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TableKind = Literal["coil", "discrete_input", "input_register", "holding_register"]
AddressingMode = Literal["modicon_reference", "pdu_zero_based"]

_BASE_BY_KIND: dict[str, int] = {
    "coil": 1,
    "discrete_input": 10001,
    "input_register": 30001,
    "holding_register": 40001,
}

_FUNCTION_BY_KIND: dict[str, str] = {
    "coil": "01",
    "discrete_input": "02",
    "holding_register": "03",
    "input_register": "04",
}


@dataclass(frozen=True)
class AddressInfo:
    kind: TableKind
    reference: int
    pdu_address: int
    function_code: str


def reference_to_pdu(reference: int, kind: TableKind, mode: AddressingMode = "modicon_reference") -> int:
    """Convierte una referencia Modicon documentada a dirección PDU cero-based.

    Ejemplos para mode='modicon_reference':
    - coil 6145 -> PDU 6144
    - discrete input 14097 -> PDU 4096
    - input register 30001 -> PDU 0
    - holding register 42049 -> PDU 2048

    En mode='pdu_zero_based', se retorna el valor sin conversión.
    """
    if reference < 0:
        raise ValueError("La dirección Modbus no puede ser negativa")

    if mode == "pdu_zero_based":
        return reference

    if mode != "modicon_reference":
        raise ValueError(f"Modo de direccionamiento no soportado: {mode}")

    try:
        base = _BASE_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"Tipo de tabla Modbus no soportado: {kind}") from exc

    pdu = reference - base
    if pdu < 0:
        raise ValueError(
            f"Referencia {reference} inválida para tabla {kind}; base esperada {base}"
        )
    return pdu


def pdu_to_reference(pdu_address: int, kind: TableKind, mode: AddressingMode = "modicon_reference") -> int:
    """Convierte una dirección PDU cero-based a referencia Modicon para la tabla indicada."""
    if pdu_address < 0:
        raise ValueError("La dirección PDU no puede ser negativa")

    if mode == "pdu_zero_based":
        return pdu_address

    if mode != "modicon_reference":
        raise ValueError(f"Modo de direccionamiento no soportado: {mode}")

    try:
        base = _BASE_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"Tipo de tabla Modbus no soportado: {kind}") from exc
    return base + pdu_address


def function_code_for(kind: TableKind) -> str:
    try:
        return _FUNCTION_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"Tipo de tabla Modbus no soportado: {kind}") from exc


def ace_reference(kind: TableKind, table_number: int, row: int, column: int = 0) -> int:
    """Calcula referencia Modicon ACE3600: offset + Z*2048 + X*256 + Y.

    Z = número de tabla, X = columna, Y = fila. Para el intercambio SCA
    se usa X=0: la columna ``Value`` documentada es semántica del tag, no
    una columna Modbus adicional que deba leerse.
    """
    if not 0 <= table_number <= 31:
        raise ValueError("Z/table_number debe estar entre 0 y 31")
    if not 0 <= column <= 7:
        raise ValueError("X/column debe estar entre 0 y 7")
    if not 0 <= row <= 249:
        raise ValueError("Y/row debe estar entre 0 y 249")
    try:
        base = _BASE_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"Tipo de tabla Modbus no soportado: {kind}") from exc
    return base + table_number * 2048 + column * 256 + row


def ace_pdu_address(kind: TableKind, table_number: int, row: int, column: int = 0) -> int:
    """Dirección PDU cero-based equivalente a la referencia ACE3600."""
    return reference_to_pdu(ace_reference(kind, table_number, row, column), kind)


def make_address_info(reference: int, kind: TableKind, mode: AddressingMode) -> AddressInfo:
    return AddressInfo(
        kind=kind,
        reference=reference,
        pdu_address=reference_to_pdu(reference, kind, mode),
        function_code=function_code_for(kind),
    )
