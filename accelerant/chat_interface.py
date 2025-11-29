from pydantic import BaseModel


class CodeSuggestion(BaseModel):
    """
    A suggestion to replace a region of code with new code.
    The snippet identifying the old code must be unique within the file.
    """

    filename: str
    old_code: str
    new_code: str
