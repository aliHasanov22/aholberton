#!/usr/bin/python3
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, time
import math
from sqlalchemy import func

app = Flask(__name__)
# Secret key is required for secure sessions
app.config['SECRET_KEY'] = 'holberton-secret-key-999'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///planner.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- LOGIN MANAGER CONFIGURATION ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 📍 CONFIGURATION ---
CAMPUS_LAT = 40.40663934042372
CAMPUS_LON = 49.848206791133954
MAX_DISTANCE_METERS = 50

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True)
    attendance = db.relationship('Attendance', backref='owner', lazy=True)
    study_sessions = db.relationship('StudySession', backref='owner', lazy=True)
    summaries = db.relationship('WeeklyTaskSummary', backref='owner', lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.String(20), default='Medium')
    status = db.Column(db.String(20), default='Pending')
    start_date = db.Column(db.String(20), nullable=True)
    due_date = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'priority': self.priority,
            'status': self.status, 'start_date': self.start_date, 'due_date': self.due_date
        }

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return { 'subject': self.subject, 'duration': self.duration_minutes }

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    entry_time = db.Column(db.String(10), nullable=False) 
    exit_time = db.Column(db.String(10), nullable=False)  
    valid_hours = db.Column(db.Float, nullable=False)     

    def to_dict(self):
        return {
            'date': self.date.strftime('%Y-%m-%d'),
            'entry': self.entry_time, 'exit': self.exit_time, 'hours': self.valid_hours
        }

class WeeklyTaskSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    total_tasks = db.Column(db.Integer, nullable=False, default=0)
    completed_tasks = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'week_start': self.week_start.strftime('%Y-%m-%d'),
            'total_tasks': self.total_tasks, 'completed_tasks': self.completed_tasks
        }

# --- HELPERS ---
def get_distance_meters(lat1, lon1, lat2, lon2):
    R = 6371000  
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
    
def calculate_valid_hours(entry_str, exit_str):
    START_LIMIT, END_LIMIT = time(8, 0), time(18, 0)
    fmt = '%H:%M'
    try:
        t_entry = datetime.strptime(entry_str, fmt).time()
        t_exit = datetime.strptime(exit_str, fmt).time()
        effective_entry, effective_exit = max(t_entry, START_LIMIT), min(t_exit, END_LIMIT)
        if effective_entry >= effective_exit: return 0.0
        dt_entry = datetime.combine(datetime.min, effective_entry)
        dt_exit = datetime.combine(datetime.min, effective_exit)
        return round((dt_exit - dt_entry).total_seconds() / 3600, 2)
    except: return 0.0

def get_week_start(date_value):
    return date_value - timedelta(days=date_value.weekday())

def compute_weekly_task_summary(week_start, user_id):
    week_end = week_start + timedelta(days=7)
    tasks = Task.query.filter(
        Task.user_id == user_id,
        Task.created_at >= datetime.combine(week_start, time.min),
        Task.created_at < datetime.combine(week_end, time.min)
    ).all()
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.status == 'Completed')
    return total_tasks, completed_tasks

