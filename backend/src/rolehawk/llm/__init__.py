"""LLM layer: one provider interface, model routing, cost metering (docs/SPEC.md "LLM layer").

Callers use `LLMService` and name a *task* (rank, extract, write, review, chat); routing picks
the model and effort, the meter logs cost and enforces the monthly cap.
"""
