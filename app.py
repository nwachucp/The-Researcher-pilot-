import json
import arxiv
import os
from datetime import datetime, timedelta
import time
import csv
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import threading

app = Flask(__name__)
# defining the name of my SQLite database file
DATABASE = 'papers.db'
LAST_RUN_TIMESTAMP_FILE = 'last_run_timestamp.txt'

# database functions

def init_db():
    """initializes the SQLite database and creates the papers table if it doesn't exist."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        # SQL command to create the 'papers' table.
        # IF NOT EXISTS prevents errors if the table already exists.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                authors TEXT NOT NULL,
                published_date TEXT NOT NULL,
                summary TEXT NOT NULL,
                arxiv_url TEXT NOT NULL UNIQUE, 
                pdf_url TEXT,
                arxiv_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL
            )
        ''')
        # commit the changes to the database
        conn.commit()
    print(f"Database '{DATABASE}' initialized successfully.")

def insert_paper(paper_data):
    """Inserts a single paper record into the database."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        try:
            # SQL command to insert a new paper into the table
            cursor.execute('''
                INSERT INTO papers (title, authors, published_date, summary, arxiv_url, pdf_url, arxiv_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                
                paper_data['Title'],
                paper_data['Authors'],
                paper_data['Published Date'],
                paper_data['Summary'],
                paper_data['ArXiv URL'],
                paper_data['PDF URL'],
                paper_data['ArXiv ID'],
                paper_data['Timestamp']
            ))
            conn.commit()
            print(f" (Logged to DB: {paper_data['Title']})")
            return True
        except sqlite3.IntegrityError as e:
            # makes sure paper isn't logged more than once
            print(f"Skipping already logged paper (DB check): {paper_data['Title']} - {e}")
            return False
        except Exception as e:
            print(f"Error logging to DB: {e}")
            return False

def get_all_papers():
    """Retrieves all paper records from the database."""
    with sqlite3.connect(DATABASE) as conn:
        # set the row_factory to sqlite3.Row to get dictionary-like objects
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # SQL command to select all papers, ordered by published date in descending order
        cursor.execute('SELECT * FROM papers ORDER BY published_date DESC')
        # convert the fetched rows into a list of dictionaries
        return [dict(row) for row in cursor.fetchall()]

# config function
# these functions manage the 'config.json' file for keywords and settings.

def load_config(config_path='config.json'):
    """Loads configuration settings from a JSON file."""
    try:
        # Open and read the config.json file
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {config_path} not found. Make sure it's in the same directory as the script.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: {config_path} contains invalid JSON. Please check its syntax.")
        return {}

def save_config(config, config_path='config.json'):
    """Saves configuration settings to a JSON file."""
    try:
        # Open the config.json file in write mode and dump the dictionary to it
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config file: {e}")

# ArXiv Search Function
def search_arxiv(keywords, max_results):
    """Searches ArXiv for papers based on provided keywords."""
    # formats the keywords into a query string for the ArXiv API
    query_string = " OR ".join([f"all:{keyword}" for keyword in keywords])
    client = arxiv.Client()
    # create a search object with the specified query, max results, and sorting
    search = arxiv.Search(
        query=query_string,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    results = []
    try:
        # Fetch the results from the ArXiv client
        for result in client.results(search):
            results.append(result)
    except Exception as e:
        print(f"An error occurred during ArXiv search: {e}")
    return results

# function to perform a search and log the papers.
def perform_search_and_log(keywords, max_results):
    """Performs an ArXiv search and logs new papers to the database."""
    print(f"Searching ArXiv for papers with keywords: {', '.join(keywords)} (Max results: {max_results})")
    papers_found = search_arxiv(keywords, max_results)
    print(f"Found {len(papers_found)} potential new papers.")
    
    papers_logged_this_run = 0
    for paper in papers_found:
        paper_data = {
            "Title": paper.title,
            "Authors": ", ".join([a.name for a in paper.authors]),
            "Published Date": paper.published.strftime('%Y-%m-%d %H:%M:%S'),
            "Summary": paper.summary,
            "ArXiv URL": paper.entry_id,
            "PDF URL": paper.pdf_url if paper.pdf_url else "",
            "ArXiv ID": paper.entry_id.split('/')[-1],
            "Timestamp": datetime.now().isoformat()
        }
        if insert_paper(paper_data):
            papers_logged_this_run += 1
            
    print(f"Logged {papers_logged_this_run} new papers.")
    save_last_run_timestamp()


# functions to handle the last run timestamp
def save_last_run_timestamp():
    """Saves the current timestamp to a file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LAST_RUN_TIMESTAMP_FILE, 'w') as f:
        f.write(timestamp)

def get_last_run_timestamp():
    """Retrieves the last run timestamp from a file."""
    if os.path.exists(LAST_RUN_TIMESTAMP_FILE):
        with open(LAST_RUN_TIMESTAMP_FILE, 'r') as f:
            return f.read().strip()
    return None

# bot's main continuous loop function 
def run_scheduled_bot():
    """
    This function contains the main loop for the bot.
    It will run a search, log papers, and then sleep for a set duration.
    This runs in a separate thread so it doesn't block the web server.
    """
    # loads environment variables just for this thread
    load_dotenv() 

    while True:
        try:
            config = load_config()
            arxiv_keywords = config.get("arxiv_keywords", [])
            arxiv_max_results = config.get("arxiv_max_results_per_run", 10)
            sleep_duration_hours = config.get("sleep_duration_hours", 4)
            sleep_duration_seconds = sleep_duration_hours * 3600
        
            current_time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n--- Bot Run Started at {current_time_stamp} ---")

            if not arxiv_keywords:
                print("Error: 'arxiv_keywords' not found or empty in config.json. Skipping this run.")
            else:
                perform_search_and_log(arxiv_keywords, arxiv_max_results)
            
        except Exception as e:
            print(f"An unexpected error occurred during a bot run: {e}")
        finally:
            next_run_time = datetime.now() + timedelta(seconds=sleep_duration_seconds)
            print(f"Bot run finished. Sleeping for {sleep_duration_hours:.1f} hours. Next run expected around {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(sleep_duration_seconds)


# flask Routes (Web Endpoints) 


@app.route('/', methods=['GET'])
def index():
    papers = get_all_papers()
    config = load_config()
    arxiv_keywords = ", ".join(config.get("arxiv_keywords", []))
    
    # gets the last run timestamp and pass it to the template
    last_researched_timestamp = get_last_run_timestamp()
    
    return render_template('index.html', papers=papers, current_keywords=arxiv_keywords, last_researched=last_researched_timestamp)

@app.route('/save_keywords', methods=['POST'])
def save_keywords_route():
    """Handles the form submission to save new keywords to config.json."""
    new_keywords_str = request.form.get('keywords', '')
    new_keywords_list = [kw.strip() for kw in new_keywords_str.split(',') if kw.strip()]
    
    config = load_config()
    config['arxiv_keywords'] = new_keywords_list
    save_config(config)
    
    print(f"Keywords updated to: {new_keywords_list}")
    return redirect(url_for('index'))

@app.route('/fetch_and_log')
def fetch_and_log():
    """Triggers an immediate paper search and logging."""
    config = load_config()
    arxiv_keywords = config.get("arxiv_keywords", [])
    arxiv_max_results = config.get("arxiv_max_results_per_run", 10)
    
    if not arxiv_keywords:
        print("Error: Cannot perform manual fetch. 'arxiv_keywords' not found or empty in config.json.")
    else:
        perform_search_and_log(arxiv_keywords, arxiv_max_results)
        
    return redirect(url_for('index'))

if __name__ == "__main__":
    
    # starts the bot thread
    init_db()
    
    bot_thread = threading.Thread(target=run_scheduled_bot)
    bot_thread.start()
    
    
    print("Starting Flask Research Paper Bot...")
    # starts my web server
    app.run(debug=True)

