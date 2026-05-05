from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort, send_from_directory, current_app)
from flask_login import login_required, current_user
from extensions import db
from models import (Project, User, Bid, Notification, Message,
                    Review, Report, File)
import os

main_bp = Blueprint('main', __name__)


# ── Landing / Home ────────────────────────────────────────────────────────────

@main_bp.route('/')
def home():
    total_projects  = Project.query.filter_by(is_approved=True).count()
    total_helpers   = User.query.filter_by(role='helper',  is_active=True).count()
    total_students  = User.query.filter_by(role='student', is_active=True).count()
    completed       = Project.query.filter_by(status='completed').count()
    recent_projects = (Project.query
                       .filter_by(status='open', is_approved=True)
                       .order_by(Project.created_at.desc())
                       .limit(6).all())
    return render_template('index.html',
                           total_projects=total_projects,
                           total_helpers=total_helpers,
                           total_students=total_students,
                           completed=completed,
                           recent_projects=recent_projects)


# ── Browse Projects (public) ──────────────────────────────────────────────────

@main_bp.route('/projects')
def browse_projects():
    q      = request.args.get('q', '').strip()
    skill  = request.args.get('skill', '').strip()
    bmin   = request.args.get('bmin', type=float)
    bmax   = request.args.get('bmax', type=float)
    page   = request.args.get('page', 1, type=int)

    query = Project.query.filter_by(status='open', is_approved=True)

    if q:
        query = query.filter(
            Project.title.ilike(f'%{q}%') |
            Project.description.ilike(f'%{q}%')
        )
    if skill:
        query = query.filter(Project.skills_required.ilike(f'%{skill}%'))
    if bmin is not None:
        query = query.filter(Project.budget_max >= bmin)
    if bmax is not None:
        query = query.filter(Project.budget_min <= bmax)

    projects = query.order_by(Project.created_at.desc()).paginate(
        page=page, per_page=current_app.config['PROJECTS_PER_PAGE'], error_out=False)

    return render_template('browse_projects.html', projects=projects,
                           q=q, skill=skill, bmin=bmin, bmax=bmax)


# ── Project Detail ────────────────────────────────────────────────────────────

@main_bp.route('/project/<int:project_id>')
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if not project.is_approved and (
            not current_user.is_authenticated or
            (current_user.role != 'admin' and current_user.id != project.student_id)):
        abort(404)

    user_bid = None
    already_reviewed = False
    if current_user.is_authenticated:
        # Any logged-in user who doesn't own the project may have placed a bid
        if current_user.id != project.student_id:
            user_bid = Bid.query.filter_by(
                project_id=project_id, helper_id=current_user.id).first()
        already_reviewed = Review.query.filter_by(
            project_id=project_id, reviewer_id=current_user.id).first() is not None

    bids  = project.bids.order_by(Bid.created_at.desc()).all() if (
        current_user.is_authenticated and
        (current_user.id == project.student_id or current_user.role == 'admin')
    ) else []
    files = project.files.order_by(File.created_at.desc()).all()
    milestones = project.milestones.all()
    reviews    = project.reviews.all()

    return render_template('project_detail.html',
                           project=project,
                           bids=bids,
                           user_bid=user_bid,
                           files=files,
                           milestones=milestones,
                           reviews=reviews,
                           already_reviewed=already_reviewed)


# ── File Download ─────────────────────────────────────────────────────────────

@main_bp.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    f = File.query.get_or_404(file_id)
    project = Project.query.get(f.project_id)

    # Only student, assigned helper, or admin may download
    allowed = (
        current_user.role == 'admin' or
        current_user.id == project.student_id or
        (project.selected_bid_id and
         Bid.query.get(project.selected_bid_id).helper_id == current_user.id)
    )
    if not allowed:
        abort(403)

    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(f.project_id))
    return send_from_directory(folder, f.filename,
                               as_attachment=True,
                               download_name=f.original_filename)


# ── Notifications ─────────────────────────────────────────────────────────────

@main_bp.route('/notifications')
@login_required
def notifications():
    page = request.args.get('page', 1, type=int)
    notifs = (Notification.query
              .filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc())
              .paginate(page=page, per_page=20, error_out=False))
    # mark all as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('notifications.html', notifs=notifs)


