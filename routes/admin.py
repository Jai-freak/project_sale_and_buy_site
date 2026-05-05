from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user
from functools import wraps
from extensions import db
from models import User, Project, Bid, Report, Review, Notification

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_users':    User.query.filter(User.role != 'admin').count(),
        'students':       User.query.filter_by(role='student').count(),
        'helpers':        User.query.filter_by(role='helper').count(),
        'open_projects':  Project.query.filter_by(status='open').count(),
        'active_projects':Project.query.filter_by(status='in_progress').count(),
        'completed':      Project.query.filter_by(status='completed').count(),
        'total_bids':     Bid.query.count(),
        'open_reports':   Report.query.filter_by(status='open').count(),
    }
    recent_users    = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()
    recent_reports  = Report.query.filter_by(status='open').order_by(Report.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
                           stats=stats,
                           recent_users=recent_users,
                           recent_projects=recent_projects,
                           recent_reports=recent_reports)


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    q    = request.args.get('q', '').strip()
    role = request.args.get('role', '')
    page = request.args.get('page', 1, type=int)

    query = User.query.filter(User.role != 'admin')
    if q:
        query = query.filter(User.name.ilike(f'%{q}%') | User.email.ilike(f'%{q}%'))
    if role:
        query = query.filter_by(role=role)

    users_page = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template('admin/users.html', users=users_page, q=q, role=role)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        abort(403)
    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.name} {status}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/verify', methods=['POST'])
@login_required
@admin_required
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    user.email_token = None
    db.session.commit()
    flash(f'{user.name} verified.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        abort(403)
    # soft-delete: just deactivate and mark unverified
    user.is_active   = False
    user.is_verified = False
    db.session.commit()
    flash(f'User {user.name} disabled.', 'warning')
    return redirect(url_for('admin.users'))


# ── Projects ──────────────────────────────────────────────────────────────────

@admin_bp.route('/projects')
@login_required
@admin_required
def projects():
    status = request.args.get('status', '')
    q      = request.args.get('q', '').strip()
    page   = request.args.get('page', 1, type=int)

    query = Project.query
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter(Project.title.ilike(f'%{q}%'))

    projects_page = query.order_by(Project.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template('admin/projects.html',
                           projects=projects_page, status=status, q=q)


@admin_bp.route('/projects/<int:project_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.is_approved = True
    db.session.commit()
    flash(f'Project "{project.title}" approved.', 'success')
    return redirect(url_for('admin.projects'))


@admin_bp.route('/projects/<int:project_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.is_approved = False
    project.status      = 'cancelled'
    db.session.commit()
    flash(f'Project "{project.title}" rejected.', 'warning')
    return redirect(url_for('admin.projects'))


@admin_bp.route('/projects/<int:project_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.status = 'cancelled'
    db.session.commit()
    flash(f'Project "{project.title}" cancelled.', 'warning')
    return redirect(url_for('admin.projects'))


# ── Reports ───────────────────────────────────────────────────────────────────

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    status = request.args.get('status', 'open')
    page   = request.args.get('page', 1, type=int)
    reps   = (Report.query
              .filter_by(status=status)
              .order_by(Report.created_at.desc())
              .paginate(page=page, per_page=20, error_out=False))
    return render_template('admin/reports.html', reports=reps, status=status)


@admin_bp.route('/reports/<int:report_id>/resolve', methods=['POST'])
@login_required
@admin_required
def resolve_report(report_id):
    report = Report.query.get_or_404(report_id)
    action = request.form.get('action', 'resolved')  # resolved / dismissed
    report.status = action
    db.session.commit()
    flash(f'Report {action}.', 'success')
    return redirect(url_for('admin.reports'))


# ── Send notification to all users ───────────────────────────────────────────

@admin_bp.route('/broadcast', methods=['POST'])
@login_required
@admin_required
def broadcast():
    title   = request.form.get('title', '').strip()
    message = request.form.get('message', '').strip()
    if title and message:
        users = User.query.filter(User.role != 'admin', User.is_active == True).all()
        for u in users:
            n = Notification(
                user_id=u.id,
                title=title,
                message=message,
                notif_type='info',
            )
            db.session.add(n)
        db.session.commit()
        flash(f'Broadcast sent to {len(users)} users.', 'success')
    return redirect(url_for('admin.dashboard'))
