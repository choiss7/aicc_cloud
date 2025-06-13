import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Chip,
  Divider,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Card,
  CardContent,
  Badge,
} from '@mui/material';
import {
  Send,
  AttachFile,
  EmojiEmotions,
  Phone,
  PersonAdd,
  MoreVert,
  Circle,
} from '@mui/icons-material';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../../store/store';
import {
  setCurrentSession,
  addMessage,
  markMessagesAsRead,
  setTypingStatus,
} from '../../store/slices/chatSlice';
import { format } from 'date-fns';
import { ko } from 'date-fns/locale';

const ChatInterface: React.FC = () => {
  const dispatch = useDispatch();
  const { activeSessions, currentSession, isConnected } = useSelector(
    (state: RootState) => state.chat
  );
  const { user } = useSelector((state: RootState) => state.auth);
  
  const [message, setMessage] = useState('');
  const [transferDialogOpen, setTransferDialogOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentSession?.messages]);

  const handleSessionSelect = (sessionId: string) => {
    dispatch(setCurrentSession(sessionId));
    dispatch(markMessagesAsRead(sessionId));
  };

  const handleSendMessage = () => {
    if (message.trim() && currentSession && user) {
      const newMessage = {
        id: Date.now().toString(),
        sessionId: currentSession.id,
        sender: 'agent' as const,
        content: message.trim(),
        timestamp: new Date(),
        type: 'text' as const,
      };
      
      dispatch(addMessage(newMessage));
      setMessage('');
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const handleTransferCall = () => {
    setTransferDialogOpen(true);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return '#4caf50';
      case 'waiting': return '#ff9800';
      case 'ended': return '#9e9e9e';
      case 'transferred': return '#2196f3';
      default: return '#9e9e9e';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return '#f44336';
      case 'high': return '#ff9800';
      case 'medium': return '#2196f3';
      case 'low': return '#4caf50';
      default: return '#9e9e9e';
    }
  };

  return (
    <Box sx={{ height: 'calc(100vh - 120px)', display: 'flex' }}>
      {/* 채팅 세션 목록 */}
      <Paper sx={{ width: 300, mr: 2, overflow: 'hidden' }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Typography variant="h6">활성 채팅</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
            <Circle
              sx={{
                fontSize: 12,
                color: isConnected ? '#4caf50' : '#f44336',
                mr: 1,
              }}
            />
            <Typography variant="body2" color="textSecondary">
              {isConnected ? '연결됨' : '연결 끊김'}
            </Typography>
          </Box>
        </Box>
        
        <List sx={{ height: 'calc(100% - 80px)', overflow: 'auto' }}>
          {activeSessions.map((session) => (
            <ListItem
              key={session.id}
              button
              selected={currentSession?.id === session.id}
              onClick={() => handleSessionSelect(session.id)}
              sx={{
                borderLeft: currentSession?.id === session.id ? 3 : 0,
                borderColor: 'primary.main',
              }}
            >
              <ListItemAvatar>
                <Badge
                  badgeContent={
                    session.messages.filter(
                      m => m.sender === 'customer' && !m.metadata?.read
                    ).length
                  }
                  color="error"
                >
                  <Avatar sx={{ bgcolor: getStatusColor(session.status) }}>
                    {session.customerName.charAt(0)}
                  </Avatar>
                </Badge>
              </ListItemAvatar>
              <ListItemText
                primary={
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Typography variant="subtitle2" sx={{ flexGrow: 1 }}>
                      {session.customerName}
                    </Typography>
                    <Chip
                      label={session.priority}
                      size="small"
                      sx={{
                        bgcolor: getPriorityColor(session.priority),
                        color: 'white',
                        fontSize: '0.7rem',
                      }}
                    />
                  </Box>
                }
                secondary={
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      {session.customerPhone}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      {format(session.startTime, 'HH:mm', { locale: ko })}
                    </Typography>
                  </Box>
                }
              />
            </ListItem>
          ))}
        </List>
      </Paper>

      {/* 채팅 영역 */}
      <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {currentSession ? (
          <>
            {/* 채팅 헤더 */}
            <Box
              sx={{
                p: 2,
                borderBottom: 1,
                borderColor: 'divider',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Avatar sx={{ mr: 2, bgcolor: getStatusColor(currentSession.status) }}>
                  {currentSession.customerName.charAt(0)}
                </Avatar>
                <Box>
                  <Typography variant="h6">{currentSession.customerName}</Typography>
                  <Typography variant="body2" color="textSecondary">
                    {currentSession.customerPhone} • {currentSession.source}
                  </Typography>
                </Box>
              </Box>
              
              <Box>
                <IconButton onClick={handleTransferCall}>
                  <PersonAdd />
                </IconButton>
                <IconButton>
                  <Phone />
                </IconButton>
                <IconButton>
                  <MoreVert />
                </IconButton>
              </Box>
            </Box>

            {/* 메시지 목록 */}
            <Box sx={{ flex: 1, overflow: 'auto', p: 1 }}>
              <List>
                {currentSession.messages.map((msg) => (
                  <ListItem
                    key={msg.id}
                    sx={{
                      flexDirection: 'column',
                      alignItems: msg.sender === 'agent' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    <Paper
                      sx={{
                        p: 2,
                        maxWidth: '70%',
                        bgcolor: msg.sender === 'agent' ? 'primary.main' : 'grey.100',
                        color: msg.sender === 'agent' ? 'white' : 'text.primary',
                      }}
                    >
                      <Typography variant="body1">{msg.content}</Typography>
                    </Paper>
                    <Typography
                      variant="caption"
                      color="textSecondary"
                      sx={{ mt: 0.5 }}
                    >
                      {format(msg.timestamp, 'HH:mm', { locale: ko })}
                    </Typography>
                  </ListItem>
                ))}
              </List>
              <div ref={messagesEndRef} />
            </Box>

            {/* 메시지 입력 */}
            <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
              <Box sx={{ display: 'flex', alignItems: 'flex-end' }}>
                <TextField
                  fullWidth
                  multiline
                  maxRows={4}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="메시지를 입력하세요..."
                  variant="outlined"
                  size="small"
                />
                <IconButton sx={{ ml: 1 }}>
                  <AttachFile />
                </IconButton>
                <IconButton sx={{ ml: 1 }}>
                  <EmojiEmotions />
                </IconButton>
                <IconButton
                  color="primary"
                  onClick={handleSendMessage}
                  disabled={!message.trim()}
                  sx={{ ml: 1 }}
                >
                  <Send />
                </IconButton>
              </Box>
            </Box>
          </>
        ) : (
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
            }}
          >
            <Typography variant="h6" color="textSecondary">
              채팅 세션을 선택하세요
            </Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
              왼쪽에서 활성 채팅을 선택하여 대화를 시작하세요
            </Typography>
          </Box>
        )}
      </Paper>

      {/* 고객 정보 패널 */}
      {currentSession && (
        <Paper sx={{ width: 300, ml: 2, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            고객 정보
          </Typography>
          
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" color="textSecondary">
                기본 정보
              </Typography>
              <Typography variant="body1" sx={{ mt: 1 }}>
                {currentSession.customerName}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {currentSession.customerPhone}
              </Typography>
              {currentSession.customerEmail && (
                <Typography variant="body2" color="textSecondary">
                  {currentSession.customerEmail}
                </Typography>
              )}
            </CardContent>
          </Card>

          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" color="textSecondary">
                상담 정보
              </Typography>
              <Box sx={{ mt: 1 }}>
                <Chip
                  label={currentSession.status}
                  size="small"
                  sx={{ mr: 1, mb: 1 }}
                />
                <Chip
                  label={currentSession.priority}
                  size="small"
                  sx={{ mr: 1, mb: 1 }}
                  color={currentSession.priority === 'urgent' ? 'error' : 'default'}
                />
              </Box>
              <Typography variant="body2" sx={{ mt: 1 }}>
                부서: {currentSession.department}
              </Typography>
              <Typography variant="body2">
                시작 시간: {format(currentSession.startTime, 'yyyy-MM-dd HH:mm', { locale: ko })}
              </Typography>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="textSecondary">
                태그
              </Typography>
              <Box sx={{ mt: 1 }}>
                {currentSession.tags.map((tag) => (
                  <Chip
                    key={tag}
                    label={tag}
                    size="small"
                    variant="outlined"
                    sx={{ mr: 0.5, mb: 0.5 }}
                  />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Paper>
      )}

      {/* 전환 다이얼로그 */}
      <Dialog open={transferDialogOpen} onClose={() => setTransferDialogOpen(false)}>
        <DialogTitle>상담 전환</DialogTitle>
        <DialogContent>
          <Typography>상담을 다른 상담원에게 전환하시겠습니까?</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTransferDialogOpen(false)}>취소</Button>
          <Button variant="contained">전환</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ChatInterface; 