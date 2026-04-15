#!/usr/bin/env python3
import sys, json, os
from PyQt6.QtCore import QSettings

# Ensure repository root is on sys.path so `py_editor` can be imported when run from tools/
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from py_editor.ui.panels.ai_chat_panel import AIClient
except Exception as e:
    print("Failed to import AIClient:", e)
    raise

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

    print("Testing AI connection with provider/endpoint:", provider_or_endpoint)
    client = AIClient(provider_or_endpoint, api_key, model=model)
    system_prompt = settings.value("system_prompt", "") or None
    try:
        resp = client.send_message("Hello from NodeCanvas connection test", mode="Assistant", timeout=30, system_prompt=system_prompt)
        try:
            from py_editor.ui.panels.ai_chat_panel import sanitize_assistant_text
            resp = sanitize_assistant_text(resp)
        except Exception:
            pass
        print("OK:", resp)
        return 0
    except Exception as e:
        print("ERROR:", str(e))
        return 2

if __name__ == "__main__":
    sys.exit(main())
