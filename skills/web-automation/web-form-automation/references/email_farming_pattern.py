#!/usr/bin/env python3
"""
Email farming pattern for registration abuse.
Generates sequential addresses a.bayov@domain.com, b.bayov@domain.com
All route to same catch-all Gmail inbox.
"""
import json, string
from pathlib import Path

class EmailGenerator:
    def __init__(self, tracker_path=None):
        self.tracker = Path(tracker_path or '/root/.hermes/antisecta_email_tracker.json')
        self._load()
    
    def _load(self):
        if self.tracker.exists():
            with open(self.tracker) as f:
                data = json.load(f)
                self.next_letter = data.get('next_letter', ord('a'))
                self.used = data.get('used_addresses', {})
                self.map = data.get('service_map', {})
        else:
            self.next_letter = ord('a')
            self.used = {}
            self.map = {}
    
    def _save(self):
        with open(self.tracker, 'w') as f:
            json.dump({
                'used_addresses': self.used,
                'next_letter': self.next_letter,
                'service_map': self.map
            }, f, indent=2)
    
    def generate_email(self, service_name):
        letter = chr(self.next_letter)
        email = f"{letter}.bayov@antisecta.com"
        self.used[f"{letter}.bayov"] = service_name
        self.map[service_name] = email
        self.next_letter += 1
        self._save()
        return email
    
    def get_service_email(self, service_name):
        return self.map.get(service_name)

if __name__ == '__main__':
    gen = EmailGenerator()
    print(gen.generate_email('example_service'))
