import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Call {
  id: string;
  customerId: string;
  customerName: string;
  customerPhone: string;
  agentId: string;
  agentName: string;
  direction: 'inbound' | 'outbound';
  status: 'ringing' | 'connected' | 'on_hold' | 'ended' | 'missed';
  startTime: Date;
  endTime?: Date;
  duration?: number; // 초 단위
  recordingUrl?: string;
  notes: string;
  disposition: string;
  transferredFrom?: string;
  transferredTo?: string;
  queueTime?: number; // 대기 시간 (초)
  connectTime?: Date;
  holdTime?: number; // 보류 시간 (초)
  category: string;
  subcategory?: string;
  resolution?: string;
  followUpRequired: boolean;
  satisfactionRating?: number;
  tags: string[];
}

export interface CallQueue {
  id: string;
  name: string;
  waitingCalls: number;
  availableAgents: number;
  averageWaitTime: number;
  longestWaitTime: number;
  callsToday: number;
  answeredToday: number;
  abandonedToday: number;
}

interface CallState {
  currentCall: Call | null;
  callHistory: Call[];
  callQueues: CallQueue[];
  isOnCall: boolean;
  isOnHold: boolean;
  isMuted: boolean;
  callTimer: number;
  holdTimer: number;
  incomingCall: Call | null;
  recentCalls: Call[];
  callStats: {
    totalCalls: number;
    answeredCalls: number;
    missedCalls: number;
    averageCallDuration: number;
    totalTalkTime: number;
    totalHoldTime: number;
  };
  isLoading: boolean;
  error: string | null;
}

const initialState: CallState = {
  currentCall: null,
  callHistory: [],
  callQueues: [],
  isOnCall: false,
  isOnHold: false,
  isMuted: false,
  callTimer: 0,
  holdTimer: 0,
  incomingCall: null,
  recentCalls: [],
  callStats: {
    totalCalls: 0,
    answeredCalls: 0,
    missedCalls: 0,
    averageCallDuration: 0,
    totalTalkTime: 0,
    totalHoldTime: 0,
  },
  isLoading: false,
  error: null,
};

const callSlice = createSlice({
  name: 'call',
  initialState,
  reducers: {
    setCurrentCall: (state, action: PayloadAction<Call | null>) => {
      state.currentCall = action.payload;
      state.isOnCall = action.payload !== null;
    },
    updateCurrentCall: (state, action: PayloadAction<Partial<Call>>) => {
      if (state.currentCall) {
        state.currentCall = { ...state.currentCall, ...action.payload };
      }
    },
    setIncomingCall: (state, action: PayloadAction<Call | null>) => {
      state.incomingCall = action.payload;
    },
    answerCall: (state) => {
      if (state.incomingCall) {
        state.currentCall = {
          ...state.incomingCall,
          status: 'connected',
          connectTime: new Date(),
        };
        state.incomingCall = null;
        state.isOnCall = true;
        state.callTimer = 0;
      }
    },
    endCall: (state) => {
      if (state.currentCall) {
        const endedCall = {
          ...state.currentCall,
          status: 'ended' as const,
          endTime: new Date(),
          duration: state.callTimer,
        };
        state.callHistory.unshift(endedCall);
        state.recentCalls.unshift(endedCall);
        if (state.recentCalls.length > 10) {
          state.recentCalls = state.recentCalls.slice(0, 10);
        }
      }
      state.currentCall = null;
      state.isOnCall = false;
      state.isOnHold = false;
      state.isMuted = false;
      state.callTimer = 0;
      state.holdTimer = 0;
    },
    holdCall: (state) => {
      state.isOnHold = true;
      if (state.currentCall) {
        state.currentCall.status = 'on_hold';
      }
    },
    resumeCall: (state) => {
      state.isOnHold = false;
      if (state.currentCall) {
        state.currentCall.status = 'connected';
      }
    },
    muteCall: (state) => {
      state.isMuted = true;
    },
    unmuteCall: (state) => {
      state.isMuted = false;
    },
    updateCallTimer: (state, action: PayloadAction<number>) => {
      state.callTimer = action.payload;
    },
    updateHoldTimer: (state, action: PayloadAction<number>) => {
      state.holdTimer = action.payload;
    },
    addCallToHistory: (state, action: PayloadAction<Call>) => {
      state.callHistory.unshift(action.payload);
    },
    setCallHistory: (state, action: PayloadAction<Call[]>) => {
      state.callHistory = action.payload;
    },
    setCallQueues: (state, action: PayloadAction<CallQueue[]>) => {
      state.callQueues = action.payload;
    },
    updateCallQueue: (state, action: PayloadAction<Partial<CallQueue> & { id: string }>) => {
      const index = state.callQueues.findIndex(queue => queue.id === action.payload.id);
      if (index !== -1) {
        state.callQueues[index] = { ...state.callQueues[index], ...action.payload };
      }
    },
    updateCallStats: (state, action: PayloadAction<Partial<CallState['callStats']>>) => {
      state.callStats = { ...state.callStats, ...action.payload };
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
  setCurrentCall,
  updateCurrentCall,
  setIncomingCall,
  answerCall,
  endCall,
  holdCall,
  resumeCall,
  muteCall,
  unmuteCall,
  updateCallTimer,
  updateHoldTimer,
  addCallToHistory,
  setCallHistory,
  setCallQueues,
  updateCallQueue,
  updateCallStats,
  setLoading,
  setError,
  clearError,
} = callSlice.actions;

export default callSlice.reducer; 