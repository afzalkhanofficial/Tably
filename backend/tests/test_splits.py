import pytest
from decimal import Decimal
from services.split_calculator import SplitCalculator

@pytest.fixture
def calculator():
    return SplitCalculator()

def test_equal_split_even(calculator):
    # Evenly divisible amount
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('0')},
        {'user_id': 2, 'value': Decimal('0')},
        {'user_id': 3, 'value': Decimal('0')},
        {'user_id': 4, 'value': Decimal('0')},
    ]
    result = calculator.calculate(total, 'equal', splits, paid_by_id=1)
    
    assert len(result) == 4
    for val in result.values():
        assert val == Decimal('25.00')
    assert sum(result.values()) == total

def test_equal_split_odd_rounding(calculator):
    # Odd amount with rounding (remainder to first person)
    total = Decimal('1000.00')
    splits = [
        {'user_id': 1, 'value': Decimal('0')},
        {'user_id': 2, 'value': Decimal('0')},
        {'user_id': 3, 'value': Decimal('0')},
    ]
    result = calculator.calculate(total, 'equal', splits, paid_by_id=1)
    
    assert len(result) == 3
    # Check that first person gets the adjusted rounding remainder (333.34)
    assert result[1] == Decimal('333.34')
    assert result[2] == Decimal('333.33')
    assert result[3] == Decimal('333.33')
    assert sum(result.values()) == total

def test_equal_split_single_person(calculator):
    # Single person edge case
    total = Decimal('50.25')
    splits = [{'user_id': 1, 'value': Decimal('0')}]
    result = calculator.calculate(total, 'equal', splits, paid_by_id=1)
    
    assert len(result) == 1
    assert result[1] == Decimal('50.25')
    assert sum(result.values()) == total

def test_equal_split_max_six_people(calculator):
    # Maximum 6 people edge case
    total = Decimal('999.99')
    splits = [{'user_id': i, 'value': Decimal('0')} for i in range(1, 7)]
    result = calculator.calculate(total, 'equal', splits, paid_by_id=1)
    
    assert len(result) == 6
    assert sum(result.values()) == total

def test_unequal_split_exact(calculator):
    # Exact sum
    total = Decimal('150.00')
    splits = [
        {'user_id': 1, 'value': Decimal('50.00')},
        {'user_id': 2, 'value': Decimal('70.00')},
        {'user_id': 3, 'value': Decimal('30.00')},
    ]
    result = calculator.calculate(total, 'unequal', splits, paid_by_id=1)
    
    assert result[1] == Decimal('50.00')
    assert result[2] == Decimal('70.00')
    assert result[3] == Decimal('30.00')
    assert sum(result.values()) == total

def test_unequal_split_small_rounding(calculator):
    # Small rounding mismatch (< 1.00) adjusted to first person
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('33.33')},
        {'user_id': 2, 'value': Decimal('33.33')},
        {'user_id': 3, 'value': Decimal('33.33')},
    ]
    result = calculator.calculate(total, 'unequal', splits, paid_by_id=1)
    
    assert result[1] == Decimal('33.34')  # adjusted by +0.01
    assert result[2] == Decimal('33.33')
    assert result[3] == Decimal('33.33')
    assert sum(result.values()) == total

def test_unequal_split_large_mismatch_error(calculator):
    # Large mismatch should raise ValueError
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('40.00')},
        {'user_id': 2, 'value': Decimal('50.00')},
    ]
    with pytest.raises(ValueError) as excinfo:
        calculator.calculate(total, 'unequal', splits, paid_by_id=1)
    assert "too large to auto-correct" in str(excinfo.value)

def test_percentage_split_exact(calculator):
    # Exact percentage split (total 100%)
    total = Decimal('500.00')
    splits = [
        {'user_id': 1, 'value': Decimal('20.00')},
        {'user_id': 2, 'value': Decimal('50.00')},
        {'user_id': 3, 'value': Decimal('30.00')},
    ]
    result = calculator.calculate(total, 'percentage', splits, paid_by_id=1)
    
    assert result[1] == Decimal('100.00')
    assert result[2] == Decimal('250.00')
    assert result[3] == Decimal('150.00')
    assert sum(result.values()) == total

