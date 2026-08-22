import os
import re
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Attendance, LeaveRequest

UPLOAD_FOLDER = 'static/uploads/profile_pics'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dayflow-secure-session-key-9f2b8c9d'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Limit to 2MB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dayflow.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure upload folder exists
os.makedirs(os.path.join(app.root_path, UPLOAD_FOLDER), exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def is_password_strong(password):
    if len(password) < 8:
        return False
    if not re.search("[a-z]", password) or not re.search("[A-Z]", password):
        return False
    if not re.search("[0-9]", password):
        return False
    if not re.search("[^A-Za-z0-9]", password):
        return False
    return True

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Validation checks
        if not employee_id or not email or not password or not role:
            flash('All fields are required.', 'error')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(employee_id=employee_id).first():
            flash('Employee ID is already registered.', 'error')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(email=email).first():
            flash('Email is already registered.', 'error')
            return redirect(url_for('signup'))
            
        if not is_password_strong(password):
            flash('Password does not meet complexity requirements.', 'error')
            return redirect(url_for('signup'))
            
        # Create and save new user
        new_user = User(
            employee_id=employee_id,
            email=email,
            role=role,
            is_verified=False
        )
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Email verification link sent.', 'success')
            login_user(new_user, remember=True)
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('signup'))
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        remember = True if request.form.get('remember_me') else False
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            flash('Incorrect email or password. Please try again.', 'error')
            return redirect(url_for('login'))
            
        login_user(user, remember=remember)
        return redirect(url_for('dashboard'))
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'HR':
        # HR/Admin Dashboard
        employees = User.query.filter(User.role != 'HR').all()
        two_weeks_ago = date.today() - timedelta(days=14)
        attendance_logs = Attendance.query.filter(Attendance.date >= two_weeks_ago).order_by(Attendance.date.desc(), Attendance.check_in.desc()).all()
        pending_leaves = LeaveRequest.query.filter_by(status='Pending').all()
        return render_template('dashboard.html', 
                               employees=employees, 
                               attendance_logs=attendance_logs, 
                               pending_leaves=pending_leaves,
                               date_today=date.today())
    else:
        # Employee Dashboard
        today_record = Attendance.query.filter_by(user_id=current_user.id, date=date.today()).first()
        my_attendance = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.date.desc()).limit(10).all()
        my_leaves = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.start_date.desc()).all()
        
        # Calculate summary numbers
        total_present = Attendance.query.filter_by(user_id=current_user.id, status='Present').count()
        total_half_days = Attendance.query.filter_by(user_id=current_user.id, status='Half-day').count()
        approved_leaves = LeaveRequest.query.filter_by(user_id=current_user.id, status='Approved').all()
        leave_days_taken = sum((l.end_date - l.start_date).days + 1 for l in approved_leaves)
        
        # Recent activities (dynamic lists of alerts)
        activities = []
        if today_record:
            if today_record.check_out:
                activities.append(f"Checked out today at {today_record.check_out.strftime('%I:%M %p')}.")
            else:
                activities.append(f"Checked in today at {today_record.check_in.strftime('%I:%M %p')}.")
        for l in my_leaves[:5]:
            status_symbol = "✅" if l.status == 'Approved' else "❌" if l.status == 'Rejected' else "⏳"
            activities.append(f"{status_symbol} Leave request ({l.leave_type}) for {l.start_date.strftime('%b %d')} is {l.status}.")
            
        return render_template('dashboard.html', 
                               today_record=today_record, 
                               my_attendance=my_attendance, 
                               my_leaves=my_leaves,
                               total_present=total_present,
                               total_half_days=total_half_days,
                               leave_days_taken=leave_days_taken,
                               activities=activities)

