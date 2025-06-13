import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface UIState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  language: 'ko' | 'en';
  notifications: boolean;
  sounds: boolean;
  autoAnswer: boolean;
  currentPage: string;
  loading: {
    [key: string]: boolean;
  };
  modals: {
    customerInfo: boolean;
    callNotes: boolean;
    transfer: boolean;
    settings: boolean;
  };
  alerts: Array<{
    id: string;
    type: 'success' | 'error' | 'warning' | 'info';
    message: string;
    timestamp: Date;
    autoClose?: boolean;
  }>;
}

const initialState: UIState = {
  sidebarOpen: true,
  theme: 'light',
  language: 'ko',
  notifications: true,
  sounds: true,
  autoAnswer: false,
  currentPage: 'dashboard',
  loading: {},
  modals: {
    customerInfo: false,
    callNotes: false,
    transfer: false,
    settings: false,
  },
  alerts: [],
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen;
    },
    setSidebarOpen: (state, action: PayloadAction<boolean>) => {
      state.sidebarOpen = action.payload;
    },
    setTheme: (state, action: PayloadAction<'light' | 'dark'>) => {
      state.theme = action.payload;
    },
    setLanguage: (state, action: PayloadAction<'ko' | 'en'>) => {
      state.language = action.payload;
    },
    setNotifications: (state, action: PayloadAction<boolean>) => {
      state.notifications = action.payload;
    },
    setSounds: (state, action: PayloadAction<boolean>) => {
      state.sounds = action.payload;
    },
    setAutoAnswer: (state, action: PayloadAction<boolean>) => {
      state.autoAnswer = action.payload;
    },
    setCurrentPage: (state, action: PayloadAction<string>) => {
      state.currentPage = action.payload;
    },
    setLoading: (state, action: PayloadAction<{ key: string; loading: boolean }>) => {
      state.loading[action.payload.key] = action.payload.loading;
    },
    openModal: (state, action: PayloadAction<keyof UIState['modals']>) => {
      state.modals[action.payload] = true;
    },
    closeModal: (state, action: PayloadAction<keyof UIState['modals']>) => {
      state.modals[action.payload] = false;
    },
    closeAllModals: (state) => {
      Object.keys(state.modals).forEach(key => {
        state.modals[key as keyof UIState['modals']] = false;
      });
    },
    addAlert: (state, action: PayloadAction<Omit<UIState['alerts'][0], 'id' | 'timestamp'>>) => {
      const alert = {
        ...action.payload,
        id: Date.now().toString(),
        timestamp: new Date(),
      };
      state.alerts.push(alert);
    },
    removeAlert: (state, action: PayloadAction<string>) => {
      state.alerts = state.alerts.filter(alert => alert.id !== action.payload);
    },
    clearAlerts: (state) => {
      state.alerts = [];
    },
  },
});

export const {
  toggleSidebar,
  setSidebarOpen,
  setTheme,
  setLanguage,
  setNotifications,
  setSounds,
  setAutoAnswer,
  setCurrentPage,
  setLoading,
  openModal,
  closeModal,
  closeAllModals,
  addAlert,
  removeAlert,
  clearAlerts,
} = uiSlice.actions;

export default uiSlice.reducer; 