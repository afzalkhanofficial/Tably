import React from 'react';

/**
 * CurrencyDisplay renders monetary amounts.
 * If currency is INR: "₹1,234.00"
 * If currency is foreign: "USD 84.00 (≈ ₹7,056.00)"
 * Formats using en-IN (lakhs/crores formatting).
 */
export default function CurrencyDisplay({ amount, currency = 'INR', amountInr, showOriginal = true }) {
  const parsedAmount = parseFloat(amount || 0);
  const parsedInr = parseFloat(amountInr || amount || 0);

  const formatINR = (val) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
  };

  const formatForeign = (val, curr) => {
    const formatted = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
    return `${curr} ${formatted}`;
  };

  if (currency === 'INR') {
    return <span className="font-semibold text-gray-900">{formatINR(parsedAmount)}</span>;
  }

  return (
    <span className="font-semibold text-gray-900">
      {showOriginal && <span>{formatForeign(parsedAmount, currency)} </span>}
      <span className="text-sm font-normal text-gray-500">
        (≈ {formatINR(parsedInr)})
      </span>
    </span>
  );
}
