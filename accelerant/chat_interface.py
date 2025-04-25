from typing import List
from pydantic import BaseModel


class RegionAnalysis(BaseModel):
    filename: str
    line: int
    performanceAnalysis: str


class ProjectAnalysis(BaseModel):
    regions: List[RegionAnalysis]


class CodeSuggestion(BaseModel):
    filename: str
    startLine: int
    endLine: int
    newCode: str


class OptimizationSuite(BaseModel):
    highLevelSummary: str
    suggestions: List[CodeSuggestion]


class ErrorFixingSuggestions(BaseModel):
    suggestions: List[CodeSuggestion]
