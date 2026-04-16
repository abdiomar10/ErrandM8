import os
from dotenv import load_dotenv
import africastalking

# Load environment variables
load_dotenv()

username = os.getenv("AFRICASTALKING_USERNAME")
api_key = os.getenv("AFRICASTALKING_API_KEY")

# Initialize SDK
africastalking.initialize(username, api_key)
sms = africastalking.SMS


# ✅ 1. Generic SMS sender
def send_sms(phone_number, message):
    try:
        response = sms.send(message, [phone_number])
        print("SMS sent:", response)
        return response
    except Exception as e:
        print("SMS error:", e)
        return None


# ✅ 2. Send OTP
def send_otp(phone_number, otp):
    message = f"Your Usend verification code is: {otp}"
    return send_sms(phone_number, message)


# ✅ 3. Task notification SMS
def send_task_notification(phone_number, task_title, amount=None):
    if amount:
        message = f"New task: {task_title}. Earn KSh {amount}. Open Usend to accept."
    else:
        message = f"New task available: {task_title}. Check Usend now."
    
    return send_sms(phone_number, message)
