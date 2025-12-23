import sqlite3
import json
import os
import logging
from datetime import datetime

class DBHandler:
    def __init__(self, db_path='email_archiver.sqlite'):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes the database schema if it doesn't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE NOT NULL,
                    provider TEXT NOT NULL,
                    subject TEXT,
                    sender TEXT,
                    recipients TEXT,
                    received_at DATETIME,
                    file_path TEXT,
                    classification TEXT,
                    extraction TEXT,
                    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Index for fast lookups by message_id
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_id ON emails (message_id)')
            
            # Checkpoints table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkpoints (
                    provider TEXT PRIMARY KEY,
                    last_sync_value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logging.info(f"Database initialized at {self.db_path}")

    def email_exists(self, message_id):
        """Checks if an email with the given message_id already exists in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM emails WHERE message_id = ?', (message_id,))
            return cursor.fetchone() is not None

    def record_email(self, message_id, provider, subject, sender, recipients, received_at, file_path, classification=None, extraction=None):
        """Records a processed email in the database."""
        # Convert objects to JSON strings if they are dicts/lists
        class_str = json.dumps(classification) if classification else None
        ext_str = json.dumps(extraction) if extraction else None
        
        # Handle datetime objects
        if isinstance(received_at, datetime):
            received_at = received_at.isoformat()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO emails (
                        message_id, provider, subject, sender, recipients, 
                        received_at, file_path, classification, extraction
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    message_id, provider, subject, sender, recipients,
                    received_at, file_path, class_str, ext_str
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            logging.warning(f"Email {message_id} already exists in database (IntegrityError).")
            return False
        except Exception as e:
            logging.error(f"Failed to record email {message_id} in database: {e}")
            return False

    def get_stats(self):
        """Returns aggregate statistics for the dashboard."""
        stats = {
            "total_archived": 0,
            "classified": 0,
            "extracted": 0,
            "categories": {}
        }
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Basic counts
                cursor.execute('SELECT COUNT(*) as total FROM emails')
                stats["total_archived"] = cursor.fetchone()["total"]
                
                cursor.execute('SELECT COUNT(*) as total FROM emails WHERE classification IS NOT NULL')
                stats["classified"] = cursor.fetchone()["total"]
                
                cursor.execute('SELECT COUNT(*) as total FROM emails WHERE extraction IS NOT NULL')
                stats["extracted"] = cursor.fetchone()["total"]
                
                # Category breakdown
                cursor.execute('SELECT classification FROM emails WHERE classification IS NOT NULL')
                for row in cursor.fetchall():
                    try:
                        data = json.loads(row["classification"])
                        cat = data.get("category", "unknown")
                        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
                    except:
                        continue
        except Exception as e:
            logging.error(f"Error fetching stats from DB: {e}")
        return stats

    def get_emails(self, limit=50, offset=0):
        """Returns a list of emails for the dashboard."""
        emails = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM emails 
                    ORDER BY received_at DESC 
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
                
                for row in cursor.fetchall():
                    email_data = dict(row)
                    # Parse JSON fields
                    if email_data["classification"]:
                        email_data["classification"] = json.loads(email_data["classification"])
                    if email_data["extraction"]:
                        email_data["extraction"] = json.loads(email_data["extraction"])
                    emails.append(email_data)
        except Exception as e:
            logging.error(f"Error fetching emails from DB: {e}")
        return emails

    def get_checkpoint(self, provider):
        """Returns the last sync value for a provider."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT last_sync_value FROM checkpoints WHERE provider = ?', (provider,))
                row = cursor.fetchone()
                return row["last_sync_value"] if row else None
        except Exception as e:
            logging.error(f"Error getting checkpoint for {provider}: {e}")
            return None

    def save_checkpoint(self, provider, value):
        """Saves a sync checkpoint value for a provider."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO checkpoints (provider, last_sync_value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(provider) DO UPDATE SET 
                        last_sync_value = excluded.last_sync_value,
                        updated_at = CURRENT_TIMESTAMP
                ''', (provider, str(value)))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error saving checkpoint for {provider}: {e}")
            return False