# ── Chat ──────────────────────────────────────────────────────────────────────

@main_bp.route('/chat')
@login_required
def chat_list():
    """Show list of conversations."""
    sent     = db.session.query(Message.receiver_id).filter_by(sender_id=current_user.id)
    received = db.session.query(Message.sender_id).filter_by(receiver_id=current_user.id)
    peer_ids = {r[0] for r in sent.all()} | {r[0] for r in received.all()}
    peers    = User.query.filter(User.id.in_(peer_ids)).all()
    return render_template('chat_list.html', peers=peers)


@main_bp.route('/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    other = User.query.get_or_404(user_id)
    if other.id == current_user.id:
        return redirect(url_for('main.chat_list'))

    project_id = request.args.get('project_id', type=int)

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            msg = Message(
                sender_id=current_user.id,
                receiver_id=user_id,
                project_id=project_id,
                content=content,
            )
            db.session.add(msg)
            # notification
            from utils.helpers import push_notification
            push_notification(
                user_id,
                f'New message from {current_user.name}',
                content[:100],
                url_for('main.chat', user_id=current_user.id),
                'info'
            )
            db.session.commit()

        return redirect(url_for('main.chat', user_id=user_id, project_id=project_id))

    # mark as read
    Message.query.filter_by(
        sender_id=user_id, receiver_id=current_user.id, is_read=False
    ).update({'is_read': True})
    db.session.commit()

    messages = (Message.query
                .filter(
                    ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
                    ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
                )
                .order_by(Message.created_at.asc())
                .all())

    project = Project.query.get(project_id) if project_id else None
    return render_template('chat.html', other=other, messages=messages, project=project)


@main_bp.route('/chat/poll/<int:user_id>')
@login_required
def chat_poll(user_id):
    """AJAX endpoint — returns new messages since a given id."""
    since = request.args.get('since', 0, type=int)
    msgs  = (Message.query
             .filter(
                 ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id)) |
                 ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id))
             )
             .filter(Message.id > since)
             .order_by(Message.created_at.asc())
             .all())
    Message.query.filter_by(
        sender_id=user_id, receiver_id=current_user.id, is_read=False
    ).update({'is_read': True})
    db.session.commit()
    from flask import jsonify
    return jsonify([{
        'id': m.id,
        'sender_id': m.sender_id,
        'content': m.content,
        'time': m.created_at.strftime('%H:%M'),
    } for m in msgs])


# ── Profile ───────────────────────────────────────────────────────────────────

@main_bp.route('/profile/<int:user_id>')
def profile(user_id):
    user    = User.query.get_or_404(user_id)
    reviews = Review.query.filter_by(reviewee_id=user_id).order_by(Review.created_at.desc()).all()
    # Count both projects completed as poster and as bidder
    posted_completed = Project.query.filter_by(student_id=user_id, status='completed').count()
    bid_completed    = (Bid.query.join(Project)
                        .filter(Bid.helper_id == user_id, Project.status == 'completed').count())
    completed = posted_completed + bid_completed
    return render_template('profile.html', profile_user=user,
                           reviews=reviews, completed=completed)


@main_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.name    = request.form.get('name', current_user.name).strip()
        current_user.bio     = request.form.get('bio', '').strip()
        current_user.skills  = request.form.get('skills', '').strip()
        current_user.phone   = request.form.get('phone', '').strip()
        current_user.college = request.form.get('college', '').strip()
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('main.profile', user_id=current_user.id))
    return render_template('edit_profile.html')


# ── Report ────────────────────────────────────────────────────────────────────

@main_bp.route('/report', methods=['POST'])
@login_required
def submit_report():
    reported_user_id = request.form.get('reported_user_id', type=int)
    project_id       = request.form.get('project_id', type=int)
    reason           = request.form.get('reason', '').strip()
    description      = request.form.get('description', '').strip()

    if not reason or not description:
        flash('Please fill in all report fields.', 'danger')
        return redirect(request.referrer or url_for('main.home'))

    report = Report(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        project_id=project_id,
        reason=reason,
        description=description,
    )
    db.session.add(report)
    db.session.commit()
    flash('Report submitted. Admin will review it.', 'success')
    return redirect(request.referrer or url_for('main.home'))
