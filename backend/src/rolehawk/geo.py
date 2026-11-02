"""Which countries a job's free-text location points to.

Job sources write locations however they like: "San Mateo, CA, United States",
"Bangalore, IND; Hyderabad, IND", "Toronto, ON, CA", "Home based - EMEA", "Remote US",
"AU - Sydney", "Hybrid". `detect()` reads country names and aliases, US states, Canadian
provinces, ISO codes, well-known cities, and regions (EMEA, APAC, Americas), and says
"unknown" rather than guess. Unknown and worldwide locations never filter a job out.

Ambiguous two-letter codes (CA = California or Canada, IN = Indiana or India, ...) count as
US states only when nothing else in the string names another country."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --- countries ----------------------------------------------------------------------------

COUNTRY_NAMES: dict[str, str] = {
    "united states": "US", "united states of america": "US", "usa": "US", "america": "US",
    "united kingdom": "GB", "great britain": "GB", "britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "brasil": "BR", "argentina": "AR",
    "chile": "CL", "colombia": "CO", "peru": "PE", "uruguay": "UY", "costa rica": "CR",
    "ireland": "IE", "republic of ireland": "IE", "germany": "DE", "deutschland": "DE",
    "france": "FR", "spain": "ES", "portugal": "PT", "italy": "IT", "netherlands": "NL",
    "the netherlands": "NL", "holland": "NL", "belgium": "BE", "luxembourg": "LU",
    "switzerland": "CH", "austria": "AT", "denmark": "DK", "sweden": "SE", "norway": "NO",
    "finland": "FI", "iceland": "IS", "poland": "PL", "czech republic": "CZ", "czechia": "CZ",
    "slovakia": "SK", "hungary": "HU", "romania": "RO", "bulgaria": "BG", "greece": "GR",
    "serbia": "RS", "croatia": "HR", "slovenia": "SI", "albania": "AL", "estonia": "EE",
    "latvia": "LV", "lithuania": "LT", "ukraine": "UA", "turkey": "TR", "turkiye": "TR",
    "cyprus": "CY", "malta": "MT", "israel": "IL", "united arab emirates": "AE", "uae": "AE",
    "saudi arabia": "SA", "qatar": "QA", "egypt": "EG", "morocco": "MA", "nigeria": "NG",
    "kenya": "KE", "south africa": "ZA", "ghana": "GH", "india": "IN", "pakistan": "PK",
    "bangladesh": "BD", "sri lanka": "LK", "singapore": "SG", "malaysia": "MY",
    "indonesia": "ID", "philippines": "PH", "thailand": "TH", "vietnam": "VN",
    "china": "CN", "hong kong": "HK", "taiwan": "TW", "japan": "JP", "south korea": "KR",
    "korea": "KR", "australia": "AU", "new zealand": "NZ",
}  # fmt: skip

# Alpha-3 codes some boards use ("Bangalore, IND").
ALPHA3: dict[str, str] = {
    "USA": "US", "GBR": "GB", "CAN": "CA", "MEX": "MX", "BRA": "BR", "IND": "IN", "IRL": "IE",
    "DEU": "DE", "FRA": "FR", "ESP": "ES", "PRT": "PT", "ITA": "IT", "NLD": "NL", "POL": "PL",
    "ISR": "IL", "AUS": "AU", "NZL": "NZ", "SGP": "SG", "JPN": "JP", "CHN": "CN", "KOR": "KR",
    "ARG": "AR", "COL": "CO", "CHL": "CL", "SWE": "SE", "CHE": "CH", "ROU": "RO", "PHL": "PH",
}  # fmt: skip

# Two-letter codes that are only ever countries here (no clash with a US state code).
ALPHA2 = {
    "US", "UK", "GB", "AU", "NZ", "SG", "IE", "BR", "MX", "JP", "ES", "FR", "NL", "PL", "PT",
    "SE", "CH", "AT", "BE", "DK", "NO", "FI", "CZ", "RO", "CL", "ZA", "PH", "CN", "HK", "TW",
    "KR", "AE", "TR", "GR", "UA", "EE", "LT", "LV", "HU", "RS", "HR", "BG", "NG", "KE", "EG",
    "PK", "VN", "MY", "TH", "CR", "UY", "LU", "IT", "DE", "IS", "SI", "QA", "SA",
}  # fmt: skip

# --- sub-national -------------------------------------------------------------------------

US_STATE_BY_NAME: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR",
}  # fmt: skip
US_STATES = set(US_STATE_BY_NAME)
US_STATE_CODES = set(US_STATE_BY_NAME.values())

CA_PROVINCE_BY_NAME: dict[str, str] = {
    "ontario": "ON", "quebec": "QC", "british columbia": "BC", "alberta": "AB",
    "manitoba": "MB", "saskatchewan": "SK", "nova scotia": "NS", "new brunswick": "NB",
    "newfoundland": "NL", "prince edward island": "PE", "yukon": "YT",
}  # fmt: skip
CA_PROVINCES = set(CA_PROVINCE_BY_NAME)
CA_PROVINCE_CODES = set(CA_PROVINCE_BY_NAME.values())

# States and provinces as "US-MI" and "CA-ON", by folded name.
SUBDIVISIONS: dict[str, str] = {
    **{name: f"US-{code}" for name, code in US_STATE_BY_NAME.items()},
    **{name: f"CA-{code}" for name, code in CA_PROVINCE_BY_NAME.items()},
}

OTHER_REGIONS: dict[str, str] = {
    "new south wales": "AU", "queensland": "AU", "western australia": "AU",
    "attica": "GR", "bavaria": "DE", "catalonia": "ES", "karnataka": "IN",
    "maharashtra": "IN", "telangana": "IN", "tamil nadu": "IN", "haryana": "IN",
}  # fmt: skip

# Cities that appear without a country ("London", "Bengaluru", "San Francisco").
CITIES: dict[str, str] = {
    # US
    "san francisco": "US", "sf bay area": "US", "bay area": "US", "new york city": "US",
    "nyc": "US", "seattle": "US", "austin": "US", "boston": "US", "chicago": "US",
    "los angeles": "US", "denver": "US", "atlanta": "US", "miami": "US", "san jose": "US",
    "palo alto": "US", "mountain view": "US", "menlo park": "US", "sunnyvale": "US",
    "san mateo": "US", "foster city": "US", "redwood city": "US", "santa clara": "US",
    "san diego": "US", "pittsburgh": "US", "philadelphia": "US", "salt lake city": "US",
    "raleigh": "US", "dallas": "US", "houston": "US", "phoenix": "US", "portland": "US",
    "bellevue": "US", "brooklyn": "US", "st louis": "US", "nashville": "US",
    "minneapolis": "US", "detroit": "US", "kirkland": "US", "irvine": "US",
    # Canada
    "toronto": "CA", "vancouver": "CA", "montreal": "CA", "ottawa": "CA", "waterloo": "CA",
    "calgary": "CA", "edmonton": "CA",
    # Europe
    "london": "GB", "manchester": "GB", "edinburgh": "GB", "bristol": "GB", "dublin": "IE",
    "cork": "IE", "berlin": "DE", "munich": "DE", "hamburg": "DE", "frankfurt": "DE",
    "paris": "FR", "amsterdam": "NL", "rotterdam": "NL", "madrid": "ES", "barcelona": "ES",
    "lisbon": "PT", "porto": "PT", "aveiro": "PT", "warsaw": "PL", "krakow": "PL", "wroclaw": "PL",
    "zurich": "CH", "geneva": "CH", "vienna": "AT", "brussels": "BE", "copenhagen": "DK",
    "aarhus": "DK", "stockholm": "SE", "oslo": "NO", "helsinki": "FI", "reykjavik": "IS",
    "prague": "CZ", "budapest": "HU", "bucharest": "RO", "sofia": "BG", "athens": "GR",
    "belgrade": "RS", "zagreb": "HR", "ljubljana": "SI", "tallinn": "EE", "riga": "LV",
    "vilnius": "LT", "kyiv": "UA", "kiev": "UA", "istanbul": "TR", "milan": "IT", "rome": "IT",
    # Middle East and Africa
    "tel aviv": "IL", "dubai": "AE", "abu dhabi": "AE", "riyadh": "SA", "doha": "QA",
    "cairo": "EG", "lagos": "NG", "nairobi": "KE", "cape town": "ZA", "johannesburg": "ZA",
    # Asia-Pacific
    "bengaluru": "IN", "bangalore": "IN", "hyderabad": "IN", "gurugram": "IN",
    "gurgaon": "IN", "pune": "IN", "mumbai": "IN", "chennai": "IN", "delhi": "IN",
    "new delhi": "IN", "noida": "IN", "kolkata": "IN", "singapore": "SG", "tokyo": "JP",
    "osaka": "JP", "seoul": "KR", "beijing": "CN", "shanghai": "CN", "shenzhen": "CN",
    "hangzhou": "CN", "taipei": "TW", "hsinchu": "TW", "manila": "PH", "jakarta": "ID",
    "kuala lumpur": "MY", "bangkok": "TH", "ho chi minh city": "VN", "hanoi": "VN",
    "sydney": "AU", "melbourne": "AU", "brisbane": "AU", "perth": "AU", "auckland": "NZ",
    "wellington": "NZ",
    # Latin America
    "sao paulo": "BR", "rio de janeiro": "BR", "mexico city": "MX", "guadalajara": "MX",
    "buenos aires": "AR", "bogota": "CO", "medellin": "CO", "santiago": "CL", "lima": "PE",
    "montevideo": "UY",
}  # fmt: skip

# --- regions ------------------------------------------------------------------------------


def _codes(text: str) -> frozenset[str]:
    return frozenset(text.split())


EUROPE = _codes(
    "GB IE DE FR ES PT IT NL BE LU CH AT DK SE NO FI IS PL CZ SK HU RO BG GR RS HR SI AL "
    "EE LV LT UA TR CY MT"
)
MIDDLE_EAST_AFRICA = _codes("IL AE SA QA EG MA NG KE ZA GH")
LATAM = _codes("MX BR AR CL CO PE UY CR")
APAC = _codes("IN PK BD LK SG MY ID PH TH VN CN HK TW JP KR AU NZ")

REGIONS: dict[str, frozenset[str]] = {
    "north america": frozenset({"US", "CA", "MX"}),
    "americas": frozenset({"US", "CA"}) | LATAM,
    "amer": frozenset({"US", "CA"}) | LATAM,
    "latam": LATAM,
    "latin america": LATAM,
    "south america": LATAM - {"MX", "CR"},
    "europe": EUROPE,
    "eu": EUROPE,
    "emea": EUROPE | MIDDLE_EAST_AFRICA,
    "middle east": MIDDLE_EAST_AFRICA - {"NG", "KE", "ZA", "GH", "MA"},
    "apac": APAC,
    "asia pacific": APAC,
    "asia": APAC - {"AU", "NZ"},
}

WORLDWIDE = ("worldwide", "anywhere", "global", "globally", "any location", "international")


@dataclass(frozen=True)
class Places:
    countries: frozenset[str] = frozenset()
    worldwide: bool = False
    subdivisions: frozenset[str] = frozenset()  # "US-MI", "CA-ON"
    cities: frozenset[str] = frozenset()  # well-known cities only (CITIES), folded

    @property
    def known(self) -> bool:
        return self.worldwide or bool(self.countries)

    @property
    def local(self) -> bool:
        """Names a state, province, or well-known city: somewhere narrower than a country."""
        return bool(self.subdivisions or self.cities)

    def allows(self, country: str) -> bool:
        """True unless the location clearly names only other countries."""
        return not self.known or self.worldwide or country.upper() in self.countries


def _fold(text: str) -> str:
    """Lowercase, accents removed ("São Paulo" -> "sao paulo"), punctuation to spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " " + re.sub(r"[^a-z0-9]+", " ", text) + " "


