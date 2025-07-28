import json
import arxiv
import os
from datetime import datetime, timedelta
import time
import csv
from dotenv import load_dotenv

from airtable_helper import AirtableLogger

def load_config(config_path='config.json'):
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {config_path} not found. Make sure it's in the same directory as the script.")
        exit(1)
    except json.JSONDecodeError:
        print(f"Error: {config_path} contains invalid JSON. Please check its syntax.")
        exit(1)

def search_arxiv(keywords, max_results):
    query_string = " OR ".join([f"all:{keyword}" for keyword in keywords])

    client = arxiv.Client()
    search = arxiv.Search(
        query=query_string,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )

    results = []
    try:
        for result in client.results(search):
            results.append(result)
    except Exception as e:
        print(f"An error occurred during ArXiv search: {e}")
    return results

def log_to_csv(paper_data):
    csv_file = "logged_papers.csv"
    try:
        file_exists = os.path.isfile(csv_file)
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ["Title", "Authors", "Published Date", "Summary", "ArXiv URL", "PDF URL", "ArXiv ID", "Timestamp"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow(paper_data)
        print(f" (Logged to CSV: {paper_data['Title']})")
    except Exception as e:
        print(f"Error logging to CSV: {e}")

if __name__ == "__main__":
    load_dotenv()

    print("Starting ArXiv Research Paper Bot...")

    config = load_config()
    arxiv_keywords = config.get("arxiv_keywords", [])
    arxiv_max_results = config.get("arxiv_max_results_per_run", 10)
    sleep_duration_hours = config.get("sleep_duration_hours", 4)
    sleep_duration_seconds = sleep_duration_hours * 3600

    if not arxiv_keywords:
        print("Error: 'arxiv_keywords' not found or empty in config.json. Please add some keywords.")
        exit(1)

    airtable_logger = None
    try:
        AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN")
        AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
        AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME")

        if not all([AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME]):
            raise ValueError("One or more Airtable environment variables are missing. Please check your .env file or Railway variables.")

        airtable_logger = AirtableLogger(AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
        print("Airtable logger initialized successfully.")
    except Exception as e:
        print(f"WARNING: Could not initialize Airtable logger: {e}. Logging to Airtable will be skipped and fallback to CSV if implemented.")

    while True: # should keep my main bot loop continously running
        current_time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n--- Bot Run Started at {current_time_stamp} ---")

        try:
            print(f"Searching ArXiv for papers with keywords: {', '.join(arxiv_keywords)} (Max results: {arxiv_max_results})")
            papers_found = search_arxiv(arxiv_keywords, arxiv_max_results)
            print(f"Found {len(papers_found)} potential new papers.")

            papers_logged_this_run = 0
            for paper in papers_found:
                if airtable_logger and airtable_logger.record_exists("ArXiv ID", paper.entry_id):
                    print(f"  Skipping already logged paper (Airtable check): {paper.title[:70]}...")
                    continue
                    # get the paper data ready for logging

                paper_data = {
                    "Title": paper.title,
                    "Authors": ", ".join([a.name for a in paper.authors]),
                    "Published Date": paper.published.strftime('%Y-%m-%d %H:%M:%S'),
                    "Summary": paper.summary,
                    "ArXiv URL": paper.entry_id,
                    "PDF URL": paper.pdf_url if paper.pdf_url else "",
                    "ArXiv ID": paper.entry_id,
                    "Timestamp": datetime.now().isoformat()
                }

                if airtable_logger:
                    logged_to_airtable = airtable_logger.create_record(paper_data)
                    if logged_to_airtable:
                        papers_logged_this_run += 1
                else:
                    print(f"Airtable logger not active, falling back to CSV for: {paper_data['Title']}")
                    log_to_csv(paper_data)
                    papers_logged_this_run += 1

            print(f"Logged {papers_logged_this_run} new papers in this run.")

        except Exception as e:
            print(f"An unexpected error occurred during a bot run: {e}")

        finally:
            next_run_time = datetime.now() + timedelta(seconds=sleep_duration_seconds)
            print(f"Bot run finished. Sleeping for {sleep_duration_hours:.1f} hours. Next run expected around {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(sleep_duration_seconds)