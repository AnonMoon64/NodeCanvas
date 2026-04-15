#!/usr/bin/env python3
import sys, os
from PyQt6.QtCore import QSettings

# Ensure repo root on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from py_editor.ui.panels.ai_chat_panel import AIClient

def main():
    settings = QSettings("NodeCanvas", "AI")
    provider = settings.value("provider", "") or ""
    endpoint = settings.value("endpoint", "") or ""
    api_key = settings.value("api_key", "") or ""
    openai_model = settings.value("openai_model", "gpt-3.5-turbo")
    mistral_model = settings.value("mistral_model", "devstral-2512")
    provider_or_endpoint = provider or endpoint or "OpenAI"
    model = None
    if provider_or_endpoint and provider_or_endpoint.lower() == "openai":
        model = openai_model
    elif provider_or_endpoint and provider_or_endpoint.lower() == "mistral":
        model = mistral_model

    system_prompt = settings.value("system_prompt", "") or None

    client = AIClient(provider_or_endpoint, api_key, model=model)

    question = "Do you know what you are and what this system is? and who I am?"
    try:
        resp = client.send_message(question, mode="Assistant", timeout=30, system_prompt=system_prompt)
        try:
            from py_editor.ui.panels.ai_chat_panel import sanitize_assistant_text
            resp = sanitize_assistant_text(resp)
        except Exception:
            pass
        print("RESPONSE:", resp)
        return 0
    except Exception as e:
        print("ERROR:", e)
        return 2

if __name__ == '__main__':
    sys.exit(main())
