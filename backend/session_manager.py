"""
Session Manager for handling session state and persistence
Manages active sessions, panes, and conversation history
"""

import logging
import os
import json
import base64
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from models import Session, ChatPane, Message

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages session state and persistence.
    
    Handles creation, retrieval, and updates of sessions and their
    associated panes and conversation history.
    """
    
    def __init__(self):
        # In-memory storage (would be replaced with database in production)
        self.sessions: Dict[str, Session] = {}
        self.max_sessions = 1000  # Limit to prevent memory issues
    
    def create_session(self, session_id: Optional[str] = None, name: Optional[str] = None) -> Session:
        """
        Create a new session.
        
        Args:
            session_id: Optional session ID (generates UUID if not provided)
            name: Optional session name
            
        Returns:
            Created session
        """
        if not session_id:
            session_id = str(uuid4())
        
        session = Session(
            id=session_id,
            name=name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        self.sessions[session_id] = session
        
        # Clean up old sessions if we exceed the limit
        if len(self.sessions) > self.max_sessions:
            self._cleanup_old_sessions()
        
        logger.info(f"Created session: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get a session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session if found, None otherwise
        """
        return self.sessions.get(session_id)
    
    def get_or_create_session(self, session_id: str, name: Optional[str] = None) -> Session:
        """
        Get existing session or create new one.
        
        Args:
            session_id: Session identifier
            name: Optional session name for new sessions
            
        Returns:
            Existing or newly created session
        """
        session = self.get_session(session_id)
        if session:
            return session
        
        return self.create_session(session_id, name)
    
    def update_session(self, session: Session) -> bool:
        """
        Update an existing session.
        
        Args:
            session: Session to update
            
        Returns:
            True if session was updated, False if not found
        """
        if session.id not in self.sessions:
            return False
        
        session.updated_at = datetime.now()
        self.sessions[session.id] = session
        
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was deleted, False if not found
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        
        return False
    
    def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        """
        List sessions with pagination.
        
        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            
        Returns:
            List of sessions
        """
        all_sessions = list(self.sessions.values())
        
        # Sort by updated_at descending (most recent first)
        all_sessions.sort(key=lambda s: s.updated_at, reverse=True)
        
        return all_sessions[offset:offset + limit]
    
    def add_pane_to_session(self, session_id: str, pane: ChatPane) -> bool:
        """
        Add a pane to a session.
        
        Args:
            session_id: Session identifier
            pane: Pane to add
            
        Returns:
            True if pane was added, False if session not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.panes.append(pane)
        session.updated_at = datetime.now()
        
        return True
    
    def remove_pane_from_session(self, session_id: str, pane_id: str) -> bool:
        """
        Remove a pane from a session.
        
        Args:
            session_id: Session identifier
            pane_id: Pane identifier
            
        Returns:
            True if pane was removed, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        original_count = len(session.panes)
        session.panes = [p for p in session.panes if p.id != pane_id]
        
        if len(session.panes) < original_count:
            session.updated_at = datetime.now()
            return True
        
        return False
    
    def get_pane(self, session_id: str, pane_id: str) -> Optional[ChatPane]:
        """
        Get a specific pane from a session.
        
        Args:
            session_id: Session identifier
            pane_id: Pane identifier
            
        Returns:
            Pane if found, None otherwise
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        return next((p for p in session.panes if p.id == pane_id), None)
    
    def add_message_to_pane(self, session_id: str, pane_id: str, message: Message) -> bool:
        """
        Add a message to a specific pane.
        
        Args:
            session_id: Session identifier
            pane_id: Pane identifier
            message: Message to add
            
        Returns:
            True if message was added, False if pane not found
        """
        pane = self.get_pane(session_id, pane_id)
        if not pane:
            return False
        
        pane.messages.append(message)
        
        # Update session timestamp
        session = self.get_session(session_id)
        if session:
            session.updated_at = datetime.now()
        
        return True
    
    def get_session_stats(self) -> Dict[str, int]:
        """
        Get statistics about managed sessions.
        
        Returns:
            Dictionary with session statistics
        """
        active_sessions = sum(1 for s in self.sessions.values() if s.status == "active")
        total_panes = sum(len(s.panes) for s in self.sessions.values())
        total_messages = sum(
            len(p.messages) for s in self.sessions.values() for p in s.panes
        )
        
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "total_panes": total_panes,
            "total_messages": total_messages
        }
    
    def _cleanup_old_sessions(self):
        """
        Clean up old sessions to prevent memory issues.
        Removes oldest sessions that are not active.
        """
        # Get sessions sorted by updated_at (oldest first)
        sessions_by_age = sorted(
            self.sessions.values(),
            key=lambda s: s.updated_at
        )
        
        # Remove oldest non-active sessions until we're under the limit
        sessions_to_remove = []
        for session in sessions_by_age:
            if len(self.sessions) - len(sessions_to_remove) <= self.max_sessions * 0.8:
                break
            
            if session.status != "active":
                sessions_to_remove.append(session.id)
        
        for session_id in sessions_to_remove:
            del self.sessions[session_id]
            logger.info(f"Cleaned up old session: {session_id}")
    
    def archive_session(self, session_id: str) -> bool:
        """
        Archive a session (mark as archived).
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was archived, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.status = "archived"
        session.updated_at = datetime.now()
        
        logger.info(f"Archived session: {session_id}")
        return True
    
    def restore_session(self, session_id: str) -> bool:
        """
        Restore an archived session (mark as active).
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was restored, False if not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.status = "active"
        session.updated_at = datetime.now()
        
        logger.info(f"Restored session: {session_id}")
        return True


class SessionFileManager:
    """
    Manages uploaded files scoped to a particular session.
    Enforces maximum file sizes and total session size constraints.
    """
    def __init__(self, storage_dir=".session_files"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.MAX_FILE_SIZE = 50 * 1024 * 1024 # 50 MB
        self.MAX_SESSION_SIZE = 50 * 1024 * 1024 # 50 MB
    
    def _get_session_dir(self, session_id: str) -> str:
        d = os.path.join(self.storage_dir, session_id)
        os.makedirs(d, exist_ok=True)
        return d
        
    def _get_session_size(self, session_id: str) -> int:
        d = self._get_session_dir(session_id)
        total_size = 0
        for f in os.listdir(d):
            if f != "metadata.json":
                total_size += os.path.getsize(os.path.join(d, f))
        return total_size
        
    def _get_overall_storage_size(self) -> int:
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(self.storage_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        return total_size

    def _get_metadata(self, session_id: str) -> dict:
        d = self._get_session_dir(session_id)
        meta_file = os.path.join(d, "metadata.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading metadata for session {session_id}: {e}")
                return {}
        return {}
        
    def _save_metadata(self, session_id: str, meta: dict):
        d = self._get_session_dir(session_id)
        with open(os.path.join(d, "metadata.json"), 'w', encoding='utf-8') as f:
            json.dump(meta, f)

    def add_file(self, session_id: str, file_id: str, name: str, mime_type: str, content: bytes) -> dict:
        size = len(content)
        if size > self.MAX_FILE_SIZE:
            raise ValueError(f"File {name} exceeds the 50MB limit")
            
        current_len = self._get_session_size(session_id)
        if current_len + size > self.MAX_SESSION_SIZE:
            raise ValueError(f"Session limit of 50MB exceeded! Current session size: {current_len//(1024*1024)}MB. Delete old files to upload more.")
            
        d = self._get_session_dir(session_id)
        
        base, extension = os.path.splitext(name)
        new_filename = name
        counter = 1
        while os.path.exists(os.path.join(d, new_filename)):
            if counter > 500:
                from uuid import uuid4
                new_filename = f"{base}_{str(uuid4())[:8]}{extension}"
                break
            new_filename = f"{base}_{counter}{extension}"
            counter += 1
            
        file_path = os.path.join(d, new_filename)
        
        with open(file_path, "wb") as f:
            f.write(content)
            
        meta = self._get_metadata(session_id)
        file_info = {
            "id": file_id,
            "name": new_filename,
            "originalName": name, # Store original name explicitly
            "type": mime_type,
            "size": size,
            "uri": f"session_file:{file_id}",
            "disk_filename": new_filename
        }
        meta[file_id] = file_info
        self._save_metadata(session_id, meta)
        
        return file_info

    def get_files(self, session_id: str) -> list:
        meta = self._get_metadata(session_id)
        return list(meta.values())
        
    def get_file_content(self, session_id: str, file_uri: str) -> str:
        # file_uri is like "session_file:123"
        try:
            file_id = file_uri.split(":", 1)[1]
            meta = self._get_metadata(session_id)
            if file_id not in meta:
                return None
                
            file_info = meta[file_id]
            disk_filename = file_info.get("disk_filename", file_id)
            file_path = os.path.join(self.storage_dir, session_id, disk_filename)
            if not os.path.exists(file_path):
                file_path = os.path.join(self.storage_dir, session_id, file_id) # fallback
            if not os.path.exists(file_path):
                return None
                
            with open(file_path, "rb") as f:
                content = f.read()
                
            return f"data:{file_info['type']};base64,{base64.b64encode(content).decode('utf-8')}"
        except Exception as e:
            logger.error(f"Error retrieving file content: {e}")
            return None