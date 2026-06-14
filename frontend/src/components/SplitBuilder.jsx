import React, { useState, useEffect } from 'react';

/**
 * SplitBuilder renders the user interface for defining expense splits.
 * Supports: equal, unequal, percentage, and share.
 * Props:
 *   - splitType: 'equal' | 'unequal' | 'percentage' | 'share'
 *   - members: Array of User objects
 *   - onChange: Function callback with splits array data
 *   - totalAmount: Number, total bill amount to split (in INR)
 */
export default function SplitBuilder({ splitType, members = [], onChange, totalAmount = 0 }) {
  // Store values per member: { [memberId]: valueAsString }
  const [values, setValues] = useState({});
  // Checkbox state for equal splits: { [memberId]: boolean }
  const [selected, setSelected] = useState({});

  // Initialize values when members or splitType changes
  useEffect(() => {
    const initialValues = {};
    const initialSelected = {};
    members.forEach((m) => {
      initialValues[m.id] = '';
      initialSelected[m.id] = true; // Default all selected in equal
    });
    setValues(initialValues);
    setSelected(initialSelected);
  }, [members, splitType]);

  // Handle equal split checkbox toggle
  const handleCheckboxToggle = (memberId) => {
    const nextSelected = { ...selected, [memberId]: !selected[memberId] };
    setSelected(nextSelected);

    // Filter to only checked users and map to payload
    const activeSplits = Object.keys(nextSelected)
      .filter((uid) => nextSelected[uid])
      .map((uid) => ({ user_id: parseInt(uid, 10), value: 1.0 }));
    onChange(activeSplits);
  };

  // Handle text input value change
  const handleValueChange = (memberId, val) => {
    const nextValues = { ...values, [memberId]: val };
    setValues(nextValues);

    // Prepare splits payload
    const activeSplits = members.map((m) => {
      const numVal = parseFloat(nextValues[m.id]) || 0;
      return {
        user_id: m.id,
        value: numVal,
      };
    });
    onChange(activeSplits);
  };

  // Live calculations
  const parsedTotal = parseFloat(totalAmount || 0);

  // 1. Unequal Splits: compute remaining INR to split
  const unequalSum = Object.values(values).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);
  const unequalRemaining = parsedTotal - unequalSum;

  // 2. Percentage Splits: compute total percentage
  const pctSum = Object.values(values).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);

  // 3. Share Splits: compute total shares
  const shareSum = Object.values(values).reduce((sum, v) => sum + (parseFloat(v) || 0), 0);

  return (
    <div className="space-y-4 rounded-lg bg-gray-50 p-4 border border-gray-200">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-800 uppercase tracking-wider">
          Split Configuration ({splitType})
        </h4>
        <span className="text-xs text-gray-500">
          Total Bill: ₹{parsedTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </span>
      </div>

      {splitType === 'equal' && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">Select which members share this bill equally:</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {members.map((m) => (
              <label
                key={m.id}
                className={`flex items-center space-x-3 rounded-md border p-2.5 transition-colors cursor-pointer ${
                  selected[m.id]
                    ? 'bg-indigo-50 border-indigo-200 text-indigo-900'
                    : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-100'
                }`}
              >
                <input
                  type="checkbox"
                  checked={!!selected[m.id]}
                  onChange={() => handleCheckboxToggle(m.id)}
                  className="h-4.5 w-4.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  aria-label={`Include ${m.name} in equal split`}
                />
                <span className="text-sm font-medium">{m.name}</span>
              </label>
            ))}
          </div>
          <div className="text-xs text-indigo-600 font-medium mt-2">
            Active participants:{' '}
            {Object.values(selected).filter(Boolean).length} of {members.length} (₹
            {Object.values(selected).filter(Boolean).length > 0
              ? (parsedTotal / Object.values(selected).filter(Boolean).length).toFixed(2)
              : '0.00'}{' '}
            each)
          </div>
        </div>
      )}

      {splitType === 'unequal' && (
        <div className="space-y-3">
          <div className="flex justify-between items-center text-xs font-semibold mb-1">
            <span className="text-gray-600">Enter exact amount per person (in INR):</span>
            <span className={unequalRemaining === 0 ? 'text-emerald-600' : 'text-amber-500'}>
              {unequalRemaining === 0
                ? '✅ Fully Allocated'
                : unequalRemaining > 0
                ? `Remaining to allocate: ₹${unequalRemaining.toFixed(2)}`
                : `Overallocated by: ₹${Math.abs(unequalRemaining).toFixed(2)}`}
            </span>
          </div>
          <div className="space-y-2">
            {members.map((m) => (
              <div key={m.id} className="flex items-center justify-between space-x-2">
                <span className="text-sm font-medium text-gray-700 w-1/3 truncate">{m.name}</span>
                <div className="relative rounded-md shadow-sm w-2/3">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                    <span className="text-gray-500 sm:text-sm">₹</span>
                  </div>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={values[m.id] || ''}
                    onChange={(e) => handleValueChange(m.id, e.target.value)}
                    className="block w-full rounded-md border-gray-300 pl-7 pr-3 py-1.5 focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                    aria-label={`INR split amount for ${m.name}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {splitType === 'percentage' && (
        <div className="space-y-3">
          <div className="flex justify-between items-center text-xs font-semibold mb-1">
            <span className="text-gray-600">Enter percentages per person:</span>
            <span className={pctSum === 100 ? 'text-emerald-600' : 'text-rose-600'}>
              Total: {pctSum}% (should be 100%)
            </span>
          </div>
          <div className="space-y-2">
            {members.map((m) => {
              const valNum = parseFloat(values[m.id]) || 0;
              const computedShare = (valNum / 100) * parsedTotal;
              return (
                <div key={m.id} className="flex items-center space-x-2 justify-between">
                  <span className="text-sm font-medium text-gray-700 w-1/3 truncate">{m.name}</span>
                  <div className="flex items-center space-x-2 w-2/3 justify-end">
                    <span className="text-xs text-gray-500">
                      ₹{computedShare.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <div className="relative rounded-md shadow-sm w-24">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        placeholder="0"
                        value={values[m.id] || ''}
                        onChange={(e) => handleValueChange(m.id, e.target.value)}
                        className="block w-full rounded-md border-gray-300 pr-7 pl-3 py-1.5 text-right focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                        aria-label={`Percentage share for ${m.name}`}
                      />
                      <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
                        <span className="text-gray-500 sm:text-sm">%</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {splitType === 'share' && (
        <div className="space-y-3">
          <div className="flex justify-between items-center text-xs font-semibold mb-1">
            <span className="text-gray-600">Enter share ratios (e.g. 1, 2, 0.5):</span>
            <span className="text-indigo-600">Total Shares: {shareSum}</span>
          </div>
          <div className="space-y-2">
            {members.map((m) => {
              const valNum = parseFloat(values[m.id]) || 0;
              const computedShare = shareSum > 0 ? (valNum / shareSum) * parsedTotal : 0;
              return (
                <div key={m.id} className="flex items-center space-x-2 justify-between">
                  <span className="text-sm font-medium text-gray-700 w-1/3 truncate">{m.name}</span>
                  <div className="flex items-center space-x-2 w-2/3 justify-end">
                    <span className="text-xs text-gray-500">
                      Share: ₹{computedShare.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <input
                      type="number"
                      min="0"
                      placeholder="0"
                      value={values[m.id] || ''}
                      onChange={(e) => handleValueChange(m.id, e.target.value)}
                      className="block w-24 rounded-md border-gray-300 px-3 py-1.5 text-right focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                      aria-label={`Share ratio for ${m.name}`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
