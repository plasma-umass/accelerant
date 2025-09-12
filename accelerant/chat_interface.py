from typing import List
from pydantic import BaseModel


class RegionAnalysis(BaseModel):
    filename: str
    line: int
    performanceAnalysis: str


class ProjectAnalysis(BaseModel):
    regions: List[RegionAnalysis]


class CodeSuggestion(BaseModel):
    """
    A suggestion to replace a region of code with new code.
    The region is identified by filename and regionName (e.g., the name of the enclosing function).
    """

    filename: str
    regionName: str
    """
    The name of the code region being replaced, e.g., the name of a function or type definition.
    """
    newCode: str


class OptimizationSuite(BaseModel):
    highLevelSummary: str
    suggestions: List[CodeSuggestion]


class ErrorFixingSuggestions(BaseModel):
    suggestions: List[CodeSuggestion]
