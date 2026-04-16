import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.db import IntegrityError
from django.conf import settings

from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm,
    TaskForm, ReviewForm, PriceCounterForm, ProfileForm,
    OTPForm, PhoneForm,
)
from .models import Profile, Task, Review, PriceCounter, Notification, ChatMessage
from .sms import send_otp, send_task_notification, send_sms


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _notify(recipient, notif_type, message, task=None):
    Notification.objects.create(
        recipient=recipient,
        notif_type=notif_type,
        message=message,
        task=task,
    )

def _unread_count(user):
    if user.is_authenticated:
        return user.notifications.filter(is_read=False).count()
    return 0

def _ctx(request, extra=None):
    ctx = {'unread': _unread_count(request.user)}
    if extra:
        ctx.update(extra)
    return ctx

def _dashboard_redirect(user):
    try:
        if user.profile.user_type == 'runner':
            return redirect('runner_dashboard')
    except Profile.DoesNotExist:
        pass
    return redirect('client_dashboard')

def _sms_if_phone(user, message):
    try:
        p = user.profile
        if p.phone_number and p.phone_verified:
            send_sms(p.phone_number, message)
    except Exception:
        pass


# ─────────────────────────────────────────────
# PUBLIC PAGES
# ─────────────────────────────────────────────

def landing_page(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)
    return render(request, 'ErrandM8App/Landing_page.html', _ctx(request))

def about(request):
    return render(request, 'ErrandM8App/About.html', _ctx(request))

def contact(request):
    return render(request, 'ErrandM8App/Contact.html', _ctx(request))

def terms_and_conditions(request):
    return render(request, 'ErrandM8App/Terms_and_conditions.html', _ctx(request))

def privacy_policy(request):
    return render(request, 'ErrandM8App/Privacy_policy.html', _ctx(request))

def csrf_failure(request, reason=''):
    return render(request, 'ErrandM8App/csrf_failure.html', {'reason': reason}, status=403)


# ─────────────────────────────────────────────
# SIGNUP + OTP
# ─────────────────────────────────────────────