@app.route('/simulate-verification', methods=['POST'])
@login_required
def simulate_verification():
    user = User.query.get(current_user.id)
    if user:
        user.is_verified = True
        db.session.commit()
        flash('Email verified successfully!', 'success')
    return redirect(url_for('dashboard'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    return handle_profile_view_or_edit(current_user.id)

@app.route('/profile/<int:user_id>', methods=['GET', 'POST'])
@login_required
def admin_view_profile(user_id):
    if current_user.role != 'HR':
        flash('Access denied. You do not have permissions to view other profiles.', 'error')
        return redirect(url_for('dashboard'))
    return handle_profile_view_or_edit(user_id)

def handle_profile_view_or_edit(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        if current_user.role == 'HR':
            user.full_name = request.form.get('full_name', '').strip()
            user.employee_id = request.form.get('employee_id', '').strip()
            user.department = request.form.get('department', '').strip()
            user.job_title = request.form.get('job_title', '').strip()
            
            salary_val = request.form.get('salary', '').strip()
            if salary_val:
                try:
                    user.salary = float(salary_val)
                except ValueError:
                    flash('Invalid salary amount.', 'error')
            else:
                user.salary = None
        
        user.phone = request.form.get('phone', '').strip()
        user.address = request.form.get('address', '').strip()
        
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = secure_filename(f"{user.id}_{file.filename}")
                    file_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    user.profile_pic = filename
                else:
                    flash('Invalid image format. Allowed formats: PNG, JPG, JPEG, GIF', 'error')
                    return redirect(request.referrer or url_for('dashboard'))

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'error')
            
        return redirect(request.referrer or url_for('dashboard'))

    return render_template('profile.html', profile_user=user)

@app.route('/check-in', methods=['POST'])
@login_required
def check_in():
    today_record = Attendance.query.filter_by(user_id=current_user.id, date=date.today()).first()
    if today_record:
        flash('You are already checked in for today.', 'error')
        return redirect(url_for('dashboard'))
    
    new_record = Attendance(
        user_id=current_user.id,
        date=date.today(),
        check_in=datetime.now(),
        status='Present'
    )
    db.session.add(new_record)
    db.session.commit()
    flash('Checked in successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/check-out', methods=['POST'])
@login_required
def check_out():
    today_record = Attendance.query.filter_by(user_id=current_user.id, date=date.today()).first()
    if not today_record:
        flash('You need to check in first.', 'error')
        return redirect(url_for('dashboard'))
    if today_record.check_out:
        flash('You have already checked out for today.', 'error')
        return redirect(url_for('dashboard'))
    
    today_record.check_out = datetime.now()
    delta = today_record.check_out - today_record.check_in
    # Set to Half-day if shift is under 4 hours
    if delta.total_seconds() < 4 * 3600:
        today_record.status = 'Half-day'
        flash('Checked out. Shift status marked as Half-day due to short duration.', 'warning')
    else:
        today_record.status = 'Present'
        flash('Checked out successfully. Have a great evening!', 'success')
        
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/apply-leave', methods=['POST'])
@login_required
def apply_leave():
    leave_type = request.form.get('leave_type')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    remarks = request.form.get('remarks', '').strip()
    
    if not leave_type or not start_date_str or not end_date_str:
        flash('All fields are required to apply for leave.', 'error')
        return redirect(url_for('dashboard'))
        
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('dashboard'))
        
    if start_date < date.today():
        flash('Start date cannot be in the past.', 'error')
        return redirect(url_for('dashboard'))
        
    if end_date < start_date:
        flash('End date cannot be before start date.', 'error')
        return redirect(url_for('dashboard'))
        
    new_leave = LeaveRequest(
        user_id=current_user.id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        remarks=remarks,
        status='Pending'
    )
    db.session.add(new_leave)
    db.session.commit()
    flash('Leave application submitted successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/leave-action/<int:leave_id>', methods=['POST'])
@login_required
def leave_action(leave_id):
    if current_user.role != 'HR':
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
        
    leave = LeaveRequest.query.get_or_404(leave_id)
    action = request.form.get('action') # 'approve' or 'reject'
    admin_comments = request.form.get('admin_comments', '').strip()
    
    if action == 'approve':
        leave.status = 'Approved'
        leave.admin_comments = admin_comments
        
        # Populate Leave status in Attendance records for those dates
        curr_date = leave.start_date
        while curr_date <= leave.end_date:
            if curr_date.weekday() < 5: # Skip weekends
                att = Attendance.query.filter_by(user_id=leave.user_id, date=curr_date).first()
                if att:
                    att.status = 'Leave'
                else:
                    att = Attendance(user_id=leave.user_id, date=curr_date, status='Leave')
                    db.session.add(att)
            curr_date += timedelta(days=1)
            
        flash(f'Leave request for {leave.user.full_name} has been approved.', 'success')
    elif action == 'reject':
        leave.status = 'Rejected'
        leave.admin_comments = admin_comments
        flash(f'Leave request for {leave.user.full_name} has been rejected.', 'info')
    else:
        flash('Invalid action.', 'error')
        
    db.session.commit()
    return redirect(url_for('dashboard'))

# Database initialization & seeding
with app.app_context():
    db.create_all()
    
    # 1. Seed HR User (Indian details)
    if not User.query.filter_by(email='admin@dayflow.com').first():
        admin = User(
            employee_id='HR001', 
            email='admin@dayflow.com', 
            role='HR', 
            is_verified=True, 
            full_name='Meera Nair',
            job_title='HR Manager',
            department='HR & Operations',
            phone='+91 98450 12345',
            address='Koramangala 4th Block, Bengaluru, Karnataka 560034',
            salary=95000.0
        )
        admin.set_password('Admin123!')
        db.session.add(admin)
        
    # 2. Seed Default Employee User (Indian details)
    if not User.query.filter_by(email='employee@dayflow.com').first():
        emp = User(
            employee_id='EMP001', 
            email='employee@dayflow.com', 
            role='Employee', 
            is_verified=True, 
            full_name='Rajesh Kumar',
            job_title='Junior Developer',
            department='Engineering',
            phone='+91 91234 56789',
            address='Andheri East, Mumbai, Maharashtra 400069',
            salary=55000.0
        )
        emp.set_password('Employee123!')
        db.session.add(emp)

    # 3. Seed Alice Smith (Indian details)
    if not User.query.filter_by(email='alice@dayflow.com').first():
        alice = User(
            employee_id='EMP002', 
            email='alice@dayflow.com', 
            role='Employee', 
            is_verified=True, 
            full_name='Aaradhya Sharma',
            job_title='UI/UX Designer',
            department='Product Design',
            phone='+91 99887 76655',
            address='Connaught Place, New Delhi, Delhi 110001',
            salary=68000.0
        )
        alice.set_password('Employee123!')
        db.session.add(alice)

    # 4. Seed Bob Johnson (Indian details)
    if not User.query.filter_by(email='bob@dayflow.com').first():
        bob = User(
            employee_id='EMP003', 
            email='bob@dayflow.com', 
            role='Employee', 
            is_verified=True, 
            full_name='Amit Patel',
            job_title='Software Engineer',
            department='Engineering',
            phone='+91 88776 65544',
            address='Satellite Road, Ahmedabad, Gujarat 380015',
            salary=85000.0
        )
        bob.set_password('Employee123!')
        db.session.add(bob)

    # 5. Seed Charlie Brown (Indian details)
    if not User.query.filter_by(email='charlie@dayflow.com').first():
        charlie = User(
            employee_id='EMP004', 
            email='charlie@dayflow.com', 
            role='Employee', 
            is_verified=True, 
            full_name='Karan Johar',
            job_title='HR Specialist',
            department='HR & Operations',
            phone='+91 77665 54433',
            address='Salt Lake Sector V, Kolkata, West Bengal 700091',
            salary=62000.0
        )
        charlie.set_password('Employee123!')
        db.session.add(charlie)

    db.session.commit()

    # 6. Seed Attendance logs for past 5 days
    if Attendance.query.count() == 0:
        employees = User.query.filter(User.role == 'Employee').all()
        today = date.today()
        
        for i in range(1, 6):
            check_date = today - timedelta(days=i)
            if check_date.weekday() >= 5:
                continue
                
            for emp in employees:
                if emp.employee_id == 'EMP002' and i == 2:
                    att = Attendance(
                        user_id=emp.id,
                        date=check_date,
                        status='Absent'
                    )
                elif emp.employee_id == 'EMP003' and i == 3:
                    check_in_time = datetime.combine(check_date, datetime.min.time()) + timedelta(hours=9, minutes=15)
                    check_out_time = datetime.combine(check_date, datetime.min.time()) + timedelta(hours=13, minutes=30)
                    att = Attendance(
                        user_id=emp.id,
                        date=check_date,
                        check_in=check_in_time,
                        check_out=check_out_time,
                        status='Half-day'
                    )
                else:
                    check_in_time = datetime.combine(check_date, datetime.min.time()) + timedelta(hours=8, minutes=50 + hash(emp.employee_id) % 25)
                    check_out_time = datetime.combine(check_date, datetime.min.time()) + timedelta(hours=17, minutes=hash(emp.employee_id) % 30)
                    att = Attendance(
                        user_id=emp.id,
                        date=check_date,
                        check_in=check_in_time,
                        check_out=check_out_time,
                        status='Present'
                    )
                db.session.add(att)
        
        # Today checkins
        for emp in employees:
            if emp.employee_id != 'EMP004':
                check_in_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=5 + hash(emp.employee_id) % 20)
                att = Attendance(
                    user_id=emp.id,
                    date=today,
                    check_in=check_in_time,
                    status='Present'
                )
                db.session.add(att)
                
        db.session.commit()

    # 7. Seed Leave Requests
    if LeaveRequest.query.count() == 0:
        emp_john = User.query.filter_by(employee_id='EMP001').first()
        emp_alice = User.query.filter_by(employee_id='EMP002').first()
        emp_bob = User.query.filter_by(employee_id='EMP003').first()
        
        if emp_john:
            l1 = LeaveRequest(
                user_id=emp_john.id,
                leave_type='Paid',
                start_date=date.today() - timedelta(days=10),
                end_date=date.today() - timedelta(days=8),
                remarks='Family vacation',
                status='Approved',
                admin_comments='Have a great trip!',
                created_at=datetime.utcnow() - timedelta(days=15)
            )
            db.session.add(l1)
            for d in range(8, 11):
                att_leave = Attendance(
                    user_id=emp_john.id,
                    date=date.today() - timedelta(days=d),
                    status='Leave'
                )
                db.session.add(att_leave)
            
        if emp_alice:
            l2 = LeaveRequest(
                user_id=emp_alice.id,
                leave_type='Unpaid',
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=6),
                remarks='Personal errands',
                status='Rejected',
                admin_comments='Sorry, we have a major release scheduled on those days. Please reschedule.',
                created_at=datetime.utcnow() - timedelta(days=2)
            )
            db.session.add(l2)
        
        if emp_bob:
            l3 = LeaveRequest(
                user_id=emp_bob.id,
                leave_type='Sick',
                start_date=date.today() + timedelta(days=2),
                end_date=date.today() + timedelta(days=3),
                remarks='Doctor appointment & dental procedure',
                status='Pending',
                created_at=datetime.utcnow() - timedelta(days=1)
            )
            db.session.add(l3)
        
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
