from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import sqlite3
import os
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = "YOUR_SECRET_KEY"  # Change this to a strong, random key!

# --- Configuration ---
DB_NAME = 'noticeboard.db'
UPLOAD_FOLDER = 'static/uploads'  # Directory to store uploaded files
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'mp3', 'wav', 'pdf', 'docx', 'pptx', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- SocketIO ---
socketio = SocketIO(app, cors_allowed_origins="*")

def get_db_connection():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def test_connect():
    print('Client connected')
    emit('my_response', {'data': 'Connected successfully!'})

@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected')

# --- Real-time Update Helper Function ---
def emit_notices_update():
    conn = get_db_connection()
    try:
        notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
        notices_list = [dict(notice) for notice in notices]
        socketio.emit('update_notices', {'notices': notices_list})
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
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
    conn = get_db_connection()
    try:
        notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        return "Database error. Check logs.", 500
    finally:
        conn.close()
    return render_template('index.html', notices=notices)

@app.route('/notices')
def get_notices():
    conn = get_db_connection()
    try:
        notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
        notices_list = [dict(notice) for notice in notices]
        return jsonify(notices_list)
    finally:
        conn.close()

@app.route('/notices/<department>')
def get_department_notices(department):
    conn = get_db_connection()
    try:
        notices = conn.execute('SELECT * FROM notices WHERE department = ? ORDER BY timestamp DESC', (department,)).fetchall()
        notices_list = [dict(notice) for notice in notices]
        return jsonify(notices_list)
    finally:
        conn.close()

@app.route('/admin')
@login_required
def admin():
    conn = get_db_connection()
    try:
        notices = conn.execute('SELECT * FROM notices ORDER BY timestamp DESC').fetchall()
    finally:
        conn.close()
    return render_template('admin.html', notices=notices)

@app.route('/notices', methods=['POST'])
@login_required
def add_notice():
    """Adds a new notice and redirects to #existing-notices to avoid jumping to top."""
    if 'file' not in request.files or 'department' not in request.form:
        return "Missing file or department field", 400

    file = request.files['file']
    title = request.form['title']
    department = request.form['department'].lower()

    if file.filename == '':
        return "No selected file"

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        absolute_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(absolute_path)

        relative_path = f"static/uploads/{filename}".replace("\\", "/")
        file_type = filename.rsplit('.', 1)[1].lower()
        print("DEBUG: Storing in DB ->", relative_path)

        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO notices (title, file_path, file_type, department) VALUES (?, ?, ?, ?)',
                (title, relative_path, file_type, department)
            )
            conn.commit()
            emit_notices_update()
        finally:
            conn.close()

        # Redirect to the admin page and jump to the "existing-notices" section
        return redirect(url_for('admin') + '#existing-notices')

    return "Invalid file type"

@app.route('/notices/<int:notice_id>/delete', methods=['POST'])
@login_required
def delete_notice(notice_id):
    """Deletes a notice and also redirects to #existing-notices."""
    conn = get_db_connection()
    try:
        notice = conn.execute('SELECT * FROM notices WHERE id = ?', (notice_id,)).fetchone()
        if notice:
            file_path = notice['file_path']
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            conn.execute('DELETE FROM notices WHERE id = ?', (notice_id,))
            conn.commit()
            emit_notices_update()

            # Redirect to #existing-notices so the user sees the updated list
            return redirect(url_for('admin') + '#existing-notices')
        else:
            return "Notice not found"
    finally:
        conn.close()

@app.route('/department/<department>')
def show_department_notices(department):
    dept_lower = department.lower()
    conn = get_db_connection()
    try:
        notices = conn.execute(
            'SELECT * FROM notices WHERE lower(department) = ? ORDER BY timestamp DESC',
            (dept_lower,)
        ).fetchall()
    finally:
        conn.close()
    return render_template('department.html', notices=notices, department=department)

if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
