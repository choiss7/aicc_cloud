"""
녹취/저장 서비스
통화 녹음, 채팅 로그, 파일 저장 관리
AWS S3, 암호화, 압축, 메타데이터 관리
"""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, BinaryIO
from dataclasses import dataclass, asdict
from enum import Enum
import boto3
import aiofiles
import aioredis
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import structlog

# 로깅 설정
logger = structlog.get_logger(__name__)

Base = declarative_base()

class RecordingType(Enum):
    VOICE_CALL = "voice_call"
    VIDEO_CALL = "video_call"
    CHAT_SESSION = "chat_session"
    SCREEN_RECORDING = "screen_recording"
    FILE_UPLOAD = "file_upload"

class RecordingStatus(Enum):
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"

class StorageType(Enum):
    S3 = "s3"
    LOCAL = "local"
    HYBRID = "hybrid"

@dataclass
class RecordingMetadata:
    """녹취 메타데이터"""
    recording_id: str
    session_id: str
    agent_id: str
    customer_id: str
    recording_type: RecordingType
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[int] = None  # seconds
    file_size: Optional[int] = None  # bytes
    file_format: Optional[str] = None
    quality: Optional[str] = None
    encryption_key: Optional[str] = None
    storage_location: Optional[str] = None
    tags: Dict[str, str] = None

class Recording(Base):
    """녹취 데이터베이스 모델"""
    __tablename__ = 'recordings'
    
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    customer_id = Column(String, nullable=False, index=True)
    recording_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default=RecordingStatus.RECORDING.value)
    
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration = Column(Integer)  # seconds
    
    file_path = Column(String)
    file_size = Column(Integer)
    file_format = Column(String)
    quality = Column(String)
    
    storage_type = Column(String, default=StorageType.S3.value)
    storage_location = Column(String)
    
    encrypted = Column(Boolean, default=True)
    encryption_key_id = Column(String)
    
    metadata = Column(Text)  # JSON
    tags = Column(Text)  # JSON
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 보존 정책
    retention_days = Column(Integer, default=2555)  # 7년
    archived = Column(Boolean, default=False)
    archive_date = Column(DateTime)

class ChatLog(Base):
    """채팅 로그 모델"""
    __tablename__ = 'chat_logs'
    
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    recording_id = Column(String, nullable=False, index=True)
    
    timestamp = Column(DateTime, nullable=False)
    sender_id = Column(String, nullable=False)
    sender_type = Column(String, nullable=False)  # agent, customer, system
    message_type = Column(String, nullable=False)  # text, file, image, etc.
    content = Column(Text)
    
    metadata = Column(Text)  # JSON
    
    created_at = Column(DateTime, default=datetime.utcnow)

class EncryptionManager:
    """암호화 관리자"""
    
    def __init__(self, master_key: str = None):
        if master_key:
            self.master_key = master_key.encode()
        else:
            self.master_key = Fernet.generate_key()
        
        self.cipher_suite = Fernet(self.master_key)
    
    def encrypt_data(self, data: bytes) -> bytes:
        """데이터 암호화"""
        return self.cipher_suite.encrypt(data)
    
    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """데이터 복호화"""
        return self.cipher_suite.decrypt(encrypted_data)
    
    def generate_key(self) -> str:
        """새로운 암호화 키 생성"""
        return Fernet.generate_key().decode()

