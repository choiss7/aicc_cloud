import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Message {
  id: string;
  sessionId: string;
  sender: 'customer' | 'agent' | 'system';
  content: string;
  timestamp: Date;
  type: 'text' | 'image' | 'file' | 'system';
  metadata?: {
    fileName?: string;
    fileSize?: number;
    fileType?: string;
    imageUrl?: string;
  };
}

export interface ChatSession {
  id: string;
  customerId: string;
  customerName: string;
  customerPhone: string;
  customerEmail?: string;
  agentId: string;
  status: 'active' | 'waiting' | 'ended' | 'transferred';
  startTime: Date;
  endTime?: Date;
  messages: Message[];
  tags: string[];
  priority: 'low' | 'medium' | 'high' | 'urgent';
  department: string;
  source: 'web' | 'mobile' | 'phone' | 'email';
}

interface ChatState {
  activeSessions: ChatSession[];
  currentSession: ChatSession | null;
  isConnected: boolean;
  isTyping: boolean;
  unreadCount: number;
  notifications: Array<{
    id: string;
    type: 'new_chat' | 'message' | 'transfer' | 'system';
    title: string;
    message: string;
    timestamp: Date;
    read: boolean;
  }>;
}

const initialState: ChatState = {
  activeSessions: [],
  currentSession: null,
  isConnected: false,
  isTyping: false,
  unreadCount: 0,
  notifications: [],
};

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setConnectionStatus: (state, action: PayloadAction<boolean>) => {
      state.isConnected = action.payload;
    },
    addChatSession: (state, action: PayloadAction<ChatSession>) => {
      state.activeSessions.push(action.payload);
    },
    updateChatSession: (state, action: PayloadAction<Partial<ChatSession> & { id: string }>) => {
      const index = state.activeSessions.findIndex(session => session.id === action.payload.id);
      if (index !== -1) {
        state.activeSessions[index] = { ...state.activeSessions[index], ...action.payload };
      }
      if (state.currentSession?.id === action.payload.id) {
        state.currentSession = { ...state.currentSession, ...action.payload };
      }
    },
    removeChatSession: (state, action: PayloadAction<string>) => {
      state.activeSessions = state.activeSessions.filter(session => session.id !== action.payload);
      if (state.currentSession?.id === action.payload) {
        state.currentSession = null;
      }
    },
    setCurrentSession: (state, action: PayloadAction<string | null>) => {
      if (action.payload) {
        const session = state.activeSessions.find(s => s.id === action.payload);
        state.currentSession = session || null;
      } else {
        state.currentSession = null;
      }
    },
    addMessage: (state, action: PayloadAction<Message>) => {
      const sessionIndex = state.activeSessions.findIndex(
        session => session.id === action.payload.sessionId
      );
      if (sessionIndex !== -1) {
        state.activeSessions[sessionIndex].messages.push(action.payload);
      }
      if (state.currentSession?.id === action.payload.sessionId) {
        state.currentSession.messages.push(action.payload);
      }
      if (action.payload.sender === 'customer') {
        state.unreadCount += 1;
      }
    },
    markMessagesAsRead: (state, action: PayloadAction<string>) => {
      // 특정 세션의 메시지를 읽음으로 표시
      const session = state.activeSessions.find(s => s.id === action.payload);
      if (session) {
        const unreadMessages = session.messages.filter(
          m => m.sender === 'customer' && !m.metadata?.read
        );
        state.unreadCount -= unreadMessages.length;
        session.messages.forEach(message => {
          if (message.sender === 'customer') {
            message.metadata = { ...message.metadata, read: true };
          }
        });
      }
    },
    setTypingStatus: (state, action: PayloadAction<boolean>) => {
      state.isTyping = action.payload;
    },
    addNotification: (state, action: PayloadAction<Omit<ChatState['notifications'][0], 'id'>>) => {
      const notification = {
        ...action.payload,
        id: Date.now().toString(),
      };
      state.notifications.unshift(notification);
    },
    markNotificationAsRead: (state, action: PayloadAction<string>) => {
      const notification = state.notifications.find(n => n.id === action.payload);
      if (notification) {
        notification.read = true;
      }
    },
    clearNotifications: (state) => {
      state.notifications = [];
    },
  },
});

export const {
  setConnectionStatus,
  addChatSession,
  updateChatSession,
  removeChatSession,
  setCurrentSession,
  addMessage,
  markMessagesAsRead,
  setTypingStatus,
  addNotification,
  markNotificationAsRead,
  clearNotifications,
} = chatSlice.actions;

export default chatSlice.reducer; 