def signup(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            phone = form.cleaned_data['phone_number']
            user_type = form.cleaned_data['user_type']

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.user_type = user_type
            profile.phone_number = phone
            profile.save()

            otp = profile.generate_otp()
            send_otp(phone, otp)

            request.session['pending_user_id'] = user.id
            request.session['pending_user_type'] = user_type

            messages.info(request, f'We sent a 6-digit code to {phone}.')
            return redirect('verify_otp')

    else:
        form = CustomUserCreationForm()

    return render(request, 'ErrandM8App/Signup.html', _ctx(request, {'form': form}))


def verify_otp(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        return redirect('signup')

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp']

            if user.profile.otp_valid(code):
                user.profile.phone_verified = True
                user.profile.otp_code = ''
                user.profile.save(update_fields=['phone_verified', 'otp_code'])

                auth_login(request, user)
                del request.session['pending_user_id']

                messages.success(request, 'Phone verified!')
                return _dashboard_redirect(user)

            messages.error(request, 'Invalid or expired code.')

        if request.POST.get('resend'):
            otp = user.profile.generate_otp()
            send_otp(user.profile.phone_number, otp)
            messages.info(request, 'New code sent.')

    else:
        form = OTPForm()

    return render(request, 'ErrandM8App/Verify_otp.html', _ctx(request, {
        'form': form,
        'phone': user.profile.phone_number,
        'user': user,
    }))


def resend_otp(request):
    user_id = request.session.get('pending_user_id') or (
        request.user.id if request.user.is_authenticated else None
    )
    if not user_id:
        return redirect('signup')

    user = get_object_or_404(User, id=user_id)
    otp = user.profile.generate_otp()
    send_otp(user.profile.phone_number, otp)

    messages.info(request, 'A new code has been sent.')
    return redirect('verify_otp')


# ─────────────────────────────────────────────
# LOGIN + 2FA
# ─────────────────────────────────────────────

def login(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)

    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if user.profile.two_fa_enabled and user.profile.phone_verified:
                otp = user.profile.generate_otp()
                send_otp(user.profile.phone_number, otp)
                request.session['twofa_user_id'] = user.id
                return redirect('two_fa_verify')

            auth_login(request, user)
            return _dashboard_redirect(user)

    else:
        form = CustomAuthenticationForm()

    return render(request, 'ErrandM8App/Login.html', _ctx(request, {'form': form}))


def two_fa_verify(request):
    user_id = request.session.get('twofa_user_id')
    if not user_id:
        return redirect('login')

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            if user.profile.otp_valid(form.cleaned_data['otp']):
                user.profile.otp_code = ''
                user.profile.save(update_fields=['otp_code'])

                auth_login(request, user)
                del request.session['twofa_user_id']

                return _dashboard_redirect(user)

    else:
        form = OTPForm()

    return render(request, 'ErrandM8App/Two_fa.html', _ctx(request, {'form': form}))


@login_required
def logout_view(request):
    auth_logout(request)
    return redirect('landing_page')


# ─────────────────────────────────────────────
# 2FA TOGGLE
# ─────────────────────────────────────────────

@login_required
@require_POST
def toggle_two_fa(request):
    profile = request.user.profile

    if not profile.phone_verified:
        messages.error(request, 'Verify phone first.')
        return redirect('profile')

    profile.two_fa_enabled = not profile.two_fa_enabled
    profile.save(update_fields=['two_fa_enabled'])

    return redirect('profile')


# ─────────────────────────────────────────────
# PASSWORD RESET
# ─────────────────────────────────────────────

def password_reset(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            for user in User.objects.filter(email__iexact=email, is_active=True):
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_url = request.build_absolute_uri(f'/reset/{uid}/{token}/')

                send_mail(
                    'Reset password',
                    f'Reset link: {reset_url}',
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            return redirect('password_reset_done')
    else:
        form = PasswordResetForm()

    return render(request, 'ErrandM8App/Password_reset.html', {'form': form})


def password_reset_done(request):
    return render(request, 'ErrandM8App/Password_reset_done.html')


def password_reset_confirm(request, uidb64=None, token=None):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    valid = user and default_token_generator.check_token(user, token)

    if request.method == 'POST' and valid:
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            return redirect('password_reset_complete')
    else:
        form = SetPasswordForm(user) if valid else None

    return render(request, 'ErrandM8App/Password_confirm.html', {
        'form': form,
        'valid_link': valid
    })


def password_reset_complete(request):
    return render(request, 'ErrandM8App/Password_reset_complete.html')


# ─────────────────────────────────────────────
# LOCATION
# ─────────────────────────────────────────────

@login_required
@require_POST
def update_location(request):
    data = json.loads(request.body)
    lat = float(data['latitude'])
    lng = float(data['longitude'])

    p = request.user.profile
    p.latitude = lat
    p.longitude = lng
    p.location_updated_at = timezone.now()
    p.is_online = True
    p.save()

    return JsonResponse({'status': 'ok'})


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────

@login_required
def notifications(request):
    notifs = request.user.notifications.all()
    request.user.notifications.filter(is_read=False).update(is_read=True)

    return render(request, 'ErrandM8App/Notifications.html', _ctx(request, {
        'notifications': notifs
    }))


@login_required
def mark_notification_read(request, notif_id):
    n = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    n.is_read = True
    n.save()
    return JsonResponse({'status': 'ok'})


# ─────────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────────

@login_required
def profile_view(request, username=None):
    target_user = get_object_or_404(User, username=username) if username else request.user

    profile = target_user.profile
    is_own = target_user == request.user

    reviews = target_user.reviews_received.all().order_by('-created_at')
    tasks_completed = Task.objects.filter(runner=target_user, status='Paid').count()

    form = None
    if is_own and request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    elif is_own:
        form = ProfileForm(instance=profile)

    return render(request, 'ErrandM8App/Profile.html', _ctx(request, {
        'target_user': target_user,
        'profile': profile,
        'form': form,
        'reviews': reviews,
        'tasks_completed': tasks_completed,
        'is_own': is_own,
    }))


# ─────────────────────────────────────────────
# DASHBOARDS
# ─────────────────────────────────────────────

@login_required
def client_dashboard(request):
    Profile.objects.get_or_create(user=request.user)

    tasks = Task.objects.filter(client=request.user).order_by('-created_at')

    for task in tasks:
        task.can_review = (
            task.status == 'Paid'
            and task.runner
            and not Review.objects.filter(task=task, reviewer=request.user).exists()
        )
        task.latest_counter = task.counters.order_by('-created_at').first()

    return render(request, 'ErrandM8App/Client_dashboard.html', _ctx(request, {'tasks': tasks}))


@login_required
def runner_dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    tasks_pending = Task.nearby_pending(profile, radius_km=3)
    tasks_accepted = Task.objects.filter(runner=request.user, status='In Progress')
    tasks_completed = Task.objects.filter(runner=request.user, status__in=['Completed', 'Paid'])

    return render(request, 'ErrandM8App/Runner_dashboard.html', _ctx(request, {
        'tasks_pending': tasks_pending,
        'tasks_accepted': tasks_accepted,
        'tasks_completed': tasks_completed,
        'has_location': profile.latitude is not None,
        'runner_lat': profile.latitude,
        'runner_lng': profile.longitude,
    }))


# ─────────────────────────────────────────────
# TASK FLOW
# ─────────────────────────────────────────────

@login_required
def post_task(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.client = request.user
            task.save()

            send_task_notification(task)
            return redirect('client_dashboard')

    return render(request, 'ErrandM8App/Post_task.html', _ctx(request, {'form': TaskForm()}))


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.user not in (task.client, task.runner):
        return redirect('landing_page')

    messages = task.messages.all()
    counters = task.counters.all()
    review = getattr(task, 'review', None)

    return render(request, 'ErrandM8App/Task_detail.html', _ctx(request, {
        'task': task,
        'messages': messages,
        'counters': counters,
        'review': review,
    }))


@login_required
def set_price(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        form = PriceCounterForm(request.POST)
        if form.is_valid():
            counter = form.save(commit=False)
            counter.task = task
            counter.proposed_by = request.user
            counter.save()

            return redirect('runner_dashboard')
    return render(request, 'ErrandM8App/Set_price.html', {'form': PriceCounterForm()})


@login_required
def counter_price(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        form = PriceCounterForm(request.POST)
        if form.is_valid():
            counter = form.save(commit=False)
            counter.task = task
            counter.save()

            return redirect('client_dashboard')
    return render(request, 'ErrandM8App/Counter_price.html', {'form': PriceCounterForm()})


@login_required
def accept_task(request, task_id, action):
    task = get_object_or_404(Task, id=task_id)
    task.status = 'In Progress' if action == 'accept' else 'Pending'
    task.save()
    return redirect('client_dashboard')


@login_required
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.status = 'Completed'
    task.save()
    return redirect('runner_dashboard')


@login_required
def pay_runner(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.status = 'Paid'
    task.save()
    return redirect('client_dashboard')


@login_required
def cancel_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.status = 'Cancelled'
    task.save()
    return redirect('client_dashboard')


@login_required
def leave_review(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.task = task
            review.save()
            return redirect('client_dashboard')


# ─────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────

@login_required
@require_POST
def send_chat(request, task_id):
    data = json.loads(request.body)
    msg = ChatMessage.objects.create(
        task_id=task_id,
        sender=request.user,
        body=data.get('body')
    )
    return JsonResponse({'id': msg.id})


@login_required
def poll_chat(request, task_id):
    msgs = ChatMessage.objects.filter(task_id=task_id)
    return JsonResponse({'messages': list(msgs.values())})
