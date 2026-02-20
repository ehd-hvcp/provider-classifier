# Provider Classifier

Classify companies from any CSV using Claude + web search. Each row is researched and assigned one of these categories (in priority order):

> **Health System** > **Non-Profit** > **National Chain** > **Franchise** > **Regional** > **Local Business** > **Unknown**

---

## Setup

### 1. Get an Anthropic API key

Go to [console.anthropic.com](https://console.anthropic.com), create an account, and generate an API key.

### 2. Configure your key

```bash
cp .env.example .env
# Edit .env and replace "your_key_here" with your actual key
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
python classify.py input.csv --name "company_name_column" --url "website_column"
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `input`  | *(required)* | Path to your input CSV |
| `--name` | `name` | Column containing company names |
| `--url`  | `website` | Column containing website URLs |

**Output:** A new file is created automatically — `input_classified.csv` — with two columns appended:
- `Category` — one of the 7 classification categories
- `Notes` — brief explanation of why

### Examples

```bash
# CSV has columns "name" and "website" (defaults)
python classify.py providers.csv

# CSV has columns "Provider Name" and "URL"
python classify.py providers.csv --name "Provider Name" --url "URL"

# No URL column available — classify by name only
python classify.py providers.csv --name "Organization"
```

---

## Classification Rules

| Category | Description |
|----------|-------------|
| Health System | Large integrated health system or hospital network (Kaiser, HCA, Ascension, etc.) |
| Non-Profit | 501(c)(3) or equivalent non-profit/not-for-profit organization |
| National Chain | For-profit company operating in many states under corporate ownership |
| Franchise | Franchised model — individual ownership under a national brand |
| Regional | For-profit operating in multiple states or large region, but not nationwide |
| Local Business | For-profit operating in a single market (city or county) |
| Unknown | Cannot be determined from available information |

The script applies categories in the order listed above — if a company qualifies for multiple categories, the highest-priority one is assigned.

---

## Tips

- The script writes output incrementally, so if it's interrupted you won't lose progress on completed rows.
- Each API call includes a 1-second delay to stay within rate limits.
- If a row fails, it's marked `Unknown` with an error note and processing continues.
