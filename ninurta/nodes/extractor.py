"""Nodes definition for Ninurta LangGraph."""

from __future__ import annotations

import json
import re

from ninurta.llm.factory import get_llm
from ninurta.prompts.registry import prompt_registry
from ninurta.schemas.job_description import JobDescription
from ninurta.state import State
from ninurta.utils.logger import get_logger

log = get_logger(__name__)




def extractor_node(state: State) -> dict:
    """First node: extract structured JSON from the job description text."""
    jd_text = state.get("jd_text", "")
    if not jd_text:
        return {"error": "No job description provided."}

    # Retrieve prompt from registry
    messages = prompt_registry.get("job_extractor", jd_text=jd_text)
    
    # Execute LLM
    llm = get_llm()  # Uses config.yaml for default model
    log.info("Sending to [bold]%s[/bold] via LangGraph...", llm.model_id)
    
    try:
        result = llm.complete(messages, max_tokens=4096, thinking=False)
        raw = result.text

        # Parse JSON
        raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw_clean = re.sub(r"```(?:json)?", "", raw_clean).strip()
        raw_clean = raw_clean.replace("```", "").strip()
        
        match = re.search(r"\{.*\}", raw_clean, re.DOTALL)
        if not match:
            return {"error": f"Model returned no JSON object. Output: {raw[:100]}..."}
            
        data = json.loads(match.group())
        parsed_job = JobDescription(**data)
        
        return {"parsed_job": parsed_job, "error": None}
        
    except Exception as e:
        log.error("Extraction failed: %s", e)
        return {"error": str(e), "parsed_job": None}