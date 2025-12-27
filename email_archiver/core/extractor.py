import json
import logging
from typing import Dict, Optional, List
from email.message import Message
import openai
from email_archiver.core.paths import get_llm_config

class EmailExtractor:
    """
    Extracts structured information from emails using LLMs.
    """
    
    def __init__(self, config: dict):
        self.config = config.get('extraction', {})
        self.enabled = self.config.get('enabled', False)
        
        if not self.enabled:
            return
            
        # 1. Standardized config from environment/defaults
        std_config = get_llm_config()
        
        # 2. Local/Specific overrides (config file or CLI)
        llm_config = config.get('classification', {})
        self.provider = self.config.get('provider', llm_config.get('provider', 'openai')).lower()
        
        # Resolve Base URL: CLI/Config(Extraction) > CLI/Config(Classification) > Env (LLM_BASE_URL)
        self.base_url = self.config.get('base_url') or llm_config.get('base_url') or std_config.get('base_url')
        
        # Resolve API Key
        api_key = self.config.get('api_key') or llm_config.get('api_key') or llm_config.get('openai_api_key') or std_config.get('api_key')
        
        if self.provider != 'openai' and not api_key:
            api_key = "not-needed"

        if not api_key:
            logging.warning("Extraction enabled but no API key provided. Disabling extraction.")
            self.enabled = False
            return
            
        self.model = self.config.get('model') or llm_config.get('model') or std_config.get('model', 'gpt-4o-mini')
        self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url)
        
        logging.info(f"Advanced extraction enabled with provider: {self.provider if self.base_url else 'openai'}, model: {self.model}")
    
    def extract_metadata(self, email_obj: Message, subject: str = None, sender: str = None) -> Optional[Dict]:
        """
        Extracts structured metadata from the email.
        """
        if not self.enabled:
            return None
            
        try:
            body = self._extract_body(email_obj)
            if not body and not subject:
                return None
                
            subject = subject or email_obj.get('subject', 'No Subject')
            sender = sender or email_obj.get('from', 'Unknown')
            
            # Truncate body for prompt
            body_preview = body[:2000] if body else ""
            
            prompt = self._create_extraction_prompt(subject, sender, body_preview)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting structured information from emails."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            extraction = json.loads(response.choices[0].message.content)
            logging.info(f"Extracted metadata for '{subject[:50]}...'")
            return extraction
            
        except Exception as e:
            logging.error(f"Error extracting metadata: {e}")
            return None

    def _extract_body(self, email_obj: Message) -> str:
        body = ""
        if email_obj.is_multipart():
            for part in email_obj.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except: pass
        else:
            try:
                body = email_obj.get_payload(decode=True).decode('utf-8', errors='ignore')
            except: pass
        return body.strip()

    def _create_extraction_prompt(self, subject: str, sender: str, body_preview: str) -> str:
        return f"""Extract structured information from this email.

Details:
- Subject: {subject}
- From: {sender}
- Body: {body_preview}

Response MUST be a JSON object with this structure:
{{
  "summary": "one sentence summary",
  "entities": {{
    "organizations": [],
    "people": [],
    "dates": [],
    "monetary_values": []
  }},
  "structured_data": {{
      "type": "invoice/receipt/meeting/newsletter/other",
      "fields": {{}}
  }},
  "action_items": []
}}

Guidelines:
- Summary: High-level TL;DR.
- Entities: List specific organizations, people, dates, and amounts found.
- Structured Data: If it's an invoice, include 'amount', 'due_date', 'invoice_number'. If a meeting, include 'time', 'location', 'attendees'. 
- Action Items: Extract specific tasks or deadlines required of the recipient."""
