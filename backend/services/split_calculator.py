from decimal import Decimal, ROUND_HALF_UP

class SplitCalculator:
    """
    Calculates how much each person owes for a given expense.
    Input: expense amount in INR (always), split type, split details
    Output: {user_id: Decimal(amount_owed_inr)}
    
    Important: Split amounts must sum EXACTLY to total_amount_inr.
    Use rounding remainder assignment to the payer to handle ₹0.01 gaps.
    """
    
    def calculate(self, amount_inr: Decimal, split_type: str, 
                  splits: list, paid_by_id: int) -> dict:
        """
        splits: [{'user_id': int, 'value': Decimal}]
        Returns: {user_id: Decimal}
        """
        if split_type == 'equal':
            return self._equal(amount_inr, splits)
        elif split_type == 'unequal':
            return self._unequal(amount_inr, splits)
        elif split_type == 'percentage':
            return self._percentage(amount_inr, splits, paid_by_id)
        elif split_type == 'share':
            return self._share(amount_inr, splits, paid_by_id)
        else:
            raise ValueError(f"Unknown split type: {split_type}")
    
    def _equal(self, total: Decimal, splits: list) -> dict:
        """
        Each person pays the same amount.
        Remainder (from rounding) goes to first person in list.
        Example: ₹1199 among 4 people = ₹299.75 each exactly.
                 ₹1000 among 3 people = ₹333.33 + ₹333.33 + ₹333.34
        """
        n = len(splits)
        per_person = (total / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        result = {s['user_id']: per_person for s in splits}
        
        # Fix rounding: ensure sum == total
        diff = total - sum(result.values())
        if diff != 0:
            first_uid = splits[0]['user_id']
            result[first_uid] += diff
        
        return result
    
    def _unequal(self, total: Decimal, splits: list) -> dict:
        """
        Each person has a fixed rupee amount.
        Validate: values must sum to total.
        """
        result = {}
        running_sum = Decimal('0')
        for s in splits:
            amt = Decimal(str(s['value'])).quantize(Decimal('0.01'))
            result[s['user_id']] = amt
            running_sum += amt
        
        diff = total - running_sum
        if abs(diff) > Decimal('1.00'):
            raise ValueError(
                f"Unequal split amounts sum to {running_sum}, expected {total}. "
                f"Difference of {abs(diff)} is too large to auto-correct."
            )
        # Small rounding difference: add to first person
        if diff != 0:
            result[splits[0]['user_id']] += diff
        
        return result
    
    def _percentage(self, total: Decimal, splits: list, paid_by_id: int) -> dict:
        """
        Each person pays a percentage of total.
        Validate: percentages must sum to 100.
        Rounding remainder goes to payer.
        """
        pct_sum = sum(Decimal(str(s['value'])) for s in splits)
        if abs(pct_sum - 100) > Decimal('0.01'):
            raise ValueError(
                f"Percentages sum to {pct_sum}%, must be 100%. "
                f"Detected by anomaly checker — this should be resolved before import."
            )
        
        result = {}
        for s in splits:
            pct = Decimal(str(s['value'])) / Decimal('100')
            amt = (total * pct).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            result[s['user_id']] = amt
        
        diff = total - sum(result.values())
        if diff != 0 and paid_by_id in result:
            result[paid_by_id] += diff
        
        return result
    
    def _share(self, total: Decimal, splits: list, paid_by_id: int) -> dict:
        """
        Ratio-based split. 
        Example: Aisha 1, Rohan 2, Priya 1, Dev 2 → total 6 shares
        Each share = total / 6
        Rohan and Dev pay 2x a single share each.
        Rounding remainder to payer.
        """
        total_shares = sum(Decimal(str(s['value'])) for s in splits)
        if total_shares == 0:
            raise ValueError("Total shares cannot be zero.")
        
        per_share = total / total_shares
        result = {}
        for s in splits:
            shares = Decimal(str(s['value']))
            amt = (per_share * shares).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            result[s['user_id']] = amt
        
        diff = total - sum(result.values())
        if diff != 0 and paid_by_id in result:
            result[paid_by_id] += diff
        
        return result
