"""Quick facts read from postings with no AI: work mode, years asked for, skills named."""

from __future__ import annotations

from rolehawk.jobs.facts import SkillFinder, job_facts, work_mode, years_asked

SKILLS = [
    "React",
    "Node.js",
    "C#",
    ".NET",
    "SQL Server",
    "Postgres",
    "Vue 3",
    "design system governance across many product teams",
    "150 component design system",
    "Java",
]


def test_finds_the_users_short_skills_at_word_edges() -> None:
    finder = SkillFinder(SKILLS)
    text = (
        "You'll build with ReactJS and NodeJS on .NET 8 and C#, store data in PostgreSQL "
        "and SQL Server, and ship Vue.js widgets. JavaScript is a plus."
    )
    assert finder.find(text) == [
        "React",
        "Node.js",
        "C#",
        ".NET",
        "SQL Server",
        "Postgres",
        "Vue 3",
    ]
    assert finder.find("We use reactive streams in Javascript and ASP.NETCore") == []


def test_reads_the_work_mode() -> None:
    assert work_mode("Engineer", "Detroit, MI (Hybrid)", False, "") == "hybrid"
    assert work_mode("Engineer", "Remote US", True, "") == "remote"
    assert work_mode("Engineer", "Troy, MI", None, "This role is hybrid: 3 days in office.") == (
        "hybrid"
    )
    assert work_mode("Engineer", "Troy, MI", None, "This is an on-site role.") == "on-site"
    assert work_mode("Engineer", "Troy, MI", None, "Build great things.") is None


def test_reads_the_years_of_experience_asked_for() -> None:
    text = "5+ years of professional experience with React. 2-3 years experience with GraphQL."
    assert years_asked(text) == 5
    assert years_asked("3 to 5 years of relevant experience") == 3
    assert years_asked("Founded 12 years ago. Great benefits.") is None  # not about experience
    assert years_asked("401 years of experience") is None


def test_job_facts_combines_them() -> None:
    facts = job_facts(
        SkillFinder(SKILLS),
        title="Senior React Developer",
        location="Remote",
        remote=True,
        description="7+ years of experience shipping web apps.",
    )
    assert (facts.work_mode, facts.years, facts.skills) == ("remote", 7, ["React"])
