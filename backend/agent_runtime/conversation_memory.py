"""
Conversation Memory Manager for session-based interactions.

Stores conversation history per job to enable multi-turn dialogues.
"""

import os
import boto3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

s3 = boto3.client('s3', region_name=os.environ.get("AWS_REGION", "us-east-1"))
BUCKET = "excel-trace-agent-bucket-549955691461"

print(f"[ConversationMemory] Initialized with BUCKET={BUCKET}")


class ConversationMemory:
    """Manages conversation history for a job session."""

    def __init__(self, job_id: str, user_id: str):
        self.job_id = job_id
        self.user_id = user_id
        self.s3_key = f"{user_id}/{job_id}/conversation/history.json"

    def get_history(self) -> List[Dict[str, Any]]:
        """Retrieve conversation history from S3."""
        try:
            response = s3.get_object(Bucket=BUCKET, Key=self.s3_key)
            data = json.loads(response['Body'].read())
            return data.get('messages', [])
        except s3.exceptions.NoSuchKey:
            return []
        except Exception as e:
            print(f"[ConversationMemory] Error loading history: {e}")
            return []

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to conversation history."""
        print(f"[ConversationMemory] add_message called - Bucket={BUCKET}, Key={self.s3_key}")
        history = self.get_history()

        message = {
            'role': role,  # 'user' or 'assistant'
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metadata': metadata or {}
        }

        history.append(message)

        # Save back to S3
        print(f"[ConversationMemory] Saving to S3: Bucket={BUCKET}, Key={self.s3_key}")
        s3.put_object(
            Bucket=BUCKET,
            Key=self.s3_key,
            Body=json.dumps({
                'job_id': self.job_id,
                'messages': history,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }, indent=2),
            ContentType='application/json'
        )

        print(f"[ConversationMemory] Added {role} message (total: {len(history)} messages)")

    def get_last_assistant_message(self) -> Optional[Dict[str, Any]]:
        """Get the most recent assistant message."""
        history = self.get_history()
        for msg in reversed(history):
            if msg['role'] == 'assistant':
                return msg
        return None

    def has_pending_clarification(self) -> bool:
        """Check if there's a pending clarification question."""
        last_msg = self.get_last_assistant_message()
        if not last_msg:
            return False

        metadata = last_msg.get('metadata', {})
        return metadata.get('type') == 'clarification' and not metadata.get('answered', False)

    def get_pending_clarification(self) -> Optional[Dict[str, Any]]:
        """Get the pending clarification context."""
        if not self.has_pending_clarification():
            return None

        last_msg = self.get_last_assistant_message()
        return last_msg.get('metadata', {}).get('clarification_context')

    def mark_clarification_answered(self):
        """Mark the current clarification as answered."""
        history = self.get_history()

        # Find the last assistant message with pending clarification
        for msg in reversed(history):
            if (msg['role'] == 'assistant' and
                msg.get('metadata', {}).get('type') == 'clarification' and
                not msg.get('metadata', {}).get('answered', False)):

                msg['metadata']['answered'] = True
                msg['metadata']['answered_at'] = datetime.now(timezone.utc).isoformat()
                break

        # Save updated history
        s3.put_object(
            Bucket=BUCKET,
            Key=self.s3_key,
            Body=json.dumps({
                'job_id': self.job_id,
                'messages': history,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }, indent=2),
            ContentType='application/json'
        )

    def get_conversation_context(self, max_messages: int = 10) -> str:
        """Get recent conversation as formatted text for LLM context."""
        history = self.get_history()
        recent = history[-max_messages:] if len(history) > max_messages else history

        context_lines = []
        for msg in recent:
            role = msg['role'].upper()
            content = msg['content']
            context_lines.append(f"{role}: {content}")

        return "\n".join(context_lines)

    def clear(self):
        """Clear conversation history."""
        try:
            s3.delete_object(Bucket=BUCKET, Key=self.s3_key)
            print(f"[ConversationMemory] Cleared history for job {self.job_id}")
        except Exception as e:
            print(f"[ConversationMemory] Error clearing history: {e}")