def _phrases() -> list[tuple[str, str | frozenset[str]]]:
    table: dict[str, str | frozenset[str]] = {}
    table.update(COUNTRY_NAMES)
    table.update(dict.fromkeys(US_STATES, "US"))
    table.update(dict.fromkeys(CA_PROVINCES, "CA"))
    table.update(OTHER_REGIONS)
    table.update(CITIES)
    table.update(REGIONS)
    # Longest first, so "new mexico" (a state) wins over "mexico" and "new south wales"
    # over "wales".
    return sorted(table.items(), key=lambda item: -len(item[0]))


def fold(text: str) -> str:
    """`_fold` without the padding: "Sterling Heights, MI" -> "sterling heights mi"."""
    return _fold(text).strip()


# What can trail a city in a place the user typed ("Austin TX", "Leeds United Kingdom").
_QUALIFIERS = sorted(
    {
        *US_STATES,
        *CA_PROVINCES,
        *COUNTRY_NAMES,
        *(code.casefold() for code in US_STATE_CODES | CA_PROVINCE_CODES | ALPHA2),
    },
    key=len,
    reverse=True,
)


def city_part(place: str) -> str:
    """The city in a place the user typed, folded: "Denver, CO", "Sterling Heights MI" and
    "Sterling Heights, Michigan, USA" give "denver" and "sterling heights". Trailing states,
    provinces and countries are dropped unless nothing else is left ("New York" stays)."""
    city = fold(place.split(",")[0])
    trimmed = True
    while trimmed:
        trimmed = False
        for qualifier in _QUALIFIERS:
            if city.endswith(f" {qualifier}"):
                city = city.removesuffix(qualifier).strip()
                trimmed = True
                break
    return city


