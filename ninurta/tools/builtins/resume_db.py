from ninurta.tools.registry import tool

@tool
def get_base_resume(resume_id: int) -> str:
    """Fetch the full text of a base resume by its database id.

    Args:
        resume_id: Primary key in the resumes table.
    """
    from ninurta.db.models import Resume
    from ninurta.db.session import SessionLocal
    with SessionLocal() as db:
        row = db.get(Resume, resume_id)
        return row.content if row else ""