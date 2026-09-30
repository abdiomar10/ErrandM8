import json
import hashlib
import hmac
import math
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages as django_messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Prefetch

from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm,
    TaskForm, ReviewForm, PriceCounterForm, ProfileForm,
    OTPForm,
)
from .models import Profile, Task, Review, PriceCounter, Notification, ChatMessage
from .sms import send_otp, send_sms


def _notify(recipient, notif_type, message, task=None):
    Notification.objects.create(
        recipient=recipient, notif_type=notif_type,
        message=message, task=task,
    )

def _ctx(request, extra=None):
    ctx = {}
    if extra:
        ctx.update(extra)
    return ctx

def _dashboard_redirect(user):
    try:
        if user.profile.user_type == 'concierge':
            return redirect('concierge_dashboard')
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


def _client_ip(request):
    return request.META.get('REMOTE_ADDR', 'unknown')


def _login_failure_keys(request):
    secret = settings.SECRET_KEY.encode()
    ip_digest = hmac.new(secret, _client_ip(request).encode(), hashlib.sha256).hexdigest()
    keys = {f'login_failures:ip:{ip_digest}': 100}
    username = request.POST.get('username', '').strip().casefold()
    if username:
        user_digest = hmac.new(secret, username.encode(), hashlib.sha256).hexdigest()
        keys[f'login_failures:user:{user_digest}'] = 5
    return keys


def _login_locked_out(keys):
    return any(cache.get(key, 0) >= limit for key, limit in keys.items())


def landing_page(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)

    category_lookup = {key: value for key, value in Task.CATEGORY_CHOICES}
    icon_lookup = {
        'delivery': '📦',
        'shopping': '🛒',
        'babysitting': '🧸',
        'pickup': '🚗',
        'document': '📄',
        'cleaning': '🧼',
        'cooking': '🍽️',
        'laundry': '🧺',
        'errands': '✅',
        'other': '✨',
    }

    category_counts = Task.objects.filter(status='Pending').values(
        'category'
    ).annotate(task_count=Count('id')).order_by('-task_count')[:5]

    popular_categories = [
        {
            'category': row['category'],
            'name': category_lookup.get(row['category'], row['category'].title()),
            'count': row['task_count'],
            'icon': icon_lookup.get(row['category'], '✨'),
        }
        for row in category_counts
    ]

    return render(request, 'ErrandM8App/Landing_page.html', _ctx(request, {'popular_categories': popular_categories}))

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


