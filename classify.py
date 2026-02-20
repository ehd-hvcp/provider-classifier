#!/usr/bin/env python3
"""
classify.py — Research and classify companies from a CSV using Claude + web search.

Usage:
    python classify.py input.csv --name "company_name" --url "website"
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

CATEGORIES = [
    "Health System",
    "Non-Profit",
    "National Chain",
    "Franchise",
    "Regional",
    "Local Business",
    "Unknown",
]

CLASSIFICATION_PROMPT = """You are a business research assistant. Your task is to classify a company into exactly one of these categories (listed in priority order — assign the highest-priority category that applies):

1. Health System — A large integrated health system, hospital network, or health system-owned entity (e.g., Kaiser, HCA, Ascension, Cleveland Clinic affiliates)
2. Non-Profit — A non-profit or not-for-profit organization (501c3 or equivalent), including non-profit health agencies and community health organizations
3. National Chain — A for-profit company operating in many states with centralized corporate ownership (e.g., Amedisys, LHC Group, BrightSpring)
4. Franchise — A franchised business model where locations are individually owned but operate under a national brand (e.g., Home Instead, Visiting Angels, Comfort Keepers)
5. Regional — A for-profit company operating in multiple states or a large multi-county region, but not nationwide
6. Local Business — A for-profit company operating in a single market (city, county, or small group of counties)
7. Unknown — Cannot be determined from available information

Company to classify:
  Name: {name}
  Website: {url}

Instructions:
- Search the web to research this company
- Look for: ownership structure, number of locations, geographic footprint, non-profit status, franchise indicators, parent company
- Apply the priority order strictly — if it qualifies for multiple categories, choose the highest-priority one
- Respond ONLY with valid JSON in this exact format:
{{"category": "<one of the 7 categories above>", "notes": "<1-2 sentence explanation of why>"}}"""


def classify_company(client: anthropic.Anthropic, name: str, url: str) -> dict:
    """Research and classify a single company using Claude with web search."""
    search_query = name if not url else f"{name} {url}"
    prompt = CLASSIFICATION_PROMPT.format(
        name=name or "(unknown)",
        url=url or "(not provided)",
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text from response content blocks
        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content += block.text

        # Parse JSON from response
        result = _parse_json(text_content)
        if result:
            return result

        # Retry once if JSON parse failed
        print(f"    Retrying JSON parse for: {name}")
        result = _parse_json_retry(client, text_content, prompt)
        if result:
            return result

        return {"category": "Unknown", "notes": "Error: Could not parse classification response"}

    except Exception as e:
        return {"category": "Unknown", "notes": f"Error: {e}"}


def _parse_json(text: str) -> dict | None:
    """Try to extract and parse JSON from a text string."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for JSON block
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _parse_json_retry(client: anthropic.Anthropic, bad_response: str, original_prompt: str) -> dict | None:
    """Ask Claude to fix a malformed JSON response."""
    try:
        fix_prompt = (
            f"The following response was supposed to be valid JSON matching "
            f'{{"category": "...", "notes": "..."}} but it was malformed. '
            f"Please return ONLY the corrected JSON, nothing else.\n\nResponse:\n{bad_response}"
        )
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": fix_prompt}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return _parse_json(text)
    except Exception:
        return None


def process_csv(input_path: str, name_col: str, url_col: str) -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set. Add it to your .env file or environment.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    output_path = input_file.parent / f"{input_file.stem}_classified{input_file.suffix}"

    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        if not fieldnames:
            print("Error: CSV has no headers.")
            sys.exit(1)

        if name_col not in fieldnames:
            print(f"Error: Column '{name_col}' not found. Available columns: {', '.join(fieldnames)}")
            sys.exit(1)

        rows = list(reader)

    total = len(rows)
    output_fields = list(fieldnames) + ["Category", "Notes"]

    with open(output_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=output_fields)
        writer.writeheader()

        for i, row in enumerate(rows, start=1):
            name = row.get(name_col, "").strip()
            url = row.get(url_col, "").strip() if url_col in fieldnames else ""

            print(f"Processing {i}/{total}: {name or '(unnamed)'}...")

            result = classify_company(client, name, url)
            row["Category"] = result.get("category", "Unknown")
            row["Notes"] = result.get("notes", "")
            writer.writerow(row)
            out_f.flush()  # write each row immediately in case of interruption

            if i < total:
                time.sleep(1)  # rate limit buffer

    print(f"\nDone! Output written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Classify companies from a CSV using Claude + web search."
    )
    parser.add_argument("input", help="Path to input CSV file")
    parser.add_argument(
        "--name",
        default="name",
        help="Column name containing company names (default: 'name')",
    )
    parser.add_argument(
        "--url",
        default="website",
        help="Column name containing website URLs (default: 'website')",
    )
    args = parser.parse_args()
    process_csv(args.input, args.name, args.url)


if __name__ == "__main__":
    main()
