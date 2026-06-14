import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useGroupStore } from '../store/groupStore';
import { useAuthStore } from '../store/authStore';
import api from '../api/axios';
import CurrencyDisplay from '../components/CurrencyDisplay';
import SplitBuilder from '../components/SplitBuilder';
import ImportPage from './ImportPage';
import {
  Calendar,
  Users,
  DollarSign,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  X,
  CreditCard,
  Check,
  TrendingUp,
  Filter,
  ArrowRight,
  User,
  Settings,
  ArrowLeft,
  ArrowUpRight,
  ArrowDownLeft,
  RefreshCw,
} from 'lucide-react';

export default function GroupDashboard() {
  const { id } = useParams();
  const groupId = parseInt(id, 10);
  const navigate = useNavigate();
  const { user: currentUser } = useAuthStore();

  const {
    currentGroup,
    expenses,
    balances,
    currencyBreakdown,
    groupTotalSpentInr,
    settlementPlan,
    isLoadingGroupDetail,
    isLoadingExpenses,
    isLoadingBalances,
    fetchGroup,
    fetchExpenses,
    fetchBalances,
    addExpense,
    deleteExpense,
    recordSettlement,
  } = useGroupStore();

  // Dashboard state
  const [activeTab, setActiveTab] = useState('expenses'); // 'expenses' | 'balances' | 'plan' | 'import'
  const [isExpenseModalOpen, setIsExpenseModalOpen] = useState(false);
  const [isSettlementModalOpen, setIsSettlementModalOpen] = useState(false);
  
  // Expenses Filter state
  const [filterFromDate, setFilterFromDate] = useState('');
  const [filterToDate, setFilterToDate] = useState('');
  const [filterPaidBy, setFilterPaidBy] = useState('');
  const [filterSplitType, setFilterSplitType] = useState('');
  const [isFilterExpanded, setIsFilterExpanded] = useState(false);
  const [expensesPage, setExpensesPage] = useState(1);

  // Expanded Expense Rows
  const [expandedExpenses, setExpandedExpenses] = useState({});

  // Slide-in Breakdown panel
  const [breakdownUser, setBreakdownUser] = useState(null);
  const [breakdownData, setBreakdownData] = useState(null);
  const [isLoadingBreakdown, setIsLoadingBreakdown] = useState(false);

  // Settlement manual form state
  const [settlementFrom, setSettlementFrom] = useState('');
  const [settlementTo, setSettlementTo] = useState('');
  const [settlementAmount, setSettlementAmount] = useState('');
  const [settlementCurrency, setSettlementCurrency] = useState('INR');
  const [settlementNotes, setSettlementNotes] = useState('');
  const [settlementError, setSettlementError] = useState('');

  // Add Expense form state
  const [expDesc, setExpDesc] = useState('');
  const [expDate, setExpDate] = useState(new Date().toISOString().split('T')[0]);
  const [expAmount, setExpAmount] = useState('');
  const [expCurrency, setExpCurrency] = useState('INR');
  const [expPaidBy, setExpPaidBy] = useState('');
  const [expSplitType, setExpSplitType] = useState('equal');
  const [expSplits, setExpSplits] = useState([]);
  const [expNotes, setExpNotes] = useState('');
  const [expenseFormError, setExpenseFormError] = useState('');
  const [isExpenseSubmitting, setIsExpenseSubmitting] = useState(false);

  useEffect(() => {
    if (groupId) {
      fetchGroup(groupId).then((g) => {
        if (g.members && g.members.length > 0) {
          setExpPaidBy(g.members[0].user_id.toString());
        }
      });
      fetchExpenses(groupId);
      fetchBalances(groupId);
    }
  }, [groupId, fetchGroup, fetchExpenses, fetchBalances]);

  // Handle page pagination
  const handlePageChange = (newPage) => {
    setExpensesPage(newPage);
    fetchExpenses(groupId, {
      page: newPage,
      from_date: filterFromDate,
      to_date: filterToDate,
      paid_by: filterPaidBy,
      split_type: filterSplitType,
    });
  };

  // Reset all filters
  const handleResetFilters = () => {
    setFilterFromDate('');
    setFilterToDate('');
    setFilterPaidBy('');
    setFilterSplitType('');
    setExpensesPage(1);
    fetchExpenses(groupId, { page: 1 });
  };

  // Trigger filters
  const handleApplyFilters = (e) => {
    e?.preventDefault();
    setExpensesPage(1);
    fetchExpenses(groupId, {
      page: 1,
      from_date: filterFromDate,
      to_date: filterToDate,
      paid_by: filterPaidBy,
      split_type: filterSplitType,
    });
  };

  const toggleExpenseExpand = (id) => {
    setExpandedExpenses((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const openBreakdownPanel = async (member) => {
    setBreakdownUser(member);
    setIsLoadingBreakdown(true);
    setBreakdownData(null);
    try {
      const response = await api.get(`/api/groups/${groupId}/members/${member.user_id}/breakdown/`);
      setBreakdownData(response.data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoadingBreakdown(false);
    }
  };

  const handleDeleteExpenseClick = async (expenseId) => {
    if (window.confirm('Are you sure you want to delete this expense? This cannot be undone.')) {
      try {
        await deleteExpense(groupId, expenseId);
      } catch (err) {
        alert(err.error || 'Failed to delete expense');
      }
    }
  };

  // Add Expense submit handler
  const handleAddExpenseSubmit = async (e) => {
    e.preventDefault();
    setExpenseFormError('');
    if (!expDesc.trim() || !expAmount || parseFloat(expAmount) <= 0) {
      setExpenseFormError('Please enter a description and valid positive amount.');
      return;
    }

    setIsExpenseSubmitting(true);
    try {
      const payload = {
        description: expDesc,
        expense_date: expDate,
        total_amount: parseFloat(expAmount),
        currency: expCurrency,
        paid_by: parseInt(expPaidBy, 10),
        split_type: expSplitType,
        splits: expSplits,
        notes: expNotes,
      };

      await addExpense(groupId, payload);

      // Reset form
      setExpDesc('');
      setExpAmount('');
      setExpNotes('');
      setExpDate(new Date().toISOString().split('T')[0]);
      setIsExpenseModalOpen(false);
    } catch (err) {
      setExpenseFormError(err.error || 'Failed to add expense.');
    } finally {
      setIsExpenseSubmitting(false);
    }
  };

  // Settlement submit handler
  const handleSettlementSubmit = async (e) => {
    e?.preventDefault();
    setSettlementError('');
    if (!settlementFrom || !settlementTo || !settlementAmount || parseFloat(settlementAmount) <= 0) {
      setSettlementError('Please select payer, payee, and enter a valid positive amount.');
      return;
    }

    try {
      await recordSettlement(groupId, {
        paid_by: parseInt(settlementFrom, 10),
        paid_to: parseInt(settlementTo, 10),
        amount: parseFloat(settlementAmount),
        currency: settlementCurrency,
        notes: settlementNotes,
      });

      // Reset form
      setSettlementAmount('');
      setSettlementNotes('');
      setIsSettlementModalOpen(false);
    } catch (err) {
      setSettlementError(err.error || 'Failed to record settlement.');
    }
  };

  const handleQuickSettle = async (tx) => {
    if (window.confirm(`Mark ₹${tx.amount_inr.toFixed(2)} payment from ${tx.from_user.name} to ${tx.to_user.name} as settled?`)) {
      try {
        await recordSettlement(groupId, {
          paid_by: tx.from_user.id,
          paid_to: tx.to_user.id,
          amount: tx.amount_inr,
          currency: 'INR',
          notes: 'Settled via settlement plan',
        });
      } catch (err) {
        alert(err.error || 'Failed to record settlement');
      }
    }
  };

  if (isLoadingGroupDetail && !currentGroup) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <RefreshCw className="h-8 w-8 text-indigo-600 animate-spin" />
        <span className="ml-3 font-semibold text-gray-700">Loading Group...</span>
      </div>
    );
  }

  if (!currentGroup) {
    return (
      <div className="p-8 text-center text-gray-600">
        <p>Group not found.</p>
        <Link to="/groups" className="text-indigo-600 underline">Return to groups</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col md:flex-row">
      {/* Sidebar Navigation - Hidden on mobile, fixed left on desktop */}
      <aside className="w-full md:w-64 bg-white border-b md:border-b-0 md:border-r border-gray-200 flex flex-col justify-between shrink-0" role="complementary">
        <div className="p-6">
          <Link
            to="/groups"
            className="inline-flex items-center space-x-1 text-xs font-bold text-gray-500 hover:text-gray-900 mb-6"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>All Groups</span>
          </Link>

          <h2 className="text-xl font-black text-gray-900 leading-tight mb-1 truncate">{currentGroup.name}</h2>
          <p className="text-xs text-gray-500 truncate mb-6">{currentGroup.description || 'Flat share group'}</p>

          <nav className="space-y-1" aria-label="Group Dashboard Tabs">
            {[
              { id: 'expenses', label: 'Expenses', icon: CreditCard },
              { id: 'balances', label: 'Balances', icon: Users },
              { id: 'plan', label: 'Settlement Plan', icon: TrendingUp },
              { id: 'import', label: 'Import CSV', icon: ArrowUpRight },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-bold transition-colors ${
                    activeTab === tab.id
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                  aria-current={activeTab === tab.id ? 'page' : undefined}
                >
                  <Icon className="h-5 w-5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        <div className="p-6 border-t border-gray-100 flex items-center justify-between">
          <Link
            to={`/groups/${currentGroup.id}/members`}
            className="inline-flex items-center space-x-2 text-xs font-extrabold text-indigo-600 hover:text-indigo-700"
          >
            <Settings className="h-4 w-4" />
            <span>Manage Members</span>
          </Link>
        </div>
      </aside>

      {/* Main Content Pane */}
      <main className="flex-grow p-4 sm:p-6 lg:p-8 overflow-y-auto">
        {/* Tab Content Rendering */}

        {/* Tab: Expenses */}
        {activeTab === 'expenses' && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <h1 className="text-2xl font-black text-gray-900 tracking-tight">Expenses Ledger</h1>
                <p className="text-xs text-gray-500 mt-0.5">
                  Total group spend this month: <span className="font-bold text-gray-800">₹{currentGroup.total_spent_inr?.toLocaleString('en-IN')}</span>
                </p>
              </div>

              <div className="flex space-x-3 w-full sm:w-auto">
                <button
                  onClick={() => setIsExpenseModalOpen(true)}
                  className="flex-grow sm:flex-grow-0 inline-flex items-center justify-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 px-4 rounded-lg shadow-sm text-sm"
                >
                  <Plus className="h-4.5 w-4.5" />
                  <span>Add Expense</span>
                </button>
              </div>
            </div>

            {/* Filter Bar */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <button
                onClick={() => setIsFilterExpanded(!isFilterExpanded)}
                className="w-full px-4 py-3 flex items-center justify-between text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none"
              >
                <span className="flex items-center space-x-2">
                  <Filter className="h-4 w-4 text-gray-400" />
                  <span>Filter Expenses</span>
                </span>
                {isFilterExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>

              {isFilterExpanded && (
                <form onSubmit={handleApplyFilters} className="p-4 border-t border-gray-150 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50">
                  <div>
                    <label htmlFor="filter-from" className="block text-xs font-bold text-gray-600 mb-1">From Date</label>
                    <input
                      id="filter-from"
                      type="date"
                      value={filterFromDate}
                      onChange={(e) => setFilterFromDate(e.target.value)}
                      className="block w-full text-xs rounded-md border-gray-300 py-1.5 focus:ring-indigo-500 bg-white"
                    />
                  </div>
                  <div>
                    <label htmlFor="filter-to" className="block text-xs font-bold text-gray-600 mb-1">To Date</label>
                    <input
                      id="filter-to"
                      type="date"
                      value={filterToDate}
                      onChange={(e) => setFilterToDate(e.target.value)}
                      className="block w-full text-xs rounded-md border-gray-300 py-1.5 focus:ring-indigo-500 bg-white"
                    />
                  </div>
                  <div>
                    <label htmlFor="filter-payer" className="block text-xs font-bold text-gray-600 mb-1">Paid By</label>
                    <select
                      id="filter-payer"
                      value={filterPaidBy}
                      onChange={(e) => setFilterPaidBy(e.target.value)}
                      className="block w-full text-xs rounded-md border-gray-300 py-1.5 focus:ring-indigo-500 bg-white"
                    >
                      <option value="">All members</option>
                      {currentGroup.members.map((m) => (
                        <option key={m.user_id} value={m.user_id}>{m.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="filter-splittype" className="block text-xs font-bold text-gray-600 mb-1">Split Type</label>
                    <select
                      id="filter-splittype"
                      value={filterSplitType}
                      onChange={(e) => setFilterSplitType(e.target.value)}
                      className="block w-full text-xs rounded-md border-gray-300 py-1.5 focus:ring-indigo-500 bg-white"
                    >
                      <option value="">All split types</option>
                      <option value="equal">Equal</option>
                      <option value="unequal">Unequal</option>
                      <option value="percentage">Percentage</option>
                      <option value="share">Share ratio</option>
                    </select>
                  </div>
                  <div className="sm:col-span-2 md:col-span-4 flex justify-end space-x-2">
                    <button
                      type="button"
                      onClick={handleResetFilters}
                      className="px-3 py-1.5 border border-gray-300 rounded text-xs font-semibold text-gray-700 bg-white hover:bg-gray-50"
                    >
                      Reset
                    </button>
                    <button
                      type="submit"
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-xs font-semibold"
                    >
                      Apply Filters
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* Expense List */}
            {isLoadingExpenses ? (
              <div className="flex justify-center items-center py-20">
                <RefreshCw className="h-6 w-6 text-indigo-600 animate-spin" />
              </div>
            ) : expenses.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
                <span className="text-3xl">📭</span>
                <p className="text-sm text-gray-500 mt-3 font-semibold">No expenses found matching the selected criteria.</p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden divide-y divide-gray-150">
                {expenses.map((expense) => {
                  const isExpanded = !!expandedExpenses[expense.id];
                  const mySplit = expense.splits?.find((s) => s.user_id === currentUser?.id);
                  const paidByMe = expense.paid_by_id === currentUser?.id;

                  return (
                    <div key={expense.id} className="transition-colors hover:bg-gray-50">
                      {/* Condensed Row Header */}
                      <div
                        onClick={() => toggleExpenseExpand(expense.id)}
                        className="p-4 flex items-center justify-between cursor-pointer"
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleExpenseExpand(expense.id); }}
                        aria-expanded={isExpanded}
                      >
                        <div className="flex items-center space-x-3 w-2/3">
                          <span className="text-xl flex-shrink-0">🍽️</span>
                          <div className="truncate">
                            <h4 className="font-extrabold text-sm text-gray-900 truncate">{expense.description}</h4>
                            <p className="text-xs text-gray-500 flex items-center space-x-1.5 mt-0.5">
                              <span>{expense.paid_by?.name || 'Unknown'} paid</span>
                              <CurrencyDisplay amount={expense.total_amount} currency={expense.currency} amountInr={expense.amount_inr} showOriginal={true} />
                              <span className="hidden sm:inline">• {new Date(expense.expense_date).toLocaleDateString()}</span>
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center space-x-4 w-1/3 justify-end">
                          <div className="text-right">
                            {mySplit ? (
                              <div className="text-xs">
                                <span className="text-gray-500 block">Your share:</span>
                                <span className="font-extrabold text-indigo-700">
                                  ₹{parseFloat(mySplit.amount_owed).toFixed(2)}
                                </span>
                              </div>
                            ) : (
                              <span className="text-[10px] text-gray-400 font-semibold bg-gray-100 px-1.5 py-0.5 rounded">Not included</span>
                            )}
                          </div>

                          <div className="flex items-center space-x-2">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteExpenseClick(expense.id);
                              }}
                              className="text-gray-400 hover:text-rose-600 p-1 rounded transition-colors"
                              aria-label={`Delete expense: ${expense.description}`}
                            >
                              <Trash2 className="h-4.5 w-4.5" />
                            </button>
                            {isExpanded ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
                          </div>
                        </div>
                      </div>

                      {/* Expanded Splits Table */}
                      {isExpanded && (
                        <div className="px-6 py-4 bg-gray-50 border-t border-gray-150">
                          <div className="flex justify-between items-center mb-3">
                            <h5 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Exact Splits Breakdown</h5>
                            {expense.notes && (
                              <span className="text-xs text-gray-500 italic">Notes: {expense.notes}</span>
                            )}
                          </div>
                          
                          {expense.currency !== 'INR' && (
                            <div className="text-xs text-amber-600 font-semibold mb-3">
                              Original exchange rate applied: 1 {expense.currency} ≈ ₹{(parseFloat(expense.amount_inr) / parseFloat(expense.total_amount)).toFixed(2)}
                            </div>
                          )}

                          <table className="min-w-full divide-y divide-gray-200 text-xs">
                            <thead>
                              <tr className="text-left text-gray-500 uppercase tracking-wider font-bold">
                                <th className="pb-2">Participant</th>
                                <th className="pb-2 text-right">Owed Amount (Original)</th>
                                <th className="pb-2 text-right">Owed Amount (INR)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 text-gray-700">
                              {expense.splits?.map((split) => {
                                const origOwed = (parseFloat(split.amount_owed) / parseFloat(expense.amount_inr)) * parseFloat(expense.total_amount);
                                return (
                                  <tr key={split.id} className={split.user_id === currentUser?.id ? 'bg-indigo-50/50 font-bold' : ''}>
                                    <td className="py-2 flex items-center space-x-1.5">
                                      {split.user_id === currentUser?.id && <span className="text-[10px] bg-indigo-600 text-white px-1 py-0.2 rounded">Me</span>}
                                      <span>{split.user?.name}</span>
                                    </td>
                                    <td className="py-2 text-right">
                                      {expense.currency === 'INR' ? '—' : `${expense.currency} ${origOwed.toFixed(2)}`}
                                    </td>
                                    <td className="py-2 text-right font-semibold">
                                      ₹{parseFloat(split.amount_owed).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab: Balances */}
        {activeTab === 'balances' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h1 className="text-2xl font-black text-gray-900 tracking-tight">Net Balances</h1>
                <p className="text-xs text-gray-500 mt-0.5">Summary of ledger debts across active members</p>
              </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="bg-white border border-gray-200 p-6 rounded-2xl shadow-sm flex items-center space-x-4">
                <div className="p-3.5 bg-indigo-50 text-indigo-600 rounded-xl">
                  <CreditCard className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-bold uppercase tracking-wider">Group Total Spent</p>
                  <p className="text-xl font-black text-gray-900 mt-0.5">₹{groupTotalSpentInr.toLocaleString('en-IN')}</p>
                </div>
              </div>
              <div className="bg-white border border-gray-200 p-6 rounded-2xl shadow-sm flex items-center space-x-4">
                <div className="p-3.5 bg-emerald-50 text-emerald-600 rounded-xl">
                  <Users className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-bold uppercase tracking-wider">Active Members</p>
                  <p className="text-xl font-black text-gray-900 mt-0.5">{currentGroup.members?.filter(m => m.is_active).length}</p>
                </div>
              </div>
            </div>

            {/* Balances List */}
            {isLoadingBalances ? (
              <div className="flex justify-center items-center py-20">
                <RefreshCw className="h-6 w-6 text-indigo-600 animate-spin" />
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                {balances.map((memberBal) => {
                  const val = memberBal.net_balance_inr;
                  let bgClass = 'bg-gray-50 border-gray-200';
                  let textClass = 'text-gray-900';
                  let labelClass = 'text-gray-500 bg-gray-100';
                  let directionText = 'Settled';

                  if (val > 0.005) {
                    bgClass = 'bg-emerald-50/50 border-emerald-100 hover:bg-emerald-50';
                    textClass = 'text-emerald-800';
                    labelClass = 'text-emerald-700 bg-emerald-100';
                    directionText = 'Owed';
                  } else if (val < -0.005) {
                    bgClass = 'bg-rose-50/50 border-rose-100 hover:bg-rose-50';
                    textClass = 'text-rose-800';
                    labelClass = 'text-rose-700 bg-rose-100';
                    directionText = 'Owes';
                  }

                  return (
                    <div
                      key={memberBal.user_id}
                      onClick={() => openBreakdownPanel(memberBal)}
                      className={`p-6 border rounded-2xl shadow-sm cursor-pointer transition-colors flex items-center justify-between ${bgClass}`}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') openBreakdownPanel(memberBal); }}
                      aria-label={`${memberBal.name}: balance is ${val > 0 ? 'owed' : 'owes'} ₹${Math.abs(val).toFixed(2)}. Click to view breakdown.`}
                    >
                      <div className="flex items-center space-x-3 truncate">
                        <div
                          className="h-10 w-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
                          style={{ backgroundColor: memberBal.avatar_color || '#8b5cf6' }}
                        >
                          {memberBal.name?.charAt(0).toUpperCase()}
                        </div>
                        <div className="truncate">
                          <h4 className="font-extrabold text-sm text-gray-900 truncate">{memberBal.name}</h4>
                          <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-full mt-1 ${labelClass}`}>
                            {directionText}
                          </span>
                        </div>
                      </div>

                      <div className="text-right">
                        <span className={`text-xl font-black ${textClass}`}>
                          {val > 0 ? '+' : ''}₹{val.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab: Settlement Plan */}
        {activeTab === 'plan' && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <h1 className="text-2xl font-black text-gray-900 tracking-tight">Settlement Plan</h1>
                <p className="text-xs text-gray-500 mt-0.5">
                  Greedy minimization route: {settlementPlan.length} payments outstanding
                </p>
              </div>

              <button
                onClick={() => setIsSettlementModalOpen(true)}
                className="inline-flex items-center justify-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 px-4 rounded-lg shadow-sm text-sm"
              >
                <Plus className="h-4.5 w-4.5" />
                <span>Record Settlement</span>
              </button>
            </div>

            {settlementPlan.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-gray-200 shadow-sm p-6 max-w-sm mx-auto">
                <span className="text-3xl">🎉</span>
                <h3 className="mt-4 text-base font-bold text-gray-900">All Settled Up!</h3>
                <p className="mt-2 text-xs text-gray-500">There are no outstanding debts to clear within this group.</p>
              </div>
            ) : (
              <div className="space-y-4 max-w-xl">
                {settlementPlan.map((tx, idx) => (
                  <div
                    key={idx}
                    className="bg-white border border-gray-250 p-5 rounded-2xl shadow-sm flex flex-col sm:flex-row justify-between sm:items-center gap-4 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-center space-x-4">
                      {/* From Payer Avatar */}
                      <div className="flex items-center space-x-1.5">
                        <div
                          className="h-8 w-8 rounded-full flex items-center justify-center text-white font-bold text-xs"
                          style={{ backgroundColor: tx.from_user.avatar_color || '#ef4444' }}
                        >
                          {tx.from_user.name?.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-xs font-bold text-gray-800">{tx.from_user.name}</span>
                      </div>

                      <ArrowRight className="h-4 w-4 text-gray-400 flex-shrink-0" />

                      {/* To Payee Avatar */}
                      <div className="flex items-center space-x-1.5">
                        <div
                          className="h-8 w-8 rounded-full flex items-center justify-center text-white font-bold text-xs"
                          style={{ backgroundColor: tx.to_user.avatar_color || '#10b981' }}
                        >
                          {tx.to_user.name?.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-xs font-bold text-gray-800">{tx.to_user.name}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end space-x-4">
                      <span className="text-base font-black text-rose-600">
                        ₹{tx.amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                      <button
                        onClick={() => handleQuickSettle(tx)}
                        className="inline-flex items-center space-x-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm focus:ring-2 focus:ring-emerald-500"
                        aria-label={`Mark payment of ₹${tx.amount_inr.toFixed(2)} as settled`}
                      >
                        <Check className="h-3.5 w-3.5" />
                        <span>Settle Debt</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab: Import */}
        {activeTab === 'import' && (
          <ImportPage groupId={groupId} members={currentGroup.members} />
        )}
      </main>

      {/* Slide-in User Breakdown Panel */}
      {breakdownUser && (
        <div className="fixed inset-0 overflow-hidden z-40" role="dialog" aria-modal="true" aria-labelledby="breakdown-title">
          <div className="absolute inset-0 bg-gray-600 bg-opacity-50 transition-opacity" onClick={() => setBreakdownUser(null)} />
          <div className="fixed inset-y-0 right-0 pl-10 max-w-full flex">
            <div className="w-screen max-w-md bg-white shadow-xl flex flex-col">
              <div className="p-6 border-b border-gray-200 flex justify-between items-center bg-gray-50">
                <h3 id="breakdown-title" className="text-lg font-black text-gray-900 leading-tight">
                  {breakdownUser.name}'s Audit Trail
                </h3>
                <button
                  onClick={() => setBreakdownUser(null)}
                  className="text-gray-400 hover:text-gray-600 focus:outline-none"
                  aria-label="Close panel"
                >
                  <X className="h-6 w-6" />
                </button>
              </div>

              {isLoadingBreakdown ? (
                <div className="flex-grow flex items-center justify-center">
                  <RefreshCw className="h-6 w-6 text-indigo-600 animate-spin" />
                </div>
              ) : !breakdownData ? (
                <div className="flex-grow p-6 text-center text-gray-500">Failed to load breakdown.</div>
              ) : (
                <div className="flex-grow overflow-y-auto p-6 space-y-6">
                  {/* Summary */}
                  <div className="bg-indigo-50 border border-indigo-100 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <p className="text-xs text-indigo-600 font-bold uppercase tracking-wider">Final Ledger Balance</p>
                      <p className="text-2xl font-black text-indigo-900 mt-0.5">
                        ₹{breakdownData.final_balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </p>
                    </div>
                  </div>

                  {/* Table */}
                  <div className="space-y-4">
                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Transaction History</h4>
                    {breakdownData.entries?.length === 0 ? (
                      <p className="text-xs text-gray-400 italic">No transactions recorded for this user.</p>
                    ) : (
                      <div className="space-y-3">
                        {breakdownData.entries.map((entry, idx) => {
                          const eff = parseFloat(entry.net_effect_inr);
                          return (
                            <div key={idx} className="border border-gray-150 p-3 rounded-xl flex justify-between items-start text-xs hover:bg-gray-50 transition-colors">
                              <div>
                                <p className="font-extrabold text-gray-900">{entry.description}</p>
                                <p className="text-[10px] text-gray-400 mt-0.5">
                                  {new Date(entry.date).toLocaleDateString()} • {entry.type}
                                </p>
                              </div>
                              <div className="text-right">
                                <span className={`font-bold block ${eff >= 0 ? 'text-emerald-700' : 'text-rose-600'}`}>
                                  {eff >= 0 ? '+' : ''}₹{eff.toFixed(2)}
                                </span>
                                <span className="text-[10px] text-gray-400 font-semibold block mt-0.5">
                                  Bal: ₹{parseFloat(entry.running_balance).toFixed(2)}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Add Expense Modal */}
      {isExpenseModalOpen && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="add-exp-title">
          <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full overflow-hidden border border-gray-100 flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-gray-200 flex justify-between items-center">
              <h2 id="add-exp-title" className="text-xl font-bold text-gray-900">Add New Expense</h2>
              <button onClick={() => setIsExpenseModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-6 w-6" />
              </button>
            </div>

            <form onSubmit={handleAddExpenseSubmit} className="flex-grow overflow-y-auto p-6 space-y-4">
              {expenseFormError && (
                <div className="p-3 bg-rose-50 border border-rose-150 text-rose-700 rounded-lg text-xs font-semibold" role="alert">
                  {expenseFormError}
                </div>
              )}

              <div>
                <label htmlFor="exp-desc" className="block text-sm font-semibold text-gray-700 mb-1">Description</label>
                <input
                  id="exp-desc"
                  type="text"
                  required
                  value={expDesc}
                  onChange={(e) => setExpDesc(e.target.value)}
                  className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                  placeholder="e.g. WiFi, Groceries"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="exp-amount" className="block text-sm font-semibold text-gray-700 mb-1">Amount</label>
                  <input
                    id="exp-amount"
                    type="number"
                    step="0.01"
                    required
                    value={expAmount}
                    onChange={(e) => setExpAmount(e.target.value)}
                    className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label htmlFor="exp-curr" className="block text-sm font-semibold text-gray-700 mb-1">Currency</label>
                  <select
                    id="exp-curr"
                    value={expCurrency}
                    onChange={(e) => setExpCurrency(e.target.value)}
                    className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    <option value="INR">INR (₹)</option>
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="exp-date" className="block text-sm font-semibold text-gray-700 mb-1">Date</label>
                  <input
                    id="exp-date"
                    type="date"
                    required
                    value={expDate}
                    onChange={(e) => setExpDate(e.target.value)}
                    className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                  />
                </div>
                <div>
                  <label htmlFor="exp-payer" className="block text-sm font-semibold text-gray-700 mb-1">Paid By</label>
                  <select
                    id="exp-payer"
                    value={expPaidBy}
                    onChange={(e) => setExpPaidBy(e.target.value)}
                    className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    {currentGroup.members?.filter(m => m.is_active).map((m) => (
                      <option key={m.user_id} value={m.user_id}>{m.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor="exp-splittype" className="block text-sm font-semibold text-gray-700 mb-1">Split Type</label>
                <select
                  id="exp-splittype"
                  value={expSplitType}
                  onChange={(e) => setExpSplitType(e.target.value)}
                  className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white mb-2"
                >
                  <option value="equal">Split Equally</option>
                  <option value="unequal">Split Unequally (INR)</option>
                  <option value="percentage">Split by Percentage (%)</option>
                  <option value="share">Split by Shares ratio</option>
                </select>

                <SplitBuilder
                  splitType={expSplitType}
                  members={currentGroup.members?.filter(m => m.is_active)}
                  onChange={setExpSplits}
                  totalAmount={parseFloat(expAmount) || 0}
                />
              </div>

              <div>
                <label htmlFor="exp-notes" className="block text-sm font-semibold text-gray-700 mb-1">Notes</label>
                <textarea
                  id="exp-notes"
                  rows="2"
                  value={expNotes}
                  onChange={(e) => setExpNotes(e.target.value)}
                  className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                  placeholder="Optional detail notes..."
                />
              </div>

              <div className="bg-gray-50 py-4 flex justify-end space-x-3 border-t border-gray-100 mt-6 sticky bottom-0">
                <button
                  type="button"
                  onClick={() => setIsExpenseModalOpen(false)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold text-gray-700 bg-white hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isExpenseSubmitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold shadow-sm disabled:opacity-50"
                >
                  Save Expense
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Manual Settlement Modal */}
      {isSettlementModalOpen && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="settle-modal-title">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden border border-gray-100">
            <form onSubmit={handleSettlementSubmit}>
              <div className="p-6">
                <h2 id="settle-modal-title" className="text-xl font-bold text-gray-900 mb-4">Record Settlement</h2>

                {settlementError && (
                  <div className="mb-4 bg-rose-50 border border-rose-150 text-rose-750 px-3 py-2 rounded text-xs font-semibold" role="alert">
                    {settlementError}
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <label htmlFor="settle-from" className="block text-sm font-semibold text-gray-700 mb-1">From (Payer)</label>
                    <select
                      id="settle-from"
                      value={settlementFrom}
                      onChange={(e) => setSettlementFrom(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                    >
                      <option value="">-- Select Payer --</option>
                      {currentGroup.members?.map((m) => (
                        <option key={m.user_id} value={m.user_id}>{m.name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor="settle-to" className="block text-sm font-semibold text-gray-700 mb-1">To (Payee)</label>
                    <select
                      id="settle-to"
                      value={settlementTo}
                      onChange={(e) => setSettlementTo(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                    >
                      <option value="">-- Select Payee --</option>
                      {currentGroup.members?.map((m) => (
                        <option key={m.user_id} value={m.user_id}>{m.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="settle-amt" className="block text-sm font-semibold text-gray-700 mb-1">Amount</label>
                      <input
                        id="settle-amt"
                        type="number"
                        step="0.01"
                        required
                        value={settlementAmount}
                        onChange={(e) => setSettlementAmount(e.target.value)}
                        className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                        placeholder="0.00"
                      />
                    </div>
                    <div>
                      <label htmlFor="settle-curr" className="block text-sm font-semibold text-gray-700 mb-1">Currency</label>
                      <select
                        id="settle-curr"
                        value={settlementCurrency}
                        onChange={(e) => setSettlementCurrency(e.target.value)}
                        className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                      >
                        <option value="INR">INR (₹)</option>
                        <option value="USD">USD ($)</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label htmlFor="settle-notes" className="block text-sm font-semibold text-gray-700 mb-1">Notes</label>
                    <textarea
                      id="settle-notes"
                      rows="2"
                      value={settlementNotes}
                      onChange={(e) => setSettlementNotes(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 bg-white"
                      placeholder="e.g. GPay repayment, cash, etc."
                    />
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 px-6 py-4 flex justify-end space-x-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsSettlementModalOpen(false)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold text-gray-700 bg-white hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold shadow-sm"
                >
                  Record Settlement
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
