"""Country detection from free-text job locations. Cases are real strings from job boards."""

from __future__ import annotations

import pytest

from offerbound.geo import detect


@pytest.mark.parametrize(
    ("location", "countries"),
    [
        ("San Mateo, CA, United States", {"US"}),
        ("San Francisco", {"US"}),
        ("New York, NY (HQ)", {"US"}),
        ("Washington, D.C.", {"US"}),
        ("Remote U.S.", {"US"}),
        ("CA - San Francisco; WA - Seattle", {"US"}),
        ("Remote - CA", {"US"}),  # a bare CA is California
        ("Toronto, ON, CA", {"CA"}),  # ...unless something else says Canada
        ("Canada - Remote (ON, AB, BC, or NS Only)", {"CA"}),
        ("Vancouver, BC", {"CA"}),
        ("Bangalore, IND; Hyderabad, IND", {"IN"}),
        ("Bengaluru", {"IN"}),
        ("Gurugram, Haryana, India", {"IN"}),
        ("London", {"GB"}),
        ("UK - London", {"GB"}),
        ("AU - Sydney", {"AU"}),
        ("New South Wales", {"AU"}),  # not Wales
        ("Albuquerque, New Mexico", {"US"}),  # not Mexico
        ("Mexico City, Mexico", {"MX"}),
        ("São Paulo, São Paulo, Brazil", {"BR"}),
        ("Remote, Brasil", {"BR"}),
        ("Reykjavík", {"IS"}),
        ("Dublin, IE", {"IE"}),
        ("Singapore, SGP", {"SG"}),
        ("Hybrid - San Francisco, New York City, London", {"US", "GB"}),
        ("Remote, Canada; Remote, United States", {"CA", "US"}),
        ("San Francisco, CA, New York, NY, Portland, OR, or Remote within Canada", {"US", "CA"}),
    ],
)
def test_detects_countries(location: str, countries: set[str]) -> None:
    places = detect(location)
    assert places.countries == countries
    assert places.worldwide is False


@pytest.mark.parametrize(
    "location", ["Remote, Global", "Anywhere in the World", "Home based - Worldwide"]
)
def test_worldwide(location: str) -> None:
    places = detect(location)
    assert places.worldwide is True
    assert places.allows("US")
    assert places.allows("DE")


@pytest.mark.parametrize("location", ["Hybrid", "Remote", "In-Office", "N/A", "", None])
def test_unknown_never_excludes(location: str | None) -> None:
    places = detect(location)
    assert places.known is False
    assert places.allows("US")


def test_regions() -> None:
    emea = detect("Home based - EMEA")
    assert "DE" in emea.countries
    assert "IL" in emea.countries
    assert not emea.allows("US")
    assert detect("Home Based - Americas").allows("US")
    assert detect("North America").allows("CA")
    assert not detect("Remote - APAC").allows("GB")


def test_allows_is_case_insensitive() -> None:
    assert detect("Remote - India").allows("in")
    assert not detect("Remote - India").allows("us")
