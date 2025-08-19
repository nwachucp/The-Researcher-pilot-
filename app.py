import os
import sqlite3
import arxiv
import time
import schedule
import threading
from flask import Flask, render_template, request, g
from collections import namedtuple
from datetime import datetime, timedelta

Paper = namedtuple('Paper', ['title', 'authors', 'published_date', 'summary', 'pdf_url', 'timestamp'])

# checks for environment variable to set up the database file path
DATABASE = os.environ.get('DATABASE_PATH', 'research.db')
KEYWORDS_FILE = os.environ.get('KEYWORDS_PATH', 'keywords.txt')

app = Flask(__name__)

# my database functions

def get_db():
    """establishes a database connection or returns the existing one."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        # allows for accessing columns by name
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """closes the database connection at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """initializes the database schema without the arxiv_id column."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE NOT NULL,
                authors TEXT,
                published_date TEXT,
                summary TEXT,
                pdf_url TEXT,
                timestamp TEXT
            )
        ''')
        db.commit()
        print(f"Database file located at: {os.path.abspath(DATABASE)}")

def insert_paper(paper):
    """inserts a new paper into the database if it doesn't already exist."""
    try:
        with app.app_context():
            db = get_db()
            cursor = db.cursor()
            cursor.execute('''
                INSERT INTO papers (title, authors, published_date, summary, pdf_url, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (paper.title, paper.authors, paper.published_date, paper.summary, paper.pdf_url, paper.timestamp))
            db.commit()
            return True
    except sqlite3.IntegrityError:
        print(f"Paper with title '{paper.title}' already exists. Skipping insertion.")
        return False

def fetch_papers():
    """Fetches all papers from the database, ordered by log time."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM papers ORDER BY timestamp DESC')
        papers = cursor.fetchall()
        return [Paper(
            title=p['title'],
            authors=p['authors'],
            published_date=p['published_date'],
            summary=p['summary'],
            pdf_url=p['pdf_url'],
            timestamp=p['timestamp']
        ) for p in papers]

# my keyword management functions 

def save_keywords(keywords_string):
    """saves keywords to a file."""
    with open(KEYWORDS_FILE, 'w') as f:
        f.write(keywords_string)
    print(f"Keywords file located at: {os.path.abspath(KEYWORDS_FILE)}")

def load_keywords():
    """loads keywords from a file."""
    if os.path.exists(KEYWORDS_FILE):
        with open(KEYWORDS_FILE, 'r') as f:
            keywords_string = f.read().strip()
            return [k.strip() for k in keywords_string.split(',') if k.strip()]
    return []


# my arXiv bot logic

def search_arxiv(keywords, max_results=20):
    """searches ArXiv for papers matching the given keywords, limited to the last month."""
    # Build the query string by handling single and multi-word keywords
    query_parts = []
    for k in keywords:
        k = k.strip()
        if ' ' in k:
            query_parts.append(f'"{k}"')
        else:
            query_parts.append(k)

    query_string = " OR ".join(query_parts)

    if not query_string:
        return []

    # Should start pulling papers from one month ago to most recent to narrow search
    one_month_ago = datetime.now() - timedelta(days=30)
    query_string = f"({query_string}) AND submittedDate:[{one_month_ago.strftime('%Y%m%d')} TO {datetime.now().strftime('%Y%m%d')}]"
    
    try:
        search = arxiv.Search(
            query=query_string,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        return list(search.results())
    except Exception as e:
        print(f"An error occurred while searching ArXiv: {e}")
        return []

def perform_search_and_log():
    """performs the ArXiv search and logs new papers to the database."""
    print(f"[{datetime.now()}] Performing scheduled search...")
    keywords = load_keywords()
    if not keywords:
        print("no keywords found. Skipping search.")
        return

    papers = search_arxiv(keywords)
    for paper in papers:

        new_paper = Paper(
            title=paper.title,
            authors=", ".join(author.name for author in paper.authors),
            published_date=paper.published.strftime('%Y-%m-%d'),
            summary=paper.summary,
            pdf_url=paper.pdf_url,
            timestamp=datetime.now().strftime('%Y-%m-%S')
        )
        insert_paper(new_paper)

# flask app routes

@app.route('/')
def index():
    """renders the new landing page."""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """renders the main bot dashboard with logged papers and current keywords."""
    init_db()
    papers = fetch_papers()
    current_keywords = ",".join(load_keywords())
    last_researched = None
    if papers:
        last_researched = papers[0].timestamp
    return render_template('dashboard.html', papers=papers, current_keywords=current_keywords, last_researched=last_researched)


@app.route('/save_keywords', methods=['POST'])
def save_keywords_route():
    """handles saving new keywords from the form."""
    keywords_string = request.form.get('keywords', '')
    save_keywords(keywords_string)
    # redirect to the dashboard after saving
    return app.redirect('/dashboard')

@app.route('/fetch_and_log')
def fetch_and_log():
    """manually triggers a search and log."""
    perform_search_and_log()
    return app.redirect('/dashboard')

def run_scheduled_bot():
    """runs the scheduled bot in a separate thread."""
    while True:
        schedule.run_pending()
        time.sleep(1)
# schedules my bot to check for new papers every hour, then start a background thread to run the schedule
schedule.every(1).hour.do(perform_search_and_log)
with app.app_context():
    init_db()

bot_thread = threading.Thread(target=run_scheduled_bot, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')



