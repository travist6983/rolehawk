"""Candidate profile and job preferences (docs/SPEC.md "/setup").

profile.md and preferences.md stay the canonical, human-editable source of truth. This package
gives them a typed shape: a parser (markdown -> model) tolerant of hand edits, a renderer
(model -> markdown) for writes, and the derived `profile_items` index for structured queries.
"""
