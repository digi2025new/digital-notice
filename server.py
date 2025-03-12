from flask import Flask, request, render_template, redirect, url_for, session, jsonify
import sqlite3
import os
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = "YOUR_SECRET_KEY"  # Change this to a strong secret key

# Database configuration
DB_NAME = 'noticeboard.db'

# File upload configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'mp3', 'wav', 'pdf', 'docx', 'pptx', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Enable WebSockets for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

# ----------------------------------------
# 🚀 DATABASE CONNECTION & FUNCTIONS
# ----------------------------------------
def get_db_connection():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def emit_notices_update():
    """ Sends real-time updates to all connected clients """
    conn = get_db_connection()
    try:
        notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
        notices_list = [dict(notice) for notice in notices]
        socketio.emit('update_notices', {'notices': notices_list})
    finally:
        conn.close()

# ----------------------------------------
# 🏠 HOME PAGE (SHOW NOTICES)
# ----------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

# ----------------------------------------
# 🔐 ADMIN LOGIN
# ----------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'dbit.in' and password == 'dbit@123':
            session['admin'] = True
            return redirect(url_for('admin'))

        return "Invalid credentials! Try again."

    return render_template('login.html')

# ----------------------------------------
# 🚪 LOGOUT
# ----------------------------------------
@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

# ----------------------------------------
# 🛠️ ADMIN PANEL (UPLOAD & DELETE NOTICES)
# ----------------------------------------
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    conn.close()
    return render_template('admin.html', notices=notices)

# ----------------------------------------
# 📤 UPLOAD NOTICE
# ----------------------------------------
@app.route('/upload', methods=['POST'])
def upload():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if 'file' not in request.files:
        return "No file uploaded!", 400

    file = request.files['file']
    title = request.form.get('title', 'Untitled Notice')

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        file_type = filename.rsplit('.', 1)[1].lower()

        conn = get_db_connection()
        conn.execute('INSERT INTO notices (title, file_path, file_type) VALUES (?, ?, ?)',
                     (title, filepath, file_type))
        conn.commit()
        conn.close()

        emit_notices_update()
        return redirect(url_for('admin'))

    return "Invalid file type!", 400

# ----------------------------------------
# 🗑️ DELETE NOTICE
# ----------------------------------------
@app.route('/delete/<int:notice_id>', methods=['POST'])
def delete_notice(notice_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    notice = conn.execute('SELECT file_path FROM notices WHERE id = ?', (notice_id,)).fetchone()
    
    if notice:
        os.remove(notice['file_path'])  # Delete the file from the server
        conn.execute('DELETE FROM notices WHERE id = ?', (notice_id,))
        conn.commit()
    
    conn.close()
    emit_notices_update()
    return redirect(url_for('admin'))

# ----------------------------------------
# 📰 GET NOTICES (JSON for JavaScript)
# ----------------------------------------
@app.route('/notices')
def get_notices():
    conn = get_db_connection()
    notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    conn.close()
    return jsonify([dict(notice) for notice in notices])

# ----------------------------------------
# 🔗 WEBSOCKET EVENTS
# ----------------------------------------
@socketio.on('connect')
def client_connect():
    print("Client connected!")
    emit_notices_update()

@socketio.on('disconnect')
def client_disconnect():
    print("Client disconnected!")

# ----------------------------------------
# 🚀 INITIALIZE DATABASE (RUN ONCE)
# ----------------------------------------
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()  # Ensures the database is ready
    socketio.run(app, debug=False, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
