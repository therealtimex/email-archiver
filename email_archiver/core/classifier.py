import json
import logging
from typing import Dict, Optional, List
from email.message import Message
import openai
from email_archiver.core.paths import get_llm_config
from email_archiver.core.llm_error_handler import SmartLLMHandler

class EmailClassifier:
    """
    Classifies emails using OpenAI's GPT models.
    """
    
    DEFAULT_CATEGORIES = [
        "important",
        "promotional", 
        "transactional",
        "social",
        "newsletter",
        "spam"
    ]
    
    def __init__(self, config: dict):
        self.config = config.get('classification', {})
        self.enabled = self.config.get('enabled', False)
        self.error_handler = SmartLLMHandler()

        if not self.enabled:
            return

        # 1. Standardized config from environment/defaults
        std_config = get_llm_config()

        # 2. Local/Specific overrides (config file or CLI)
        self.base_url = self.config.get('base_url') or std_config.get('base_url')

        # Resolve API Key: CLI/Config > Env (LLM_API_KEY > OPENAI_API_KEY)
        api_key = self.config.get('api_key') or self.config.get('openai_api_key') or std_config.get('api_key')

        # Infer if we're using a local provider that doesn't need an API key
        is_openai = not self.base_url or "openai.com" in self.base_url
        if not is_openai and not api_key:
            logging.debug("Local LLM detected (via custom base_url), using dummy API key.")
            api_key = "not-needed"

        if not api_key:
            logging.warning("Classification enabled but no API key provided. Disabling classification.")
            self.enabled = False
            return

        self.model = self.config.get('model') or std_config.get('model', 'gpt-4o-mini')
        self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url, timeout=60.0)

        self.categories = self.config.get('categories', self.DEFAULT_CATEGORIES)
        self.skip_categories = self.config.get('skip_categories', [])

        logging.info(f"Email classification enabled with model: {self.model} (Endpoint: {self.base_url or 'OpenAI'})")
    
    def check_health(self) -> bool:
        """
        Quick health check to test LLM connectivity before processing.
        Returns True if healthy, False otherwise.
        """
        if not self.enabled:
            return True

        try:
            logging.info("Testing LLM connectivity...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                timeout=5.0
            )
            logging.info(f"✅ LLM is reachable ({self.base_url or 'OpenAI'})")
            return True
        except Exception as e:
            logging.error(f"❌ LLM health check failed: {e}")
            should_disable = self.error_handler.handle_error(e, "health check")
            if should_disable:
                logging.warning("AI classification will be disabled for this sync.")
                self.enabled = False
            return False

    def should_skip(self, classification: Dict) -> bool:
        """
        Determines if an email should be skipped based on its classification.
        """
        if not self.enabled:
            return False

        category = classification.get('category', '').lower()
        return category in [c.lower() for c in self.skip_categories]

    def get_stats(self) -> dict:
        """Get error handler statistics"""
        return self.error_handler.get_stats_summary()

    def format_stats(self) -> str:
        """Format statistics as human-readable string"""
        return self.error_handler.format_stats_summary()
    
    def classify_email(self, email_obj: Message, subject: str = None, sender: str = None, to: str = None, cc: str = None) -> Optional[Dict]:
        """
        Classifies an email using OpenAI.
        Returns classification metadata or None if classification is disabled.
        """
        if not self.enabled or self.error_handler.is_circuit_open():
            return None

        self.error_handler.record_attempt()

        try:
            from email_archiver.core.utils import decode_mime_header
            # Extract email content
            subject = subject or decode_mime_header(email_obj.get('subject', 'No Subject'))
            sender = sender or decode_mime_header(email_obj.get('from', 'Unknown'))
            to = to or decode_mime_header(email_obj.get('to', ''))
            cc = cc or decode_mime_header(email_obj.get('cc', ''))
            
            # Extract useful headers for context
            headers = {
                "X-Priority": email_obj.get('X-Priority'),
                "Importance": email_obj.get('Importance'),
                "List-Unsubscribe": email_obj.get('List-Unsubscribe')
            }
            
            # Get email body (prefer plain text)
            body = self._extract_body(email_obj)
            
            # Use ContentCleaner
            from email_archiver.core.content_cleaner import ContentCleaner
            body = ContentCleaner.clean_email_body(body)
            
            # Truncate body to avoid token limits (keep first 1500 chars - slightly more than before due to cleaning)
            body_preview = body[:1500] if body else ""
            
            # Create optimized classification prompt
            prompt = self._create_classification_prompt(subject, sender, to, cc, body_preview, headers)
            
            # Prepare OpenAI call arguments
            completion_args = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are an email classifier."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
            }

            # Only add response_format if it's likely OpenAI
            is_openai = not self.base_url or "openai.com" in self.base_url
            if is_openai:
                completion_args["response_format"] = {"type": "json_object"}

            # Call OpenAI
            response = self.client.chat.completions.create(**completion_args)
            
            # Parse response
            classification_text = response.choices[0].message.content
            classification = self._parse_json_response(classification_text)
            
            if not classification:
                logging.error(f"Failed to parse classification JSON. Raw response: {classification_text[:500]}...")
                return None

            # Record success
            self.error_handler.record_success()
            logging.info(f"Classified email '{subject[:50]}...' as '{classification.get('category')}'")

            return classification

        except Exception as e:
            # Use smart error handler
            context = f"email '{subject[:50] if subject else 'unknown'}...'"
            should_disable = self.error_handler.handle_error(e, context)

            if should_disable:
                logging.error("❌ Disabling classification for remaining emails in this sync")
                self.enabled = False

            return None
    
    def _extract_body(self, email_obj: Message) -> str:
        """
        Extracts email body text, preferring plain text but falling back to HTML.
        """
        body = ""
        html_body = ""
        
        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except:
                        pass
                elif content_type == "text/html":
                    try:
                        html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except:
                        pass
        else:
            try:
                payload = email_obj.get_payload(decode=True).decode('utf-8', errors='ignore')
                if email_obj.get_content_type() == "text/html":
                    html_body = payload
                else:
                    body = payload
            except:
                pass
        
        # Determine strict preference
        final_body = body if body.strip() else html_body
        return final_body.strip()
    
    def _create_classification_prompt(self, subject: str, sender: str, to: str, cc: str, body_preview: str, headers: Dict) -> str:
        """
        Creates the classification prompt for OpenAI.
        """
        categories_str = ", ".join(self.categories)
        
        # Additional signals from headers
        signals = []
        if headers.get('List-Unsubscribe'):
            signals.append("- Contains List-Unsubscribe header (Likely Newsletter/Promotional)")
        if headers.get('X-Priority') or headers.get('Importance'):
            signals.append(f"- Priority/Importance level: {headers.get('X-Priority') or headers.get('Importance')}")

        signals_str = "\n".join(signals) if signals else "- None"
        
        prompt = f"""EMAIL CONTENT:
Subject: {subject}
From: {sender}
To: {to}
Cc: {cc}
Body:
{body_preview}

METADATA SIGNALS:
{signals_str}

INSTRUCTIONS:
Classify this email into ONE category: {categories_str}.

Definitions:
- "important": Work-related, urgent, from known contacts
- "promotional": Marketing, sales, discounts
- "transactional": Receipts, shipping, confirmations
- "social": LinkedIn, friends, social updates
- "newsletter": Subscribed content
- "spam": Junk, suspicious

REQUIRED OUTPUT FORMAT (JSON):
{{
  "category": "category_name",
  "confidence": 0.0-1.0,
  "reasoning": "short explanation",
  "is_important": true/false,
  "tags": ["tag1", "tag2"]
}}

Return ONLY JSON."""
        return prompt

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
            # Look for ```json ... ``` or just ``` ... ```
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
