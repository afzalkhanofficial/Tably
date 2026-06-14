import { create } from 'zustand';
import api from '../api/axios';

export const useAuthStore = create((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post('/api/auth/login/', { email, password });
      const { tokens, user } = response.data;
      
      localStorage.setItem('access_token', tokens.access);
      localStorage.setItem('refresh_token', tokens.refresh);
      localStorage.setItem('user', JSON.stringify(user));

      set({
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
      return true;
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message || 'Login failed';
      set({
        isLoading: false,
        error: errorMsg,
      });
      throw err;
    }
  },

  logout: () => {
    localStorage.clear();
    set({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
  },

  initialize: async () => {
    set({ isLoading: true });
    const token = localStorage.getItem('access_token');
    const cachedUser = localStorage.getItem('user');
    
    if (token) {
      try {
        // Fetch fresh profile details from /api/auth/me/
        const response = await api.get('/api/auth/me/');
        const user = response.data;
        localStorage.setItem('user', JSON.stringify(user));
        set({
          user,
          isAuthenticated: true,
          isLoading: false,
        });
      } catch (err) {
        // Token might be expired/invalid
        if (cachedUser) {
          try {
            set({
              user: JSON.parse(cachedUser),
              isAuthenticated: true,
              isLoading: false,
            });
          } catch {
            get().logout();
          }
        } else {
          get().logout();
        }
      }
    } else {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  updateUser: (updatedUser) => {
    localStorage.setItem('user', JSON.stringify(updatedUser));
    set({ user: updatedUser });
  }
}));
