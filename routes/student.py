from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user
from extensions import db
from models import Project, Bid, File, Review, Milestone
from utils.helpers import push_notification, save_file, allowed_file
from datetime import datetime, date

student_bp = Blueprint('student', __name__)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@student_bp.route('/dashboard')
@login_required
def dashboard():
    # Projects the user posted
    projects = (Project.query
                .filter_by(student_id=current_user.id)
                .order_by(Project.created_at.desc()).all())
    active_projects   = [p for p in projects if p.status in ('open', 'in_progress')]
    completed_projects= [p for p in projects if p.status == 'completed']

    # Bids the user placed on others' projects
    bids = current_user.bids_placed.order_by(Bid.created_at.desc()).all()
    active_bids    = [b for b in bids if b.status == 'accepted' and b.project.status == 'in_progress']
    completed_bids = [b for b in bids if b.status == 'accepted' and b.project.status == 'completed']
    earnings       = sum(b.amount for b in completed_bids)

    return render_template('student/dashboard.html',
                           projects=projects,
                           active_projects=active_projects,
                           completed_projects=completed_projects,
                           bids=bids,
                           active_bids=active_bids,
                           completed_bids=completed_bids,
                           earnings=earnings)


# ── Post Project ──────────────────────────────────────────────────────────────

@student_bp.route('/post-project', methods=['GET', 'POST'])
@login_required
def post_project():
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        budget_min  = request.form.get('budget_min', 0, type=float)
        budget_max  = request.form.get('budget_max', 0, type=float)
        deadline_str= request.form.get('deadline', '')
        skills      = request.form.get('skills', '').strip()
        tags        = request.form.get('tags', '').strip()

        errors = []
        if not title:
            errors.append('Title is required.')
        if not description or len(description) < 30:
            errors.append('Description must be at least 30 characters.')
        if budget_min < 0 or budget_max < 0:
            errors.append('Budget must be positive.')
        if budget_max < budget_min:
            errors.append('Max budget must be ≥ min budget.')

        deadline = None
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
            if deadline <= date.today():
                errors.append('Deadline must be in the future.')
        except ValueError:
            errors.append('Invalid deadline date.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('student/post_project.html', form_data=request.form)

        project = Project(
            title=title,
            description=description,
            budget_min=budget_min,
            budget_max=budget_max,
            deadline=deadline,
            skills_required=skills,
            tags=tags,
            student_id=current_user.id,
        )
        db.session.add(project)
        db.session.commit()

        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename and allowed_file(file.filename):
                stored, original, size = save_file(file, project.id)
                f = File(
                    project_id=project.id,
                    filename=stored,
                    original_filename=original,
                    uploaded_by=current_user.id,
                    file_size=size,
                    description='Initial requirement document',
                )
                db.session.add(f)
                db.session.commit()

        flash('Project posted successfully!', 'success')
        return redirect(url_for('main.project_detail', project_id=project.id))

    return render_template('student/post_project.html', form_data={})


# ── My Projects ───────────────────────────────────────────────────────────────

@student_bp.route('/my-projects')
@login_required
def my_projects():
    status   = request.args.get('status', '')
    query    = Project.query.filter_by(student_id=current_user.id)
    if status:
        query = query.filter_by(status=status)
    projects = query.order_by(Project.created_at.desc()).all()
    return render_template('student/my_projects.html', projects=projects, filter_status=status)


# ── View Bids for a Project ───────────────────────────────────────────────────

@student_bp.route('/project/<int:project_id>/bids')
@login_required
def project_bids(project_id):
    project = Project.query.get_or_404(project_id)
    if project.student_id != current_user.id and current_user.role != 'admin':
        abort(403)
    bids = project.bids.order_by(Bid.created_at.desc()).all()
    return render_template('student/project_bids.html', project=project, bids=bids)


# ── Accept Bid ────────────────────────────────────────────────────────────────

@student_bp.route('/accept-bid/<int:bid_id>', methods=['POST'])
@login_required
def accept_bid(bid_id):
    bid     = Bid.query.get_or_404(bid_id)
    project = Project.query.get(bid.project_id)

    if project.student_id != current_user.id:
        abort(403)
    if project.status != 'open':
        flash('Project is no longer open.', 'danger')
        return redirect(url_for('student.project_bids', project_id=project.id))

    project.bids.filter(Bid.id != bid_id).update({'status': 'rejected'})
    bid.status               = 'accepted'
    project.status           = 'in_progress'
    project.selected_bid_id  = bid.id
    db.session.commit()

    push_notification(
        bid.helper_id,
        'Your bid was accepted!',
        f'Congratulations! Your bid on "{project.title}" was accepted.',
        url_for('main.project_detail', project_id=project.id),
        'success'
    )
    db.session.commit()
    flash(f'Bid accepted! {bid.helper.name} will work on your project.', 'success')
    return redirect(url_for('main.project_detail', project_id=project.id))


# ── Reject Bid ────────────────────────────────────────────────────────────────

@student_bp.route('/reject-bid/<int:bid_id>', methods=['POST'])
@login_required
def reject_bid(bid_id):
    bid     = Bid.query.get_or_404(bid_id)
    project = Project.query.get(bid.project_id)

    if project.student_id != current_user.id:
        abort(403)

    bid.status = 'rejected'
    db.session.commit()

    push_notification(
        bid.helper_id,
        'Your bid was not selected',
        f'Your bid on "{project.title}" was not selected this time.',
        url_for('main.browse_projects'),
        'warning'
    )
    db.session.commit()
    flash('Bid rejected.', 'info')
    return redirect(url_for('student.project_bids', project_id=project.id))


# ── Mark Project Complete ─────────────────────────────────────────────────────

@student_bp.route('/complete/<int:project_id>', methods=['POST'])
@login_required
def complete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.student_id != current_user.id:
        abort(403)
    if project.status != 'in_progress':
        flash('Project is not in progress.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    project.status = 'completed'
    db.session.commit()

    if project.selected_bid_id:
        helper_id = Bid.query.get(project.selected_bid_id).helper_id
        push_notification(
            helper_id,
            'Project marked as complete!',
            f'"{project.title}" has been completed. Please leave a review.',
            url_for('main.project_detail', project_id=project_id),
            'success'
        )
        db.session.commit()

    flash('Project marked as completed! Please leave a review.', 'success')
    return redirect(url_for('student.review_project', project_id=project_id))


# ── Cancel Project ────────────────────────────────────────────────────────────

@student_bp.route('/cancel/<int:project_id>', methods=['POST'])
@login_required
def cancel_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.student_id != current_user.id:
        abort(403)
    if project.status == 'completed':
        flash('Cannot cancel a completed project.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    project.status = 'cancelled'
    db.session.commit()
    flash('Project cancelled.', 'info')
    return redirect(url_for('student.my_projects'))


# ── Review Helper ─────────────────────────────────────────────────────────────

@student_bp.route('/review/<int:project_id>', methods=['GET', 'POST'])
@login_required
def review_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.student_id != current_user.id:
        abort(403)
    if project.status != 'completed':
        flash('Project must be completed before reviewing.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    already = Review.query.filter_by(project_id=project_id, reviewer_id=current_user.id).first()
    if already:
        flash('You already submitted a review.', 'info')
        return redirect(url_for('main.project_detail', project_id=project_id))

    if not project.selected_bid_id:
        flash('No helper assigned.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    helper = Bid.query.get(project.selected_bid_id).helper

    if request.method == 'POST':
        rating  = request.form.get('rating', type=int)
        comment = request.form.get('comment', '').strip()

        if not rating or rating not in range(1, 6):
            flash('Please select a rating (1–5).', 'danger')
            return render_template('student/review.html', project=project, helper=helper)

        review = Review(
            project_id=project_id,
            reviewer_id=current_user.id,
            reviewee_id=helper.id,
            rating=rating,
            comment=comment,
        )
        db.session.add(review)
        push_notification(
            helper.id,
            'New review received!',
            f'{current_user.name} gave you {rating} stars for "{project.title}".',
            url_for('main.profile', user_id=helper.id),
            'success'
        )
        db.session.commit()
        flash('Review submitted!', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id))

    return render_template('student/review.html', project=project, helper=helper)


# ── Upload requirement file ───────────────────────────────────────────────────

@student_bp.route('/upload/<int:project_id>', methods=['POST'])
@login_required
def upload_file(project_id):
    project = Project.query.get_or_404(project_id)
    if project.student_id != current_user.id:
        abort(403)

    file = request.files.get('file')
    if not file or not file.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))
    if not allowed_file(file.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    stored, original, size = save_file(file, project_id)
    desc = request.form.get('description', '').strip()

    f = File(
        project_id=project_id,
        filename=stored,
        original_filename=original,
        uploaded_by=current_user.id,
        file_size=size,
        description=desc,
    )
    db.session.add(f)
    db.session.commit()
    flash('File uploaded.', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))