def signup(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            phone     = form.cleaned_data['phone_number']
            user_type = form.cleaned_data['user_type']

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.user_type    = user_type
            profile.phone_number = phone
            profile.save()

            otp = profile.generate_otp()
            send_otp(phone, otp)

            request.session['pending_user_id']   = user.id
            request.session['pending_user_type'] = user_type
            django_messages.info(request, f'We sent a 6-digit code to {phone}.')
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
        if request.POST.get('resend'):
            profile = user.profile
            if profile.otp_created_at and (timezone.now() - profile.otp_created_at).total_seconds() < 60:
                django_messages.warning(request, 'Please wait 60 seconds before requesting another code.')
            else:
                otp = profile.generate_otp()
                send_otp(profile.phone_number, otp)
                django_messages.info(request, 'New code sent.')
            return redirect('verify_otp')

        form = OTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp']
            if user.profile.verify_otp(code):
                user.profile.phone_verified = True
                user.profile.save(update_fields=['phone_verified'])
                auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                del request.session['pending_user_id']
                django_messages.success(request, f'Welcome to ErrandM8, {user.username}!')
                return _dashboard_redirect(user)
            django_messages.error(request, 'Invalid or expired code.')
    else:
        form = OTPForm()

    return render(request, 'ErrandM8App/Verify_otp.html', _ctx(request, {
        'form': form,
        'phone': user.profile.phone_number,
        'user': user,
    }))


@require_POST
def resend_otp(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        return redirect('signup')
    user = get_object_or_404(User, id=user_id)
    profile = user.profile
    if profile.otp_created_at and (timezone.now() - profile.otp_created_at).total_seconds() < 60:
        django_messages.warning(request, 'Please wait 60 seconds before requesting another code.')
        return redirect('verify_otp')
    otp = profile.generate_otp()
    send_otp(profile.phone_number, otp)
    django_messages.info(request, 'A new code has been sent.')
    return redirect('verify_otp')


def login(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)

    failure_keys = _login_failure_keys(request)
    if _login_locked_out(failure_keys):
        django_messages.error(request, 'Too many failed login attempts. Please wait 10 minutes and try again.')
        return render(request, 'ErrandM8App/Login.html', _ctx(request, {'form': CustomAuthenticationForm()}))

    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            cache.delete_many(failure_keys)
            user = form.get_user()
            if user.profile.two_fa_enabled and user.profile.phone_verified:
                profile = user.profile
                if not profile.otp_created_at or (timezone.now() - profile.otp_created_at).total_seconds() >= 60:
                    otp = profile.generate_otp()
                    send_otp(profile.phone_number, otp)
                request.session['twofa_user_id'] = user.id
                django_messages.info(request, f'Code sent to {user.profile.phone_number}.')
                return redirect('two_fa_verify')
            auth_login(request, user)
            return _dashboard_redirect(user)

        for key in failure_keys:
            if not cache.add(key, 1, timeout=600):
                cache.incr(key)
        remaining_attempts = min(
            limit - cache.get(key, 0)
            for key, limit in failure_keys.items()
        )
        if remaining_attempts <= 0:
            django_messages.error(request, 'Too many failed login attempts. Please wait 10 minutes and try again.')
        else:
            django_messages.error(request, f'Invalid username or password. {remaining_attempts} attempts remaining before lockout.')
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
            if user.profile.verify_otp(form.cleaned_data['otp']):
                auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                del request.session['twofa_user_id']
                return _dashboard_redirect(user)
            django_messages.error(request, 'Invalid or expired code.')
    else:
        form = OTPForm()

    return render(request, 'ErrandM8App/Two_fa.html', _ctx(request, {
        'form': form,
        'phone': user.profile.phone_number,
    }))


@login_required
@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect('landing_page')


@login_required
@require_POST
def toggle_two_fa(request):
    profile = request.user.profile
    if not profile.phone_verified:
        django_messages.error(request, 'Verify your phone number first.')
        return redirect('profile')
    profile.two_fa_enabled = not profile.two_fa_enabled
    profile.save(update_fields=['two_fa_enabled'])
    state = 'enabled' if profile.two_fa_enabled else 'disabled'
    django_messages.success(request, f'Two-factor authentication {state}.')
    return redirect('profile')


def password_reset(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            for user in User.objects.filter(email__iexact=email, is_active=True):
                uid   = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_url = request.build_absolute_uri(f'/reset/{uid}/{token}/')
                send_mail(
                    'Reset your ErrandM8 password',
                    f'Hi {user.username},\n\nReset your password:\n{reset_url}\n\n- ErrandM8',
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
        uid  = force_str(urlsafe_base64_decode(uidb64))
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
        'form': form, 'valid_link': valid,
    })

def password_reset_complete(request):
    return render(request, 'ErrandM8App/Password_reset_complete.html')


@login_required
@require_POST
def update_location(request):
    try:
        data = json.loads(request.body)
        lat  = float(data['latitude'])
        lng  = float(data['longitude'])
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError('Coordinates are out of range.')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'bad payload'}, status=400)

    p = request.user.profile
    if p.user_type != 'concierge':
        return JsonResponse({'error': 'forbidden'}, status=403)
    p.latitude = lat
    p.longitude = lng
    p.location_updated_at = timezone.now()
    p.is_online = True
    p.save(update_fields=['latitude', 'longitude', 'location_updated_at', 'is_online'])
    return JsonResponse({'status': 'ok'})


@login_required
def notifications(request):
    notifs = request.user.notifications.all()
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'ErrandM8App/Notifications.html', _ctx(request, {
        'notifications': notifs,
    }))

@login_required
def mark_notification_read(request, notif_id):
    n = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    n.is_read = True
    n.save()
    return JsonResponse({'status': 'ok'})


