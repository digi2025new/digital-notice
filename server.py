from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import sqlite3
import os
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = "YOUR_STRONG_SECRET_KEY"  # Change this to a strong secret key!

# --- Configuration ---
DB_NAME = "noticeboard.db"
UPLOAD_FOLDER = "static/uploads"
# All doc formats + images/videos/audio
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4", "avi", "mov",
                      "mp3", "wav", "pdf", "docx", "pptx", "txt"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

def get_db_connection():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------
# Database Initialization
# ----------------------------------------
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Drop old tables to start fresh
    cur.execute("DROP TABLE IF EXISTS users")
    cur.execute("DROP TABLE IF EXISTS notices")
    # Create users table (for admin login)
    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    # Create notices table (for uploaded notices)
    cur.execute("""
        CREATE TABLE notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            department TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Insert default admin user
    cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "admin123"))
    conn.commit()
    conn.close()

# ----------------------------------------
# Socket.IO Handlers & Real-Time Update
# ----------------------------------------
@socketio.on("connect")
def on_connect():
    print("Client connected")
    emit_notices_update()

@socketio.on("disconnect")
def on_disconnect():
    print("Client disconnected")

def emit_notices_update():
    """Fetch all notices & broadcast them (if needed)"""
    conn = get_db_connection()
    try:
        notices = conn.execute("SELECT * FROM notices ORDER BY timestamp DESC").fetchall()
        notices_list = [dict(n) for n in notices]
        socketio.emit("update_notices", {"notices": notices_list})
    finally:
        conn.close()

# ----------------------------------------
# Helper: Login Required Decorator
# ----------------------------------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------------
# Routes
# ----------------------------------------

@app.route("/")
def index():
    """(Optional) Main slideshow page for all notices."""
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Admin login page."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            return redirect(url_for("admin_panel"))
        else:
            return render_template("login.html", error="Invalid username or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin_panel():
    """Admin panel to manage notices."""
    conn = get_db_connection()
    try:
        notices = conn.execute("SELECT * FROM notices ORDER BY timestamp DESC").fetchall()
    finally:
        conn.close()
    return render_template("admin.html", notices=notices)

@app.route("/upload", methods=["POST"])
@login_required
def upload_notice():
    """Uploads a notice for a specific department."""
    if "file" not in request.files or "department" not in request.form:
        return "Missing file or department", 400

    file = request.files["file"]
    title = request.form["title"]
    department = request.form["department"].lower()

    if file.filename == "":
        return "No file selected", 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        absolute_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(absolute_path)

        # Store relative path for HTML usage
        relative_path = f"static/uploads/{filename}".replace("\\", "/")
        file_type = filename.rsplit(".", 1)[1].lower()
        print("DEBUG: Storing in DB ->", relative_path)

        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO notices (title, file_path, file_type, department)
                VALUES (?, ?, ?, ?)
            """, (title, relative_path, file_type, department))
            conn.commit()
        finally:
            conn.close()

        emit_notices_update()
        return redirect(url_for("admin_panel") + "#existing-notices")
    return "Invalid file type", 400

@app.route("/delete/<int:notice_id>", methods=["POST"])
@login_required
def delete_notice(notice_id):
    """Delete a notice from the DB and remove the file from disk."""
    conn = get_db_connection()
    try:
        notice = conn.execute("SELECT file_path FROM notices WHERE id=?", (notice_id,)).fetchone()
        if notice:
            file_path = notice["file_path"]
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            conn.execute("DELETE FROM notices WHERE id=?", (notice_id,))
            conn.commit()
            emit_notices_update()
            return redirect(url_for("admin_panel") + "#existing-notices")
        else:
            return "Notice not found", 404
    finally:
        conn.close()

# ----------- Department-Specific Routes -----------
# Each department has its own URL: /extc, /it, /cs, /mech
# We'll pass the department param to a single 'department.html' slideshow page

@app.route("/extc")
def show_extc():
    """Slideshow for EXTC department only."""
    return render_template("department.html", department="extc")

@app.route("/it")
def show_it():
    """Slideshow for IT department only."""
    return render_template("department.html", department="it")

@app.route("/cs")
def show_cs():
    """Slideshow for CS department only."""
    return render_template("department.html", department="cs")

@app.route("/mech")
def show_mech():
    """Slideshow for MECH department only."""
    return render_template("department.html", department="mech")

# ----------- Department JSON Endpoint -----------
@app.route("/notices/<department>")
def get_department_notices(department):
    """Returns JSON of notices for a specific department."""
    conn = get_db_connection()
    try:
        notices = conn.execute(
            "SELECT * FROM notices WHERE department=? ORDER BY timestamp DESC",
            (department.lower(),)
        ).fetchall()
        return jsonify([dict(n) for n in notices])
    finally:
        conn.close()

# ----------------------------------------
# Main
# ----------------------------------------
if __name__ == "__main__":
    # Drop and recreate fresh DB tables
    init_db()
    socketio.run(app, debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
