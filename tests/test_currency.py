import pytest
from decimal import Decimal
from app.core.currency import pounds_to_pence, pence_to_pounds, format_pence

def test_pounds_to_pence_precision():
    assert pounds_to_pence(19.99) == 1999
    assert pounds_to_pence("19.99") == 1999
    assert pounds_to_pence("£1,250.50") == 125050
    assert pounds_to_pence(0.01) == 1
    assert pounds_to_pence(0) == 0
    assert pounds_to_pence(-50.25) == -5025
    assert pounds_to_pence(Decimal("100.05")) == 10005

def test_pence_to_pounds():
    assert pence_to_pounds(1999) == 19.99
    assert pence_to_pounds(0) == 0.0
    assert pence_to_pounds(-5025) == -50.25

def test_format_pence():
    assert format_pence(1999) == "£19.99"
    assert format_pence(125050) == "£1,250.50"
    assert format_pence(0) == "£0.00"
    assert format_pence(-250) == "-£2.50"

