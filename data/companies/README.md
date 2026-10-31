# Company watchlists

ATS sources search by company, not keyword. Each CSV lists company board slugs for one ATS:

- `slug`: the company's board identifier in that ATS (for example, the part after `boards.greenhouse.io/`)
- `name`: display name
- `industry`: free-text industry tag, used by /setup to suggest companies
- `country`: ISO 3166-1 alpha-2 code for the company's main market, or `*`

The starter lists (about 500 slugs per ATS) are populated in Chunk 6.
