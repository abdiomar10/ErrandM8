from django.urls import path
from . import views

urlpatterns = [
    # ── Public ───────────────────────────────────────────────────────────────
    path('', views.landing_page, name='landing_page'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('terms/', views.terms_and_conditions, name='terms_and_conditions'),
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    path('csrf-failure/', views.csrf_failure, name='csrf_failure'),

    # ── Auth ─────────────────────────────────────────────────────────────────
    path('signup/', views.signup, name='signup'),
    path('signup/verify/', views.verify_otp, name='verify_otp'),
    path('signup/resend-otp/', views.resend_otp, name='resend_otp'),
    path('login/', views.login, name='login'),
    path('login/2fa/', views.two_fa_verify, name='two_fa_verify'),
    path('logout/', views.logout_view, name='logout'),

    # ── 2FA toggle ───────────────────────────────────────────────────────────
    path('profile/toggle-2fa/', views.toggle_two_fa, name='toggle_two_fa'),

    # ── Password reset ────────────────────────────────────────────────────────
    path('password-reset/', views.password_reset, name='password_reset'),
    path('password-reset/done/', views.password_reset_done, name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('reset/done/', views.password_reset_complete, name='password_reset_complete'),

    # ── Location (AJAX) ───────────────────────────────────────────────────────
    path('update-location/', views.update_location, name='update_location'),

    # ── Notifications ─────────────────────────────────────────────────────────
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notif_id>/read/', views.mark_notification_read, name='mark_notification_read'),

    # ── Profile ───────────────────────────────────────────────────────────────
    path('profile/', views.profile_view, name='profile'),
    path('profile/<str:username>/', views.profile_view, name='profile_user'),

    # ── Dashboards ────────────────────────────────────────────────────────────
    path('dashboard/client/', views.client_dashboard, name='client_dashboard'),
    path('dashboard/runner/', views.runner_dashboard, name='runner_dashboard'),

    # ── Errand lifecycle ──────────────────────────────────────────────────────
    path('errands/post/', views.post_task, name='post_task'),
    path('errands/<int:task_id>/', views.task_detail, name='task_detail'),
    path('errands/<int:task_id>/set-price/', views.set_price, name='set_price'),
    path('errands/<int:task_id>/counter/', views.counter_price, name='counter_price'),
    path('errands/<int:task_id>/accept/<str:action>/', views.accept_task, name='accept_task'),
    path('errands/<int:task_id>/complete/', views.complete_task, name='complete_task'),
    path('errands/<int:task_id>/pay/', views.pay_runner, name='pay_runner'),
    path('errands/<int:task_id>/cancel/', views.cancel_task, name='cancel_task'),
    path('errands/<int:task_id>/review/', views.leave_review, name='leave_review'),

    # ── Chat ──────────────────────────────────────────────────────────────────
    path('errands/<int:task_id>/chat/send/', views.send_chat, name='send_chat'),
    path('errands/<int:task_id>/chat/poll/', views.poll_chat, name='poll_chat'),
]