import pytest

from rolehawk.memory.files import TEMPLATES, MemoryTarget
from rolehawk.profile.markdown import (
    parse_preferences,
    parse_profile,
    render_preferences,
    render_profile,
)
from rolehawk.profile.merge import merge_preferences, merge_profile, norm
from rolehawk.profile.model import (
    Certification,
    Contact,
    Education,
    Experience,
    Preferences,
    Profile,
    Project,
    RemotePreference,
    SalaryFloor,
    SalaryPeriod,
)
from rolehawk.profile.parsing import (
    parse_date,
    parse_date_range,
    parse_salary,
    split_lines,
    split_list,
)


def full_profile() -> Profile:
    return Profile(
        contact=Contact(
            name="Ada Example",
            email="ada@example.com",
            phone="+1 555 0100",
            location="Austin, TX",
            links=["https://github.com/ada-example", "https://ada.example.com"],
        ),
        headline="Senior Frontend Engineer",
        summary="Builds accessible, fast web apps.\nLikes design systems.",
        experience=[
            Experience(
                title="Senior Frontend Engineer",
                company="Northwind Payments",
                location="Remote",
                start="2021-03",
                current=True,
                highlights=["Led the checkout redesign, lifting conversion 12%"],
            ),
            Experience(
                title="Frontend Engineer",
                company="Contoso Health",
                start="2017-06",
                end="2021-02",
                highlights=["Migrated the portal to React", "Mentored four engineers"],
            ),
        ],
        education=[
            Education(
                institution="University of Texas at Austin",
                degree="BSc",
                field="Computer Science",
                start="2013",
                end="2017",
                notes="ACM chapter",
            )
        ],
        skills=["TypeScript", "React", "PostgreSQL"],
        projects=[Project(name="a11y-lint", url="https://x.dev", highlights=["400 stars"])],
        certifications=[
            Certification(name="AWS Certified Developer", issuer="AWS", date="2023-01")
        ],
        achievements=["Speaker at React Summit 2024"],
        languages=["English", "Spanish (professional)"],
        extra_sections={"Volunteering": "Code mentor at a local bootcamp."},
    )


# --- markdown round trips -------------------------------------------------------------


def test_profile_round_trip() -> None:
    profile = full_profile()
    text = render_profile(profile)
    assert parse_profile(text) == profile
    assert render_profile(parse_profile(text)) == text  # stable


def test_template_parses_to_empty_profile() -> None:
    assert parse_profile(TEMPLATES[MemoryTarget.PROFILE]) == Profile()
    assert parse_preferences(TEMPLATES[MemoryTarget.PREFERENCES]) == Preferences()


def test_parser_tolerates_hand_edits() -> None:
    text = """# Profile

Some intro the user typed.

## Experience

Freelance between roles.

### Staff Engineer at Globex
- Dates: Jan 2020 \u2013 Mar 2022
- Location: Berlin
- Scaled the API to 10x traffic

## Skills
- Go, Rust, Kubernetes

## Hobbies
Climbing and chess.
"""
    profile = parse_profile(text)
    exp = profile.experience[0]
    assert (exp.title, exp.company, exp.location) == ("Staff Engineer", "Globex", "Berlin")
    assert (exp.start, exp.end, exp.current) == ("2020-01", "2022-03", False)
    assert exp.highlights == ["Scaled the API to 10x traffic"]
    assert profile.skills == ["Go", "Rust", "Kubernetes"]
    assert profile.extra_sections == {
        "Experience notes": "Freelance between roles.",
        "Hobbies": "Climbing and chess.",
    }
    rendered = render_profile(profile)
    assert "## Hobbies\n\nClimbing and chess." in rendered
    assert "Freelance between roles." in rendered


def test_preferences_round_trip_and_tolerant_values() -> None:
    prefs = Preferences(
        target_titles=["Senior Frontend Engineer", "Staff Engineer"],
        seniority="Senior",
        locations=["Austin", "Remote (US)"],
        remote=RemotePreference.HYBRID,
        country="US",
        salary_floor=SalaryFloor(amount=150000, currency="USD"),
        work_authorization="Citizen or permanent resident",
        deal_breakers=["Mandatory on-call"],
        energizing=["Building tools from scratch", "Mentoring"],
        draining=["Maintaining legacy systems"],
    )
    assert parse_preferences(render_preferences(prefs)) == prefs
    assert "## Work that energizes me" in render_preferences(prefs)
    hand = "## Remote\n- fully remote please\n## Salary floor\n- 90k\n## Country\n- gb"
    parsed = parse_preferences(hand, default_currency="GBP")
    assert parsed.remote is RemotePreference.REMOTE
    assert parsed.salary_floor == SalaryFloor(amount=90000, currency="GBP")
    assert parsed.country == "GB"


