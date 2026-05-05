from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User
from utils.email_utils import send_verification_email, send_reset_email

auth_bp = Blueprint('auth', __name__)


def _redirect_by_role(user):
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('student.dashboard'))


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        college  = request.form.get('college', '').strip()

        errors = []
        if len(name) < 2:
            errors.append('Name must be at least 2 characters.')
        if not email:
            errors.append('Email is required.')
        if User.query.filter_by(email=email).first():
            errors.append('That email is already registered.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html', form_data=request.form)

        user = User(
            name=name,
            email=email,
            role='user',
            college=college,
            is_active=True,
            is_verified=False,
        )
        user.set_password(password)
        user.generate_email_token()
        db.session.add(user)
        db.session.commit()

        try:
            send_verification_email(user)
            flash(f'Account created! Check {email} for a verification link.', 'success')
        except Exception:
            verify_url = url_for('auth.verify_email', token=user.email_token, _external=True)
            flash(
                f'Account created! '
                f'<a href="{verify_url}" class="alert-link">Click here to verify your email</a>.',
                'info'
            )

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form_data={})


# ── Verify Email ──────────────────────────────────────────────────────────────

@auth_bp.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(email_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('auth.login'))

    user.is_verified = True
    user.email_token = None
    db.session.commit()
    flash('Email verified! You can now log in.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/resend/<email>')
def resend_verification(email):
    user = User.query.filter_by(email=email).first()
    if user and not user.is_verified:
        user.generate_email_token()
        db.session.commit()
        try:
            send_verification_email(user)
            flash('Verification email resent!', 'success')
        except Exception:
            verify_url = url_for('auth.verify_email', token=user.email_token, _external=True)
            flash(f'<a href="{verify_url}" class="alert-link">Click here to verify</a>', 'info')
    return redirect(url_for('auth.login'))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account is deactivated. Contact admin.', 'danger')
            return render_template('auth/login.html')

        if not user.is_verified:
            flash(
                f'Please verify your email. '
                f'<a href="{url_for("auth.resend_verification", email=user.email)}" '
                f'class="alert-link">Resend verification link</a>',
                'warning'
            )
            return render_template('auth/login.html')

        login_user(user, remember=remember)
        next_page = request.args.get('next')
        return redirect(next_page or _redirect_by_role(user).location)

    return render_template('auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


# ── Forgot / Reset Password ───────────────────────────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            user.generate_reset_token()
            db.session.commit()
            try:
                send_reset_email(user)
            except Exception:
                reset_url = url_for('auth.reset_password', token=user.reset_token, _external=True)
                flash(
                    f'<a href="{reset_url}" class="alert-link">Click here to reset your password</a>',
                    'info'
                )
        flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/reset_password.html', token=token)
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(password)
        user.reset_token = None
        db.session.commit()
        flash('Password reset! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)