class S3StorageManager:
    """AWS S3 저장소 관리자"""
    
    def __init__(self, bucket_name: str, region_name: str = 'ap-northeast-2'):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3', region_name=region_name)
        self.region_name = region_name
    
    async def upload_file(self, file_path: str, s3_key: str, 
                         metadata: Dict[str, str] = None) -> str:
        """파일을 S3에 업로드"""
        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
            
            # 서버 사이드 암호화 설정
            extra_args['ServerSideEncryption'] = 'AES256'
            
            self.s3_client.upload_file(
                file_path, 
                self.bucket_name, 
                s3_key,
                ExtraArgs=extra_args
            )
            
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            logger.info("S3 업로드 완료", s3_url=s3_url, file_size=os.path.getsize(file_path))
            
            return s3_url
            
        except Exception as e:
            logger.error("S3 업로드 실패", error=str(e), s3_key=s3_key)
            raise
    
    async def download_file(self, s3_key: str, local_path: str) -> str:
        """S3에서 파일 다운로드"""
        try:
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            logger.info("S3 다운로드 완료", s3_key=s3_key, local_path=local_path)
            return local_path
            
        except Exception as e:
            logger.error("S3 다운로드 실패", error=str(e), s3_key=s3_key)
            raise
    
    async def delete_file(self, s3_key: str):
        """S3에서 파일 삭제"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info("S3 파일 삭제 완료", s3_key=s3_key)
            
        except Exception as e:
            logger.error("S3 파일 삭제 실패", error=str(e), s3_key=s3_key)
            raise
    
    async def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """사전 서명된 URL 생성"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
            
        except Exception as e:
            logger.error("사전 서명된 URL 생성 실패", error=str(e), s3_key=s3_key)
            raise

class AudioProcessor:
    """오디오 처리기"""
    
    def __init__(self):
        self.supported_formats = ['wav', 'mp3', 'flac', 'aac']
    
    async def convert_audio(self, input_path: str, output_path: str, 
                           target_format: str = 'mp3', quality: str = 'medium') -> str:
        """오디오 포맷 변환"""
        try:
            import ffmpeg
            
            # 품질 설정
            quality_settings = {
                'low': {'audio_bitrate': '64k'},
                'medium': {'audio_bitrate': '128k'},
                'high': {'audio_bitrate': '256k'}
            }
            
            settings = quality_settings.get(quality, quality_settings['medium'])
            
            # FFmpeg를 사용한 변환
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(stream, output_path, **settings)
            ffmpeg.run(stream, overwrite_output=True, quiet=True)
            
            logger.info("오디오 변환 완료", 
                       input_path=input_path, 
                       output_path=output_path,
                       format=target_format,
                       quality=quality)
            
            return output_path
            
        except Exception as e:
            logger.error("오디오 변환 실패", error=str(e))
            raise
    
    async def extract_audio_metadata(self, file_path: str) -> Dict[str, Any]:
        """오디오 메타데이터 추출"""
        try:
            import ffmpeg
            
            probe = ffmpeg.probe(file_path)
            audio_stream = next(
                (stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), 
                None
            )
            
            if not audio_stream:
                raise ValueError("오디오 스트림을 찾을 수 없습니다")
            
            metadata = {
                'duration': float(audio_stream.get('duration', 0)),
                'sample_rate': int(audio_stream.get('sample_rate', 0)),
                'channels': int(audio_stream.get('channels', 0)),
                'codec': audio_stream.get('codec_name'),
                'bitrate': int(audio_stream.get('bit_rate', 0)) if audio_stream.get('bit_rate') else None
            }
            
            return metadata
            
        except Exception as e:
            logger.error("오디오 메타데이터 추출 실패", error=str(e))
            return {}

