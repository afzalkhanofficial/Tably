import React, { useState, useEffect } from 'react';
import api from '../api/axios';
import AnomalyCard from '../components/AnomalyCard';
import { UploadCloud, CheckCircle, AlertCircle, FileText, ChevronDown, ChevronRight, Download, RefreshCw } from 'lucide-react';

export default function ImportPage({ groupId, members }) {
  const [step, setStep] = useState('upload'); // 'upload' | 'report'
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  // Report phase states
  const [session, setSession] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [resolvedCount, setResolvedCount] = useState(0);
  const [totalAnomaliesToResolve, setTotalAnomaliesToResolve] = useState(0);

  // Collapsible sections
  const [showAutoImported, setShowAutoImported] = useState(false);
  const [showAutoFixed, setShowAutoFixed] = useState(false);
  const [showNeedsReview, setShowNeedsReview] = useState(true);

  // Original parsed summary list for display
  const [summary, setSummary] = useState({
    total_rows: 0,
    auto_imported: 0,
    auto_fixed: 0,
    pending_review: 0,
    skipped: 0
  });

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append('csv_file', file);

    try {
      const response = await api.post(`/api/groups/${groupId}/import/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const data = response.data;
      setSession(data);
      setSummary(data.summary);
      setAnomalies(data.anomalies);
      setTotalAnomaliesToResolve(data.summary.pending_review);
      setResolvedCount(0);
      setStep('report');
    } catch (err) {
      setUploadError(err.response?.data?.error || err.message || 'Failed to upload file');
    } finally {
      setIsUploading(false);
    }
  };

  const handleResolveAnomaly = async (anomalyId, choice, value) => {
    try {
      const response = await api.post(`/api/import/${session.session_id}/anomalies/${anomalyId}/resolve/`, {
        choice,
        value,
      });

      // Update local anomalies list
      setAnomalies((prev) => prev.filter((a) => a.id !== anomalyId));
      setResolvedCount((prev) => prev + 1);

      // Re-fetch session status to verify it
      if (response.data.session_status === 'complete') {
        // Reload summary if needed
      }
    } catch (err) {
      throw err;
    }
  };

  const downloadReport = async () => {
    try {
      const response = await api.get(`/api/import/${session.session_id}/report/`);
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(response.data, null, 2));
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute("href", dataStr);
      downloadAnchor.setAttribute("download", `import_report_session_${session.session_id}.json`);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
    } catch (err) {
      alert('Failed to download report');
    }
  };

  return (
    <div className="space-y-6">
      {step === 'upload' && (
        <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <h3 className="text-lg font-bold text-gray-900 mb-4">Import Flat Bills from CSV</h3>
          
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-10 transition-colors ${
              dragActive ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 bg-gray-50'
            }`}
          >
            <UploadCloud className="h-12 w-12 text-gray-400 mb-4" />
            <p className="text-sm text-gray-700 font-semibold text-center">
              Drag your CSV file here or{' '}
              <label className="text-indigo-600 hover:text-indigo-700 cursor-pointer underline">
                click to browse
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </label>
            </p>
            <p className="text-xs text-gray-500 mt-2">Only .csv files up to 5MB are supported.</p>
          </div>

          {file && (
            <div className="mt-4 p-3 bg-indigo-50 border border-indigo-100 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FileText className="h-5 w-5 text-indigo-600" />
                <div>
                  <p className="text-sm font-semibold text-gray-900 truncate max-w-xs">{file.name}</p>
                  <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              </div>
              <button
                onClick={() => setFile(null)}
                className="text-gray-500 hover:text-gray-700 text-xs font-semibold"
              >
                Clear
              </button>
            </div>
          )}

          {uploadError && (
            <div className="mt-4 p-3 bg-rose-50 border border-rose-100 text-rose-700 rounded-lg text-sm font-semibold flex items-center space-x-2">
              <AlertCircle className="h-5 w-5 text-rose-500" />
              <span>{uploadError}</span>
            </div>
          )}

          <div className="mt-6 flex justify-end">
            <button
              onClick={handleUpload}
              disabled={!file || isUploading}
              className="inline-flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-6 rounded-lg shadow-sm text-sm disabled:opacity-50"
            >
              {isUploading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin mr-1" />
                  <span>Processing CSV...</span>
                </>
              ) : (
                <span>Upload and Process</span>
              )}
            </button>
          </div>
        </div>
      )}

      {step === 'report' && (
        <div className="space-y-6">
          {/* Summary Banner */}
          <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Import Session Summary</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="bg-emerald-50 border border-emerald-100 p-4 rounded-xl text-center">
                <span className="text-xl">✅</span>
                <p className="text-2xl font-black text-emerald-800 mt-1">{summary.auto_imported}</p>
                <p className="text-xs font-bold text-emerald-600 mt-0.5 uppercase tracking-wider">Clean Rows</p>
              </div>
              <div className="bg-amber-50 border border-amber-100 p-4 rounded-xl text-center">
                <span className="text-xl">🔧</span>
                <p className="text-2xl font-black text-amber-800 mt-1">{summary.auto_fixed}</p>
                <p className="text-xs font-bold text-amber-600 mt-0.5 uppercase tracking-wider">Auto-fixed</p>
              </div>
              <div className="bg-rose-50 border border-rose-100 p-4 rounded-xl text-center">
                <span className="text-xl">⚠️</span>
                <p className="text-2xl font-black text-rose-800 mt-1">{anomalies.length}</p>
                <p className="text-xs font-bold text-rose-600 mt-0.5 uppercase tracking-wider">Needs Review</p>
              </div>
              <div className="bg-gray-50 border border-gray-100 p-4 rounded-xl text-center">
                <span className="text-xl">⏭️</span>
                <p className="text-2xl font-black text-gray-800 mt-1">{summary.skipped}</p>
                <p className="text-xs font-bold text-gray-600 mt-0.5 uppercase tracking-wider">Skipped</p>
              </div>
            </div>

            {/* Resolution Progress Bar */}
            {totalAnomaliesToResolve > 0 && (
              <div className="mt-6">
                <div className="flex justify-between items-center text-xs font-semibold text-gray-600 mb-1">
                  <span>Anomalies resolved: {resolvedCount} of {totalAnomaliesToResolve}</span>
                  <span>{Math.round((resolvedCount / totalAnomaliesToResolve) * 100)}%</span>
                </div>
                <div className="w-full bg-gray-150 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-indigo-600 h-full transition-all duration-350"
                    style={{ width: `${(resolvedCount / totalAnomaliesToResolve) * 100}%` }}
                  />
                </div>
              </div>
            )}

            {anomalies.length === 0 && (
              <div className="mt-6 p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl flex items-center space-x-3">
                <CheckCircle className="h-6 w-6 text-emerald-600 flex-shrink-0" />
                <div>
                  <h4 className="font-extrabold text-sm">All done!</h4>
                  <p className="text-xs mt-0.5">All pending import reviews have been resolved and committed successfully.</p>
                </div>
              </div>
            )}

            <div className="mt-6 flex justify-between">
              <button
                onClick={() => setStep('upload')}
                className="text-xs font-bold text-indigo-600 hover:text-indigo-700 underline"
              >
                Upload another file
              </button>
              <button
                onClick={downloadReport}
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-xs font-semibold shadow-sm focus:ring-2 focus:ring-gray-300"
              >
                <Download className="h-4 w-4" />
                <span>Download Report</span>
              </button>
            </div>
          </div>

          {/* Section: Needs Your Review */}
          <div className="space-y-3">
            <button
              onClick={() => setShowNeedsReview(!showNeedsReview)}
              className="flex items-center space-x-2 text-sm font-bold text-gray-700 focus:outline-none"
            >
              {showNeedsReview ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              <span>NEEDS YOUR REVIEW ({anomalies.length})</span>
            </button>

            {showNeedsReview && (
              <div className="space-y-4">
                {anomalies.length === 0 ? (
                  <p className="text-xs text-gray-500 italic pl-6">No pending issues to review.</p>
                ) : (
                  anomalies.map((anomaly) => (
                    <AnomalyCard
                      key={anomaly.id}
                      anomaly={anomaly}
                      members={members}
                      onResolve={handleResolveAnomaly}
                    />
                  ))
                )}
              </div>
            )}
          </div>

          {/* Section: Auto-fixed */}
          <div className="space-y-3 border-t border-gray-200 pt-4">
            <button
              onClick={() => setShowAutoFixed(!showAutoFixed)}
              className="flex items-center space-x-2 text-sm font-bold text-gray-700 focus:outline-none"
            >
              {showAutoFixed ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              <span>AUTO-FIXED ({summary.auto_fixed})</span>
            </button>

            {showAutoFixed && (
              <div className="space-y-2 pl-6">
                {summary.auto_fixed === 0 ? (
                  <p className="text-xs text-gray-500 italic">No auto-fixed rows in this import.</p>
                ) : (
                  <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
                    <p className="text-xs text-gray-500 p-3">
                      These rows contained anomalies (like dates in different formats or trailing spaces in names) 
                      which were parsed, standard-formatted, and committed automatically.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Section: Clean / Auto-imported */}
          <div className="space-y-3 border-t border-gray-200 pt-4">
            <button
              onClick={() => setShowAutoImported(!showAutoImported)}
              className="flex items-center space-x-2 text-sm font-bold text-gray-700 focus:outline-none"
            >
              {showAutoImported ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              <span>AUTO-IMPORTED CLEAN ({summary.auto_imported})</span>
            </button>

            {showAutoImported && (
              <div className="space-y-2 pl-6">
                {summary.auto_imported === 0 ? (
                  <p className="text-xs text-gray-500 italic">No clean rows imported.</p>
                ) : (
                  <div className="bg-white border border-gray-200 rounded-xl p-3">
                    <p className="text-xs text-gray-600">
                      These rows were fully clean and committed instantly to the ledger.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
