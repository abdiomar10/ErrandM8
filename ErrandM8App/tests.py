from datetime import timedelta
import json

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Profile, Task


class OtpSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='client', password='Strong-test-pass-123')
        self.profile = self.user.profile

    def test_otp_is_hashed_and_single_use(self):
        code = self.profile.generate_otp()
        self.profile.refresh_from_db()

        self.assertNotEqual(self.profile.otp_code, code)
        self.assertTrue(self.profile.verify_otp(code))
        self.assertFalse(self.profile.verify_otp(code))

    def test_five_invalid_attempts_invalidate_otp(self):
        code = self.profile.generate_otp()

        for _ in range(5):
            self.assertFalse(self.profile.verify_otp('000000' if code != '000000' else '111111'))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.otp_code, '')
        self.assertEqual(self.profile.otp_attempts, 5)
        self.assertFalse(self.profile.verify_otp(code))

    def test_expired_otp_is_rejected(self):
        code = self.profile.generate_otp()
        self.profile.otp_created_at = timezone.now() - timedelta(minutes=11)
        self.profile.save(update_fields=['otp_created_at'])

        self.assertFalse(self.profile.verify_otp(code))


class NearbyTaskTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username='task-client')
        self.concierge = User.objects.create_user(username='task-concierge')
        self.profile = self.concierge.profile
        self.profile.latitude = -1.286389
        self.profile.longitude = 36.817223
        self.profile.save(update_fields=['latitude', 'longitude'])

    def make_task(self, title, latitude=None, longitude=None):
        return Task.objects.create(
            client=self.client_user,
            title=title,
            description='A sample errand',
            location_from='Westlands',
            location_to='CBD',
            pickup_latitude=latitude,
            pickup_longitude=longitude,
        )

    def test_nearby_lookup_filters_by_radius_and_keeps_unknown_locations(self):
        nearby = self.make_task('nearby', -1.29, 36.82)
        far_away = self.make_task('far away', -1.4, 36.82)
        unknown = self.make_task('unknown location')

        results = Task.nearby_pending(self.profile)

        self.assertEqual([task.pk for task in results], [nearby.pk, unknown.pk])
        self.assertNotIn(far_away.pk, [task.pk for task in results])
        self.assertIsNone(next(task for task in results if task.pk == unknown.pk).distance)

    def test_lookup_includes_tasks_on_either_side_of_longitude_dateline(self):
        self.profile.latitude = 0
        self.profile.longitude = 179.99
        self.profile.save(update_fields=['latitude', 'longitude'])
        across_dateline = self.make_task('across dateline', 0, -179.99)

        results = Task.nearby_pending(self.profile)

        self.assertIn(across_dateline.pk, [task.pk for task in results])


class AccessControlTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username='client-user', password='Strong-test-pass-123')
        self.concierge = User.objects.create_user(username='concierge-user', password='Strong-test-pass-123')
        self.concierge.profile.user_type = 'concierge'
        self.concierge.profile.save(update_fields=['user_type'])
        self.task = Task.objects.create(
            client=self.client_user,
            title='Test errand',
            description='Test description',
            location_from='Westlands',
            location_to='CBD',
            status='Completed',
            concierge=self.concierge,
            proposed_price=500,
        )
        self.pending_task = Task.objects.create(
            client=self.client_user,
            title='Pending errand',
            description='Test description',
            location_from='Westlands',
            location_to='CBD',
            status='Pending',
        )
        self.client.force_login(self.client_user)

    def test_state_changes_reject_get_requests(self):
        for url in (
            reverse('pay_concierge', args=[self.task.pk]),
            reverse('cancel_task', args=[self.task.pk]),
            reverse('accept_task', args=[self.task.pk, 'accept']),
            reverse('logout'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'Completed')

    def test_client_cannot_propose_concierge_price(self):
        response = self.client.post(
            reverse('set_price', args=[self.pending_task.pk]),
            {'amount': 100},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pending_task.counters.count(), 0)

    def test_invalid_coordinates_are_rejected(self):
        self.client.force_login(self.concierge)

        response = self.client.post(
            reverse('update_location'),
            data=json.dumps({'latitude': 91, 'longitude': 36}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.concierge.profile.refresh_from_db()
        self.assertIsNone(self.concierge.profile.latitude)

    def test_client_dashboard_paginates_and_renders_task_history(self):
        Task.objects.bulk_create([
            Task(
                client=self.client_user,
                title=f'Errand {index}',
                description='Test description',
                location_from='Westlands',
                location_to='CBD',
            )
            for index in range(19)
        ])

        response = self.client.get(reverse('client_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 21)
        self.assertEqual(len(response.context['tasks']), 20)
        self.assertContains(response, 'Errand history pages')


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
    }
})
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_failed_logins_are_throttled(self):
        for _ in range(5):
            self.client.post(
                reverse('login'),
                {'username': 'unknown-account', 'password': 'incorrect-password'},
            )

        response = self.client.post(
            reverse('login'),
            {'username': 'unknown-account', 'password': 'incorrect-password'},
        )

        self.assertContains(response, 'Too many failed login attempts', status_code=200)