@login_required
def profile_view(request, username=None):
    target_user = get_object_or_404(User, username=username) if username else request.user
    profile     = target_user.profile
    is_own      = (target_user == request.user)
    reviews     = target_user.reviews_received.select_related('reviewer', 'task').order_by('-created_at')
    tasks_completed = Task.objects.filter(concierge=target_user, status='Paid').count()

    form = None
    if is_own and request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            django_messages.success(request, 'Profile updated.')
            return redirect('profile')
    elif is_own:
        form = ProfileForm(instance=profile)

    return render(request, 'ErrandM8App/Profile.html', _ctx(request, {
        'target_user':    target_user,
        'profile':        profile,
        'form':           form,
        'reviews':        reviews,
        'tasks_completed': tasks_completed,
        'is_own':         is_own,
    }))


@login_required
def client_dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'client':
        return redirect('concierge_dashboard')
    tasks = Task.objects.filter(client=request.user).select_related(
        'concierge', 'review'
    ).prefetch_related(
        Prefetch(
            'counters',
            queryset=PriceCounter.objects.select_related('proposed_by').order_by('-created_at'),
            to_attr='dashboard_counters',
        )
    )

    page_obj = Paginator(tasks, 20).get_page(request.GET.get('page'))
    for task in page_obj:
        task.can_review = (
            task.status == 'Paid'
            and task.concierge is not None
            and not getattr(task, 'review', None)
        )
        task.latest_counter = task.dashboard_counters[0] if task.dashboard_counters else None
        if task.client_budget and task.proposed_price:
            task.suggested_price = round(
                (float(task.client_budget) + float(task.proposed_price)) / 2
            )
        else:
            task.suggested_price = None

    return render(request, 'ErrandM8App/Client_dashboard.html', _ctx(request, {
        'tasks': page_obj,
        'page_obj': page_obj,
    }))


@login_required
def concierge_dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.user_type != 'concierge':
        return redirect('client_dashboard')

    tasks_pending   = Task.nearby_pending(profile, radius_km=3)
    tasks_accepted  = Task.objects.filter(concierge=request.user, status='In Progress')
    tasks_completed = Task.objects.filter(concierge=request.user, status__in=['Completed', 'Paid'])

    return render(request, 'ErrandM8App/Concierge_dashboard.html', _ctx(request, {
        'tasks_pending':   tasks_pending,
        'tasks_accepted':  tasks_accepted,
        'tasks_completed': tasks_completed,
        'has_location':    profile.latitude is not None,
        'concierge_lat':   profile.latitude,
        'concierge_lng':   profile.longitude,
    }))


@login_required
def post_task(request):
    if request.user.profile.user_type != 'client':
        django_messages.error(request, 'Only clients can post errands.')
        return redirect('concierge_dashboard')

    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.client = request.user
            lat = request.POST.get('pickup_latitude')
            lng = request.POST.get('pickup_longitude')
            if lat or lng:
                try:
                    latitude = float(lat)
                    longitude = float(lng)
                except (TypeError, ValueError):
                    form.add_error(None, 'We could not validate the pickup coordinates. Please try again.')
                    return render(request, 'ErrandM8App/Post_task.html', _ctx(request, {'form': form}), status=400)
                if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
                    form.add_error(None, 'Pickup coordinates are out of range. Please try again.')
                    return render(request, 'ErrandM8App/Post_task.html', _ctx(request, {'form': form}), status=400)
                task.pickup_latitude = latitude
                task.pickup_longitude = longitude
            task.save()
            django_messages.success(request, 'Errand posted! Nearby concierges will be notified.')
            return redirect('client_dashboard')
    else:
        form = TaskForm()
    return render(request, 'ErrandM8App/Post_task.html', _ctx(request, {'form': form}))


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.user not in (task.client, task.concierge):
        django_messages.error(request, 'Access denied.')
        return redirect('landing_page')

    chat_messages = task.messages.select_related('sender').all()
    counters      = task.counters.select_related('proposed_by').all()
    review        = getattr(task, 'review', None)

    task.messages.exclude(sender=request.user).update(is_read=True)

    if request.method == 'POST' and request.POST.get('chat_body'):
        body = request.POST['chat_body'].strip()
        if body:
            ChatMessage.objects.create(task=task, sender=request.user, body=body)
            other = task.concierge if request.user == task.client else task.client
            if other:
                _notify(other, 'chat_message', f'{request.user.username}: {body[:80]}', task=task)
            return redirect('task_detail', task_id=task_id)

    task_participant_ids = [task.client_id, task.concierge_id] if task.concierge_id else [task.client_id]

    return render(request, 'ErrandM8App/Task_detail.html', _ctx(request, {
        'task':          task,
        'chat_messages': chat_messages,
        'counters':      counters,
        'review':        review,
        'task_participant_ids': task_participant_ids,
    }))


