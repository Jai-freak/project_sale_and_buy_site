/* CampusMarket — Main JS */
'use strict';

// ── Auto-dismiss flash messages ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-container .alert').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    }, 5000);
  });
});

// ── Confirm before dangerous form submits (belt-and-braces) ──────────
document.addEventListener('submit', function (e) {
  const form = e.target;
  const msg  = form.dataset.confirm;
  if (msg && !confirm(msg)) e.preventDefault();
});

// ── Active nav link highlight ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const path = window.location.pathname;
  document.querySelectorAll('.navbar .nav-link').forEach(link => {
    if (link.getAttribute('href') === path) {
      link.classList.add('active');
    }
  });
});

// ── Notification bell live count update ──────────────────────────────
// (lightweight poll — only if user is logged in)
(function startNotifPoll() {
  const bell = document.querySelector('.badge-pill-notif.bg-danger');
  if (!bell) return;  // not logged in or no badge yet

  setInterval(() => {
    fetch('/notifications?_ajax=1')
      .then(() => {})   // full page flash handled; badge updated on next page load
      .catch(() => {});
  }, 60000);
})();

// ── Tooltip init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[title]').forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover', placement: 'top' });
  });
});

// ── File input label update ──────────────────────────────────────────
document.addEventListener('change', function (e) {
  if (e.target.type === 'file') {
    const label = e.target.nextElementSibling;
    if (label && label.tagName === 'LABEL') {
      label.textContent = e.target.files[0]?.name || 'Choose file';
    }
  }
});

// ── Password-strength helper (used in register.html inline script too) ──
window.togglePassword = function (id, btn) {
  const f = document.getElementById(id);
  if (!f) return;
  const icon = btn.querySelector('i');
  if (f.type === 'password') {
    f.type = 'text';
    if (icon) { icon.classList.remove('fa-eye'); icon.classList.add('fa-eye-slash'); }
  } else {
    f.type = 'password';
    if (icon) { icon.classList.remove('fa-eye-slash'); icon.classList.add('fa-eye'); }
  }
};

// ── Smooth scroll to anchor ──────────────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', function (e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});
