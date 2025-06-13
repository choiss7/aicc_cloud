import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Customer {
  id: string;
  name: string;
  email: string;
  phone: string;
  address?: string;
  dateOfBirth?: string;
  gender?: 'male' | 'female' | 'other';
  preferredLanguage: string;
  customerType: 'individual' | 'business';
  status: 'active' | 'inactive' | 'blocked';
  createdAt: Date;
  updatedAt: Date;
  tags: string[];
  notes: string;
  // 금융 관련 정보
  accountNumbers?: string[];
  creditScore?: number;
  riskLevel: 'low' | 'medium' | 'high';
  // 상담 이력
  totalCalls: number;
  totalChats: number;
  lastContactDate?: Date;
  satisfactionScore?: number;
}

export interface CustomerInteraction {
  id: string;
  customerId: string;
  agentId: string;
  agentName: string;
  type: 'call' | 'chat' | 'email' | 'sms';
  subject: string;
  description: string;
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  category: string;
  subcategory?: string;
  resolution?: string;
  satisfactionRating?: number;
  createdAt: Date;
  updatedAt: Date;
  duration?: number; // 통화 시간 (초)
  attachments?: Array<{
    id: string;
    fileName: string;
    fileSize: number;
    fileType: string;
    url: string;
  }>;
}

interface CustomerState {
  currentCustomer: Customer | null;
  customerHistory: CustomerInteraction[];
  searchResults: Customer[];
  isLoading: boolean;
  error: string | null;
  searchQuery: string;
  filters: {
    status?: Customer['status'];
    customerType?: Customer['customerType'];
    riskLevel?: Customer['riskLevel'];
    dateRange?: {
      start: Date;
      end: Date;
    };
  };
}

const initialState: CustomerState = {
  currentCustomer: null,
  customerHistory: [],
  searchResults: [],
  isLoading: false,
  error: null,
  searchQuery: '',
  filters: {},
};

const customerSlice = createSlice({
  name: 'customer',
  initialState,
  reducers: {
    setCurrentCustomer: (state, action: PayloadAction<Customer | null>) => {
      state.currentCustomer = action.payload;
    },
    updateCustomer: (state, action: PayloadAction<Partial<Customer> & { id: string }>) => {
      if (state.currentCustomer?.id === action.payload.id) {
        state.currentCustomer = { ...state.currentCustomer, ...action.payload };
      }
      const searchIndex = state.searchResults.findIndex(c => c.id === action.payload.id);
      if (searchIndex !== -1) {
        state.searchResults[searchIndex] = { ...state.searchResults[searchIndex], ...action.payload };
      }
    },
    setCustomerHistory: (state, action: PayloadAction<CustomerInteraction[]>) => {
      state.customerHistory = action.payload;
    },
    addCustomerInteraction: (state, action: PayloadAction<CustomerInteraction>) => {
      state.customerHistory.unshift(action.payload);
    },
    updateCustomerInteraction: (state, action: PayloadAction<Partial<CustomerInteraction> & { id: string }>) => {
      const index = state.customerHistory.findIndex(interaction => interaction.id === action.payload.id);
      if (index !== -1) {
        state.customerHistory[index] = { ...state.customerHistory[index], ...action.payload };
      }
    },
    setSearchResults: (state, action: PayloadAction<Customer[]>) => {
      state.searchResults = action.payload;
    },
    setSearchQuery: (state, action: PayloadAction<string>) => {
      state.searchQuery = action.payload;
    },
    setFilters: (state, action: PayloadAction<CustomerState['filters']>) => {
      state.filters = { ...state.filters, ...action.payload };
    },
    clearFilters: (state) => {
      state.filters = {};
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload;
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
});

export const {
  setCurrentCustomer,
  updateCustomer,
  setCustomerHistory,
  addCustomerInteraction,
  updateCustomerInteraction,
  setSearchResults,
  setSearchQuery,
  setFilters,
  clearFilters,
  setLoading,
  setError,
  clearError,
} = customerSlice.actions;

export default customerSlice.reducer; 