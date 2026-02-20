#!/usr/bin/env python3
"""
classify.py — Research and classify companies from a CSV using Claude + web search.

Usage:
    python classify.py input.csv --name "name" --url "website"
    python classify.py input.csv --name "name" --url "website" --resume  # skip already-done rows
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
- {search_instruction}
- Look for: ownership structure, number of locations, geographic footprint, non-profit status, franchise indicators, parent company
- Apply the priority order strictly — if it qualifies for multiple categories, choose the highest-priority one
- Respond ONLY with valid JSON in this exact format:
{{"category": "<one of the 7 categories above>", "notes": "<1-2 sentence explanation of why>"}}"""


def classify_company(client: anthropic.Anthropic, name: str, url: str) -> dict:
    """Classify a single company. Uses web search only if no URL is provided."""
    has_url = bool(url and url.strip())

    if has_url:
        search_instruction = "Use the company name and website URL provided to classify this company based on your knowledge"
        tools = []
    else:
        search_instruction = "Search the web to research this company"
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]

    prompt = CLASSIFICATION_PROMPT.format(
        name=name or "(unknown)",
        url=url or "(not provided)",
        search_instruction=search_instruction,
    )

    try:
        kwargs = dict(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        if tools:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)

        text_content = "".join(b.text for b in response.content if hasattr(b, "text"))

        result = _parse_json(text_content)
        if result:
            return result

        print(f"    Retrying JSON parse for: {name}")
        result = _parse_json_retry(client, text_content)
        if result:
            return result

        return {"category": "Unknown", "notes": "Error: Could not parse classification response"}

    except Exception as e:
        return {"category": "Unknown", "notes": f"Error: {e}"}


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None


def _parse_json_retry(client: anthropic.Anthropic, bad_response: str) -> dict | None:
    try:
        fix_prompt = (
            f"The following response was supposed to be valid JSON matching "
            f'{{"category": "...", "notes": "..."}} but it was malformed. '
            f"Return ONLY the corrected JSON, nothing else.\n\nResponse:\n{bad_response}"
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


def process_csv(input_path: str, name_col: str, url_col: str, resume: bool) -> None:
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

    # If resuming, figure out how many rows are already done
    already_done = 0
    if resume and output_path.exists():
        with open(output_path, newline="", encoding="utf-8") as f:
            already_done = sum(1 for _ in csv.DictReader(f))
        print(f"Resuming from row {already_done + 1} ({already_done} already done)")

    total = len(rows)
    output_fields = list(fieldnames) + ["Category", "Notes"]

    # Open in append mode if resuming, write mode otherwise
    file_mode = "a" if resume and already_done > 0 else "w"
    with open(output_path, file_mode, newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=output_fields)
        if file_mode == "w":
            writer.writeheader()

        for i, row in enumerate(rows, start=1):
            if i <= already_done:
                continue

            name = row.get(name_col, "").strip()
            url = row.get(url_col, "").strip() if url_col in fieldnames else ""

            print(f"Processing {i}/{total}: {name or '(unnamed)'}...")

            result = classify_company(client, name, url)
            row["Category"] = result.get("category", "Unknown")
            row["Notes"] = result.get("notes", "")
            writer.writerow(row)
            out_f.flush()

            if i < total:
                time.sleep(0.5)

    print(f"\nDone! Output written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Classify companies from a CSV using Claude."
    )
    parser.add_argument("input", help="Path to input CSV file")
    parser.add_argument("--name", default="name", help="Column containing company names (default: 'name')")
    parser.add_argument("--url", default="website", help="Column containing website URLs (default: 'website')")
    parser.add_argument("--resume", action="store_true", help="Skip rows already in the output file")
    args = parser.parse_args()
    process_csv(args.input, args.name, args.url, args.resume)


if __name__ == "__main__":
    main()
