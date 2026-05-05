from extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import secrets


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role         = db.Column(db.String(20), default='user')  # user / admin
    is_verified  = db.Column(db.Boolean, default=False)
    is_active    = db.Column(db.Boolean, default=True)
    profile_pic  = db.Column(db.String(200), default='')
    bio          = db.Column(db.Text, default='')
    skills       = db.Column(db.String(500), default='')   # comma-separated
    phone        = db.Column(db.String(30), default='')
    college      = db.Column(db.String(200), default='')
    email_token  = db.Column(db.String(120), nullable=True)
    reset_token  = db.Column(db.String(120), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    projects_posted  = db.relationship('Project', backref='student',  lazy='dynamic',
                                       foreign_keys='Project.student_id')
    bids_placed      = db.relationship('Bid',     backref='helper',   lazy='dynamic',
                                       foreign_keys='Bid.helper_id')
    sent_messages    = db.relationship('Message', backref='sender',   lazy='dynamic',
                                       foreign_keys='Message.sender_id')
    received_messages= db.relationship('Message', backref='receiver', lazy='dynamic',
                                       foreign_keys='Message.receiver_id')
    notifications    = db.relationship('Notification', backref='user', lazy='dynamic')
    reports_filed    = db.relationship('Report', backref='reporter',  lazy='dynamic',
                                       foreign_keys='Report.reporter_id')

    # ── helpers ─────────────────────────────────────────────────────────────

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_email_token(self):
        self.email_token = secrets.token_urlsafe(32)
        return self.email_token

    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        return self.reset_token

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills.split(',') if s.strip()] if self.skills else []

    @property
    def avg_rating(self):
        reviews = Review.query.filter_by(reviewee_id=self.id).all()
        if not reviews:
            return 0.0
        return round(sum(r.rating for r in reviews) / len(reviews), 1)

    @property
    def total_reviews(self):
        return Review.query.filter_by(reviewee_id=self.id).count()

    @property
    def unread_messages(self):
        return Message.query.filter_by(receiver_id=self.id, is_read=False).count()

    def __repr__(self):
        return f'<User {self.email}>'


class Project(db.Model):
    __tablename__ = 'projects'

    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(200), nullable=False)
    description    = db.Column(db.Text,        nullable=False)
    budget_min     = db.Column(db.Float, default=0)
    budget_max     = db.Column(db.Float, default=0)
    deadline       = db.Column(db.Date,  nullable=False)
    skills_required= db.Column(db.String(500), default='')
    tags           = db.Column(db.String(500), default='')
    # open / in_progress / completed / cancelled
    status         = db.Column(db.String(20), default='open')
    student_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    selected_bid_id= db.Column(db.Integer, db.ForeignKey('bids.id'),  nullable=True)
    is_approved    = db.Column(db.Boolean, default=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    bids       = db.relationship('Bid',       backref='project', lazy='dynamic',
                                 foreign_keys='Bid.project_id')
    files      = db.relationship('File',      backref='project', lazy='dynamic')
    reviews    = db.relationship('Review',    backref='project', lazy='dynamic')
    milestones = db.relationship('Milestone', backref='project', lazy='dynamic')

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills_required.split(',') if s.strip()]

    @property
    def tags_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    @property
    def bid_count(self):
        return self.bids.count()

    @property
    def lowest_bid(self):
        bid = self.bids.order_by(Bid.amount.asc()).first()
        return bid.amount if bid else None

    @property
    def is_overdue(self):
        from datetime import date
        return self.deadline < date.today() and self.status == 'open'

    @property
    def selected_bid(self):
        if self.selected_bid_id:
            return Bid.query.get(self.selected_bid_id)
        return None

    def __repr__(self):
        return f'<Project {self.title}>'


class Bid(db.Model):
    __tablename__ = 'bids'

    id            = db.Column(db.Integer, primary_key=True)
    project_id    = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    helper_id     = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    amount        = db.Column(db.Float,   nullable=False)
    delivery_days = db.Column(db.Integer, nullable=False)
    message       = db.Column(db.Text,    nullable=False)
    # pending / accepted / rejected / withdrawn
    status        = db.Column(db.String(20), default='pending')
    created_at    = db.Column(db.DateTime,   default=datetime.utcnow)

    def __repr__(self):
        return f'<Bid {self.id} on Project {self.project_id}>'


class File(db.Model):
    __tablename__ = 'files'

    id                = db.Column(db.Integer, primary_key=True)
    project_id        = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    bid_id            = db.Column(db.Integer, db.ForeignKey('bids.id'),     nullable=True)
    filename          = db.Column(db.String(300), nullable=False)   # stored on disk
    original_filename = db.Column(db.String(300), nullable=False)   # original name
    uploaded_by       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_size         = db.Column(db.Integer, default=0)            # bytes
    version           = db.Column(db.Integer, default=1)
    description       = db.Column(db.String(500), default='')
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    bid_ref  = db.relationship('Bid',  foreign_keys=[bid_id])

    @property
    def file_size_human(self):
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} GB'

    def __repr__(self):
        return f'<File {self.original_filename}>'


class Review(db.Model):
    __tablename__ = 'reviews'

    id          = db.Column(db.Integer, primary_key=True)
    project_id  = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    rating      = db.Column(db.Integer, nullable=False)   # 1–5
    comment     = db.Column(db.Text,    default='')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    reviewer = db.relationship('User', foreign_keys=[reviewer_id])
    reviewee = db.relationship('User', foreign_keys=[reviewee_id])

    def __repr__(self):
        return f'<Review {self.id} rating={self.rating}>'


class Message(db.Model):
    __tablename__ = 'messages'

    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    project_id  = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    content     = db.Column(db.Text,    nullable=False)
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    project_ref = db.relationship('Project', foreign_keys=[project_id])

    def __repr__(self):
        return f'<Message {self.id}>'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title      = db.Column(db.String(200), nullable=False)
    message    = db.Column(db.Text, nullable=False)
    link       = db.Column(db.String(300), default='')
    is_read    = db.Column(db.Boolean, default=False)
    notif_type = db.Column(db.String(30), default='info')  # info/success/warning/danger
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Notification {self.id}>'


class Milestone(db.Model):
    __tablename__ = 'milestones'

    id          = db.Column(db.Integer, primary_key=True)
    project_id  = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    amount      = db.Column(db.Float, default=0)
    # pending / in_progress / completed
    status      = db.Column(db.String(20), default='pending')
    due_date    = db.Column(db.Date, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Milestone {self.title}>'


class Report(db.Model):
    __tablename__ = 'reports'

    id               = db.Column(db.Integer, primary_key=True)
    reporter_id      = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=True)
    project_id       = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    reason           = db.Column(db.String(100), nullable=False)
    description      = db.Column(db.Text, nullable=False)
    # open / resolved / dismissed
    status           = db.Column(db.String(20), default='open')
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    reported_user = db.relationship('User',    foreign_keys=[reported_user_id])
    project_ref   = db.relationship('Project', foreign_keys=[project_id])

    def __repr__(self):
        return f'<Report {self.id}>'
