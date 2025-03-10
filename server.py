# server.py
from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename  # for secure file uploads
from flask_socketio import SocketIO, emit  # For real-time updates

app = Flask(__name__)
app.secret_key = "YOUR_SECRET_KEY"  # Change this to a strong, random key!

# --- Configuration ---
DB_NAME = 'noticeboard.db'
UPLOAD_FOLDER = 'static/uploads'  # Directory to store uploaded files
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mp3', 'txt'}  # Allowed file types
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Create the upload folder if it doesn't exist

# --- SocketIO ---
socketio = SocketIO(app)  # Initialize SocketIO

def get_db_connection():
    # Use an absolute path for the database file
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)  # Absolute path here too
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def test_connect():
    print('Client connected')
    emit('my response', {'data': 'Connected!'})  # Send a message back to the client

# --- Helper function to emit update ---
def emit_notices_update():
    socketio.emit('update_notices', {'data': 'Notices updated'})

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # IMPORTANT: Hash in a real app

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                            (username, password)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    print("Running Index")  # Debugging check

    conn = get_db_connection()

    try:
        notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        conn.close()
        return "Database error. Check the console for details.", 500  # Return an error page

    conn.close()
    print(f"Notices from db: {notices}")  # Debugging: print notices retrieved

    return render_template('index.html', notices=notices)

@app.route('/notices')
def get_notices():
    conn = get_db_connection()
    notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    conn.close()
    notices_list = [dict(notice) for notice in notices]  # Convert Row objects to dictionaries
    return jsonify(notices_list) # returns json list


@app.route('/admin')
@login_required  # Protect the admin route
def admin():
    conn = get_db_connection()
    notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    conn.close()
    return render_template('admin.html', notices=notices)

@app.route('/notices', methods=['POST'])
@login_required
def add_notice():
    if 'file' not in request.files:
        return "No file part"

    file = request.files['file']
    title = request.form['title']

    if file.filename == '':
        return "No selected file"

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        file_type = filename.rsplit('.', 1)[1].lower()  # extract extension as file type

        conn = get_db_connection()
        conn.execute('INSERT INTO notices (title, file_path, file_type) VALUES (?, ?, ?)',
                     (title, file_path, file_type))
        conn.commit()
        conn.close()

        emit_notices_update()  # Send update to the display side
        return redirect(url_for('admin'))

    return "Invalid file type"

@app.route('/notices/<int:notice_id>/delete', methods=['POST'])
@login_required
def delete_notice(notice_id):
    conn = get_db_connection()
    notice = conn.execute('SELECT * FROM notices WHERE id = ?', (notice_id,)).fetchone()

    if notice:
        file_path = notice['file_path']
        if file_path and os.path.exists(file_path):
            os.remove(file_path)  # Delete the file from the server

        conn.execute('DELETE FROM notices WHERE id = ?', (notice_id,))
        conn.commit()
        conn.close()

        emit_notices_update()  # Send update to the display side
        return redirect(url_for('admin'))
    else:
        conn.close()
        return "Notice not found"

# --- Run the App ---
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')  # Use socketio.run instead of app.run
