import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGroupStore } from '../store/groupStore';
import { useAuthStore } from '../store/authStore';
import api from '../api/axios';
import { Users, Calendar, Plus, RefreshCw, LogOut, Info } from 'lucide-react';

// Inner component to fetch and render the user's balance for a specific group
function GroupBalanceChip({ groupId, currentUserId }) {
  const [balanceData, setBalanceData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.get(`/api/groups/${groupId}/balances/`)
      .then((res) => {
        if (active) {
          const userBal = res.data.balances.find((b) => b.user_id === currentUserId);
          setBalanceData(userBal);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [groupId, currentUserId]);

  if (loading) {
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-400 animate-pulse">
        Checking...
      </span>
    );
  }

  if (!balanceData) {
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
        No balance
      </span>
    );
  }

  const bal = balanceData.net_balance_inr;
  if (bal > 0.005) {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800" aria-label={`You are owed ₹${bal.toFixed(2)}`}>
        ↑ You are owed ₹{bal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
      </span>
    );
  } else if (bal < -0.005) {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800" aria-label={`You owe ₹${Math.abs(bal).toFixed(2)}`}>
        ↓ You owe ₹{Math.abs(bal).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
      </span>
    );
  } else {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-600" aria-label="Settled up">
        Settled
      </span>
    );
  }
}

export default function GroupsPage() {
  const { groups, fetchGroups, createGroup, isLoadingGroups } = useGroupStore();
  const { user, logout } = useAuthStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupDesc, setNewGroupDesc] = useState('');
  const [modalError, setModalError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchGroups();
  }, [fetchGroups]);

  const handleCreateGroup = async (e) => {
    e.preventDefault();
    if (!newGroupName.trim()) return;
    setIsSubmitting(true);
    setModalError('');
    try {
      await createGroup(newGroupName, newGroupDesc);
      setNewGroupName('');
      setNewGroupDesc('');
      setIsModalOpen(false);
    } catch (err) {
      setModalError(err.error || 'Failed to create group');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Navigation Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10" role="banner">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center h-16">
          <div className="flex items-center space-x-3">
            <span className="text-2xl" aria-hidden="true">💸</span>
            <span className="font-extrabold text-xl text-gray-900 tracking-tight">Flat Expenses</span>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div
                className="h-8 w-8 rounded-full flex items-center justify-center text-white font-bold text-sm"
                style={{ backgroundColor: user?.avatar_color || '#4f46e5' }}
              >
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <span className="text-sm font-semibold text-gray-700 hidden sm:inline">{user?.name}</span>
            </div>
            <button
              onClick={logout}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:ring-2 focus:ring-indigo-500"
              aria-label="Logout"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Skip to Main Content target */}
        <div id="main-content" tabIndex="-1" className="outline-none" />

        {/* Page Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight">My Groups</h1>
            <p className="mt-1 text-sm text-gray-500">Select a group to manage expenses or start a new one</p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-4 rounded-lg shadow-sm text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            aria-haspopup="dialog"
            aria-expanded={isModalOpen}
          >
            <Plus className="h-5 w-5" />
            <span>Create Group</span>
          </button>
        </div>

        {/* Groups Grid */}
        {isLoadingGroups ? (
          <div className="flex justify-center items-center py-20">
            <RefreshCw className="h-8 w-8 text-indigo-600 animate-spin" />
            <span className="ml-3 text-gray-600 font-medium">Loading groups...</span>
          </div>
        ) : groups.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-2xl border border-gray-200 shadow-sm p-8 max-w-md mx-auto">
            <span className="text-4xl" aria-hidden="true">🏢</span>
            <h3 className="mt-4 text-lg font-bold text-gray-900">No Groups Found</h3>
            <p className="mt-2 text-sm text-gray-500">
              You are not a member of any shared flat groups yet. Create one or ask your flatmate to invite you.
            </p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="mt-6 inline-flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-4 rounded-lg shadow-sm text-sm"
            >
              <Plus className="h-4 w-4" />
              <span>Get Started</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {groups.map((group) => (
              <div
                key={group.id}
                onClick={() => navigate(`/groups/${group.id}`)}
                className="bg-white rounded-2xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer overflow-hidden flex flex-col justify-between"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    navigate(`/groups/${group.id}`);
                  }
                }}
                aria-label={`Group ${group.name}. ${group.description || ''}`}
              >
                <div className="p-6 flex-grow">
                  <h3 className="text-lg font-bold text-gray-900 truncate">{group.name}</h3>
                  <p className="text-xs text-gray-500 mt-1 line-clamp-2 min-h-[32px]">{group.description || 'No description provided'}</p>

                  <div className="flex items-center space-x-4 mt-4 text-xs font-semibold text-gray-600">
                    <span className="flex items-center space-x-1">
                      <Users className="h-4 w-4 text-gray-400" aria-hidden="true" />
                      <span>{group.member_count} members</span>
                    </span>
                    {group.last_expense_date && (
                      <span className="flex items-center space-x-1">
                        <Calendar className="h-4 w-4 text-gray-400" aria-hidden="true" />
                        <span>
                          Active:{' '}
                          {new Date(group.last_expense_date).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                          })}
                        </span>
                      </span>
                    )}
                  </div>
                </div>

                <div className="bg-gray-50 px-6 py-4 border-t border-gray-100 flex items-center justify-between">
                  <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">Your Balance</span>
                  {user && <GroupBalanceChip groupId={group.id} currentUserId={user.id} />}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Create Group Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="modal-title">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden border border-gray-100">
            <form onSubmit={handleCreateGroup}>
              <div className="p-6">
                <h2 id="modal-title" className="text-xl font-bold text-gray-900 mb-4">Create New Group</h2>

                {modalError && (
                  <div className="mb-4 bg-rose-50 border border-rose-200 text-rose-700 px-3 py-2 rounded text-sm font-semibold" role="alert">
                    {modalError}
                  </div>
                )}

                <div className="space-y-4">
                  <div>
                    <label htmlFor="group-name" className="block text-sm font-semibold text-gray-700 mb-1">
                      Group Name
                    </label>
                    <input
                      id="group-name"
                      type="text"
                      required
                      value={newGroupName}
                      onChange={(e) => setNewGroupName(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                      placeholder="e.g. Flat 404, Summer Trip"
                    />
                  </div>

                  <div>
                    <label htmlFor="group-desc" className="block text-sm font-semibold text-gray-700 mb-1">
                      Description
                    </label>
                    <textarea
                      id="group-desc"
                      rows="3"
                      value={newGroupDesc}
                      onChange={(e) => setNewGroupDesc(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                      placeholder="Describe what this group is for..."
                    />
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 px-6 py-4 flex justify-end space-x-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold text-gray-700 bg-white hover:bg-gray-50 focus:ring-2 focus:ring-indigo-500"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !newGroupName.trim()}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold shadow-sm disabled:opacity-50 flex items-center space-x-1"
                >
                  {isSubmitting && <RefreshCw className="h-4 w-4 animate-spin mr-1" />}
                  <span>Create Group</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
