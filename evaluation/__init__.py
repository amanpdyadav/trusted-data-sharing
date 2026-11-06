"""Evaluation harness: measures a protected release against the requirements.

Lives outside `src/` on purpose: it uses the organisers' scorer (pets-eval) and the package's answer files,
which runtime code must never touch (production rule 1).
"""
