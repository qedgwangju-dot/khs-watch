from __future__ import annotations

import json
import os
import urllib.request
from models import Document


def analyze_if_configured(documents: list[Document]) -> dict:
    """Called only after the collector has persisted at least one new document."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "OPENAI_API_KEY 미설정"}
    prompt = {
        "task": "새 공식 문서만 분석하여 SVIC 82호/83호 투자, 금액, 지분, PoC, 인증, 양산, 실패 사실을 JSON으로 추출하라. 근거 없는 추론은 하지 마라.",
        "documents": [
            {"url": d.url, "title": d.title, "published_at": d.published_at, "official": d.official, "text": d.body[:12000]}
            for d in documents
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps({"model": os.getenv("OPENAI_MODEL", "gpt-5"), "input": json.dumps(prompt, ensure_ascii=False)}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read())

