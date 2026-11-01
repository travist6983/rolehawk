from rolehawk.config import LLMSettings
from rolehawk.llm.typical_cost import ACTIVE, LIGHT, typical_cost, weekly_cost


def test_default_models_give_a_realistic_monthly_range() -> None:
    cost = typical_cost(LLMSettings())
    # Opus 5.5 writes, Haiku 5.5 ranks: an active search lands in the teens of dollars.
    assert 10 < cost.active.monthly_usd < 30
    assert 2 < cost.light.monthly_usd < 8
    assert cost.writing_model == "Claude Opus 5.5"
    assert cost.ranking_model == "Claude Haiku 5.5"


def test_estimate_follows_the_chosen_model_and_routing() -> None:
    default = weekly_cost(ACTIVE, LLMSettings())
    assert weekly_cost(ACTIVE, LLMSettings(model="claude-fable-5-1")) > default
    assert weekly_cost(ACTIVE, LLMSettings(model="claude-sonnet-5-5")) < default
    # Without smart routing, ranking runs on the chosen model too.
    assert weekly_cost(LIGHT, LLMSettings(smart_routing=False)) > weekly_cost(LIGHT, LLMSettings())


def test_unknown_model_is_priced_conservatively() -> None:
    cost = typical_cost(LLMSettings(model="claude-future-9"))
    assert cost.writing_model == "claude-future-9"
    assert cost.active.monthly_usd > typical_cost(LLMSettings()).active.monthly_usd
