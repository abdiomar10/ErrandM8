from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ErrandM8App.models import Profile

class Command(BaseCommand):
    help = 'Create missing profiles for existing users.'

    def handle(self, *args, **kwargs):
        users_without_profiles = User.objects.filter(profile__isnull=True)
        for user in users_without_profiles:
            Profile.objects.create(user=user, role='client')  # Default to 'client' or set appropriate role
            self.stdout.write(self.style.SUCCESS(f'Created profile for user: {user.username}'))

        if not users_without_profiles:
            self.stdout.write(self.style.SUCCESS('All users already have profiles.'))
        else:
            self.stdout.write(self.style.SUCCESS('Profiles created for users without profiles.'))
