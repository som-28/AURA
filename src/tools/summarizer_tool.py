"""Summarizer tool. Uses OpenAI if configured, otherwise falls back to a simple extractive summarizer."""
from typing import Tuple, List
import os
import re


def _simple_extractive(text: str, max_sentences: int = 5) -> str:
    # naive sentence split
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    return "\n- " + "\n- ".join(sentences[:max_sentences])


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    logs = []
    mode = args.get("mode", "bullet")
    max_sentences = int(args.get("max_sentences", 5))

    # collect text from context (scrape outputs first, then search snippets)
    texts = []
    for v in context.values():
        if isinstance(v, dict) and v.get("pages"):
            for p in v.get("pages", []):
                texts.append(p.get("text", ""))
        if isinstance(v, dict) and v.get("results"):
            texts.extend([r.get("snippet", "") for r in v.get("results")])

    joined = "\n\n".join([t for t in texts if t])
    if not joined:
        logs.append("No content found to summarise")
        return logs, {"summary": "(no content)"}

    # If OpenAI is configured, call completion using modern v1+ client
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            prompt = f"Summarize the following text in {max_sentences} bullets:\n\n{joined[:3000]}"
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            summary = resp.choices[0].message.content.strip()
            logs.append("Generated summary using OpenAI")
            return logs, {"summary": summary}
        except Exception as e:
            logs.append(f"OpenAI summarization failed: {e}")

    # fallback simple extractive summarizer
    summary = _simple_extractive(joined, max_sentences=max_sentences)
    logs.append("Generated extractive summary (fallback)")
    return logs, {"summary": summary}
