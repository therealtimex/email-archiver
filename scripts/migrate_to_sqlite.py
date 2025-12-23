import json
import os
import logging
from email_archiver.core.db_handler import DBHandler

def migrate_jsonl_to_sqlite(jsonl_path='email_metadata.jsonl', db_path='email_archiver.sqlite'):
    if not os.path.exists(jsonl_path):
        print(f"No metadata file found at {jsonl_path}. Skipping migration.")
        return

    db = DBHandler(db_path)
    count = 0
    skipped = 0
    
    print(f"Migrating data from {jsonl_path} to {db_path}...")
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                message_id = data.get("message_id")
                if not message_id:
                    continue
                
                # Check if already exists to avoid duplicates
                if db.email_exists(message_id):
                    skipped += 1
                    continue
                
                # record_email(self, message_id, provider, subject, sender, recipients, received_at, file_path, classification=None, extraction=None)
                success = db.record_email(
                    message_id=message_id,
                    provider='unknown', # We don't have provider in old JSONL
                    subject=data.get("subject"),
                    sender=data.get("from"),
                    recipients=data.get("to"),
                    received_at=data.get("date"),
                    file_path=data.get("file_path"),
                    classification=data.get("classification"),
                    extraction=data.get("extraction")
                )
                if success:
                    count += 1
            except Exception as e:
                print(f"Error migrating line: {e}")

    print(f"Migration complete. Imported {count} records, skipped {skipped} duplicates.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_jsonl_to_sqlite()
