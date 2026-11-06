import pandas as pd
import pytest

from pets_transformer.assess.kanon import k_anonymity
from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.text.base import merge_spans, redact


class TestKAnonymity:
    frame = pd.DataFrame(
        {
            "age": ["30-39"] * 5 + ["40-49"] * 2,
            "sex": ["F"] * 5 + ["M"] * 2,
        }
    )

    def test_reports_smallest_group_and_share_below_k(self) -> None:
        r = k_anonymity(self.frame, ["age", "sex"], k_target=5)
        assert (r.k_min, r.groups, r.rows) == (2, 2, 7)
        assert r.share_below_k == pytest.approx(2 / 7)
        assert not r.passes

    def test_passes_when_every_group_is_big_enough(self) -> None:
        assert k_anonymity(self.frame, ["age", "sex"], k_target=2).passes

    def test_no_quasi_identifiers_means_one_group(self) -> None:
        r = k_anonymity(self.frame, [], k_target=5)
        assert (r.k_min, r.groups) == (7, 1)

    def test_empty_table(self) -> None:
        r = k_anonymity(self.frame.iloc[0:0], ["age"], k_target=5)
        assert (r.rows, r.k_min, r.share_below_k, r.passes) == (0, 0, 0.0, True)

    def test_unknown_column_is_an_error(self) -> None:
        with pytest.raises(KeyError, match="postcode"):
            k_anonymity(self.frame, ["postcode"])


class TestRedact:
    text = "Soita Ainolle numeroon 040 123 4567"

    def _span(self, start: int, end: int, label: SpanLabel) -> Span:
        return Span(start=start, end=end, label=label, text=self.text[start:end])

    def test_replaces_spans_with_typed_tags(self) -> None:
        spans = [self._span(6, 13, SpanLabel.PERSON), self._span(23, 35, SpanLabel.PHONE)]
        assert redact(self.text, spans) == "Soita [PERSON] numeroon [PHONE]"

    def test_nested_and_overlapping_spans_do_not_duplicate_tags(self) -> None:
        outer = self._span(23, 35, SpanLabel.PHONE)
        inner = self._span(27, 30, SpanLabel.ACCOUNT_NUMBER)
        overlap = self._span(20, 26, SpanLabel.LOCATION)
        assert merge_spans([inner, outer]) == [outer]
        out = redact(self.text, [overlap, outer])
        assert "040" not in out
        assert out.count("[") == 2

    def test_no_spans_returns_text_unchanged(self) -> None:
        assert redact(self.text, []) == self.text
