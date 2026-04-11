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
)
from .models import Profile, Task, Review, PriceCounter, Notification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notify(recipient, notif_type, message, task=None):
    """Create an in-app notification."""
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


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

def landing_page(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)
    return render(request, 'UsendApp/Landing_page.html', {
        'unread': _unread_count(request.user),
    })


def about(request):
    return render(request, 'UsendApp/About.html', {
        'unread': _unread_count(request.user),
    })


def contact(request):
    return render(request, 'UsendApp/Contact.html', {
        'unread': _unread_count(request.user),
    })


def terms_and_conditions(request):
    return render(request, 'UsendApp/Terms_and_conditions.html')


def privacy_policy(request):
    return render(request, 'UsendApp/Privacy_policy.html')


def csrf_failure(request, reason=""):
    return render(request, 'UsendApp/csrf_failure.html', {'reason': reason}, status=403)


# ---------------------------------------------------------------------------
# Auth — Sign up
# ---------------------------------------------------------------------------

def signup(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            user_type = form.cleaned_data['user_type']
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.user_type = user_type
            profile.save()
            messages.success(request, f'Welcome to Usend, {user.username}!')
            return redirect('client_dashboard' if user_type == 'client' else 'runner_dashboard')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = CustomUserCreationForm()
    return render(request, 'UsendApp/Signup.html', {'form': form})


# ---------------------------------------------------------------------------
# Auth — Log in / out
# ---------------------------------------------------------------------------

def login(request):
    if request.user.is_authenticated:
        return _dashboard_redirect(request.user)
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return _dashboard_redirect(user)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = CustomAuthenticationForm()
    return render(request, 'UsendApp/Login.html', {'form': form})


@login_required
def logout_view(request):
    auth_logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('landing_page')


def _dashboard_redirect(user):
    try:
        if user.profile.user_type == 'runner':
            return redirect('runner_dashboard')
    except Profile.DoesNotExist:
        pass
    return redirect('client_dashboard')


# ---------------------------------------------------------------------------
# Password reset — full implementation using Django's built-in tokens
# ---------------------------------------------------------------------------

def password_reset(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            users = User.objects.filter(email__iexact=email, is_active=True)
            for user in users:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_url = request.build_absolute_uri(
                    f'/reset/{uid}/{token}/'
                )
                send_mail(
                    subject='Reset your Usend password',
                    message=(
                        f'Hi {user.username},\n\n'
                        f'Click the link below to reset your password:\n{reset_url}\n\n'
                        f'If you didn\'t request this, ignore this email.\n\n— The Usend team'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            # Always redirect to "done" — don't reveal whether email exists
            return redirect('password_reset_done')
    else:
        form = PasswordResetForm()
    return render(request, 'UsendApp/Password_reset.html', {'form': form})


def password_reset_done(request):
    return render(request, 'UsendApp/Password_reset_done.html')


def password_reset_confirm(request, uidb64=None, token=None):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    valid = user is not None and default_token_generator.check_token(user, token)

    if request.method == 'POST' and valid:
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password updated — please log in.')
            return redirect('password_reset_complete')
    else:
        form = SetPasswordForm(user) if valid else None

    return render(request, 'UsendApp/Password_confirm.html', {
        'form': form,
        'valid_link': valid,
    })


def password_reset_complete(request):
    return render(request, 'UsendApp/Password_reset_complete.html')


# ---------------------------------------------------------------------------
# Location — runner sends GPS coords
# ---------------------------------------------------------------------------

@login_required
@require_POST
def update_location(request):
    try:
        data = json.loads(request.body)
        lat = float(data['latitude'])
        lng = float(data['longitude'])
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid payload'}, status=400)

    profile = request.user.profile
    profile.latitude = lat
    profile.longitude = lng
    profile.location_updated_at = timezone.now()
    profile.save(update_fields=['latitude', 'longitude', 'location_updated_at'])
    return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@login_required
def notifications(request):
    notifs = request.user.notifications.all()[:50]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'UsendApp/Notifications.html', {
        'notifications': notifs,
        'unread': 0,
    })


@login_required
@require_POST
def mark_notification_read(request, notif_id):
    request.user.notifications.filter(id=notif_id).update(is_read=True)
    return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@login_required
def profile_view(request, username=None):
    if username:
        target_user = get_object_or_404(User, username=username)
    else:
        target_user = request.user

    profile = target_user.profile
    reviews_received = target_user.reviews_received.select_related('reviewer', 'task').order_by('-created_at')
    tasks_completed = Task.objects.filter(runner=target_user, status='Paid').count()

    is_own = (request.user == target_user)

    if is_own and request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        form = ProfileForm(instance=profile) if is_own else None

    return render(request, 'UsendApp/Profile.html', {
        'target_user': target_user,
        'profile': profile,
        'reviews': reviews_received,
        'tasks_completed': tasks_completed,
        'form': form,
        'is_own': is_own,
        'unread': _unread_count(request.user),
    })


# ---------------------------------------------------------------------------
# Client dashboard
# ---------------------------------------------------------------------------

@login_required
def client_dashboard(request):
    if not hasattr(request.user, 'profile'):
        Profile.objects.create(user=request.user, user_type='client')

    tasks = Task.objects.filter(client=request.user).prefetch_related('counters').order_by('-created_at')

    for task in tasks:
        task.can_review = (
            task.status == 'Paid'
            and task.runner is not None
            and not Review.objects.filter(task=task, reviewer=request.user).exists()
        )
        # Latest pending counter on this task (from the runner)
        task.latest_counter = task.counters.filter(is_accepted=None).order_by('-created_at').first()

    return render(request, 'UsendApp/Client_dashboard.html', {
        'tasks': tasks,
        'unread': _unread_count(request.user),
    })


# ---------------------------------------------------------------------------
# Runner dashboard
# ---------------------------------------------------------------------------

@login_required
def runner_dashboard(request):
    if not hasattr(request.user, 'profile'):
        Profile.objects.create(user=request.user, user_type='runner')

    profile = request.user.profile
    tasks_pending = Task.nearby_pending(profile, radius_km=3)
    has_location = profile.latitude is not None

    tasks_accepted = Task.objects.filter(
        runner=request.user, status='In Progress'
    ).prefetch_related('counters')

    tasks_completed = Task.objects.filter(
        runner=request.user, status__in=['Completed', 'Paid']
    ).order_by('-updated_at')[:20]

    # Earnings summary
    paid_tasks = Task.objects.filter(runner=request.user, status='Paid')
    total_earned = sum(t.proposed_price or 0 for t in paid_tasks)

    return render(request, 'UsendApp/Runner_dashboard.html', {
        'tasks_pending': tasks_pending,
        'tasks_accepted': tasks_accepted,
        'tasks_completed': tasks_completed,
        'has_location': has_location,
        'total_earned': total_earned,
        'profile': profile,
        'unread': _unread_count(request.user),
    })


# ---------------------------------------------------------------------------
# Errand lifecycle
# ---------------------------------------------------------------------------

@login_required
def post_task(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.client = request.user

            # GPS from hidden fields populated by JS geolocation
            try:
                task.pickup_latitude = float(request.POST['pickup_latitude']) if request.POST.get('pickup_latitude') else None
                task.pickup_longitude = float(request.POST['pickup_longitude']) if request.POST.get('pickup_longitude') else None
            except (ValueError, KeyError):
                task.pickup_latitude = None
                task.pickup_longitude = None

            task.save()
            messages.success(request, 'Errand posted! Runners in your area will see it shortly.')
            return redirect('client_dashboard')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = TaskForm()
    return render(request, 'UsendApp/Post_task.html', {
        'form': form,
        'unread': _unread_count(request.user),
    })


@login_required
def task_detail(request, task_id):
    """Public task detail — both client and runner can view."""
    task = get_object_or_404(Task, id=task_id)
    counters = task.counters.select_related('proposed_by').order_by('created_at')
    review = getattr(task, 'review', None)
    return render(request, 'UsendApp/Task_detail.html', {
        'task': task,
        'counters': counters,
        'review': review,
        'unread': _unread_count(request.user),
    })


@login_required
def set_price(request, task_id):
    """
    Runner proposes (or counter-proposes) a price for a task.
    Creates a PriceCounter and sets task.proposed_price + task.runner.
    """
    task = get_object_or_404(Task, id=task_id, status='Pending')

    # Only runners can propose prices
    if request.user.profile.user_type != 'runner':
        messages.error(request, 'Only runners can propose prices.')
        return redirect('client_dashboard')

    if request.method == 'POST':
        form = PriceCounterForm(request.POST)
        if form.is_valid():
            counter = form.save(commit=False)
            counter.task = task
            counter.proposed_by = request.user
            counter.save()

            # Update the task with this runner's proposal
            task.runner = request.user
            task.proposed_price = counter.amount
            task.save(update_fields=['runner', 'proposed_price'])

            # Notify the client
            _notify(
                recipient=task.client,
                notif_type='price_proposed',
                message=f'{request.user.username} proposed KSh {counter.amount} for "{task.title}".',
                task=task,
            )

            messages.success(request, 'Price submitted — waiting for the client to respond.')
            return redirect('runner_dashboard')
    else:
        form = PriceCounterForm()

    return render(request, 'UsendApp/Set_price.html', {
        'task': task,
        'form': form,
        'unread': _unread_count(request.user),
    })


@login_required
def counter_price(request, task_id):
    """
    Client counters the runner's proposed price.
    Creates a new PriceCounter from the client's side.
    """
    task = get_object_or_404(Task, id=task_id)

    if request.user != task.client:
        messages.error(request, 'Only the task owner can counter a price.')
        return redirect('client_dashboard')

    if request.method == 'POST':
        form = PriceCounterForm(request.POST)
        if form.is_valid():
            counter = form.save(commit=False)
            counter.task = task
            counter.proposed_by = request.user
            counter.save()

            # Notify the runner
            if task.runner:
                _notify(
                    recipient=task.runner,
                    notif_type='price_countered',
                    message=f'{request.user.username} countered with KSh {counter.amount} for "{task.title}".',
                    task=task,
                )

            messages.success(request, 'Counter-offer sent to the runner.')
            return redirect('client_dashboard')
    else:
        form = PriceCounterForm()

    return render(request, 'UsendApp/Counter_price.html', {
        'task': task,
        'form': form,
        'unread': _unread_count(request.user),
    })


@login_required
def accept_task(request, task_id, action):
    """Client accepts or declines the runner's proposed price."""
    task = get_object_or_404(Task, id=task_id)

    if request.user != task.client:
        messages.error(request, 'Only the task owner can do this.')
        return redirect('client_dashboard')

    if action == 'accept' and task.runner:
        # Mark the latest counter as accepted
        latest = task.counters.filter(is_accepted=None).order_by('-created_at').first()
        if latest:
            latest.is_accepted = True
            latest.save()

        task.status = 'In Progress'
        task.save(update_fields=['status'])

        _notify(
            recipient=task.runner,
            notif_type='task_accepted',
            message=f'Your price for "{task.title}" was accepted. Get started!',
            task=task,
        )
        messages.success(request, 'Errand accepted! The runner has been notified.')

    elif action == 'decline':
        # Mark the latest counter as declined and reset the task
        latest = task.counters.filter(is_accepted=None).order_by('-created_at').first()
        if latest:
            latest.is_accepted = False
            latest.save()

        if task.runner:
            _notify(
                recipient=task.runner,
                notif_type='task_declined',
                message=f'Your price for "{task.title}" was declined.',
                task=task,
            )

        task.runner = None
        task.proposed_price = None
        task.status = 'Pending'
        task.save(update_fields=['runner', 'proposed_price', 'status'])
        messages.info(request, 'Price declined. The errand is back in the pool for other runners.')

    return redirect('client_dashboard')


@login_required
def complete_task(request, task_id):
    """Runner marks a task as completed."""
    task = get_object_or_404(Task, id=task_id, status='In Progress')

    if request.user != task.runner:
        messages.error(request, 'Only the assigned runner can mark this complete.')
        return redirect('runner_dashboard')

    task.status = 'Completed'
    task.save(update_fields=['status'])

    _notify(
        recipient=task.client,
        notif_type='task_completed',
        message=f'"{task.title}" has been marked complete. Please pay the runner.',
        task=task,
    )
    messages.success(request, 'Errand marked complete — the client will pay you shortly.')
    return redirect('runner_dashboard')


@login_required
def pay_runner(request, task_id):
    """Client confirms payment to the runner."""
    task = get_object_or_404(Task, id=task_id, status='Completed')

    if request.user != task.client:
        messages.error(request, 'Only the task owner can confirm payment.')
        return redirect('client_dashboard')

    task.status = 'Paid'
    task.save(update_fields=['status'])

    if task.runner:
        _notify(
            recipient=task.runner,
            notif_type='payment_received',
            message=f'Payment confirmed for "{task.title}". KSh {task.proposed_price} received!',
            task=task,
        )
    messages.success(request, 'Payment confirmed! Please leave the runner a review.')
    return redirect('client_dashboard')


@login_required
def cancel_task(request, task_id):
    """Client cancels a pending task."""
    task = get_object_or_404(Task, id=task_id)

    if request.user != task.client:
        messages.error(request, 'Only the task owner can cancel this errand.')
        return redirect('client_dashboard')

    if task.status not in ('Pending',):
        messages.error(request, 'You can only cancel a pending errand.')
        return redirect('client_dashboard')

    task.status = 'Cancelled'
    task.save(update_fields=['status'])

    if task.runner:
        _notify(
            recipient=task.runner,
            notif_type='task_declined',
            message=f'The errand "{task.title}" was cancelled by the client.',
            task=task,
        )

    messages.success(request, 'Errand cancelled.')
    return redirect('client_dashboard')


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@login_required
def leave_review(request, task_id):
    task = get_object_or_404(Task, id=task_id, status='Paid')

    if request.user != task.client:
        messages.error(request, 'Only the client can leave a review here.')
        return redirect('client_dashboard')

    if Review.objects.filter(task=task, reviewer=request.user).exists():
        messages.info(request, 'You have already reviewed this errand.')
        return redirect('client_dashboard')

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.task = task
            review.reviewer = request.user
            review.reviewee = task.runner
            review.save()

            _notify(
                recipient=task.runner,
                notif_type='review_received',
                message=f'{request.user.username} left you a {review.score}★ review.',
                task=task,
            )
            messages.success(request, 'Review submitted. Thank you!')
            return redirect('client_dashboard')
    else:
        form = ReviewForm()

    return render(request, 'UsendApp/Leave_review.html', {
        'form': form,
        'task': task,
        'unread': _unread_count(request.user),
    })