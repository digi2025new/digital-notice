# create_db.py
import sqlite3
import os

DB_NAME = 'noticeboard.db'  # Define the database name

def create_db():
    # Use an absolute path for the database file
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)  # Corrected path
    cursor = conn.cursor()

    # Users table (for admin login)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL  -- IMPORTANT: Hash this in a real application!
        )
    ''')

    # Notices table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,  -- For text-based notices
            file_path TEXT, -- Path to the file (image, video, audio)
            file_type TEXT NOT NULL, -- 'image', 'video', 'audio', 'text'
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert a default admin user (CHANGE the password in the database after running this!)
    cursor.execute("INSERT OR IGNORE INTO users (username, password) VALUES ('admin', 'password')")

    conn.commit()
    conn.close()
    print("Database created/updated successfully!") # Confirmation message
    print(f"Database located at: {db_path}")


# Call this when your app starts for the first time (or when you need to reset the database)
if __name__ == '__main__':
    create_db()
