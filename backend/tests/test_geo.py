"""Country detection from free-text job locations. Cases are real strings from job boards."""

from __future__ import annotations

import pytest

from rolehawk.geo import city_part, detect, place_subdivisions


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


@pytest.mark.parametrize(
    ("place", "city"),
    [
        ("Denver, CO", "denver"),
        ("Sterling Heights MI", "sterling heights"),
        ("Sterling Heights, Michigan", "sterling heights"),
        ("sterling heights mi usa", "sterling heights"),
        ("Austin TX, United States", "austin"),
        ("Toronto ON", "toronto"),
        ("New York", "new york"),  # a state name, but nothing else is left
        ("New York NY", "new york"),
        ("St. Louis", "st louis"),
        ("São Paulo", "sao paulo"),
        ("Remote", "remote"),
    ],
)
def test_city_part(place: str, city: str) -> None:
    assert city_part(place) == city


@pytest.mark.parametrize(
    ("place", "regions"),
    [
        ("Sterling Heights MI", {"US-MI"}),
        ("sterling heights, michigan", {"US-MI"}),
        ("Denver, CO, USA", {"US-CO"}),
        ("Toronto ON", {"CA-ON"}),
        ("New York", set()),  # the city: no state after it
        ("Denver", set()),
    ],
)
def test_place_subdivisions(place: str, regions: set[str]) -> None:
    assert place_subdivisions(place) == regions


def test_states_provinces_and_cities() -> None:
    assert detect("Troy, MI 48084").subdivisions == {"US-MI"}
    assert detect("Detroit, Michigan").subdivisions == {"US-MI"}
    assert detect("Toronto, ON, CA").subdivisions == {"CA-ON"}
    assert detect("Seattle").cities == {"seattle"}
    assert not detect("United States").local  # a country, no narrower place
    assert not detect("Warren, Macomb County").local  # unknown: nothing to go on
    assert detect("San Francisco, CA").local
