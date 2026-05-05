from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort, current_app)
from flask_login import login_required, current_user
from extensions import db
from models import Project, Bid, File, Review, Milestone
from utils.helpers import push_notification, save_file, allowed_file
from datetime import date

helper_bp = Blueprint('helper', __name__)


# ── Browse Projects ───────────────────────────────────────────────────────────

@helper_bp.route('/browse')
@login_required
def browse():
    q     = request.args.get('q', '').strip()
    skill = request.args.get('skill', '').strip()
    bmin  = request.args.get('bmin', type=float)
    bmax  = request.args.get('bmax', type=float)
    page  = request.args.get('page', 1, type=int)

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

    bid_map = {b.project_id: b for b in current_user.bids_placed.all()}

    return render_template('helper/browse.html',
                           projects=projects,
                           bid_map=bid_map,
                           q=q, skill=skill, bmin=bmin, bmax=bmax)


# ── Place Bid ─────────────────────────────────────────────────────────────────

@helper_bp.route('/bid/<int:project_id>', methods=['GET', 'POST'])
@login_required
def place_bid(project_id):
    project = Project.query.get_or_404(project_id)

    if project.status != 'open':
        flash('This project is no longer accepting bids.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    if project.student_id == current_user.id:
        flash("You can't bid on your own project.", 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    existing = Bid.query.filter_by(project_id=project_id, helper_id=current_user.id).first()
    if existing and existing.status not in ('rejected', 'withdrawn'):
        flash('You already have an active bid on this project.', 'info')
        return redirect(url_for('main.project_detail', project_id=project_id))

    if request.method == 'POST':
        amount        = request.form.get('amount', type=float)
        delivery_days = request.form.get('delivery_days', type=int)
        message       = request.form.get('message', '').strip()

        errors = []
        if not amount or amount <= 0:
            errors.append('Enter a valid bid amount.')
        if not delivery_days or delivery_days <= 0:
            errors.append('Enter valid delivery days.')
        if len(message) < 20:
            errors.append('Proposal message must be at least 20 characters.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('helper/place_bid.html', project=project, existing=existing)

        if existing:
            existing.amount        = amount
            existing.delivery_days = delivery_days
            existing.message       = message
            existing.status        = 'pending'
        else:
            bid = Bid(
                project_id=project_id,
                helper_id=current_user.id,
                amount=amount,
                delivery_days=delivery_days,
                message=message,
            )
            db.session.add(bid)

        db.session.flush()

        push_notification(
            project.student_id,
            'New bid on your project!',
            f'{current_user.name} placed a ₹{amount} bid on "{project.title}".',
            url_for('student.project_bids', project_id=project_id),
            'info'
        )
        db.session.commit()
        flash('Bid placed successfully!', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id))

    return render_template('helper/place_bid.html', project=project, existing=existing)


# ── Withdraw Bid ──────────────────────────────────────────────────────────────

@helper_bp.route('/withdraw/<int:bid_id>', methods=['POST'])
@login_required
def withdraw_bid(bid_id):
    bid = Bid.query.get_or_404(bid_id)
    if bid.helper_id != current_user.id:
        abort(403)
    if bid.status != 'pending':
        flash('Only pending bids can be withdrawn.', 'danger')
        return redirect(url_for('helper.my_bids'))
    bid.status = 'withdrawn'
    db.session.commit()
    flash('Bid withdrawn.', 'info')
    return redirect(url_for('helper.my_bids'))


# ── My Bids ───────────────────────────────────────────────────────────────────

@helper_bp.route('/my-bids')
@login_required
def my_bids():
    status = request.args.get('status', '')
    query  = current_user.bids_placed
    if status:
        query = query.filter_by(status=status)
    bids = query.order_by(Bid.created_at.desc()).all()
    return render_template('helper/my_bids.html', bids=bids, filter_status=status)


# ── Upload Work Files ─────────────────────────────────────────────────────────

@helper_bp.route('/upload/<int:project_id>', methods=['POST'])
@login_required
def upload_file(project_id):
    project = Project.query.get_or_404(project_id)

    if not project.selected_bid_id:
        abort(403)
    accepted_bid = Bid.query.get(project.selected_bid_id)
    if accepted_bid.helper_id != current_user.id:
        abort(403)
    if project.status != 'in_progress':
        flash('Project is not in progress.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    file = request.files.get('file')
    if not file or not file.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))
    if not allowed_file(file.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    stored, original, size = save_file(file, project_id)
    desc = request.form.get('description', '').strip()

    existing_versions = File.query.filter_by(
        project_id=project_id,
        original_filename=original,
        uploaded_by=current_user.id
    ).count()

    f = File(
        project_id=project_id,
        bid_id=accepted_bid.id,
        filename=stored,
        original_filename=original,
        uploaded_by=current_user.id,
        file_size=size,
        description=desc,
        version=existing_versions + 1,
    )
    db.session.add(f)

    push_notification(
        project.student_id,
        'New file uploaded!',
        f'{current_user.name} uploaded "{original}" for "{project.title}".',
        url_for('main.project_detail', project_id=project_id),
        'info'
    )
    db.session.commit()
    flash('File uploaded successfully!', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))


# ── Milestones ────────────────────────────────────────────────────────────────

@helper_bp.route('/milestones/<int:project_id>', methods=['GET', 'POST'])
@login_required
def manage_milestones(project_id):
    project = Project.query.get_or_404(project_id)

    if not project.selected_bid_id:
        abort(403)
    accepted_bid = Bid.query.get(project.selected_bid_id)
    if accepted_bid.helper_id != current_user.id and current_user.role != 'admin':
        abort(403)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            title    = request.form.get('title', '').strip()
            desc     = request.form.get('description', '').strip()
            amount   = request.form.get('amount', 0, type=float)
            due_date = None
            try:
                due_date_str = request.form.get('due_date', '')
                if due_date_str:
                    from datetime import datetime
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
            if title:
                m = Milestone(project_id=project_id, title=title,
                              description=desc, amount=amount, due_date=due_date)
                db.session.add(m)
                db.session.commit()
                flash('Milestone added.', 'success')

        elif action == 'update':
            milestone_id = request.form.get('milestone_id', type=int)
            new_status   = request.form.get('status', '')
            m = Milestone.query.get(milestone_id)
            if m and m.project_id == project_id:
                m.status = new_status
                db.session.commit()
                push_notification(
                    project.student_id,
                    'Milestone updated',
                    f'Milestone "{m.title}" is now {new_status}.',
                    url_for('main.project_detail', project_id=project_id),
                    'info'
                )
                db.session.commit()
                flash('Milestone updated.', 'success')

        return redirect(url_for('helper.manage_milestones', project_id=project_id))

    milestones = project.milestones.all()
    return render_template('helper/milestones.html',
                           project=project, milestones=milestones,
                           accepted_bid=accepted_bid)


# ── Leave Review for Project Owner ────────────────────────────────────────────

@helper_bp.route('/review/<int:project_id>', methods=['GET', 'POST'])
@login_required
def review_student(project_id):
    project = Project.query.get_or_404(project_id)
    if not project.selected_bid_id:
        abort(404)
    accepted_bid = Bid.query.get(project.selected_bid_id)
    if accepted_bid.helper_id != current_user.id:
        abort(403)
    if project.status != 'completed':
        flash('Project must be completed first.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    already = Review.query.filter_by(project_id=project_id, reviewer_id=current_user.id).first()
    if already:
        flash('You already reviewed this project.', 'info')
        return redirect(url_for('main.project_detail', project_id=project_id))

    if request.method == 'POST':
        rating  = request.form.get('rating', type=int)
        comment = request.form.get('comment', '').strip()
        if not rating or rating not in range(1, 6):
            flash('Please pick a rating.', 'danger')
            return render_template('helper/review_student.html',
                                   project=project, student=project.student)

        review = Review(
            project_id=project_id,
            reviewer_id=current_user.id,
            reviewee_id=project.student_id,
            rating=rating,
            comment=comment,
        )
        db.session.add(review)
        push_notification(
            project.student_id,
            'New review from your helper!',
            f'{current_user.name} reviewed you for "{project.title}".',
            url_for('main.profile', user_id=current_user.id),
            'info'
        )
        db.session.commit()
        flash('Review submitted!', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id))

    return render_template('helper/review_student.html',
                           project=project, student=project.student)