@login_required
def set_price(request, task_id):
    task = get_object_or_404(Task, id=task_id, status='Pending')
    if request.user.profile.user_type != 'concierge':
        django_messages.error(request, 'Only concierges can propose a price.')
        return redirect('client_dashboard')

    if request.method == 'POST':
        form = PriceCounterForm(request.POST)
        if form.is_valid():
            counter = form.save(commit=False)
            counter.task        = task
            counter.proposed_by = request.user
            counter.save()

            task.concierge      = request.user
            task.proposed_price = counter.amount
            task.save(update_fields=['concierge', 'proposed_price'])

            _notify(
                task.client, 'price_proposed',
                f'{request.user.username} proposed KSh {counter.amount} for "{task.title}".',
                task=task,
            )
            _sms_if_phone(
                task.client,
                f'ErrandM8: {request.user.username} proposed KSh {counter.amount} for "{task.title}". Log in to accept.',
            )
            django_messages.success(request, 'Price submitted - waiting for the client.')
            return redirect('concierge_dashboard')
    else:
        form = PriceCounterForm()

    return render(request, 'ErrandM8App/Set_price.html', _ctx(request, {
        'task': task, 'form': form,
    }))


@login_required
def counter_price(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.user != task.client:
        django_messages.error(request, 'Only the client can counter a price.')
        return redirect('client_dashboard')

    if request.method == 'POST':
        form = PriceCounterForm(request.POST)
        if form.is_valid():
            counter = form.save(commit=False)
            counter.task        = task
            counter.proposed_by = request.user
            counter.save()

            if task.concierge:
                _notify(
                    task.concierge, 'price_countered',
                    f'{request.user.username} countered with KSh {counter.amount}.',
                    task=task,
                )
                _sms_if_phone(
                    task.concierge,
                    f'ErrandM8: {request.user.username} countered with KSh {counter.amount} for "{task.title}".',
                )
            django_messages.success(request, 'Counter-offer sent.')
            return redirect('client_dashboard')
    else:
        form = PriceCounterForm()

    return render(request, 'ErrandM8App/Counter_price.html', _ctx(request, {
        'task': task, 'form': form,
    }))


@login_required
@require_POST
def accept_task(request, task_id, action):
    task = get_object_or_404(Task, id=task_id)

    if request.user != task.client:
        django_messages.error(request, 'Only the client can do this.')
        return redirect('client_dashboard')

    if action == 'accept' and task.concierge:
        latest = task.counters.filter(is_accepted=None).order_by('-created_at').first()
        if latest:
            latest.is_accepted = True
            latest.save()
        task.status = 'In Progress'
        task.save(update_fields=['status'])
        _notify(
            task.concierge, 'task_accepted',
            f'Your price for "{task.title}" was accepted! Get started.',
            task=task,
        )
        _sms_if_phone(task.concierge, f'ErrandM8: Your price was accepted for "{task.title}". Get started!')
        django_messages.success(request, 'Errand accepted - the concierge has been notified.')

    elif action == 'decline':
        latest = task.counters.filter(is_accepted=None).order_by('-created_at').first()
        if latest:
            latest.is_accepted = False
            latest.save()
        if task.concierge:
            _notify(
                task.concierge, 'task_declined',
                f'Your price for "{task.title}" was declined.',
                task=task,
            )
        task.concierge      = None
        task.proposed_price = None
        task.status         = 'Pending'
        task.save(update_fields=['concierge', 'proposed_price', 'status'])
        django_messages.info(request, 'Price declined. Errand is back in the pool.')

    return redirect('client_dashboard')


@login_required
@require_POST
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, status='In Progress')

    if request.user != task.concierge:
        django_messages.error(request, 'Only the assigned concierge can mark this complete.')
        return redirect('concierge_dashboard')

    task.status = 'Completed'
    task.save(update_fields=['status'])

    _notify(
        task.client, 'task_completed',
        f'"{task.title}" is complete. Please pay your concierge.',
        task=task,
    )
    _sms_if_phone(
        task.client,
        f'ErrandM8: "{task.title}" is complete. Please pay the concierge KSh {task.proposed_price}.',
    )
    django_messages.success(request, 'Marked complete - waiting for client payment.')
    return redirect('concierge_dashboard')