_PHRASES = _phrases()
_DOTTED = re.compile(r"\b(?:U\.S\.A\.?|U\.S\.|U\.K\.|D\.C\.)", re.IGNORECASE)
_CODE = re.compile(r"\b[A-Z]{2,3}\b")


def detect(location: str | None) -> Places:
    if not location or not location.strip():
        return Places()
    raw = _DOTTED.sub(lambda m: m.group(0).replace(".", "").upper(), location)
    text = _fold(raw)
    if any(f" {word} " in text for word in WORLDWIDE):
        return Places(worldwide=True)

    found: set[str] = set()
    subdivisions: set[str] = set()
    cities: set[str] = set()
    for phrase, value in _PHRASES:
        needle = f" {phrase} "
        if needle in text:
            found.update({value} if isinstance(value, str) else value)
            if phrase in SUBDIVISIONS:
                subdivisions.add(SUBDIVISIONS[phrase])
            elif phrase in CITIES:
                cities.add(phrase)
            text = text.replace(needle, " ")  # "new mexico" mustn't also match "mexico"

    states: set[str] = set()
    for code in _CODE.findall(raw):
        if code in ALPHA3:
            found.add(ALPHA3[code])
        elif code in ALPHA2 and code != "CA":
            found.add("GB" if code == "UK" else code)
        elif code in CA_PROVINCE_CODES and code not in US_STATE_CODES:
            found.add("CA")
            subdivisions.add(f"CA-{code}")
        elif code in US_STATE_CODES:
            states.add(f"US-{code}")
    # "San Francisco, CA" is California; "Toronto, ON, CA" is Canada.
    if states and (not found or "US" in found):
        found.add("US")
        subdivisions |= states
    return Places(
        countries=frozenset(found),
        subdivisions=frozenset(subdivisions),
        cities=frozenset(cities),
    )


def place_subdivisions(place: str) -> frozenset[str]:
    """The states and provinces a place the user typed names after its city, in any case:
    "Sterling Heights mi" and "Sterling Heights, Michigan" give {"US-MI"}."""
    city = city_part(place)
    rest = fold(place).removeprefix(city)
    if not rest:
        return frozenset()
    padded = f" {rest} "
    found = {code for name, code in SUBDIVISIONS.items() if f" {name} " in padded}
    for word in rest.split():
        code = word.upper()
        if code in US_STATE_CODES:
            found.add(f"US-{code}")
        elif code in CA_PROVINCE_CODES:
            found.add(f"CA-{code}")
    return frozenset(found)