class VoiceRecordingManager:
    """음성 녹음 관리자"""
    
    def __init__(self, storage_manager: S3StorageManager, 
                 encryption_manager: EncryptionManager,
                 audio_processor: AudioProcessor):
        self.storage_manager = storage_manager
        self.encryption_manager = encryption_manager
        self.audio_processor = audio_processor
        self.active_recordings: Dict[str, Dict] = {}
    
    async def start_recording(self, session_id: str, agent_id: str, 
                            customer_id: str) -> str:
        """음성 녹음 시작"""
        recording_id = str(uuid.uuid4())
        
        recording_info = {
            'recording_id': recording_id,
            'session_id': session_id,
            'agent_id': agent_id,
            'customer_id': customer_id,
            'start_time': datetime.now(),
            'temp_file': None,
            'status': RecordingStatus.RECORDING
        }
        
        self.active_recordings[recording_id] = recording_info
        
        logger.info("음성 녹음 시작", 
                   recording_id=recording_id, 
                   session_id=session_id)
        
        return recording_id
    
    async def stop_recording(self, recording_id: str) -> RecordingMetadata:
        """음성 녹음 중지 및 처리"""
        if recording_id not in self.active_recordings:
            raise ValueError(f"활성 녹음을 찾을 수 없습니다: {recording_id}")
        
        recording_info = self.active_recordings[recording_id]
        recording_info['end_time'] = datetime.now()
        recording_info['status'] = RecordingStatus.PROCESSING
        
        try:
            # 임시 파일에서 최종 처리
            temp_file = recording_info.get('temp_file')
            if not temp_file or not os.path.exists(temp_file):
                raise ValueError("녹음 파일을 찾을 수 없습니다")
            
            # 오디오 메타데이터 추출
            audio_metadata = await self.audio_processor.extract_audio_metadata(temp_file)
            
            # 오디오 변환 (MP3로 압축)
            converted_file = temp_file.replace('.wav', '.mp3')
            await self.audio_processor.convert_audio(
                temp_file, converted_file, 'mp3', 'medium'
            )
            
            # 파일 암호화
            encrypted_file = converted_file + '.enc'
            await self._encrypt_file(converted_file, encrypted_file)
            
            # S3에 업로드
            s3_key = f"recordings/voice/{recording_info['session_id']}/{recording_id}.mp3.enc"
            s3_url = await self.storage_manager.upload_file(
                encrypted_file, 
                s3_key,
                metadata={
                    'recording_id': recording_id,
                    'session_id': recording_info['session_id'],
                    'agent_id': recording_info['agent_id'],
                    'customer_id': recording_info['customer_id'],
                    'recording_type': RecordingType.VOICE_CALL.value
                }
            )
            
            # 메타데이터 생성
            metadata = RecordingMetadata(
                recording_id=recording_id,
                session_id=recording_info['session_id'],
                agent_id=recording_info['agent_id'],
                customer_id=recording_info['customer_id'],
                recording_type=RecordingType.VOICE_CALL,
                start_time=recording_info['start_time'],
                end_time=recording_info['end_time'],
                duration=int(audio_metadata.get('duration', 0)),
                file_size=os.path.getsize(encrypted_file),
                file_format='mp3',
                quality='medium',
                storage_location=s3_url
            )
            
            # 임시 파일 정리
            for file_path in [temp_file, converted_file, encrypted_file]:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # 활성 녹음에서 제거
            del self.active_recordings[recording_id]
            
            logger.info("음성 녹음 완료", 
                       recording_id=recording_id,
                       duration=metadata.duration,
                       file_size=metadata.file_size)
            
            return metadata
            
        except Exception as e:
            recording_info['status'] = RecordingStatus.FAILED
            logger.error("음성 녹음 처리 실패", 
                        recording_id=recording_id, 
                        error=str(e))
            raise
    
    async def _encrypt_file(self, input_file: str, output_file: str):
        """파일 암호화"""
        async with aiofiles.open(input_file, 'rb') as f_in:
            data = await f_in.read()
        
        encrypted_data = self.encryption_manager.encrypt_data(data)
        
        async with aiofiles.open(output_file, 'wb') as f_out:
            await f_out.write(encrypted_data)

