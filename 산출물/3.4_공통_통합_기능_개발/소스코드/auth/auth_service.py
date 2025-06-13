"""
인증/권한 관리 서비스
JWT 토큰, RBAC, SSO, MFA 지원
AWS Cognito, LDAP 연동
"""

import asyncio
import json
import logging
import secrets
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import jwt
import bcrypt
import pyotp
import qrcode
import boto3
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import structlog

# 로깅 설정
logger = structlog.get_logger(__name__)

Base = declarative_base()

class UserRole(Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    AGENT = "agent"
    VIEWER = "viewer"

class Permission(Enum):
    # 시스템 관리
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_CONFIG = "system:config"
    
    # 사용자 관리
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    
    # 상담 관리
    CALL_HANDLE = "call:handle"
    CALL_TRANSFER = "call:transfer"
    CALL_MONITOR = "call:monitor"
    CALL_RECORD = "call:record"
    
    # 채팅 관리
    CHAT_HANDLE = "chat:handle"
    CHAT_TRANSFER = "chat:transfer"
    CHAT_MONITOR = "chat:monitor"
    
    # 고객 정보
    CUSTOMER_READ = "customer:read"
    CUSTOMER_UPDATE = "customer:update"
    CUSTOMER_DELETE = "customer:delete"
    
    # 리포트
    REPORT_VIEW = "report:view"
    REPORT_EXPORT = "report:export"
    REPORT_ADMIN = "report:admin"

@dataclass
class TokenPayload:
    """JWT 토큰 페이로드"""
    user_id: str
    username: str
    email: str
    roles: List[str]
    permissions: List[str]
    exp: int
    iat: int
    jti: str

class User(Base):
    """사용자 모델"""
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    
    first_name = Column(String)
    last_name = Column(String)
    phone_number = Column(String)
    
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # MFA 설정
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String)
    backup_codes = Column(Text)  # JSON
    
    # 로그인 정보
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    
    # 비밀번호 정책
    password_changed_at = Column(DateTime, default=datetime.utcnow)
    password_expires_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    user_roles = relationship("UserRole", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")

class Role(Base):
    """역할 모델"""
    __tablename__ = 'roles'
    
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    
    is_system_role = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    role_permissions = relationship("RolePermission", back_populates="role")
    user_roles = relationship("UserRole", back_populates="role")

class UserRole(Base):
    """사용자-역할 매핑"""
    __tablename__ = 'user_roles'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    role_id = Column(String, ForeignKey('roles.id'), nullable=False)
    
    granted_by = Column(String, ForeignKey('users.id'))
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    # 관계
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")

class RolePermission(Base):
    """역할-권한 매핑"""
    __tablename__ = 'role_permissions'
    
    id = Column(String, primary_key=True)
    role_id = Column(String, ForeignKey('roles.id'), nullable=False)
    permission = Column(String, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 관계
    role = relationship("Role", back_populates="role_permissions")

class UserSession(Base):
    """사용자 세션"""
    __tablename__ = 'user_sessions'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    
    ip_address = Column(String)
    user_agent = Column(String)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    is_active = Column(Boolean, default=True)
    
    # 관계
    user = relationship("User", back_populates="sessions")

class AuditLog(Base):
    """감사 로그"""
    __tablename__ = 'audit_logs'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'))
    
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(String)
    
    ip_address = Column(String)
    user_agent = Column(String)
    
    details = Column(Text)  # JSON
    
    created_at = Column(DateTime, default=datetime.utcnow)

class PasswordManager:
    """비밀번호 관리자"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """비밀번호 해시"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """비밀번호 검증"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def generate_password(length: int = 12) -> str:
        """안전한 비밀번호 생성"""
        import string
        characters = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(characters) for _ in range(length))
    
    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """비밀번호 강도 검증"""
        result = {
            'is_valid': True,
            'score': 0,
            'issues': []
        }
        
        if len(password) < 8:
            result['issues'].append('최소 8자 이상이어야 합니다')
            result['is_valid'] = False
        else:
            result['score'] += 1
        
        if not any(c.isupper() for c in password):
            result['issues'].append('대문자를 포함해야 합니다')
            result['is_valid'] = False
        else:
            result['score'] += 1
        
        if not any(c.islower() for c in password):
            result['issues'].append('소문자를 포함해야 합니다')
            result['is_valid'] = False
        else:
            result['score'] += 1
        
        if not any(c.isdigit() for c in password):
            result['issues'].append('숫자를 포함해야 합니다')
            result['is_valid'] = False
        else:
            result['score'] += 1
        
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            result['issues'].append('특수문자를 포함해야 합니다')
        else:
            result['score'] += 1
        
        return result

class MFAManager:
    """다중 인증 관리자"""
    
    @staticmethod
    def generate_secret() -> str:
        """MFA 시크릿 생성"""
        return pyotp.random_base32()
    
    @staticmethod
    def generate_qr_code(secret: str, username: str, issuer: str = "AICC") -> bytes:
        """QR 코드 생성"""
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name=issuer
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        import io
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        return img_buffer.getvalue()
    
    @staticmethod
    def verify_totp(secret: str, token: str) -> bool:
        """TOTP 토큰 검증"""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)
    
    @staticmethod
    def generate_backup_codes(count: int = 10) -> List[str]:
        """백업 코드 생성"""
        return [secrets.token_hex(4).upper() for _ in range(count)]

