from flask import Flask, redirect, url_for
from config import Config
from extensions import db, login_manager, mail
from datetime import datetime
import os


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # ── blueprints ────────────────────────────────────────────────────────────
    from routes.auth    import auth_bp
    from routes.main    import main_bp
    from routes.student import student_bp
    from routes.helper  import helper_bp
    from routes.admin   import admin_bp

    app.register_blueprint(auth_bp,    url_prefix='/auth')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(helper_bp,  url_prefix='/helper')
    app.register_blueprint(admin_bp,   url_prefix='/admin')
    app.register_blueprint(main_bp)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ── context processor ─────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from models import Notification
        unread_notifs   = 0
        unread_messages = 0
        if current_user.is_authenticated:
            unread_notifs   = Notification.query.filter_by(
                user_id=current_user.id, is_read=False).count()
            unread_messages = current_user.unread_messages
        return dict(
            now=datetime.utcnow(),
            unread_notifs=unread_notifs,
            unread_messages=unread_messages,
        )

    # ── db init + default admin ───────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _create_default_admin()

    return app


def _create_default_admin():
    from models import User
    if not User.query.filter_by(role='admin').first():
        admin = User(
            name='Admin',
            email='admin@marketplace.com',
            role='admin',
            is_verified=True,
            is_active=True,
        )
        admin.set_password('Admin@123')
        db.session.add(admin)
        db.session.commit()
        print('Default admin created: admin@marketplace.com / Admin@123')


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