@login_required
@require_POST
def pay_concierge(request, task_id):
    task = get_object_or_404(Task, id=task_id, status='Completed')

    if request.user != task.client:
        django_messages.error(request, 'Only the client can confirm payment.')
        return redirect('client_dashboard')

    task.status = 'Paid'
    task.save(update_fields=['status'])

    if task.concierge:
        p = task.concierge.profile
        p.jobs_completed += 1
        if task.proposed_price:
            p.total_earned += task.proposed_price
        p.save(update_fields=['jobs_completed', 'total_earned'])
        _notify(
            task.concierge, 'payment_received',
            f'Payment confirmed for "{task.title}". KSh {task.proposed_price} received!',
            task=task,
        )
        _sms_if_phone(
            task.concierge,
            f'ErrandM8: Payment of KSh {task.proposed_price} received for "{task.title}". Well done!',
        )

    django_messages.success(request, 'Payment confirmed! Please rate your concierge.')
    return redirect('client_dashboard')


@login_required
@require_POST
def cancel_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.user != task.client:
        django_messages.error(request, 'Only the client can cancel this errand.')
        return redirect('client_dashboard')

    if task.status not in ('Pending',):
        django_messages.error(request, 'You can only cancel a pending errand.')
        return redirect('client_dashboard')

    task.status = 'Cancelled'
    task.save(update_fields=['status'])

    if task.concierge:
        _notify(
            task.concierge, 'task_declined',
            f'The errand "{task.title}" was cancelled by the client.',
            task=task,
        )
    django_messages.success(request, 'Errand cancelled.')
    return redirect('client_dashboard')


@login_required
def leave_review(request, task_id):
    task = get_object_or_404(Task, id=task_id, status='Paid')

    if request.user != task.client:
        django_messages.error(request, 'Only the client can leave a review.')
        return redirect('client_dashboard')

    if Review.objects.filter(task=task, reviewer=request.user).exists():
        django_messages.info(request, 'You have already reviewed this errand.')
        return redirect('client_dashboard')

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review          = form.save(commit=False)
            review.task     = task
            review.reviewer = request.user
            review.reviewee = task.concierge
            review.save()
            _notify(
                task.concierge, 'review_received',
                f'{request.user.username} left you a {review.score} review.',
                task=task,
            )
            django_messages.success(request, 'Review submitted. Thank you!')
            return redirect('client_dashboard')
    else:
        form = ReviewForm()

    return render(request, 'ErrandM8App/Leave_review.html', _ctx(request, {
        'form': form, 'task': task,
    }))


@login_required
@require_POST
def send_chat(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.user not in (task.client, task.concierge):
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        body = data.get('body', '').strip()
    except Exception:
        return JsonResponse({'error': 'bad request'}, status=400)
    if not body:
        return JsonResponse({'error': 'empty'}, status=400)

    msg   = ChatMessage.objects.create(task=task, sender=request.user, body=body)
    other = task.concierge if request.user == task.client else task.client
    if other:
        _notify(other, 'chat_message', f'{request.user.username}: {body[:80]}', task=task)

    return JsonResponse({
        'id':     msg.id,
        'sender': request.user.username,
        'body':   msg.body,
        'time':   msg.created_at.strftime('%H:%M'),
    })


@login_required
def poll_chat(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.user not in (task.client, task.concierge):
        return JsonResponse({'error': 'forbidden'}, status=403)
    since = int(request.GET.get('since', 0))
    msgs  = task.messages.filter(id__gt=since).exclude(sender=request.user)
    msgs.update(is_read=True)
    return JsonResponse({'messages': [
        {'id': m.id, 'sender': m.sender.username, 'body': m.body, 'time': m.created_at.strftime('%H:%M')}
        for m in msgs
    ]})