class JWTManager:
    """JWT 토큰 관리자"""
    
    def __init__(self, secret_key: str, algorithm: str = 'HS256'):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire = timedelta(hours=1)
        self.refresh_token_expire = timedelta(days=30)
    
    def create_access_token(self, payload: TokenPayload) -> str:
        """액세스 토큰 생성"""
        now = datetime.utcnow()
        payload.iat = int(now.timestamp())
        payload.exp = int((now + self.access_token_expire).timestamp())
        payload.jti = str(uuid.uuid4())
        
        return jwt.encode(asdict(payload), self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_id: str) -> str:
        """리프레시 토큰 생성"""
        now = datetime.utcnow()
        payload = {
            'user_id': user_id,
            'type': 'refresh',
            'iat': int(now.timestamp()),
            'exp': int((now + self.refresh_token_expire).timestamp()),
            'jti': str(uuid.uuid4())
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """토큰 검증"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("토큰이 만료되었습니다")
        except jwt.InvalidTokenError:
            raise Exception("유효하지 않은 토큰입니다")
    
    def refresh_access_token(self, refresh_token: str, user_data: Dict[str, Any]) -> str:
        """액세스 토큰 갱신"""
        payload = self.verify_token(refresh_token)
        
        if payload.get('type') != 'refresh':
            raise Exception("리프레시 토큰이 아닙니다")
        
        new_payload = TokenPayload(
            user_id=user_data['user_id'],
            username=user_data['username'],
            email=user_data['email'],
            roles=user_data['roles'],
            permissions=user_data['permissions'],
            exp=0,  # 설정됨
            iat=0,  # 설정됨
            jti=""  # 설정됨
        )
        
        return self.create_access_token(new_payload)

class AuthService:
    """인증 서비스"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # 데이터베이스 설정
        self.engine = create_engine(config['database_url'])
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # JWT 관리자
        self.jwt_manager = JWTManager(config['jwt_secret'])
        
        # AWS Cognito (선택적)
        if config.get('aws_cognito_user_pool_id'):
            self.cognito_client = boto3.client('cognito-idp')
            self.user_pool_id = config['aws_cognito_user_pool_id']
        
        # 기본 역할 및 권한 설정
        self._setup_default_roles()
    
    def _setup_default_roles(self):
        """기본 역할 및 권한 설정"""
        default_roles = {
            UserRole.SUPER_ADMIN.value: [
                Permission.SYSTEM_ADMIN.value,
                Permission.SYSTEM_CONFIG.value,
                Permission.USER_CREATE.value,
                Permission.USER_READ.value,
                Permission.USER_UPDATE.value,
                Permission.USER_DELETE.value,
                Permission.REPORT_ADMIN.value
            ],
            UserRole.ADMIN.value: [
                Permission.USER_CREATE.value,
                Permission.USER_READ.value,
                Permission.USER_UPDATE.value,
                Permission.CALL_MONITOR.value,
                Permission.CHAT_MONITOR.value,
                Permission.CUSTOMER_READ.value,
                Permission.CUSTOMER_UPDATE.value,
                Permission.REPORT_VIEW.value,
                Permission.REPORT_EXPORT.value
            ],
            UserRole.SUPERVISOR.value: [
                Permission.USER_READ.value,
                Permission.CALL_MONITOR.value,
                Permission.CALL_TRANSFER.value,
                Permission.CHAT_MONITOR.value,
                Permission.CHAT_TRANSFER.value,
                Permission.CUSTOMER_READ.value,
                Permission.CUSTOMER_UPDATE.value,
                Permission.REPORT_VIEW.value
            ],
            UserRole.AGENT.value: [
                Permission.CALL_HANDLE.value,
                Permission.CALL_RECORD.value,
                Permission.CHAT_HANDLE.value,
                Permission.CUSTOMER_READ.value,
                Permission.CUSTOMER_UPDATE.value
            ],
            UserRole.VIEWER.value: [
                Permission.CUSTOMER_READ.value,
                Permission.REPORT_VIEW.value
            ]
        }
        
        with self.SessionLocal() as session:
            for role_name, permissions in default_roles.items():
                # 역할 생성
                role = session.query(Role).filter(Role.name == role_name).first()
                if not role:
                    role = Role(
                        id=str(uuid.uuid4()),
                        name=role_name,
                        description=f"기본 {role_name} 역할",
                        is_system_role=True
                    )
                    session.add(role)
                    session.flush()
                
                # 권한 할당
                existing_permissions = {rp.permission for rp in role.role_permissions}
                for permission in permissions:
                    if permission not in existing_permissions:
                        role_permission = RolePermission(
                            id=str(uuid.uuid4()),
                            role_id=role.id,
                            permission=permission
                        )
                        session.add(role_permission)
            
            session.commit()
    
    async def register_user(self, username: str, email: str, password: str,
                          first_name: str = None, last_name: str = None,
                          phone_number: str = None, roles: List[str] = None) -> str:
        """사용자 등록"""
        # 비밀번호 강도 검증
        password_check = PasswordManager.validate_password_strength(password)
        if not password_check['is_valid']:
            raise ValueError(f"비밀번호가 안전하지 않습니다: {', '.join(password_check['issues'])}")
        
        with self.SessionLocal() as session:
            # 중복 확인
            existing_user = session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing_user:
                raise ValueError("이미 존재하는 사용자명 또는 이메일입니다")
            
            # 사용자 생성
            user_id = str(uuid.uuid4())
            user = User(
                id=user_id,
                username=username,
                email=email,
                password_hash=PasswordManager.hash_password(password),
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
                password_expires_at=datetime.utcnow() + timedelta(days=90)
            )
            
            session.add(user)
            session.flush()
            
            # 역할 할당
            if not roles:
                roles = [UserRole.AGENT.value]
            
            for role_name in roles:
                role = session.query(Role).filter(Role.name == role_name).first()
                if role:
                    user_role = UserRole(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        role_id=role.id
                    )
                    session.add(user_role)
            
            session.commit()
            
            # 감사 로그
            await self._log_audit("user_registered", "user", user_id, None, {
                'username': username,
                'email': email,
                'roles': roles
            })
            
            logger.info("사용자 등록 완료", user_id=user_id, username=username)
            return user_id
    
    async def authenticate_user(self, username: str, password: str,
                             mfa_token: str = None, ip_address: str = None,
                             user_agent: str = None) -> Dict[str, Any]:
        """사용자 인증"""
        with self.SessionLocal() as session:
            user = session.query(User).filter(
                (User.username == username) | (User.email == username)
            ).first()
            
            if not user or not user.is_active:
                await self._log_audit("login_failed", "user", None, ip_address, {
                    'username': username,
                    'reason': 'user_not_found_or_inactive'
                })
                raise ValueError("사용자를 찾을 수 없거나 비활성화되었습니다")
            
            # 계정 잠금 확인
            if user.locked_until and user.locked_until > datetime.utcnow():
                await self._log_audit("login_failed", "user", user.id, ip_address, {
                    'username': username,
                    'reason': 'account_locked'
                })
                raise ValueError("계정이 잠겨있습니다")
            
            # 비밀번호 검증
            if not PasswordManager.verify_password(password, user.password_hash):
                user.failed_login_attempts += 1
                
                # 5회 실패 시 계정 잠금
                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                
                session.commit()
                
                await self._log_audit("login_failed", "user", user.id, ip_address, {
                    'username': username,
                    'reason': 'invalid_password',
                    'failed_attempts': user.failed_login_attempts
                })
                raise ValueError("잘못된 비밀번호입니다")
            
            # MFA 검증
            if user.mfa_enabled:
                if not mfa_token:
                    raise ValueError("MFA 토큰이 필요합니다")
                
                if not MFAManager.verify_totp(user.mfa_secret, mfa_token):
                    await self._log_audit("login_failed", "user", user.id, ip_address, {
                        'username': username,
                        'reason': 'invalid_mfa_token'
                    })
                    raise ValueError("잘못된 MFA 토큰입니다")
            
            # 로그인 성공 처리
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            user.login_count += 1
            
            # 사용자 역할 및 권한 조회
            roles = []
            permissions = set()
            
            for user_role in user.user_roles:
                if user_role.expires_at is None or user_role.expires_at > datetime.utcnow():
                    roles.append(user_role.role.name)
                    for role_permission in user_role.role.role_permissions:
                        permissions.add(role_permission.permission)
            
            # JWT 토큰 생성
            token_payload = TokenPayload(
                user_id=user.id,
                username=user.username,
                email=user.email,
                roles=roles,
                permissions=list(permissions),
                exp=0,  # JWT 매니저에서 설정
                iat=0,  # JWT 매니저에서 설정
                jti=""  # JWT 매니저에서 설정
            )
            
            access_token = self.jwt_manager.create_access_token(token_payload)
            refresh_token = self.jwt_manager.create_refresh_token(user.id)
            
            # 세션 생성
            session_id = str(uuid.uuid4())
            user_session = UserSession(
                id=session_id,
                user_id=user.id,
                access_token=access_token,
                refresh_token=refresh_token,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=datetime.utcnow() + self.jwt_manager.refresh_token_expire
            )
            
            session.add(user_session)
            session.commit()
            
            # 감사 로그
            await self._log_audit("login_success", "user", user.id, ip_address, {
                'username': username,
                'session_id': session_id
            })
            
            logger.info("사용자 인증 성공", user_id=user.id, username=username)
            
            return {
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'roles': roles,
                'permissions': list(permissions),
                'access_token': access_token,
                'refresh_token': refresh_token,
                'session_id': session_id,
                'mfa_enabled': user.mfa_enabled
            }
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """토큰 갱신"""
        try:
            payload = self.jwt_manager.verify_token(refresh_token)
            user_id = payload['user_id']
            
            with self.SessionLocal() as session:
                # 세션 확인
                user_session = session.query(UserSession).filter(
                    UserSession.refresh_token == refresh_token,
                    UserSession.is_active == True
                ).first()
                
                if not user_session:
                    raise ValueError("유효하지 않은 세션입니다")
                
                # 사용자 정보 조회
                user = session.query(User).filter(User.id == user_id).first()
                if not user or not user.is_active:
                    raise ValueError("사용자를 찾을 수 없습니다")
                
                # 역할 및 권한 조회
                roles = []
                permissions = set()
                
                for user_role in user.user_roles:
                    if user_role.expires_at is None or user_role.expires_at > datetime.utcnow():
                        roles.append(user_role.role.name)
                        for role_permission in user_role.role.role_permissions:
                            permissions.add(role_permission.permission)
                
                # 새 액세스 토큰 생성
                user_data = {
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'roles': roles,
                    'permissions': list(permissions)
                }
                
                new_access_token = self.jwt_manager.refresh_access_token(refresh_token, user_data)
                
                # 세션 업데이트
                user_session.access_token = new_access_token
                user_session.last_activity = datetime.utcnow()
                session.commit()
                
                return {
                    'access_token': new_access_token,
                    'refresh_token': refresh_token
                }
                
        except Exception as e:
            logger.error("토큰 갱신 실패", error=str(e))
            raise
    
    async def logout(self, session_id: str):
        """로그아웃"""
        with self.SessionLocal() as session:
            user_session = session.query(UserSession).filter(UserSession.id == session_id).first()
            
            if user_session:
                user_session.is_active = False
                session.commit()
                
                await self._log_audit("logout", "user", user_session.user_id, None, {
                    'session_id': session_id
                })
                
                logger.info("로그아웃 완료", session_id=session_id)
    
    async def setup_mfa(self, user_id: str) -> Dict[str, Any]:
        """MFA 설정"""
        with self.SessionLocal() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                raise ValueError("사용자를 찾을 수 없습니다")
            
            # MFA 시크릿 생성
            secret = MFAManager.generate_secret()
            backup_codes = MFAManager.generate_backup_codes()
            
            # QR 코드 생성
            qr_code = MFAManager.generate_qr_code(secret, user.username)
            
            # 임시 저장 (검증 후 활성화)
            user.mfa_secret = secret
            user.backup_codes = json.dumps(backup_codes)
            session.commit()
            
            return {
                'secret': secret,
                'qr_code': qr_code,
                'backup_codes': backup_codes
            }
    
    async def verify_mfa_setup(self, user_id: str, token: str) -> bool:
        """MFA 설정 검증"""
        with self.SessionLocal() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user or not user.mfa_secret:
                raise ValueError("MFA 설정이 없습니다")
            
            if MFAManager.verify_totp(user.mfa_secret, token):
                user.mfa_enabled = True
                session.commit()
                
                await self._log_audit("mfa_enabled", "user", user_id, None, {})
                
                logger.info("MFA 활성화 완료", user_id=user_id)
                return True
            
            return False
    
    async def check_permission(self, user_id: str, permission: str) -> bool:
        """권한 확인"""
        with self.SessionLocal() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user or not user.is_active:
                return False
            
            # 사용자 권한 조회
            for user_role in user.user_roles:
                if user_role.expires_at is None or user_role.expires_at > datetime.utcnow():
                    for role_permission in user_role.role.role_permissions:
                        if role_permission.permission == permission:
                            return True
            
            return False
    
    async def _log_audit(self, action: str, resource_type: str, resource_id: str,
                        ip_address: str, details: Dict[str, Any]):
        """감사 로그 기록"""
        with self.SessionLocal() as session:
            audit_log = AuditLog(
                id=str(uuid.uuid4()),
                user_id=resource_id if resource_type == "user" else None,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                details=json.dumps(details)
            )
            
            session.add(audit_log)
            session.commit()

# 설정 예시
DEFAULT_CONFIG = {
    'database_url': 'postgresql://user:password@localhost:5432/aicc_db',
    'jwt_secret': 'your-secret-key-here',
    'aws_cognito_user_pool_id': None  # 선택적
}

async def main():
    """메인 실행 함수"""
    auth_service = AuthService(DEFAULT_CONFIG)
    
    try:
        # 사용자 등록
        user_id = await auth_service.register_user(
            username="test_agent",
            email="agent@example.com",
            password="SecurePass123!",
            first_name="Test",
            last_name="Agent",
            roles=[UserRole.AGENT.value]
        )
        
        # 로그인
        auth_result = await auth_service.authenticate_user(
            username="test_agent",
            password="SecurePass123!",
            ip_address="127.0.0.1"
        )
        
        logger.info("인증 테스트 완료", 
                   user_id=user_id,
                   access_token=auth_result['access_token'][:20] + "...")
        
    except Exception as e:
        logger.error("인증 테스트 실패", error=str(e))

if __name__ == "__main__":
    asyncio.run(main()) 