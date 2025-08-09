import json
import arxiv
import os
from datetime import datetime, timedelta
import time
import csv
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
# NEW: Import the threading module to run the bot in a separate process
import threading

# --- Flask Application Setup ---
# Initialize the Flask application
app = Flask(__name__)
# Define the name of the SQLite database file
DATABASE = 'papers.db'

# --- Database Functions ---
# These functions handle all interactions with the SQLite database.

def init_db():
    """Initializes the SQLite database and creates the papers table if it doesn't exist."""
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
        # Commit the changes to the database
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
                # The values to be inserted, corresponding to the '?' placeholders
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
            # This block handles the error if a paper with the same arxiv_url or arxiv_id already exists
            print(f"Skipping already logged paper (DB check): {paper_data['Title']} - {e}")
            return False
        except Exception as e:
            # General error handling for any other issues during insertion
            print(f"Error logging to DB: {e}")
            return False

def get_all_papers():
    """Retrieves all paper records from the database."""
    with sqlite3.connect(DATABASE) as conn:
        # Set the row_factory to sqlite3.Row to get dictionary-like objects
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # SQL command to select all papers, ordered by published date in descending order
        cursor.execute('SELECT * FROM papers ORDER BY published_date DESC')
        # Convert the fetched rows into a list of dictionaries
        return [dict(row) for row in cursor.fetchall()]

# --- Configuration Functions ---
# These functions manage the 'config.json' file for keywords and settings.

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

# --- ArXiv Search Function ---
def search_arxiv(keywords, max_results):
    """Searches ArXiv for papers based on provided keywords."""
    # Format the keywords into a query string for the ArXiv API
    query_string = " OR ".join([f"all:{keyword}" for keyword in keywords])
    client = arxiv.Client()
    # Create a search object with the specified query, max results, and sorting
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

# --- NEW: Bot's main continuous loop function ---
def run_scheduled_bot():
    """
    This function contains the main loop for the bot.
    It will run a search, log papers, and then sleep for a set duration.
    This runs in a separate thread so it doesn't block the web server.
    """
    # Load environment variables just for this thread
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
                print(f"Searching ArXiv for papers with keywords: {', '.join(arxiv_keywords)} (Max results: {arxiv_max_results})")
                papers_found = search_arxiv(arxiv_keywords, arxiv_max_results)
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
                
                print(f"Logged {papers_logged_this_run} new papers in this run.")

        except Exception as e:
            print(f"An unexpected error occurred during a bot run: {e}")
        finally:
            next_run_time = datetime.now() + timedelta(seconds=sleep_duration_seconds)
            print(f"Bot run finished. Sleeping for {sleep_duration_hours:.1f} hours. Next run expected around {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(sleep_duration_seconds)


# --- Flask Routes (Web Endpoints) ---
@app.route('/', methods=['GET'])
def index():
    """Main page to display logged papers and manage keywords."""
    papers = get_all_papers()
    config = load_config()
    arxiv_keywords = ", ".join(config.get("arxiv_keywords", []))
    return render_template('index.html', papers=papers, current_keywords=arxiv_keywords)

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
    """Confirms that the bot is running in the background and redirects to the main page."""
    print("Manual trigger received. The bot is running on a schedule in the background.")
    return redirect(url_for('index'))


# --- Main Execution Block ---
# This block ensures the code runs only when the script is executed directly.

if __name__ == "__main__":
    # NEW: Create a new thread for the bot's scheduled logic
    bot_thread = threading.Thread(target=run_scheduled_bot)
    
    # Start the bot thread. It will now run in the background.
    bot_thread.start()
    
    # Initialize the database before the application starts
    init_db()
    
    print("Starting Flask Research Paper Bot...")
    # Run the Flask development server in the main thread
    app.run(debug=True, host='0.0.0.0', port=5000)