class ChatLogManager:
    """채팅 로그 관리자"""
    
    def __init__(self, storage_manager: S3StorageManager,
                 encryption_manager: EncryptionManager):
        self.storage_manager = storage_manager
        self.encryption_manager = encryption_manager
        self.active_sessions: Dict[str, List[Dict]] = {}
    
    async def start_chat_logging(self, session_id: str, agent_id: str, 
                               customer_id: str) -> str:
        """채팅 로깅 시작"""
        recording_id = str(uuid.uuid4())
        
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = []
        
        logger.info("채팅 로깅 시작", 
                   recording_id=recording_id,
                   session_id=session_id)
        
        return recording_id
    
    async def log_message(self, session_id: str, sender_id: str, 
                         sender_type: str, message_type: str, 
                         content: str, metadata: Dict = None):
        """메시지 로깅"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = []
        
        log_entry = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'sender_id': sender_id,
            'sender_type': sender_type,
            'message_type': message_type,
            'content': content,
            'metadata': metadata or {}
        }
        
        self.active_sessions[session_id].append(log_entry)
        
        logger.debug("메시지 로깅", 
                    session_id=session_id,
                    sender_type=sender_type,
                    message_type=message_type)
    
    async def end_chat_logging(self, session_id: str, recording_id: str) -> RecordingMetadata:
        """채팅 로깅 종료 및 저장"""
        if session_id not in self.active_sessions:
            raise ValueError(f"활성 채팅 세션을 찾을 수 없습니다: {session_id}")
        
        chat_logs = self.active_sessions[session_id]
        
        try:
            # 채팅 로그를 JSON으로 직렬화
            chat_data = {
                'session_id': session_id,
                'recording_id': recording_id,
                'start_time': chat_logs[0]['timestamp'] if chat_logs else datetime.now().isoformat(),
                'end_time': datetime.now().isoformat(),
                'message_count': len(chat_logs),
                'messages': chat_logs
            }
            
            # 임시 파일에 저장
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json.dump(chat_data, temp_file, ensure_ascii=False, indent=2)
                temp_file_path = temp_file.name
            
            # 파일 암호화
            encrypted_file = temp_file_path + '.enc'
            await self._encrypt_file(temp_file_path, encrypted_file)
            
            # S3에 업로드
            s3_key = f"recordings/chat/{session_id}/{recording_id}.json.enc"
            s3_url = await self.storage_manager.upload_file(
                encrypted_file,
                s3_key,
                metadata={
                    'recording_id': recording_id,
                    'session_id': session_id,
                    'recording_type': RecordingType.CHAT_SESSION.value,
                    'message_count': str(len(chat_logs))
                }
            )
            
            # 메타데이터 생성
            start_time = datetime.fromisoformat(chat_logs[0]['timestamp']) if chat_logs else datetime.now()
            end_time = datetime.now()
            
            metadata = RecordingMetadata(
                recording_id=recording_id,
                session_id=session_id,
                agent_id=chat_logs[0]['sender_id'] if chat_logs else '',
                customer_id='',  # 채팅에서 고객 ID 추출 로직 필요
                recording_type=RecordingType.CHAT_SESSION,
                start_time=start_time,
                end_time=end_time,
                duration=int((end_time - start_time).total_seconds()),
                file_size=os.path.getsize(encrypted_file),
                file_format='json',
                storage_location=s3_url
            )
            
            # 임시 파일 정리
            for file_path in [temp_file_path, encrypted_file]:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # 활성 세션에서 제거
            del self.active_sessions[session_id]
            
            logger.info("채팅 로깅 완료",
                       recording_id=recording_id,
                       session_id=session_id,
                       message_count=len(chat_logs))
            
            return metadata
            
        except Exception as e:
            logger.error("채팅 로깅 저장 실패",
                        recording_id=recording_id,
                        session_id=session_id,
                        error=str(e))
            raise
    
    async def _encrypt_file(self, input_file: str, output_file: str):
        """파일 암호화"""
        async with aiofiles.open(input_file, 'rb') as f_in:
            data = await f_in.read()
        
        encrypted_data = self.encryption_manager.encrypt_data(data)
        
        async with aiofiles.open(output_file, 'wb') as f_out:
            await f_out.write(encrypted_data)

class RecordingService:
    """통합 녹취/저장 서비스"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # 데이터베이스 설정
        self.engine = create_engine(config['database_url'])
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Redis 설정
        self.redis_client = None
        if config.get('redis_url'):
            self.redis_client = aioredis.from_url(config['redis_url'])
        
        # 컴포넌트 초기화
        self.encryption_manager = EncryptionManager(config.get('encryption_key'))
        self.storage_manager = S3StorageManager(
            config['s3_bucket'], 
            config.get('aws_region', 'ap-northeast-2')
        )
        self.audio_processor = AudioProcessor()
        
        self.voice_recording_manager = VoiceRecordingManager(
            self.storage_manager,
            self.encryption_manager,
            self.audio_processor
        )
        
        self.chat_log_manager = ChatLogManager(
            self.storage_manager,
            self.encryption_manager
        )
    
    async def start_voice_recording(self, session_id: str, agent_id: str, 
                                  customer_id: str) -> str:
        """음성 녹음 시작"""
        recording_id = await self.voice_recording_manager.start_recording(
            session_id, agent_id, customer_id
        )
        
        # 데이터베이스에 녹음 정보 저장
        await self._save_recording_to_db(
            recording_id, session_id, agent_id, customer_id,
            RecordingType.VOICE_CALL, RecordingStatus.RECORDING
        )
        
        return recording_id
    
    async def stop_voice_recording(self, recording_id: str) -> RecordingMetadata:
        """음성 녹음 중지"""
        metadata = await self.voice_recording_manager.stop_recording(recording_id)
        
        # 데이터베이스 업데이트
        await self._update_recording_in_db(recording_id, metadata, RecordingStatus.COMPLETED)
        
        return metadata
    
    async def start_chat_logging(self, session_id: str, agent_id: str, 
                               customer_id: str) -> str:
        """채팅 로깅 시작"""
        recording_id = await self.chat_log_manager.start_chat_logging(
            session_id, agent_id, customer_id
        )
        
        # 데이터베이스에 녹음 정보 저장
        await self._save_recording_to_db(
            recording_id, session_id, agent_id, customer_id,
            RecordingType.CHAT_SESSION, RecordingStatus.RECORDING
        )
        
        return recording_id
    
    async def log_chat_message(self, session_id: str, sender_id: str,
                             sender_type: str, message_type: str,
                             content: str, metadata: Dict = None):
        """채팅 메시지 로깅"""
        await self.chat_log_manager.log_message(
            session_id, sender_id, sender_type, 
            message_type, content, metadata
        )
    
    async def end_chat_logging(self, session_id: str, recording_id: str) -> RecordingMetadata:
        """채팅 로깅 종료"""
        metadata = await self.chat_log_manager.end_chat_logging(session_id, recording_id)
        
        # 데이터베이스 업데이트
        await self._update_recording_in_db(recording_id, metadata, RecordingStatus.COMPLETED)
        
        return metadata
    
    async def get_recording(self, recording_id: str) -> Optional[Recording]:
        """녹음 정보 조회"""
        with self.SessionLocal() as session:
            return session.query(Recording).filter(Recording.id == recording_id).first()
    
    async def search_recordings(self, filters: Dict[str, Any], 
                              limit: int = 100, offset: int = 0) -> List[Recording]:
        """녹음 검색"""
        with self.SessionLocal() as session:
            query = session.query(Recording)
            
            if filters.get('session_id'):
                query = query.filter(Recording.session_id == filters['session_id'])
            
            if filters.get('agent_id'):
                query = query.filter(Recording.agent_id == filters['agent_id'])
            
            if filters.get('customer_id'):
                query = query.filter(Recording.customer_id == filters['customer_id'])
            
            if filters.get('recording_type'):
                query = query.filter(Recording.recording_type == filters['recording_type'])
            
            if filters.get('start_date'):
                query = query.filter(Recording.start_time >= filters['start_date'])
            
            if filters.get('end_date'):
                query = query.filter(Recording.start_time <= filters['end_date'])
            
            return query.offset(offset).limit(limit).all()
    
    async def download_recording(self, recording_id: str, output_path: str) -> str:
        """녹음 파일 다운로드"""
        recording = await self.get_recording(recording_id)
        if not recording:
            raise ValueError(f"녹음을 찾을 수 없습니다: {recording_id}")
        
        # S3에서 다운로드
        s3_key = recording.storage_location.replace(f"s3://{self.config['s3_bucket']}/", "")
        encrypted_file = output_path + '.enc'
        
        await self.storage_manager.download_file(s3_key, encrypted_file)
        
        # 복호화
        async with aiofiles.open(encrypted_file, 'rb') as f_in:
            encrypted_data = await f_in.read()
        
        decrypted_data = self.encryption_manager.decrypt_data(encrypted_data)
        
        async with aiofiles.open(output_path, 'wb') as f_out:
            await f_out.write(decrypted_data)
        
        # 임시 암호화 파일 삭제
        os.remove(encrypted_file)
        
        logger.info("녹음 파일 다운로드 완료", 
                   recording_id=recording_id,
                   output_path=output_path)
        
        return output_path
    
    async def delete_recording(self, recording_id: str):
        """녹음 삭제"""
        recording = await self.get_recording(recording_id)
        if not recording:
            raise ValueError(f"녹음을 찾을 수 없습니다: {recording_id}")
        
        # S3에서 파일 삭제
        s3_key = recording.storage_location.replace(f"s3://{self.config['s3_bucket']}/", "")
        await self.storage_manager.delete_file(s3_key)
        
        # 데이터베이스에서 삭제
        with self.SessionLocal() as session:
            session.delete(recording)
            session.commit()
        
        logger.info("녹음 삭제 완료", recording_id=recording_id)
    
    async def archive_old_recordings(self, days: int = 2555):
        """오래된 녹음 아카이브"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self.SessionLocal() as session:
            old_recordings = session.query(Recording).filter(
                Recording.created_at < cutoff_date,
                Recording.archived == False
            ).all()
            
            for recording in old_recordings:
                # 아카이브 처리 (예: Glacier로 이동)
                recording.archived = True
                recording.archive_date = datetime.now()
            
            session.commit()
            
            logger.info("녹음 아카이브 완료", count=len(old_recordings))
    
    async def _save_recording_to_db(self, recording_id: str, session_id: str,
                                  agent_id: str, customer_id: str,
                                  recording_type: RecordingType,
                                  status: RecordingStatus):
        """데이터베이스에 녹음 정보 저장"""
        with self.SessionLocal() as session:
            recording = Recording(
                id=recording_id,
                session_id=session_id,
                agent_id=agent_id,
                customer_id=customer_id,
                recording_type=recording_type.value,
                status=status.value,
                start_time=datetime.now()
            )
            
            session.add(recording)
            session.commit()
    
    async def _update_recording_in_db(self, recording_id: str, 
                                    metadata: RecordingMetadata,
                                    status: RecordingStatus):
        """데이터베이스의 녹음 정보 업데이트"""
        with self.SessionLocal() as session:
            recording = session.query(Recording).filter(Recording.id == recording_id).first()
            
            if recording:
                recording.status = status.value
                recording.end_time = metadata.end_time
                recording.duration = metadata.duration
                recording.file_size = metadata.file_size
                recording.file_format = metadata.file_format
                recording.quality = metadata.quality
                recording.storage_location = metadata.storage_location
                recording.updated_at = datetime.now()
                
                session.commit()

# 설정 예시
DEFAULT_CONFIG = {
    'database_url': 'postgresql://user:password@localhost:5432/aicc_db',
    'redis_url': 'redis://localhost:6379',
    's3_bucket': 'aicc-recordings',
    'aws_region': 'ap-northeast-2',
    'encryption_key': None  # 자동 생성
}

async def main():
    """메인 실행 함수"""
    recording_service = RecordingService(DEFAULT_CONFIG)
    
    # 예시 사용법
    try:
        # 음성 녹음 시작
        voice_recording_id = await recording_service.start_voice_recording(
            'session_123', 'agent_456', 'customer_789'
        )
        
        # 채팅 로깅 시작
        chat_recording_id = await recording_service.start_chat_logging(
            'session_123', 'agent_456', 'customer_789'
        )
        
        # 채팅 메시지 로깅
        await recording_service.log_chat_message(
            'session_123', 'agent_456', 'agent', 'text', '안녕하세요!'
        )
        
        await recording_service.log_chat_message(
            'session_123', 'customer_789', 'customer', 'text', '네, 안녕하세요.'
        )
        
        # 시뮬레이션을 위한 대기
        await asyncio.sleep(5)
        
        # 녹음 중지
        voice_metadata = await recording_service.stop_voice_recording(voice_recording_id)
        chat_metadata = await recording_service.end_chat_logging('session_123', chat_recording_id)
        
        logger.info("녹취 서비스 테스트 완료",
                   voice_recording=voice_metadata.recording_id,
                   chat_recording=chat_metadata.recording_id)
        
    except Exception as e:
        logger.error("녹취 서비스 테스트 실패", error=str(e))

if __name__ == "__main__":
    asyncio.run(main()) 