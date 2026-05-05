import os
import uuid
from flask import current_app
from werkzeug.utils import secure_filename
from models import Notification
from extensions import db


def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
    )


def save_file(file, project_id):
    """Save uploaded file and return (stored_filename, original_filename, size)."""
    original = secure_filename(file.filename)
    ext = original.rsplit('.', 1)[1].lower() if '.' in original else 'bin'
    stored = f"{uuid.uuid4().hex}.{ext}"

    project_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], str(project_id))
    os.makedirs(project_dir, exist_ok=True)

    path = os.path.join(project_dir, stored)
    file.save(path)
    size = os.path.getsize(path)
    return stored, original, size


def push_notification(user_id, title, message, link='', notif_type='info'):
    """Create an in-app notification for a user."""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        link=link,
        notif_type=notif_type,
    )
    db.session.add(notif)
    # commit handled by caller


def stars_html(rating):
    full  = int(rating)
    empty = 5 - full
    return '★' * full + '☆' * empty
