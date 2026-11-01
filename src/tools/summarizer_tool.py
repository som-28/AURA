"""Summarize content with the configured LLM, or use an extractive fallback."""
from typing import Tuple, List
import re
import os
from src.utils.llm_client import get_llm_client


def _simple_extractive(text: str, max_sentences: int = 5) -> str:
    # naive sentence split
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    return "\n- " + "\n- ".join(sentences[:max_sentences])


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    logs = []
    mode = args.get("mode", "bullet")
    max_sentences = int(args.get("max_sentences", 5))

    # Keep source boundaries so the model can distinguish evidence and cite it.
    texts = []
    evidence_texts = []
    for v in context.values():
        if isinstance(v, dict) and v.get("pages"):
            for p in v.get("pages", []):
                if p.get("text"):
                    evidence_texts.append(str(p.get("text", "")))
                    texts.append(f"Source: {p.get('title') or p.get('url') or 'Page'}\nURL: {p.get('url', '')}\nEvidence: {p.get('text', '')}")
        if isinstance(v, dict) and v.get("results"):
            for r in v.get("results", []):
                if r.get("snippet"):
                    evidence_texts.append(str(r.get("snippet", "")))
                    texts.append(f"Source: {r.get('title') or r.get('source') or 'Search result'}\nURL: {r.get('url', '')}\nEvidence: {r.get('snippet', '')}")

    joined = "\n\n".join([t for t in texts if t])
    if not joined:
        logs.append("No content found to summarise")
        return logs, {"summary": "(no content)"}

    try:
        if os.getenv("SUMMARY_MODE", "extractive").strip().lower() == "extractive":
            summary = _simple_extractive("\n\n".join(evidence_texts), max_sentences=max_sentences)
            logs.append("Generated fast extractive summary (set SUMMARY_MODE=llm for model summaries)")
            return logs, {"summary": summary}
        configured = get_llm_client()
        if configured:
            client, model, provider_name = configured
            prompt = (
                f"Summarize these sources in at most {max_sentences} concise bullets. "
                "Use only facts explicitly stated in the source evidence. Never infer salary, location, seniority, "
                "availability, or eligibility. Put the source title in brackets after each claim. If a detail is "
                "not stated, omit it.\n\n" + joined[:5000]
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            summary = (resp.choices[0].message.content or "").strip()
            if summary:
                logs.append(f"Generated summary using {provider_name}")
                return logs, {"summary": summary}
    except Exception as e:
        logs.append(f"LLM summarization failed: {e}")

    # fallback simple extractive summarizer
    summary = _simple_extractive("\n\n".join(evidence_texts), max_sentences=max_sentences)
    logs.append("Generated extractive summary (fallback)")
    return logs, {"summary": summary}
