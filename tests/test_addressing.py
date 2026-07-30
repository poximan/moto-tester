import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trasvase-tester"))

from app.addressing import ace_pdu_address, ace_reference, reference_to_pdu


def test_modicon_reference_conversion():
    assert reference_to_pdu(30001, "input_register") == 0
    assert reference_to_pdu(30026, "input_register") == 25
    assert reference_to_pdu(42049, "holding_register") == 2048
    assert reference_to_pdu(42070, "holding_register") == 2069
    assert reference_to_pdu(42076, "holding_register") == 2075
    assert reference_to_pdu(42083, "holding_register") == 2082
    assert reference_to_pdu(14097, "discrete_input") == 4096
    assert reference_to_pdu(14173, "discrete_input") == 4172
    assert reference_to_pdu(6145, "coil") == 6144
    assert reference_to_pdu(6162, "coil") == 6161
    assert reference_to_pdu(6168, "coil") == 6167
    assert reference_to_pdu(6187, "coil") == 6186


def test_pdu_zero_based_mode():
    assert reference_to_pdu(42049, "holding_register", "pdu_zero_based") == 42049


def test_ace3600_formula_for_intercambio_sca_column_zero():
    assert ace_reference("input_register", table_number=0, row=0) == 30001
    assert ace_reference("input_register", table_number=0, row=25) == 30026
    assert ace_pdu_address("input_register", table_number=0, row=25) == 25

    assert ace_reference("holding_register", table_number=1, row=0) == 42049
    assert ace_reference("holding_register", table_number=1, row=27) == 42076
    assert ace_reference("holding_register", table_number=1, row=34) == 42083
    assert ace_pdu_address("holding_register", table_number=1, row=34) == 2082

    assert ace_reference("discrete_input", table_number=2, row=0) == 14097
    assert ace_reference("discrete_input", table_number=2, row=76) == 14173
    assert ace_pdu_address("discrete_input", table_number=2, row=76) == 4172

    assert ace_reference("coil", table_number=3, row=0) == 6145
    assert ace_reference("coil", table_number=3, row=23) == 6168
    assert ace_reference("coil", table_number=3, row=42) == 6187
    assert ace_pdu_address("coil", table_number=3, row=42) == 6186
