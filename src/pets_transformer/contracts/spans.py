"""Personal-data spans found in free text, in the JSONL shape `pets-eval text` scores."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pets_transformer.contracts.taxonomy import SpanLabel


class Span(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    label: SpanLabel
    text: str
    source: str = "rules"  # which detector found it: rules, ner, llm ...

    @model_validator(mode="after")
    def _end_after_start(self) -> "Span":
        if self.end <= self.start:
            raise ValueError("span end must be after start")
        if len(self.text) != self.end - self.start:
            raise ValueError("span text length must match its offsets")
        return self


class RecordSpans(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    spans: list[Span]

    def to_pets_eval(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "spans": [{"start": s.start, "end": s.end, "label": s.label.value} for s in self.spans],
        }
