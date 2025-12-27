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
        
        # Resolve Base URL: CLI/Config(Extraction) > CLI/Config(Classification) > Env (LLM_BASE_URL)
        self.base_url = self.config.get('base_url') or llm_config.get('base_url') or std_config.get('base_url')
        
        # Resolve API Key
        api_key = self.config.get('api_key') or llm_config.get('api_key') or llm_config.get('openai_api_key') or std_config.get('api_key')
        
        # Infer if we're using a local provider that doesn't need an API key
        is_openai = not self.base_url or "openai.com" in self.base_url
        if not is_openai and not api_key:
            logging.debug("Local LLM detected (via custom base_url), using dummy API key.")
            api_key = "not-needed"

        if not api_key:
            logging.warning("Extraction enabled but no API key provided. Disabling extraction.")
            self.enabled = False
            return
            
        self.model = self.config.get('model') or llm_config.get('model') or std_config.get('model', 'gpt-4o-mini')
        self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url, timeout=60.0)
        
        logging.info(f"Advanced extraction enabled with model: {self.model} (Endpoint: {self.base_url or 'OpenAI'})")
    
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
            
            # Use ContentCleaner
            from email_archiver.core.content_cleaner import ContentCleaner
            body = ContentCleaner.clean_email_body(body)
            
            # Truncate body for prompt (2500 chars, cleaning helps fit more real content)
            body_preview = body[:2500] if body else ""
            
            prompt = self._create_extraction_prompt(subject, sender, body_preview)
            
            # Prepare call arguments
            completion_args = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a data extraction assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
            }

            # Only add response_format if it's likely OpenAI
            is_openai = not self.base_url or "openai.com" in self.base_url
            if is_openai:
                completion_args["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**completion_args)
            
            raw_content = response.choices[0].message.content
            extraction = self._parse_json_response(raw_content)
            
            if not extraction:
                logging.error(f"Failed to parse extraction JSON. Raw response: {raw_content[:500]}...")
                return None
            logging.info(f"Extracted metadata for '{subject[:50]}...'")
            return extraction
            
        except Exception as e:
            logging.error(f"Error extracting metadata: {e}")
            return None

    def _extract_body(self, email_obj: Message) -> str:
        body = ""
        html_body = ""
        
        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except: pass
                elif content_type == "text/html":
                    try:
                        html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except: pass
        else:
            try:
                payload = email_obj.get_payload(decode=True).decode('utf-8', errors='ignore')
                if email_obj.get_content_type() == "text/html":
                    html_body = payload
                else:
                    body = payload
            except: pass
            
        final_body = body if body.strip() else html_body
        return final_body.strip()

    def _create_extraction_prompt(self, subject: str, sender: str, body_preview: str) -> str:
        return f"""EMAIL CONTENT:
Subject: {subject}
From: {sender}
Body:
{body_preview}

INSTRUCTIONS:
Extract structured data from the email above.

Guidelines:
- Summary: High-level TL;DR (max 2 sentences).
- Entities: Specific organizations, people, dates, amounts.
- Structured Data: Identify type (Invoice/Meeting/etc) and key fields.
- Action Items: Tasks or deadlines for the recipient.

REQUIRED OUTPUT FORMAT (JSON):
{{
  "summary": "string",
  "entities": {{
    "organizations": ["org1"],
    "people": ["person1"],
    "dates": ["date1"],
    "monetary_values": ["$10.00"]
  }},
  "structured_data": {{
      "type": "invoice/meeting/other",
      "fields": {{ "key": "value" }}
  }},
  "action_items": ["task1", "task2"]
}}

Return ONLY JSON."""

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """
        Robustly parses JSON from LLM response, handling markdown blocks and extra text.
        """
        if not text:
            return None
            
        text = text.strip()
        
        def strip_comments(json_str):
            import re
            # Strip C-style comments (// ...) but be careful about URLs or strings
            # Simple approach: remove anything from // to end of line if not preceded by :
            return re.sub(r'(?<!:)\/\/.*$', '', json_str, flags=re.MULTILINE)

        # 1. Try direct parsing
        try:
            return json.loads(strip_comments(text))
        except json.JSONDecodeError:
            pass
            
        # 2. Try removing markdown code blocks
        if "```" in text:
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if json_match:
                try:
                    return json.loads(strip_comments(json_match.group(1).strip()))
                except json.JSONDecodeError:
                    pass
                    
        # 3. Last ditch effort: find anything between the first { and last }
        try:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                return json.loads(text[start:end+1])
        except (json.JSONDecodeError, ValueError):
            pass
            
        return None
