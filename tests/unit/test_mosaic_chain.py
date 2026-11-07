"""Mosaic chains: link labels from the clues that narrowed the visits, and identifier masking."""

from evaluation.mosaic_chain import link_label, mask_hetu, mask_iban, mask_phone, mask_street


def test_link_label_names_the_clues_that_narrowed_the_visits() -> None:
    funnel = [["arrived in the hours before the post", 88], ["'Riitta' is usually a woman's name", 46],
              ["stayed about 3 hours", 3], ["symptoms point to injury", 1]]  # fmt: skip
    assert link_label(funnel) == "time · sex · stay · symptoms"


def test_identifiers_are_partly_masked() -> None:
    assert mask_hetu("200564-966L") == "200564-9••L"
    assert mask_phone("+358 40 236 5404") == "040 ••• 5404"
    assert mask_iban("FI2112345600000785") == "FI21 •••• •••• •••• 85"
    assert mask_street("Aaltokatu 30 A 1") == "Aaltokatu ••"
