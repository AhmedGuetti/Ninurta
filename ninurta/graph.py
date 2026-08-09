"""LangGraph graph definitions for Ninurta.

Two independent pipelines share the same :class:`State`:

* ``extract_graph`` — START → extractor → END
  (job-description extraction; run via ``ninurta extract``)
* ``resume_graph`` — START → resume_reader → resume_validator →
  resume_reviewer → resume_saver → END
  (resume parse → LLM validate → user review → save to DB;
  run via ``ninurta resume``)

``graph`` is kept as an alias for ``extract_graph`` for backward compatibility.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from ninurta.state import State
from ninurta.nodes.extractor import extractor_node
from ninurta.nodes.resume_reader import resume_reader_node
from ninurta.nodes.resume_validator import resume_validator_node
from ninurta.nodes.resume_reviewer import resume_reviewer_node
from ninurta.nodes.resume_saver import resume_saver_node


# ---------------------------------------------------------------------------
# Extract graph — job-description extraction
# ---------------------------------------------------------------------------
extract_builder = StateGraph(State)
extract_builder.add_node("extractor", extractor_node)
extract_builder.add_edge(START, "extractor")
extract_builder.add_edge("extractor", END)
extract_graph = extract_builder.compile()

# Backward-compatible alias for code that imports `graph`
graph = extract_graph


# ---------------------------------------------------------------------------
# Resume graph — parse → validate → review → save
# ---------------------------------------------------------------------------
resume_builder = StateGraph(State)
resume_builder.add_node("resume_reader", resume_reader_node)
resume_builder.add_node("resume_validator", resume_validator_node)
resume_builder.add_node("resume_reviewer", resume_reviewer_node)
resume_builder.add_node("resume_saver", resume_saver_node)

resume_builder.add_edge(START, "resume_reader")
resume_builder.add_edge("resume_reader", "resume_validator")
resume_builder.add_edge("resume_validator", "resume_reviewer")
resume_builder.add_edge("resume_reviewer", "resume_saver")
resume_builder.add_edge("resume_saver", END)

resume_graph = resume_builder.compile()
