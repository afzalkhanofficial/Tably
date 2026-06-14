import { create } from 'zustand';
import api from '../api/axios';

export const useGroupStore = create((set, get) => ({
  groups: [],
  currentGroup: null,
  expenses: [],
  expensesCount: 0,
  expensesNext: null,
  expensesPrevious: null,
  balances: [],
  currencyBreakdown: {},
  groupTotalSpentInr: 0,
  settlementPlan: [],
  isLoadingGroups: false,
  isLoadingGroupDetail: false,
  isLoadingExpenses: false,
  isLoadingBalances: false,
  error: null,

  fetchGroups: async () => {
    set({ isLoadingGroups: true, error: null });
    try {
      const response = await api.get('/api/groups/');
      set({ groups: response.data, isLoadingGroups: false });
    } catch (err) {
      set({ error: err.response?.data?.error || err.message, isLoadingGroups: false });
    }
  },

  createGroup: async (name, description) => {
    try {
      const response = await api.post('/api/groups/', { name, description });
      // Refresh list
      await get().fetchGroups();
      return response.data;
    } catch (err) {
      throw err.response?.data || err;
    }
  },

  fetchGroup: async (id) => {
    set({ isLoadingGroupDetail: true, error: null });
    try {
      const response = await api.get(`/api/groups/${id}/`);
      set({ currentGroup: response.data, isLoadingGroupDetail: false });
      return response.data;
    } catch (err) {
      set({ error: err.response?.data?.error || err.message, isLoadingGroupDetail: false });
      throw err;
    }
  },

  fetchExpenses: async (id, filters = {}) => {
    set({ isLoadingExpenses: true, error: null });
    try {
      const params = new URLSearchParams();
      Object.keys(filters).forEach(key => {
        if (filters[key] !== undefined && filters[key] !== null && filters[key] !== '') {
          params.append(key, filters[key]);
        }
      });

      const response = await api.get(`/api/groups/${id}/expenses/?${params.toString()}`);
      
      // Since it's paginated, response.data has count, next, previous, results
      if (response.data && response.data.results !== undefined) {
        set({
          expenses: response.data.results,
          expensesCount: response.data.count,
          expensesNext: response.data.next,
          expensesPrevious: response.data.previous,
          isLoadingExpenses: false,
        });
      } else {
        set({
          expenses: response.data,
          expensesCount: response.data.length,
          expensesNext: null,
          expensesPrevious: null,
          isLoadingExpenses: false,
        });
      }
    } catch (err) {
      set({ error: err.response?.data?.error || err.message, isLoadingExpenses: false });
    }
  },

  fetchBalances: async (id, asOfDate = '') => {
    set({ isLoadingBalances: true, error: null });
    try {
      const url = asOfDate 
        ? `/api/groups/${id}/balances/?as_of_date=${asOfDate}`
        : `/api/groups/${id}/balances/`;

      const responseBalances = await api.get(url);
      const responsePlan = await api.get(`/api/groups/${id}/settlement-plan/`);

      set({
        balances: responseBalances.data.balances,
        currencyBreakdown: responseBalances.data.currency_breakdown,
        groupTotalSpentInr: responseBalances.data.group_total_spent_inr,
        settlementPlan: responsePlan.data.transactions,
        isLoadingBalances: false,
      });
    } catch (err) {
      set({ error: err.response?.data?.error || err.message, isLoadingBalances: false });
    }
  },

  addExpense: async (groupId, data) => {
    try {
      const response = await api.post(`/api/groups/${groupId}/expenses/`, data);
      // Refresh expenses and balances
      await get().fetchExpenses(groupId);
      await get().fetchBalances(groupId);
      // Refresh current group detail to update spend stats
      await get().fetchGroup(groupId);
      return response.data;
    } catch (err) {
      throw err.response?.data || err;
    }
  },

  deleteExpense: async (groupId, expenseId) => {
    try {
      await api.delete(`/api/groups/${groupId}/expenses/${expenseId}/`);
      // Refresh expenses and balances
      await get().fetchExpenses(groupId);
      await get().fetchBalances(groupId);
      await get().fetchGroup(groupId);
    } catch (err) {
      throw err.response?.data || err;
    }
  },

  recordSettlement: async (groupId, data) => {
    try {
      const response = await api.post(`/api/groups/${groupId}/settlements/`, data);
      // Refresh balances
      await get().fetchBalances(groupId);
      return response.data;
    } catch (err) {
      throw err.response?.data || err;
    }
  },

  addMember: async (groupId, userId, joinedAt) => {
    try {
      await api.post(`/api/groups/${groupId}/members/`, { user_id: userId, joined_at: joinedAt });
      await get().fetchGroup(groupId);
    } catch (err) {
      throw err.response?.data || err;
    }
  },

  departMember: async (groupId, userId, leftAt) => {
    try {
      await api.patch(`/api/groups/${groupId}/members/${userId}/`, { left_at: leftAt });
      await get().fetchGroup(groupId);
    } catch (err) {
      throw err.response?.data || err;
    }
  }
}));
