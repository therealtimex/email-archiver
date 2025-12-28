import sqlite3
import json
import os
import logging
from datetime import datetime

from email_archiver.core.paths import get_db_path

class DBHandler:
    def __init__(self, db_path=None):
        self.db_path = db_path if db_path else str(get_db_path())
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

            # Run migration for existing databases (adds AI status columns)
            self._migrate_ai_status_columns()

            # Create AI status index AFTER migration ensures columns exist
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_status ON emails (ai_classification_status, ai_extraction_status)')
            conn.commit()

    def _migrate_ai_status_columns(self):
        """Adds AI status columns to existing databases that don't have them."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Check if columns already exist
                cursor.execute("PRAGMA table_info(emails)")
                columns = [row[1] for row in cursor.fetchall()]

                # Add missing columns
                if 'ai_classification_status' not in columns:
                    cursor.execute('ALTER TABLE emails ADD COLUMN ai_classification_status TEXT')
                    logging.info("Added ai_classification_status column to database")

                if 'ai_extraction_status' not in columns:
                    cursor.execute('ALTER TABLE emails ADD COLUMN ai_extraction_status TEXT')
                    logging.info("Added ai_extraction_status column to database")

                if 'ai_processing_error' not in columns:
                    cursor.execute('ALTER TABLE emails ADD COLUMN ai_processing_error TEXT')
                    logging.info("Added ai_processing_error column to database")

                if 'ai_processed_at' not in columns:
                    cursor.execute('ALTER TABLE emails ADD COLUMN ai_processed_at DATETIME')
                    logging.info("Added ai_processed_at column to database")

                conn.commit()
        except Exception as e:
            logging.error(f"Error during AI status column migration: {e}")

    def email_exists(self, message_id):
        """Checks if an email with the given message_id already exists in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM emails WHERE message_id = ?', (message_id,))
            return cursor.fetchone() is not None

    def record_email(self, message_id, provider, subject, sender, recipients, received_at, file_path,
                     classification=None, extraction=None,
                     ai_classification_status=None, ai_extraction_status=None,
                     ai_processing_error=None):
        """
        Records a processed email in the database.

        Args:
            ai_classification_status: 'success', 'failed', 'skipped', 'disabled', or None
            ai_extraction_status: 'success', 'failed', 'skipped', 'disabled', or None
            ai_processing_error: Error message if AI processing failed
        """
        # Convert objects to JSON strings if they are dicts/lists
        class_str = json.dumps(classification) if classification else None
        ext_str = json.dumps(extraction) if extraction else None

        # Handle datetime objects
        if isinstance(received_at, datetime):
            received_at = received_at.isoformat()

        # Set AI processed timestamp if any AI processing was attempted
        ai_processed_at = datetime.now().isoformat() if (ai_classification_status or ai_extraction_status) else None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO emails (
                        message_id, provider, subject, sender, recipients,
                        received_at, file_path, classification, extraction,
                        ai_classification_status, ai_extraction_status,
                        ai_processing_error, ai_processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    message_id, provider, subject, sender, recipients,
                    received_at, file_path, class_str, ext_str,
                    ai_classification_status, ai_extraction_status,
                    ai_processing_error, ai_processed_at
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            logging.info(f"Email {message_id} already exists. Updating its metadata and file path.")
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE emails SET
                            subject = ?, sender = ?, recipients = ?,
                            received_at = ?, file_path = ?,
                            classification = ?, extraction = ?,
                            ai_classification_status = ?, ai_extraction_status = ?,
                            ai_processing_error = ?, ai_processed_at = ?,
                            processed_at = CURRENT_TIMESTAMP
                        WHERE message_id = ?
                    ''', (
                        subject, sender, recipients, received_at,
                        file_path, class_str, ext_str,
                        ai_classification_status, ai_extraction_status,
                        ai_processing_error, ai_processed_at,
                        message_id
                    ))
                    conn.commit()
                    return True
            except Exception as e:
                logging.error(f"Failed to update email {message_id} in database: {e}")
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

    def get_emails(self, limit=50, offset=0, search_query=None):
        """Returns a list of emails for the dashboard, with optional search."""
        emails = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = "SELECT * FROM emails"
                params = []
                
                if search_query:
                    query += " WHERE subject LIKE ? OR sender LIKE ? OR recipients LIKE ? OR classification LIKE ? OR extraction LIKE ?"
                    search_param = f"%{search_query}%"
                    params.extend([search_param] * 5)
                
                query += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                cursor.execute(query, params)
                
                for row in cursor.fetchall():
                    email_data = dict(row)
                    # Parse JSON fields
                    if email_data["classification"]:
                        try:
                            email_data["classification"] = json.loads(email_data["classification"])
                        except: pass
                    if email_data["extraction"]:
                        try:
                            email_data["extraction"] = json.loads(email_data["extraction"])
                        except: pass
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

    def get_email(self, message_id):
        """Retrieves a specific email record by its message_id."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM emails WHERE message_id = ?', (message_id,))
                row = cursor.fetchone()
                if row:
                    email_data = dict(row)
                    if email_data["classification"]:
                        try: email_data["classification"] = json.loads(email_data["classification"])
                        except: pass
                    if email_data["extraction"]:
                        try: email_data["extraction"] = json.loads(email_data["extraction"])
                        except: pass
                    return email_data
        except Exception as e:
            logging.error(f"Error fetching email {message_id}: {e}")
        return None

    def update_email_path(self, message_id, new_path):
        """Updates the stored file path for an email."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE emails SET file_path = ? WHERE message_id = ?', (new_path, message_id))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error updating path for email {message_id}: {e}")
            return False

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

    def get_emails_by_ai_status(self, status='failed', limit=100):
        """
        Returns emails that match the specified AI processing status.

        Args:
            status: 'failed', 'skipped', 'disabled', or 'success'
            limit: Maximum number of emails to return

        Returns:
            List of email records with failed/skipped AI processing
        """
        emails = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = '''
                    SELECT * FROM emails
                    WHERE ai_classification_status = ? OR ai_extraction_status = ?
                    ORDER BY received_at DESC
                    LIMIT ?
                '''
                cursor.execute(query, (status, status, limit))

                for row in cursor.fetchall():
                    email_data = dict(row)
                    # Parse JSON fields
                    if email_data["classification"]:
                        try:
                            email_data["classification"] = json.loads(email_data["classification"])
                        except:
                            pass
                    if email_data["extraction"]:
                        try:
                            email_data["extraction"] = json.loads(email_data["extraction"])
                        except:
                            pass
                    emails.append(email_data)
        except Exception as e:
            logging.error(f"Error fetching emails by AI status '{status}': {e}")
        return emails

    def get_ai_stats(self):
        """
        Returns statistics about AI processing success/failure rates.

        Returns:
            Dict with AI processing statistics
        """
        stats = {
            'classification': {'success': 0, 'failed': 0, 'skipped': 0, 'disabled': 0, 'total': 0},
            'extraction': {'success': 0, 'failed': 0, 'skipped': 0, 'disabled': 0, 'total': 0}
        }
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Classification stats
                cursor.execute('''
                    SELECT ai_classification_status, COUNT(*) as count
                    FROM emails
                    WHERE ai_classification_status IS NOT NULL
                    GROUP BY ai_classification_status
                ''')
                for row in cursor.fetchall():
                    status, count = row
                    if status in stats['classification']:
                        stats['classification'][status] = count
                        stats['classification']['total'] += count

                # Extraction stats
                cursor.execute('''
                    SELECT ai_extraction_status, COUNT(*) as count
                    FROM emails
                    WHERE ai_extraction_status IS NOT NULL
                    GROUP BY ai_extraction_status
                ''')
                for row in cursor.fetchall():
                    status, count = row
                    if status in stats['extraction']:
                        stats['extraction'][status] = count
                        stats['extraction']['total'] += count

        except Exception as e:
            logging.error(f"Error fetching AI statistics: {e}")
        return stats
