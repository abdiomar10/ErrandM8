import os
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------
# Core SMS sender
# ---------------------------------------------

def send_sms(phone, message):
    phone = phone.strip().replace(' ', '')

    # Normalize Kenyan numbers
    if phone.startswith('07') or phone.startswith('01'):
        phone = '+254' + phone[1:]
    elif phone.startswith('254'):
        phone = '+' + phone

    username = os.environ.get('AT_USERNAME')
    api_key = os.environ.get('AT_API_KEY')

    # Dev mode fallback
    if not username or not api_key:
        logger.warning(f'[SMS DEV] To {phone}: {message}')
        print(f'\n?? SMS ? {phone}\n{message}\n')
        return True

    try:
        import africastalking
        africastalking.initialize(username, api_key)
        sms = africastalking.SMS
        response = sms.send(message, [phone])

        recipients = response.get('SMSMessageData', {}).get('Recipients', [])
        return bool(recipients and recipients[0].get('status') == 'Success')

    except Exception as e:
        logger.error(f'SMS exception to {phone}: {e}')
        return False


# ---------------------------------------------
# OTP
# ---------------------------------------------

def send_otp(phone, otp):
    return send_sms(
        phone,
        f'Your Usend verification code is: {otp}\nValid for 10 minutes. Do not share.'
    )


# ---------------------------------------------
# TASK NOTIFICATIONS (FIXED + COMPATIBLE)
# ---------------------------------------------

def send_task_notification(task, event='new_errand', recipient_phone=None):
    """
    FIXED:
    - Now accepts task object (used in your views)
    - Also supports manual phone fallback
    """

    title = getattr(task, 'title', 'your errand')

    msgs = {
        'runner_accepted':  f'Usend: A runner accepted "{title}".',
        'task_started':     f'Usend: "{title}" is now in progress!',
        'task_completed':   f'Usend: "{title}" is complete. Please pay the runner.',
        'payment_received': f'Usend: Payment received for "{title}". Well done!',
        'new_errand':       f'Usend: New errand nearby - "{title}". Open the app to accept.',
        'price_proposed':   f'Usend: New price proposed for "{title}". Check your app.',
        'price_countered':  f'Usend: Counter offer received for "{title}".',
        'chat_message':     f'Usend: New message about "{title}".',
        'task_declined':    f'Usend: Update on "{title}".',
    }

    message = msgs.get(event, f'Usend: Update on "{title}".')

    # Try to get phone automatically from task
    phone = recipient_phone

    if not phone:
        try:
            # client or runner fallback
            if hasattr(task, 'client') and task.client:
                phone = task.client.profile.phone_number
            elif hasattr(task, 'runner') and task.runner:
                phone = task.runner.profile.phone_number
        except Exception:
            phone = None

    if not phone:
        logger.warning(f'[SMS] No phone found for event={event}')
        return False

    return send_sms(phone, message)
