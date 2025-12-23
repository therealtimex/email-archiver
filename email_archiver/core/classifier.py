import json
import logging
from typing import Dict, Optional, List
from email.message import Message
import openai

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
        
        if not self.enabled:
            return
            
        # Provider configuration
        self.provider = self.config.get('provider', 'openai').lower()
        self.base_url = self.config.get('base_url')
        api_key = self.config.get('api_key') or self.config.get('openai_api_key')
        
        # Default base URLs for common local providers if not specified
        if not self.base_url:
            if self.provider == 'ollama':
                self.base_url = "http://localhost:11434/v1"
            elif self.provider == 'lm_studio':
                self.base_url = "http://localhost:1234/v1"
            elif self.provider == 'local':
                self.base_url = "http://localhost:8000/v1"

        # Local providers often don't need an API key
        if self.provider != 'openai' and not api_key:
            api_key = "not-needed"

        if not api_key:
            logging.warning("Classification enabled but no API key provided. Disabling classification.")
            self.enabled = False
            return
            
        self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url)
        self.model = self.config.get('model', 'gpt-4o-mini')
        self.categories = self.config.get('categories', self.DEFAULT_CATEGORIES)
        self.skip_categories = self.config.get('skip_categories', [])
        
        logging.info(f"Email classification enabled with provider: {self.provider}, model: {self.model}")
    
    def should_skip(self, classification: Dict) -> bool:
        """
        Determines if an email should be skipped based on its classification.
        """
        if not self.enabled:
            return False
            
        category = classification.get('category', '').lower()
        return category in [c.lower() for c in self.skip_categories]
    
    def classify_email(self, email_obj: Message, subject: str = None, sender: str = None, to: str = None, cc: str = None) -> Optional[Dict]:
        """
        Classifies an email using OpenAI.
        Returns classification metadata or None if classification is disabled.
        """
        if not self.enabled:
            return None
        
        try:
            # Extract email content
            subject = subject or email_obj.get('subject', 'No Subject')
            sender = sender or email_obj.get('from', 'Unknown')
            to = to or email_obj.get('to', '')
            cc = cc or email_obj.get('cc', '')
            
            # Get email body (prefer plain text)
            body = self._extract_body(email_obj)
            
            # Truncate body to avoid token limits (keep first 1000 chars)
            body_preview = body[:1000] if body else ""
            
            # Create classification prompt
            prompt = self._create_classification_prompt(subject, sender, to, cc, body_preview)
            
            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an email classification assistant. Classify emails accurately and provide reasoning."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent classifications
                response_format={"type": "json_object"}
            )
            
            # Parse response
            classification_text = response.choices[0].message.content
            classification = json.loads(classification_text)
            
            logging.info(f"Classified email '{subject[:50]}...' as '{classification.get('category')}'")
            
            return classification
            
        except Exception as e:
            logging.error(f"Error classifying email: {e}")
            return None
    
    def _extract_body(self, email_obj: Message) -> str:
        """
        Extracts email body text.
        """
        body = ""
        
        if email_obj.is_multipart():
            for part in email_obj.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except:
                        pass
        else:
            try:
                body = email_obj.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                pass
        
        return body.strip()
    
    def _create_classification_prompt(self, subject: str, sender: str, to: str, cc: str, body_preview: str) -> str:
        """
        Creates the classification prompt for OpenAI.
        """
        categories_str = ", ".join(self.categories)
        
        prompt = f"""Classify the following email into one of these categories: {categories_str}

Email Details:
- Subject: {subject}
- From: {sender}
- To: {to}
- Cc: {cc}
- Body Preview: {body_preview}

Provide your response as JSON with the following structure:
{{
  "category": "one of the categories",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "is_important": true/false,
  "tags": ["tag1", "tag2", "tag3"]
}}

Guidelines:
- "important": Work-related, urgent, from known contacts, requires action
- "promotional": Marketing, sales, offers, discounts
- "transactional": Receipts, confirmations, shipping notifications
- "social": Social media notifications, friend requests
- "newsletter": Subscribed content, regular updates
- "spam": Unsolicited, suspicious, phishing attempts

Be accurate and concise."""
        
        return prompt
