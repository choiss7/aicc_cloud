import React from 'react';
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  List,
  Typography,
  Divider,
  IconButton,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Badge,
  Avatar,
  Menu,
  MenuItem,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard,
  Chat,
  Person,
  History,
  Settings,
  Notifications,
  AccountCircle,
  Phone,
  PhoneDisabled,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../../store/store';
import { toggleSidebar, openModal } from '../../store/slices/uiSlice';
import { logout, updateUserStatus } from '../../store/slices/authSlice';

const drawerWidth = 240;

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  
  const { sidebarOpen } = useSelector((state: RootState) => state.ui);
  const { user } = useSelector((state: RootState) => state.auth);
  const { unreadCount } = useSelector((state: RootState) => state.chat);
  const { isOnCall } = useSelector((state: RootState) => state.call);
  
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

  const menuItems = [
    { text: '대시보드', icon: <Dashboard />, path: '/dashboard' },
    { text: '채팅', icon: <Chat />, path: '/chat', badge: unreadCount },
    { text: '고객정보', icon: <Person />, path: '/customer' },
    { text: '상담이력', icon: <History />, path: '/history' },
    { text: '설정', icon: <Settings />, path: '/settings' },
  ];

  const handleDrawerToggle = () => {
    dispatch(toggleSidebar());
  };

  const handleMenuClick = (path: string) => {
    navigate(path);
  };

  const handleProfileMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleProfileMenuClose = () => {
    setAnchorEl(null);
  };

  const handleStatusChange = (status: 'available' | 'busy' | 'away' | 'offline') => {
    if (user) {
      dispatch(updateUserStatus(status));
    }
    handleProfileMenuClose();
  };

  const handleLogout = () => {
    dispatch(logout());
    handleProfileMenuClose();
    navigate('/login');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'available': return '#4caf50';
      case 'busy': return '#f44336';
      case 'away': return '#ff9800';
      case 'offline': return '#9e9e9e';
      default: return '#9e9e9e';
    }
  };

  const drawer = (
    <div>
      <Toolbar>
        <Typography variant="h6" noWrap component="div">
          상담원 데스크탑
        </Typography>
      </Toolbar>
      <Divider />
      <List>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => handleMenuClick(item.path)}
            >
              <ListItemIcon>
                {item.badge ? (
                  <Badge badgeContent={item.badge} color="error">
                    {item.icon}
                  </Badge>
                ) : (
                  item.icon
                )}
              </ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </div>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${sidebarOpen ? drawerWidth : 0}px)` },
          ml: { sm: `${sidebarOpen ? drawerWidth : 0}px` },
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2 }}
          >
            <MenuIcon />
          </IconButton>
          
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            {menuItems.find(item => item.path === location.pathname)?.text || '상담원 데스크탑'}
          </Typography>

          {/* 통화 상태 표시 */}
          <Box sx={{ display: 'flex', alignItems: 'center', mr: 2 }}>
            {isOnCall ? (
              <Box sx={{ display: 'flex', alignItems: 'center', color: '#4caf50' }}>
                <Phone sx={{ mr: 1 }} />
                <Typography variant="body2">통화중</Typography>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', color: '#9e9e9e' }}>
                <PhoneDisabled sx={{ mr: 1 }} />
                <Typography variant="body2">대기중</Typography>
              </Box>
            )}
          </Box>

          <IconButton
            size="large"
            aria-label="show notifications"
            color="inherit"
            onClick={() => dispatch(openModal('settings'))}
          >
            <Badge badgeContent={0} color="error">
              <Notifications />
            </Badge>
          </IconButton>

          <IconButton
            size="large"
            edge="end"
            aria-label="account of current user"
            aria-controls="primary-search-account-menu"
            aria-haspopup="true"
            onClick={handleProfileMenuOpen}
            color="inherit"
          >
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Avatar
                sx={{
                  width: 32,
                  height: 32,
                  mr: 1,
                  border: `2px solid ${getStatusColor(user?.status || 'offline')}`,
                }}
                src={user?.avatar}
              >
                {user?.username?.charAt(0).toUpperCase()}
              </Avatar>
              <AccountCircle />
            </Box>
          </IconButton>
        </Toolbar>
      </AppBar>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleProfileMenuClose}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
      >
        <MenuItem onClick={() => handleStatusChange('available')}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Box
              sx={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: '#4caf50',
                mr: 1,
              }}
            />
            상담 가능
          </Box>
        </MenuItem>
        <MenuItem onClick={() => handleStatusChange('busy')}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Box
              sx={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: '#f44336',
                mr: 1,
              }}
            />
            상담 중
          </Box>
        </MenuItem>
        <MenuItem onClick={() => handleStatusChange('away')}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Box
              sx={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: '#ff9800',
                mr: 1,
              }}
            />
            자리 비움
          </Box>
        </MenuItem>
        <Divider />
        <MenuItem onClick={handleLogout}>로그아웃</MenuItem>
      </Menu>

      <Box
        component="nav"
        sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}
        aria-label="mailbox folders"
      >
        <Drawer
          variant="temporary"
          open={sidebarOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true,
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="persistent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open={sidebarOpen}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${sidebarOpen ? drawerWidth : 0}px)` },
        }}
      >
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
};

export default Layout; 