# --- small parsers ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2021-03", "2021-03"),
        ("03/2021", "2021-03"),
        ("Mar 2021", "2021-03"),
        ("September 2019", "2019-09"),
        ("2020", "2020"),
        ("2021-13", None),
        ("Smarch 2020", None),
        ("", None),
    ],
)
def test_parse_date(text: str, expected: str | None) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mar 2021 - Present", ("2021-03", None, True)),
        ("2019 to 2021", ("2019", "2021", False)),
        ("2019-2021", ("2019", "2021", False)),
        ("2020-03 \u2013 2024-06", ("2020-03", "2024-06", False)),  # en dash
        ("2020-03 to 2024-06", ("2020-03", "2024-06", False)),
        ("since 2022", ("2022", None, True)),
        ("2018", ("2018", "2018", False)),
    ],
)
def test_parse_date_range(text: str, expected: tuple[str | None, str | None, bool]) -> None:
    parsed = parse_date_range(text)
    assert parsed is not None
    assert (parsed.start, parsed.end, parsed.current) == expected


def test_parse_date_range_rejects_nonsense() -> None:
    assert parse_date_range("a while ago") is None
    assert parse_date_range("2020 - someday") is None


@pytest.mark.parametrize(
    ("text", "amount", "currency", "period"),
    [
        ("$120k", 120000, "USD", SalaryPeriod.YEAR),
        ("120,000 USD", 120000, "USD", SalaryPeriod.YEAR),
        ("£90k per year", 90000, "GBP", SalaryPeriod.YEAR),
        ("60/hour", 60, "EUR", SalaryPeriod.HOUR),
        ("8.5k eur a month", 8500, "EUR", SalaryPeriod.MONTH),
    ],
)
def test_parse_salary(text: str, amount: int, currency: str, period: SalaryPeriod) -> None:
    assert parse_salary(text, default_currency="EUR") == SalaryFloor(
        amount=amount, currency=currency, period=period
    )


def test_list_splitting() -> None:
    assert split_list("React, TypeScript, react") == ["React", "TypeScript"]
    assert split_list("- Go\n- Rust, the language\n2) SQL") == ["Go", "Rust, the language", "SQL"]
    assert split_lines("Cut costs 20%, saved $1M\n• Shipped v2") == [
        "Cut costs 20%, saved $1M",
        "Shipped v2",
    ]


# --- merging ---------------------------------------------------------------------------


def test_merge_is_idempotent_and_fills_gaps() -> None:
    current = full_profile()
    current.experience[1].start = None
    current.experience[1].end = None
    incoming = Profile(
        contact=Contact(name="Someone Else", phone="+1 555 9999"),
        experience=[
            Experience(
                title="frontend engineer",
                company="Contoso Health, Inc.",
                start="2017-06",
                end="2021-02",
                highlights=["Mentored four engineers", "Shipped telehealth video"],
            ),
            Experience(title="Intern", company="Initech", start="2016", end="2016"),
        ],
        skills=["react", "GraphQL"],
    )
    merged, report = merge_profile(current, incoming)
    assert merged.contact.name == "Ada Example"  # existing values win
    assert len(merged.experience) == 3
    contoso = next(e for e in merged.experience if e.company == "Contoso Health")
    assert (contoso.start, contoso.end) == ("2017-06", "2021-02")
    assert contoso.highlights[-1] == "Shipped telehealth video"
    assert merged.skills == ["TypeScript", "React", "PostgreSQL", "GraphQL"]
    assert next(e.company for e in merged.experience) == "Northwind Payments"  # current first
    assert report.added == {"experience": 1, "skills": 1}
    assert report.updated == {"experience": 1}

    again, second = merge_profile(merged, incoming)
    assert again == merged
    assert not second.changed


def test_norm_ignores_case_punctuation_and_suffixes() -> None:
    assert norm("Acme, Inc.") == norm("ACME") == "acme"


def test_merge_preferences_keeps_existing_values() -> None:
    current = Preferences(remote=RemotePreference.REMOTE, target_titles=["Engineer"])
    incoming = Preferences(
        remote=RemotePreference.ONSITE, target_titles=["engineer", "Lead"], country="US"
    )
    merged = merge_preferences(current, incoming)
    assert merged.remote is RemotePreference.REMOTE
    assert merged.target_titles == ["Engineer", "Lead"]
    assert merged.country == "US"


def test_places_and_titles_keep_their_commas() -> None:
    from rolehawk.profile.parsing import split_places

    assert split_places("Denver, CO; Boulder, CO\nRemote (US)") == [
        "Denver, CO",
        "Boulder, CO",
        "Remote (US)",
    ]
    prefs = parse_preferences(
        "## Target titles\n- Engineer, Platform\n## Locations\n- Austin, TX\n- Remote"
    )
    assert prefs.target_titles == ["Engineer, Platform"]
    assert prefs.locations == ["Austin, TX", "Remote"]
