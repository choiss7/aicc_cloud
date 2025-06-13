from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import json
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    """WebSocket 연결 관리 클래스"""
    
    def __init__(self):
        # 활성 연결: agent_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        
        # 세션 참여자: session_id -> Set[agent_id]
        self.session_participants: Dict[str, Set[str]] = {}
        
        # 상담원별 참여 세션: agent_id -> Set[session_id]
        self.agent_sessions: Dict[str, Set[str]] = {}
        
        # 타이핑 상태: session_id -> Dict[agent_id, is_typing]
        self.typing_status: Dict[str, Dict[str, bool]] = {}

    async def connect(self, websocket: WebSocket, agent_id: str):
        """새로운 WebSocket 연결 수락"""
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        
        # 상담원 세션 초기화
        if agent_id not in self.agent_sessions:
            self.agent_sessions[agent_id] = set()
        
        logger.info(f"Agent {agent_id} connected. Total connections: {len(self.active_connections)}")
        
        # 연결 확인 메시지 전송
        await self.send_personal_message(agent_id, {
            "type": "connection_established",
            "data": {
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat()
            }
        })

    def disconnect(self, agent_id: str):
        """WebSocket 연결 해제"""
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
        
        # 모든 세션에서 상담원 제거
        if agent_id in self.agent_sessions:
            for session_id in self.agent_sessions[agent_id].copy():
                self.leave_session(agent_id, session_id)
            del self.agent_sessions[agent_id]
        
        logger.info(f"Agent {agent_id} disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, agent_id: str, message: dict):
        """특정 상담원에게 개인 메시지 전송"""
        if agent_id in self.active_connections:
            try:
                await self.active_connections[agent_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to agent {agent_id}: {e}")
                # 연결이 끊어진 경우 정리
                self.disconnect(agent_id)

    async def broadcast_to_session(self, session_id: str, message: dict):
        """특정 세션의 모든 참여자에게 메시지 브로드캐스트"""
        if session_id in self.session_participants:
            disconnected_agents = []
            
            for agent_id in self.session_participants[session_id]:
                if agent_id in self.active_connections:
                    try:
                        await self.active_connections[agent_id].send_text(json.dumps(message))
                    except Exception as e:
                        logger.error(f"Error broadcasting to agent {agent_id}: {e}")
                        disconnected_agents.append(agent_id)
                else:
                    disconnected_agents.append(agent_id)
            
            # 연결이 끊어진 상담원들 정리
            for agent_id in disconnected_agents:
                self.leave_session(agent_id, session_id)

    async def broadcast_to_all(self, message: dict):
        """모든 연결된 상담원에게 메시지 브로드캐스트"""
        disconnected_agents = []
        
        for agent_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to agent {agent_id}: {e}")
                disconnected_agents.append(agent_id)
        
        # 연결이 끊어진 상담원들 정리
        for agent_id in disconnected_agents:
            self.disconnect(agent_id)

    async def join_session(self, agent_id: str, session_id: str):
        """상담원을 세션에 추가"""
        if session_id not in self.session_participants:
            self.session_participants[session_id] = set()
        
        self.session_participants[session_id].add(agent_id)
        self.agent_sessions[agent_id].add(session_id)
        
        logger.info(f"Agent {agent_id} joined session {session_id}")
        
        # 세션 참여 알림
        await self.broadcast_to_session(session_id, {
            "type": "agent_joined",
            "data": {
                "agent_id": agent_id,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
        })

    def leave_session(self, agent_id: str, session_id: str):
        """상담원을 세션에서 제거"""
        if session_id in self.session_participants:
            self.session_participants[session_id].discard(agent_id)
            
            # 세션에 참여자가 없으면 세션 정리
            if not self.session_participants[session_id]:
                del self.session_participants[session_id]
                if session_id in self.typing_status:
                    del self.typing_status[session_id]
        
        if agent_id in self.agent_sessions:
            self.agent_sessions[agent_id].discard(session_id)
        
        logger.info(f"Agent {agent_id} left session {session_id}")

    async def set_typing_status(self, agent_id: str, session_id: str, is_typing: bool):
        """타이핑 상태 설정 및 브로드캐스트"""
        if session_id not in self.typing_status:
            self.typing_status[session_id] = {}
        
        self.typing_status[session_id][agent_id] = is_typing
        
        # 타이핑 상태를 다른 참여자들에게 브로드캐스트
        await self.broadcast_to_session(session_id, {
            "type": "typing_status",
            "data": {
                "agent_id": agent_id,
                "session_id": session_id,
                "is_typing": is_typing,
                "timestamp": datetime.now().isoformat()
            }
        })

    async def notify_agent_status_change(self, agent_id: str, status: str):
        """상담원 상태 변경 알림"""
        message = {
            "type": "agent_status_change",
            "data": {
                "agent_id": agent_id,
                "status": status,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # 해당 상담원의 모든 세션 참여자들에게 알림
        if agent_id in self.agent_sessions:
            for session_id in self.agent_sessions[agent_id]:
                await self.broadcast_to_session(session_id, message)

    async def notify_new_session(self, session_id: str, session_data: dict):
        """새로운 세션 생성 알림"""
        message = {
            "type": "new_session",
            "data": {
                "session_id": session_id,
                "session_data": session_data,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # 모든 상담원에게 알림 (부서별 필터링 가능)
        await self.broadcast_to_all(message)

    async def notify_session_ended(self, session_id: str):
        """세션 종료 알림"""
        message = {
            "type": "session_ended",
            "data": {
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # 세션 참여자들에게 알림
        await self.broadcast_to_session(session_id, message)
        
        # 세션 정리
        if session_id in self.session_participants:
            for agent_id in self.session_participants[session_id].copy():
                self.leave_session(agent_id, session_id)

    def get_session_participants(self, session_id: str) -> List[str]:
        """세션 참여자 목록 반환"""
        return list(self.session_participants.get(session_id, set()))

    def get_agent_sessions(self, agent_id: str) -> List[str]:
        """상담원이 참여 중인 세션 목록 반환"""
        return list(self.agent_sessions.get(agent_id, set()))

    def get_connection_stats(self) -> dict:
        """연결 통계 반환"""
        return {
            "total_connections": len(self.active_connections),
            "active_sessions": len(self.session_participants),
            "total_participants": sum(len(participants) for participants in self.session_participants.values())
        }

    async def ping_all_connections(self):
        """모든 연결에 ping 메시지 전송 (연결 상태 확인)"""
        ping_message = {
            "type": "ping",
            "data": {
                "timestamp": datetime.now().isoformat()
            }
        }
        
        await self.broadcast_to_all(ping_message)

# 전역 연결 관리자 인스턴스
manager = ConnectionManager()

# 주기적으로 ping을 보내는 백그라운드 태스크
async def periodic_ping():
    """주기적으로 모든 연결에 ping 전송"""
    while True:
        await asyncio.sleep(30)  # 30초마다
        try:
            await manager.ping_all_connections()
        except Exception as e:
            logger.error(f"Error in periodic ping: {e}")

# 백그라운드 태스크 시작
def start_background_tasks():
    """백그라운드 태스크 시작"""
    asyncio.create_task(periodic_ping()) 