def ensure_weekly_summaries(user_id):
    today = datetime.utcnow().date()
    current_week_start = get_week_start(today)
    latest_summary = WeeklyTaskSummary.query.filter_by(user_id=user_id).order_by(WeeklyTaskSummary.week_start.desc()).first()

    if latest_summary is None:
        prev_start = current_week_start - timedelta(days=7)
        total, completed = compute_weekly_task_summary(prev_start, user_id)
        db.session.add(WeeklyTaskSummary(user_id=user_id, week_start=prev_start, total_tasks=total, completed_tasks=completed))
        db.session.commit()
        return

    week_cursor = latest_summary.week_start + timedelta(days=7)
    while week_cursor < current_week_start:
        total, completed = compute_weekly_task_summary(week_cursor, user_id)
        db.session.add(WeeklyTaskSummary(user_id=user_id, week_start=week_cursor, total_tasks=total, completed_tasks=completed))
        week_cursor += timedelta(days=7)
    db.session.commit()

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Login failed. Check credentials.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'))
        new_user = User(username=request.form.get('username'), password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- APP ROUTES ---
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/api/tasks', methods=['GET'])
@login_required
def get_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    return jsonify([task.to_dict() for task in tasks])

@app.route('/api/tasks', methods=['POST'])
@login_required
def add_task():
    data = request.json
    new_task = Task(
        user_id=current_user.id, title=data['title'], 
        priority=data.get('priority', 'Medium'),
        start_date=data.get('start_date'), due_date=data.get('due_date')
    )
    db.session.add(new_task)
    db.session.commit()
    return jsonify(new_task.to_dict()), 201

@app.route('/api/tasks/<int:id>/toggle', methods=['PUT'])
@login_required
def toggle_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    task.status = 'Completed' if task.status == 'Pending' else 'Pending'
    db.session.commit()
    return jsonify(task.to_dict())

@app.route('/api/tasks/weekly-summary', methods=['GET'])
@login_required
def task_weekly_summary():
    ensure_weekly_summaries(current_user.id)
    summaries = WeeklyTaskSummary.query.filter_by(user_id=current_user.id).order_by(WeeklyTaskSummary.week_start.asc()).all()
    today = datetime.utcnow().date()
    curr_start = get_week_start(today)
    total, completed = compute_weekly_task_summary(curr_start, current_user.id)
    response = [s.to_dict() for s in summaries]
    if not summaries or summaries[-1].week_start != curr_start:
        response.append({'week_start': curr_start.strftime('%Y-%m-%d'), 'total_tasks': total, 'completed_tasks': completed})
    return jsonify(response)

@app.route('/api/tasks/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    task = Task.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Deleted'})

@app.route('/api/study', methods=['POST'])
@login_required
def log_study_session():
    data = request.json
    new_session = StudySession(user_id=current_user.id, subject=data['subject'], duration_minutes=data['duration'])
    db.session.add(new_session)
    db.session.commit()
    return jsonify(new_session.to_dict()), 201

@app.route('/api/attendance/check-location', methods=['POST'])
@login_required
def check_location():
    data = request.json
    dist = get_distance_meters(data.get('lat'), data.get('lon'), CAMPUS_LAT, CAMPUS_LON)
    if dist <= MAX_DISTANCE_METERS:
        return jsonify({'status': 'allowed', 'distance': round(dist, 2), 'time': datetime.now().strftime('%H:%M'), 'message': f'✅ Access Granted!'})
    return jsonify({'status': 'denied', 'message': f'❌ Too far! ({int(dist)}m)'}), 403

@app.route('/admin')
@login_required #<-- Uncomment this when your login system is active
def admin_dashboard():
    users = User.query.all()
    student_data = []
    
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())

    # Variables for top cards
    total_students = len(users)
    under_quota_count = 0
    total_weekly_hours = 0

    for student in users:
        logs = Attendance.query.filter(
            Attendance.user_id == student.id, 
            Attendance.date >= start_of_week
        ).all()
        
        total_hrs = sum(log.valid_hours for log in logs)
        total_weekly_hours += total_hrs
        
        if total_hrs < 15:
            under_quota_count += 1
            
        student_data.append({
            'username': student.username,
            'hours': round(total_hrs, 2),
            'logs_count': len(logs)
        })

    avg_hours = round(total_weekly_hours / total_students, 1) if total_students > 0 else 0

    return render_template('admin.html', 
                           students=student_data, 
                           total_students=total_students, 
                           under_quota=under_quota_count,
                           avg_hours=avg_hours)

@app.route('/api/attendance', methods=['GET'])
@login_required
def get_attendance():
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    logs = Attendance.query.filter(Attendance.user_id == current_user.id, Attendance.date >= start_of_week)\
                           .order_by(Attendance.date.desc()).all()
    return jsonify({'logs': [log.to_dict() for log in logs], 'total_hours': round(sum(l.valid_hours for l in logs), 2)})

@app.route('/api/attendance', methods=['POST'])
@login_required
def add_attendance():
    data = request.json
    log_date = datetime.strptime(data['date'], '%Y-%m-%d').date() if data.get('date') else datetime.utcnow().date()
    if log_date.weekday() > 4: return jsonify({'error': 'Weekends not allowed'}), 400
    hours = calculate_valid_hours(data['entry'], data['exit'])
    new_log = Attendance(user_id=current_user.id, date=log_date, entry_time=data['entry'], exit_time=data['exit'], valid_hours=hours)
    db.session.add(new_log)
    db.session.commit()
    return jsonify(new_log.to_dict())

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
