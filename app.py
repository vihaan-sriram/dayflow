import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dayflow-secure-session-key-9f2b8c9d'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dayflow.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    return render_template('dashboard.html')

@app.route('/simulate-verification', methods=['POST'])
@login_required
def simulate_verification():
    user = User.query.get(current_user.id)
    if user:
        user.is_verified = True
        db.session.commit()
        flash('Email verified successfully!', 'success')
    return redirect(url_for('dashboard'))

# Database initialization & seeding
with app.app_context():
    db.create_all()
    # Seed default user accounts so they can sign in immediately
    if not User.query.filter_by(email='admin@dayflow.com').first():
        admin = User(employee_id='HR001', email='admin@dayflow.com', role='HR', is_verified=True, full_name='Admin User')
        admin.set_password('Admin123!')
        db.session.add(admin)
    if not User.query.filter_by(email='employee@dayflow.com').first():
        emp = User(employee_id='EMP001', email='employee@dayflow.com', role='Employee', is_verified=True, full_name='Employee User')
        emp.set_password('Employee123!')
        db.session.add(emp)
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
