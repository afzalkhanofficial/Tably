import React, { useState } from 'react';
import { AlertTriangle, Check, RefreshCw } from 'lucide-react';

/**
 * AnomalyCard renders the CSV import anomaly and provides interactive options
 * to resolve the issue inline.
 * Props:
 *   - anomaly: The ImportAnomaly object
 *   - members: List of current group members (to select from for paid_by, etc.)
 *   - onResolve: callback(choice, value) returning a promise
 */
export default function AnomalyCard({ anomaly, members = [], onResolve }) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [selectedPayer, setSelectedPayer] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [isEditingManually, setIsEditingManually] = useState(false);

  const handleResolveAction = async (choice, value = null) => {
    setIsSubmitting(true);
    setError(null);
    try {
      await onResolve(anomaly.id, choice, value);
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Resolution failed');
      setIsSubmitting(false);
    }
  };

  const anomalyType = anomaly.anomaly_type;
  const rawData = anomaly.raw_row_data || {};

  // Formats raw data for monospace display
  const rawCsvString = Object.entries(rawData)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' | ');

  return (
    <div
      className="bg-white rounded-lg border-l-4 border-rose-500 shadow-sm border border-gray-200 overflow-hidden"
      role="region"
      aria-label={`Anomaly in row ${anomaly.row_number}: ${anomaly.description}`}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5 text-rose-500 flex-shrink-0" aria-hidden="true" />
            <h5 className="font-semibold text-gray-900 text-sm">
              Row {anomaly.row_number}: {anomalyType.replace(/_/g, ' ')}
            </h5>
          </div>
          <span className="text-xs font-mono text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
            ID: {anomaly.id}
          </span>
        </div>

        {/* Monospace CSV row data */}
        <div className="mt-2 text-xs font-mono bg-gray-900 text-gray-100 p-2.5 rounded overflow-x-auto leading-relaxed">
          <code>{rawCsvString || JSON.stringify(rawData)}</code>
        </div>

        {/* Problem description */}
        <p className="mt-3 text-sm text-gray-700 font-medium">
          {anomaly.description}
        </p>

        {/* Dynamic Action Buttons based on Anomaly Type */}
        <div className="mt-4 border-t border-gray-100 pt-3">
          {isSubmitting ? (
            <div className="flex items-center space-x-2 text-indigo-600 text-sm py-1.5">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Resolving anomaly...</span>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2 items-center">
              {/* EXACT DUPLICATE */}
              {anomalyType === 'EXACT_DUPLICATE' && (
                <>
                  <button
                    onClick={() => handleResolveAction('keep')}
                    className="inline-flex items-center px-3 py-1.5 border border-indigo-600 text-indigo-600 rounded-md text-xs font-semibold hover:bg-indigo-50 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    aria-label={`Keep duplicate row ${anomaly.row_number}`}
                  >
                    Keep Duplicate Row
                  </button>
                  <button
                    onClick={() => handleResolveAction('skip')}
                    className="inline-flex items-center px-3 py-1.5 bg-rose-600 text-white rounded-md text-xs font-semibold hover:bg-rose-700 focus:ring-2 focus:ring-rose-500 focus:outline-none"
                    aria-label={`Skip duplicate row ${anomaly.row_number}`}
                  >
                    Skip Row
                  </button>
                </>
              )}

              {/* CONFLICTING DUPLICATE */}
              {anomalyType === 'CONFLICTING_DUPLICATE' && (
                <>
                  <button
                    onClick={() => handleResolveAction('keep')}
                    className="inline-flex items-center px-3 py-1.5 border border-indigo-600 text-indigo-600 rounded-md text-xs font-semibold hover:bg-indigo-50 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  >
                    Keep Both Rows
                  </button>
                  <button
                    onClick={() => handleResolveAction('skip')}
                    className="inline-flex items-center px-3 py-1.5 bg-rose-600 text-white rounded-md text-xs font-semibold hover:bg-rose-700 focus:ring-2 focus:ring-rose-500 focus:outline-none"
                  >
                    Skip This Row
                  </button>
                  {anomaly.suggested_fix?.conflicting_row && (
                    <button
                      onClick={() =>
                        handleResolveAction('set_value', {
                          total_amount: parseFloat(anomaly.suggested_fix.conflicting_row.amount),
                        })
                      }
                      className="inline-flex items-center px-3 py-1.5 border border-gray-300 bg-white text-gray-700 rounded-md text-xs font-semibold hover:bg-gray-50 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    >
                      Use Conflicting Row Amount (₹{anomaly.suggested_fix.conflicting_row.amount})
                    </button>
                  )}
                </>
              )}

              {/* PERCENTAGE SUM ERROR */}
              {anomalyType === 'PERCENTAGE_SUM_ERROR' && (
                <>
                  <button
                    onClick={() => {
                      if (anomaly.suggested_fix?.scaled_splits) {
                        handleResolveAction('set_value', {
                          splits: anomaly.suggested_fix.scaled_splits,
                        });
                      } else {
                        handleResolveAction('keep');
                      }
                    }}
                    className="inline-flex items-center px-3 py-1.5 bg-indigo-600 text-white rounded-md text-xs font-semibold hover:bg-indigo-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  >
                    Scale to 100% Automatically
                  </button>
                  {!isEditingManually ? (
                    <button
                      onClick={() => setIsEditingManually(true)}
                      className="inline-flex items-center px-3 py-1.5 border border-gray-300 bg-white text-gray-700 rounded-md text-xs font-semibold hover:bg-gray-50 focus:ring-2 focus:ring-indigo-500"
                    >
                      Edit Manually
                    </button>
                  ) : (
                    <div className="flex items-center space-x-2 mt-2 w-full">
                      <input
                        type="text"
                        placeholder="Comma separated values e.g. 50,50"
                        value={customValue}
                        onChange={(e) => setCustomValue(e.target.value)}
                        className="rounded-md border-gray-300 text-xs py-1 px-2 focus:ring-indigo-500 focus:border-indigo-500"
                        aria-label="Enter manual split values"
                      />
                      <button
                        onClick={() => {
                          const splitsArray = customValue.split(',').map((val, idx) => ({
                            user_id: members[idx]?.id || 1,
                            value: parseFloat(val.trim()) || 0,
                          }));
                          handleResolveAction('set_value', { splits: splitsArray });
                        }}
                        className="bg-indigo-600 text-white px-2 py-1 rounded text-xs"
                      >
                        Submit
                      </button>
                      <button
                        onClick={() => setIsEditingManually(false)}
                        className="text-gray-500 text-xs hover:underline"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* MISSING PAID BY / NAME FUZZY MATCH */}
              {(anomalyType === 'MISSING_PAID_BY' || anomalyType === 'NAME_FUZZY_MATCH') && (
                <div className="flex items-center space-x-2 w-full sm:w-auto">
                  <select
                    value={selectedPayer}
                    onChange={(e) => setSelectedPayer(e.target.value)}
                    className="rounded-md border-gray-300 text-xs py-1.5 pl-3 pr-8 focus:ring-indigo-500 focus:border-indigo-500 bg-white border"
                    aria-label="Select payer to resolve anomaly"
                  >
                    <option value="">-- Select Payer --</option>
                    {members.map((m) => (
                      <option key={m.id} value={m.name}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={!selectedPayer}
                    onClick={() => handleResolveAction('set_value', { paid_by: selectedPayer })}
                    className="inline-flex items-center px-3 py-1.5 bg-indigo-600 text-white rounded-md text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  >
                    Confirm Payer
                  </button>
                </div>
              )}

              {/* AMBIGUOUS DATE */}
              {anomalyType === 'AMBIGUOUS_DATE' && (
                <>
                  {anomaly.suggested_fix?.options?.map((dateOpt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleResolveAction('set_value', { expense_date: dateOpt })}
                      className="inline-flex items-center px-3 py-1.5 border border-indigo-600 text-indigo-600 bg-white rounded-md text-xs font-semibold hover:bg-indigo-50 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    >
                      {new Date(dateOpt).toLocaleDateString('en-US', {
                        month: 'long',
                        day: 'numeric',
                        year: 'numeric',
                      })}
                    </button>
                  ))}
                </>
              )}

              {/* UNKNOWN MEMBER */}
              {anomalyType === 'UNKNOWN_MEMBER' && (
                <>
                  <button
                    onClick={() => handleResolveAction('keep')}
                    className="inline-flex items-center px-3 py-1.5 bg-indigo-600 text-white rounded-md text-xs font-semibold hover:bg-indigo-700 focus:ring-2 focus:ring-indigo-500"
                  >
                    Add as Guest
                  </button>
                  <button
                    onClick={() => handleResolveAction('skip')}
                    className="inline-flex items-center px-3 py-1.5 border border-rose-600 text-rose-600 bg-white rounded-md text-xs font-semibold hover:bg-rose-50 focus:ring-2 focus:ring-rose-500"
                  >
                    Split Among Group (Skip Member)
                  </button>
                </>
              )}

              {/* MEMBER POST DEPARTURE */}
              {anomalyType === 'MEMBER_POST_DEPARTURE' && (
                <>
                  <button
                    onClick={() => handleResolveAction('skip')}
                    className="inline-flex items-center px-3 py-1.5 bg-rose-600 text-white rounded-md text-xs font-semibold hover:bg-rose-700 focus:ring-2 focus:ring-rose-500"
                  >
                    Confirm Removal
                  </button>
                  <button
                    onClick={() => handleResolveAction('keep')}
                    className="inline-flex items-center px-3 py-1.5 border border-indigo-600 text-indigo-600 bg-white rounded-md text-xs font-semibold hover:bg-indigo-50 focus:ring-2 focus:ring-indigo-500"
                  >
                    Override & Keep
                  </button>
                </>
              )}

              {/* MISSING CURRENCY */}
              {anomalyType === 'MISSING_CURRENCY' && (
                <>
                  <button
                    onClick={() => handleResolveAction('set_value', { currency: 'INR' })}
                    className="inline-flex items-center px-3 py-1.5 bg-indigo-600 text-white rounded-md text-xs font-semibold hover:bg-indigo-700 focus:ring-2 focus:ring-indigo-500"
                  >
                    Confirm INR
                  </button>
                  <button
                    onClick={() => handleResolveAction('set_value', { currency: 'USD' })}
                    className="inline-flex items-center px-3 py-1.5 border border-indigo-600 text-indigo-600 bg-white rounded-md text-xs font-semibold hover:bg-indigo-50 focus:ring-2 focus:ring-indigo-500"
                  >
                    Set USD
                  </button>
                  <button
                    onClick={() => handleResolveAction('set_value', { currency: 'EUR' })}
                    className="inline-flex items-center px-3 py-1.5 border border-indigo-600 text-indigo-600 bg-white rounded-md text-xs font-semibold hover:bg-indigo-50 focus:ring-2 focus:ring-indigo-500"
                  >
                    Set EUR
                  </button>
                </>
              )}

              {/* Fallback for other anomaly types */}
              {!['EXACT_DUPLICATE', 'CONFLICTING_DUPLICATE', 'PERCENTAGE_SUM_ERROR', 'MISSING_PAID_BY', 'NAME_FUZZY_MATCH', 'AMBIGUOUS_DATE', 'UNKNOWN_MEMBER', 'MEMBER_POST_DEPARTURE', 'MISSING_CURRENCY'].includes(anomalyType) && (
                <>
                  <button
                    onClick={() => handleResolveAction('keep')}
                    className="inline-flex items-center px-3 py-1.5 bg-indigo-600 text-white rounded-md text-xs font-semibold hover:bg-indigo-700 focus:ring-2 focus:ring-indigo-500"
                  >
                    Accept Suggested Fix
                  </button>
                  <button
                    onClick={() => handleResolveAction('skip')}
                    className="inline-flex items-center px-3 py-1.5 border border-rose-600 text-rose-600 bg-white rounded-md text-xs font-semibold hover:bg-rose-50 focus:ring-2 focus:ring-rose-500"
                  >
                    Skip Row
                  </button>
                </>
              )}
            </div>
          )}
        </div>

        {/* Error message */}
        {error && (
          <div className="mt-2 text-xs text-rose-600 font-semibold" aria-live="polite">
            Error: {error}
          </div>
        )}
      </div>
    </div>
  );
}