def test_percentage_split_rounding_to_payer(calculator):
    # Percentage split with rounding adjusted to payer
    total = Decimal('1000.00')
    splits = [
        {'user_id': 1, 'value': Decimal('33.33')},
        {'user_id': 2, 'value': Decimal('33.33')},
        {'user_id': 3, 'value': Decimal('33.34')},
    ]
    # Payer is user 2
    result = calculator.calculate(total, 'percentage', splits, paid_by_id=2)
    
    # 1000 * 0.3333 = 333.30
    # 1000 * 0.3334 = 333.40
    # Sum: 333.30 + 333.30 + 333.40 = 1000.00 (exact, no diff)
    assert result[1] == Decimal('333.30')
    assert result[2] == Decimal('333.30')
    assert result[3] == Decimal('333.40')
    assert sum(result.values()) == total

    # Let's test with odd total
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('33.33')},
        {'user_id': 2, 'value': Decimal('33.33')},
        {'user_id': 3, 'value': Decimal('33.34')},
    ]
    # 100 * 0.3333 = 33.33
    # 100 * 0.3334 = 33.34
    # Sum: 33.33 + 33.33 + 33.34 = 100.00 (exact)

    # Let's use a total that creates a rounding gap
    total = Decimal('10.00')
    splits = [
        {'user_id': 1, 'value': Decimal('33.33')},
        {'user_id': 2, 'value': Decimal('33.33')},
        {'user_id': 3, 'value': Decimal('33.34')},
    ]
    # 10 * 0.3333 = 3.33
    # 10 * 0.3334 = 3.33 (quantized from 3.334)
    # Sum: 3.33 + 3.33 + 3.33 = 9.99
    # Payer (user 2) gets the remainder: 3.33 + 0.01 = 3.34
    result = calculator.calculate(total, 'percentage', splits, paid_by_id=2)
    assert result[1] == Decimal('3.33')
    assert result[2] == Decimal('3.34')  # adjusted by +0.01 since user 2 is the payer
    assert result[3] == Decimal('3.33')
    assert sum(result.values()) == total

def test_percentage_split_invalid_sum_error(calculator):
    # Total percentage not equal to 100%
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('50.00')},
        {'user_id': 2, 'value': Decimal('49.00')},
    ]
    with pytest.raises(ValueError) as excinfo:
        calculator.calculate(total, 'percentage', splits, paid_by_id=1)
    assert "must be 100%" in str(excinfo.value)

def test_share_split_exact(calculator):
    # Share ratio split (e.g. Aisha 1, Rohan 2, Priya 1, Dev 2 → total 6 shares)
    total = Decimal('600.00')
    splits = [
        {'user_id': 1, 'value': Decimal('1')},
        {'user_id': 2, 'value': Decimal('2')},
        {'user_id': 3, 'value': Decimal('1')},
        {'user_id': 4, 'value': Decimal('2')},
    ]
    result = calculator.calculate(total, 'share', splits, paid_by_id=1)
    
    assert result[1] == Decimal('100.00')
    assert result[2] == Decimal('200.00')
    assert result[3] == Decimal('100.00')
    assert result[4] == Decimal('200.00')
    assert sum(result.values()) == total

def test_share_split_rounding_to_payer(calculator):
    # Share split with rounding adjusted to payer
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('1')},
        {'user_id': 2, 'value': Decimal('1')},
        {'user_id': 3, 'value': Decimal('1')},
    ]
    # total shares = 3. 100/3 = 33.33333...
    # each pays 33.33
    # sum = 99.99
    # Payer (user 2) gets remaining 0.01 -> 33.34
    result = calculator.calculate(total, 'share', splits, paid_by_id=2)
    assert result[1] == Decimal('33.33')
    assert result[2] == Decimal('33.34')  # adjusted
    assert result[3] == Decimal('33.33')
    assert sum(result.values()) == total

def test_share_split_zero_shares_error(calculator):
    # Total shares equal to 0
    total = Decimal('100.00')
    splits = [
        {'user_id': 1, 'value': Decimal('0')},
        {'user_id': 2, 'value': Decimal('0')},
    ]
    with pytest.raises(ValueError) as excinfo:
        calculator.calculate(total, 'share', splits, paid_by_id=1)
    assert "Total shares cannot be zero" in str(excinfo.value)
