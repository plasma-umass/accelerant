from pydantic import BaseModel


class CodeSuggestion(BaseModel):
    """
    A suggestion to replace a region of code with new code.
    The region is identified by filename and region_name (e.g., the name of the enclosing function).
    """

    filename: str
    region_name: str
    """
    The name of the code region being replaced, e.g., the name of a function or type definition.
    """
    new_code: str
