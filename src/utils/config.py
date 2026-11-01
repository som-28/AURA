"""Configuration helpers."""
from dotenv import load_dotenv
import os


def load_config():
    load_dotenv()
    cfg = {
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "openai"),
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        "LLM_REQUEST_TIMEOUT": os.getenv("LLM_REQUEST_TIMEOUT", "120"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "SMTP_HOST": os.getenv("SMTP_HOST"),
        "SMTP_PORT": os.getenv("SMTP_PORT"),
        "SMTP_USER": os.getenv("SMTP_USER"),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD"),
        "SMTP_FROM": os.getenv("SMTP_FROM"),
        "DEFAULT_FROM": os.getenv("DEFAULT_FROM"),
    }
    return cfg
