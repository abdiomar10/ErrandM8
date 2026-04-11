import os
from twilio.rest import Client

account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

message = client.messages.create(
    body="Hello from Twilio!",
    from_='+254713453498',
    to='+254700524557'
)
print(f"Message SID: {message.sid}")