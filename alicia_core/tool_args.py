"""Typed input contracts shared by web and desktop compositions."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Consulta inválida.")
        return value


class OpenAppArgs(StrictArgs):
    app_name: str = Field(min_length=1, max_length=80)


class ExpressionArgs(StrictArgs):
    expression_file: str = Field(min_length=1, max_length=500)
