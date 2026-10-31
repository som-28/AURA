"""Configuration helpers."""
from dotenv import load_dotenv
import os


def load_config():
    load_dotenv()
    cfg = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "SMTP_HOST": os.getenv("SMTP_HOST"),
        "SMTP_PORT": os.getenv("SMTP_PORT"),
        "SMTP_USER": os.getenv("SMTP_USER"),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD"),
        "DEFAULT_FROM": os.getenv("DEFAULT_FROM"),
    }
    return cfg
