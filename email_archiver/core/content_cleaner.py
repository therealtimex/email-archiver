import re

class ContentCleaner:
    """
    Utilities for cleaning and preparing email content for LLM processing.
    """

    @staticmethod
    def clean_email_body(text: str) -> str:
        """
        Cleans email body by removing noise, quoted replies, and footers.
        """
        if not text:
            return ""

        # 0. Lightweight HTML -> Markdown Conversion
        
        # Structure: <br>, <p> -> Newlines
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p.*?>', '', text, flags=re.IGNORECASE) # Open p tags just gone
        
        # Structure: Headers <h1>-<h6> -> # Title
        text = re.sub(r'<h[1-6].*?>(.*?)</h[1-6]>', r'\n# \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Structure: Lists <li> -> - Item
        text = re.sub(r'<li.*?>(.*?)</li>', r'\n- \1', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<ul.*?>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</ul>', '\n', text, flags=re.IGNORECASE)
        
        # Links: <a href="...">text</a> -> [text](href)
        # Note: Simple regex, might miss complex attrs, but covers 90% of cases
        text = re.sub(r'<a\s+(?:[^>]*?\s+)?href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Images: <img src="..." alt="..."> -> ![alt](src)
        text = re.sub(r'<img\s+(?:[^>]*?\s+)?src="([^"]*)"(?:[^>]*?\s+)?alt="([^"]*)"[^>]*>', r'![\2](\1)', text, flags=re.DOTALL | re.IGNORECASE)

        # Style/Script removal (strictly remove content)
        text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Final Strip of remaining tags
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Entity decoding (Basic)
        text = re.sub(r'&nbsp;', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'&amp;', '&', text, flags=re.IGNORECASE)
        text = re.sub(r'&lt;', '<', text, flags=re.IGNORECASE)
        text = re.sub(r'&gt;', '>', text, flags=re.IGNORECASE)
        text = re.sub(r'&quot;', '"', text, flags=re.IGNORECASE)
        text = re.sub(r'&#39;', "'", text, flags=re.IGNORECASE)

        lines = text.splitlines()
        cleaned_lines = []
        
        # Heuristics for reply headers
        reply_header_patterns = [
            r'^On .* wrote:$',
            r'^From: .*$',
            r'^Sent: .*$',
            r'^To: .*$',
            r'^Subject: .*$'
        ]

        # Heuristics for footers
        footer_patterns = [
            r'unsubscribe',
            r'privacy policy',
            r'terms of service',
            r'view in browser',
            r'copyright \d{4}'
        ]

        parsing_header = False
        
        for line in lines:
            line_stripped = line.strip()
            
            # 1. Skip strictly empty lines (keep some for formatting?)
            # We'll allow empty lines but collapse multiple later
            
            # 2. Quoted text removal (lines starting with >)
            if line_stripped.startswith('>'):
                continue
                
            # 3. Check for specific reply separators
            is_reply_header = False
            for pattern in reply_header_patterns:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    is_reply_header = True
                    break
            
            # If we hit a reply header, we might assume everything after is the previous thread
            # For now, let's just skip the header line itself to be safe, rather than truncating
            # everything, as sometimes it's inline.
            # ideally, if we see "On [date] [user] wrote:", we stop purely if we want just the NEW content.
            # But the prompt might benefit from context. Let's just strip standard noise.
            
            # For LLM optimization: We largely want the *core* message. 
            # If we see a classic reply header, let's stop if it looks like a full thread dump.
            if re.match(r'^On .* wrote:$', line_stripped, re.IGNORECASE):
                # Aggressive strategy: Stop here. The LLM usually only needs the latest context.
                # However, for 'meeting' extraction, thread context is useful.
                # Let's keep it simple: Just skip the line for now to reduce token spam, 
                # but maybe don't truncate fully unless user asks.
                # Re-reading plan: "Remove quoted reply chains."
                # Okay, let's truncate if we see the start of a reply block to save BIG tokens.
                break

            # 4. Footer removal (simple check on short lines)
            if len(line_stripped) < 100:
                is_footer = False
                for pattern in footer_patterns:
                    if re.search(pattern, line_stripped, re.IGNORECASE):
                        is_footer = True
                        break
                if is_footer:
                    continue

            # 5. URL Normalization (simplify long tracking links)
            # Find http/https links
            # This regex finds URLs and keeps them, but we could truncate query params?
            # For now, let's just leave them as-is to avoid breaking valid verification links.
            
            cleaned_lines.append(line)

        # Reassemble
        text = '\n'.join(cleaned_lines)
        
        # Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
