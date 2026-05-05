from flask import url_for, current_app
from flask_mail import Message as MailMessage
from extensions import mail


def send_verification_email(user):
    verify_url = url_for('auth.verify_email', token=user.email_token, _external=True)
    msg = MailMessage(
        subject='Verify Your Campus Marketplace Account',
        recipients=[user.email],
    )
    msg.html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#1e3a5f;padding:24px;text-align:center">
        <h1 style="color:#fff;margin:0">Campus Marketplace</h1>
      </div>
      <div style="padding:32px;background:#f9fafb">
        <h2>Hi {user.name},</h2>
        <p>Thanks for registering! Click the button below to verify your email address.</p>
        <div style="text-align:center;margin:32px 0">
          <a href="{verify_url}"
             style="background:#f97316;color:#fff;padding:14px 32px;border-radius:8px;
                    text-decoration:none;font-size:16px;font-weight:bold">
            Verify Email
          </a>
        </div>
        <p style="color:#666;font-size:13px">
          Or copy this link: <a href="{verify_url}">{verify_url}</a>
        </p>
        <p style="color:#999;font-size:12px">
          If you did not create an account, you can safely ignore this email.
        </p>
      </div>
    </div>
    """
    mail.send(msg)


def send_reset_email(user):
    reset_url = url_for('auth.reset_password', token=user.reset_token, _external=True)
    msg = MailMessage(
        subject='Reset Your Campus Marketplace Password',
        recipients=[user.email],
    )
    msg.html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#1e3a5f;padding:24px;text-align:center">
        <h1 style="color:#fff;margin:0">Campus Marketplace</h1>
      </div>
      <div style="padding:32px;background:#f9fafb">
        <h2>Hi {user.name},</h2>
        <p>We received a request to reset your password. Click below to proceed.</p>
        <div style="text-align:center;margin:32px 0">
          <a href="{reset_url}"
             style="background:#ef4444;color:#fff;padding:14px 32px;border-radius:8px;
                    text-decoration:none;font-size:16px;font-weight:bold">
            Reset Password
          </a>
        </div>
        <p style="color:#666;font-size:13px">
          Or copy this link: <a href="{reset_url}">{reset_url}</a>
        </p>
        <p style="color:#999;font-size:12px">
          This link expires in 1 hour. If you did not request a reset, ignore this email.
        </p>
      </div>
    </div>
    """
    mail.send(msg)


def send_bid_notification(project, bid):
    """Notify student that a new bid arrived."""
    if not project.student.email:
        return
    try:
        msg = MailMessage(
            subject=f'New Bid on Your Project: {project.title}',
            recipients=[project.student.email],
        )
        msg.body = (
            f'Hi {project.student.name},\n\n'
            f'{bid.helper.name} placed a bid of ₹{bid.amount} on your project "{project.title}".\n'
            f'Log in to review it.\n\nCampus Marketplace'
        )
        mail.send(msg)
    except Exception:
        pass
