import React, { useState } from 'react';
import { useGroupStore } from '../store/groupStore';
import { Calendar, UserPlus, UserMinus, Clock, ChevronLeft, AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const DEMO_USERS = [
  { id: 1, name: 'Aisha', email: 'aisha@test.com' },
  { id: 2, name: 'Rohan', email: 'rohan@test.com' },
  { id: 3, name: 'Meera', email: 'meera@test.com' },
  { id: 4, name: 'Sam', email: 'sam@test.com' },
];

export default function MembersPage() {
  const { currentGroup, addMember, departMember, error } = useGroupStore();
  const [searchEmail, setSearchEmail] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [joinDate, setJoinDate] = useState(new Date().toISOString().split('T')[0]);
  const [leftDate, setLeftDate] = useState(new Date().toISOString().split('T')[0]);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isDepartOpen, setIsDepartOpen] = useState(null); // stores user object
  const [actionError, setActionError] = useState('');
  const navigate = useNavigate();

  if (!currentGroup) {
    return (
      <div className="p-8 text-center text-gray-500">
        <p>No group selected. Please return to the dashboard.</p>
        <button onClick={() => navigate('/groups')} className="mt-4 text-indigo-600 font-semibold underline">
          Go to Groups
        </button>
      </div>
    );
  }

  const handleSearch = (val) => {
    setSearchEmail(val);
    if (!val.trim()) {
      setSearchResults([]);
      return;
    }
    // Filter demo users by email, excluding users already in the group
    const existingIds = new Set(currentGroup.members.map((m) => m.user_id));
    const filtered = DEMO_USERS.filter(
      (u) => u.email.toLowerCase().includes(val.toLowerCase()) && !existingIds.has(u.id)
    );
    setSearchResults(filtered);
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!selectedUser) return;
    setActionError('');
    try {
      await addMember(currentGroup.id, selectedUser.id, joinDate);
      setIsAddOpen(false);
      setSelectedUser(null);
      setSearchEmail('');
      setSearchResults([]);
    } catch (err) {
      setActionError(err.user_id?.[0] || err.error || 'Failed to add member');
    }
  };

  const handleDepartMember = async (e) => {
    e.preventDefault();
    if (!isDepartOpen) return;
    setActionError('');
    try {
      await departMember(currentGroup.id, isDepartOpen.user_id, leftDate);
      setIsDepartOpen(null);
    } catch (err) {
      setActionError(err.left_at?.[0] || err.error || 'Failed to mark member as departed');
    }
  };

  const activeMembers = currentGroup.members.filter((m) => m.is_active);
  const pastMembers = currentGroup.members.filter((m) => !m.is_active);

  // Timeline Helper Calculations
  const getTimelineStats = () => {
    const dates = currentGroup.members.flatMap((m) => [
      new Date(m.joined_at),
      m.left_at ? new Date(m.left_at) : new Date(),
    ]);
    if (dates.length === 0) return { start: new Date(), end: new Date(), spanDays: 1 };
    
    const start = new Date(Math.min(...dates));
    const end = new Date(Math.max(...dates));
    const spanDays = Math.max((end - start) / (1000 * 60 * 60 * 24), 1);
    return { start, end, spanDays };
  };

  const { start: tlStart, spanDays: tlSpan } = getTimelineStats();

  const getPositionStyles = (joinedAt, leftAt) => {
    const jDate = new Date(joinedAt);
    const lDate = leftAt ? new Date(leftAt) : new Date();

    const leftPct = ((jDate - tlStart) / (1000 * 60 * 60 * 24) / tlSpan) * 100;
    const widthPct = ((lDate - jDate) / (1000 * 60 * 60 * 24) / tlSpan) * 100;

    return {
      left: `${Math.max(0, Math.min(leftPct, 100))}%`,
      width: `${Math.max(1, Math.min(widthPct, 100))}%`,
    };
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <button
        onClick={() => navigate(`/groups/${currentGroup.id}`)}
        className="inline-flex items-center space-x-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-700 mb-6 focus:ring-2 focus:ring-indigo-500 rounded"
        aria-label="Back to dashboard"
      >
        <ChevronLeft className="h-4 w-4" />
        <span>Back to Dashboard</span>
      </button>

      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">Manage Members</h1>
          <p className="mt-1 text-sm text-gray-500">{currentGroup.name} members directory & tenure timeline</p>
        </div>
        <button
          onClick={() => {
            setActionError('');
            setIsAddOpen(true);
          }}
          className="inline-flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 px-4 rounded-lg shadow-sm text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
        >
          <UserPlus className="h-5 w-5" />
          <span>Add Member</span>
        </button>
      </div>

      {actionError && (
        <div className="mb-6 p-4 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl flex items-center space-x-2" role="alert">
          <AlertCircle className="h-5 w-5 text-rose-500" />
          <span className="font-semibold">{actionError}</span>
        </div>
      )}

      {/* Grid of Active and Past Members */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10">
        {/* Active Members */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
            <span>Active Members ({activeMembers.length})</span>
          </h3>

          <div className="divide-y divide-gray-150">
            {activeMembers.map((m) => (
              <div key={m.user_id} className="py-4 flex justify-between items-center">
                <div>
                  <h4 className="font-bold text-gray-900 text-sm">{m.name}</h4>
                  <p className="text-xs text-gray-500">{m.email}</p>
                  <p className="text-xs text-gray-400 mt-1 flex items-center space-x-1">
                    <Clock className="h-3.5 w-3.5" />
                    <span>Joined: {new Date(m.joined_at).toLocaleDateString()}</span>
                  </p>
                </div>
                <button
                  onClick={() => {
                    setActionError('');
                    setIsDepartOpen(m);
                  }}
                  className="inline-flex items-center space-x-1 text-xs text-rose-600 hover:text-rose-700 border border-rose-200 hover:bg-rose-50 px-2 py-1.5 rounded-lg font-semibold"
                >
                  <UserMinus className="h-3.5 w-3.5" />
                  <span>Mark as Left</span>
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Past Members */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-gray-400" aria-hidden="true" />
            <span>Past Members ({pastMembers.length})</span>
          </h3>

          {pastMembers.length === 0 ? (
            <p className="text-sm text-gray-400 italic py-6 text-center">No past members found.</p>
          ) : (
            <div className="divide-y divide-gray-150">
              {pastMembers.map((m) => (
                <div key={m.user_id} className="py-4">
                  <h4 className="font-bold text-gray-500 text-sm">{m.name}</h4>
                  <p className="text-xs text-gray-400">{m.email}</p>
                  <p className="text-xs text-gray-400 mt-1 flex items-center space-x-1">
                    <Calendar className="h-3.5 w-3.5" />
                    <span>
                      Tenure: {new Date(m.joined_at).toLocaleDateString()} - {new Date(m.left_at).toLocaleDateString()}
                    </span>
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Tenure Timeline Chart */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 mb-10">
        <h3 className="text-lg font-bold text-gray-900 mb-2">Tenure Timeline</h3>
        <p className="text-xs text-gray-500 mb-6">Visual overview of roomates' durations in the apartment group</p>

        <div className="space-y-6 relative pt-4">
          {currentGroup.members.map((m) => {
            const styles = getPositionStyles(m.joined_at, m.left_at);
            return (
              <div key={m.user_id} className="relative">
                <div className="flex justify-between items-center text-xs mb-1">
                  <span className="font-bold text-gray-800">{m.name}</span>
                  <span className="text-gray-400 font-mono text-[10px]">
                    {m.joined_at} {m.left_at ? `to ${m.left_at}` : '(Current)'}
                  </span>
                </div>
                <div className="h-4 w-full bg-gray-100 rounded-full relative">
                  <div
                    style={styles}
                    className={`absolute h-full rounded-full transition-all duration-500 ${
                      m.is_active ? 'bg-indigo-600' : 'bg-gray-400'
                    }`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Add Member Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="add-modal-title">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden border border-gray-100">
            <form onSubmit={handleAddMember}>
              <div className="p-6">
                <h2 id="add-modal-title" className="text-xl font-bold text-gray-900 mb-4">Add Group Member</h2>

                <div className="space-y-4">
                  {/* Email Search Box */}
                  <div>
                    <label htmlFor="user-email-search" className="block text-sm font-semibold text-gray-700 mb-1">
                      Search User by Email
                    </label>
                    <input
                      id="user-email-search"
                      type="text"
                      value={searchEmail}
                      onChange={(e) => handleSearch(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                      placeholder="e.g. rohan@test.com"
                    />

                    {/* Search Results List */}
                    {searchResults.length > 0 && (
                      <div className="mt-2 border border-gray-200 rounded-lg divide-y divide-gray-100 bg-white max-h-40 overflow-y-auto">
                        {searchResults.map((u) => (
                          <div
                            key={u.id}
                            onClick={() => {
                              setSelectedUser(u);
                              setSearchResults([]);
                              setSearchEmail(u.email);
                            }}
                            className="p-2 hover:bg-indigo-50 cursor-pointer text-xs font-semibold text-gray-700 flex justify-between"
                          >
                            <span>{u.name}</span>
                            <span className="text-gray-400">{u.email}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {selectedUser && (
                    <div className="p-3 bg-indigo-50 border border-indigo-150 rounded-lg text-xs font-semibold text-indigo-900">
                      Selected: {selectedUser.name} ({selectedUser.email})
                    </div>
                  )}

                  <div>
                    <label htmlFor="join-date" className="block text-sm font-semibold text-gray-700 mb-1">
                      Join Date
                    </label>
                    <input
                      id="join-date"
                      type="date"
                      required
                      value={joinDate}
                      onChange={(e) => setJoinDate(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                    />
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 px-6 py-4 flex justify-end space-x-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsAddOpen(false)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold text-gray-700 bg-white hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!selectedUser}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold shadow-sm disabled:opacity-50"
                >
                  Add Member
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Mark as Left Modal */}
      {isDepartOpen && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4 z-50" role="dialog" aria-modal="true" aria-labelledby="depart-modal-title">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden border border-gray-100">
            <form onSubmit={handleDepartMember}>
              <div className="p-6">
                <h2 id="depart-modal-title" className="text-xl font-bold text-gray-900 mb-2">Mark Member as Departed</h2>
                <p className="text-xs text-gray-500 mb-4">
                  Setting a departure date will exclude this member from any new expenses added after this date.
                </p>

                <div className="space-y-4">
                  <div className="p-3 bg-gray-50 border rounded-lg text-xs font-semibold">
                    Member: {isDepartOpen.name} ({isDepartOpen.email})
                  </div>

                  <div>
                    <label htmlFor="left-date" className="block text-sm font-semibold text-gray-700 mb-1">
                      Departure Date
                    </label>
                    <input
                      id="left-date"
                      type="date"
                      required
                      value={leftDate}
                      onChange={(e) => setLeftDate(e.target.value)}
                      className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                    />
                  </div>
                </div>
              </div>

              <div className="bg-gray-50 px-6 py-4 flex justify-end space-x-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsDepartOpen(null)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-semibold text-gray-700 bg-white hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-sm font-semibold shadow-sm"
                >
                  Confirm Departure
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
