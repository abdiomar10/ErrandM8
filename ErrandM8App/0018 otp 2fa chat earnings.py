from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ErrandM8App', '0017_alter_task_options_profile_avatar_profile_bio_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Profile — OTP / 2FA / online / earnings
        migrations.AddField(
            model_name='profile',
            name='phone_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='otp_code',
            field=models.CharField(blank=True, max_length=6),
        ),
        migrations.AddField(
            model_name='profile',
            name='otp_created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='two_fa_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='is_online',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='total_earned',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='profile',
            name='jobs_completed',
            field=models.PositiveIntegerField(default=0),
        ),

        # Task — expanded categories
        migrations.AlterField(
            model_name='task',
            name='category',
            field=models.CharField(
                choices=[
                    ('delivery',    'Parcel Delivery'),
                    ('shopping',    'Grocery Shopping'),
                    ('babysitting', 'Babysitting'),
                    ('pickup',      'Pickup'),
                    ('document',    'Document'),
                    ('cleaning',    'Cleaning'),
                    ('cooking',     'Cooking'),
                    ('laundry',     'Laundry'),
                    ('errands',     'General Errands'),
                    ('other',       'Other'),
                ],
                default='other', max_length=20,
            ),
        ),

        # ChatMessage
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_read', models.BooleanField(default=False)),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='ErrandM8App.task')),
            ],
            options={'ordering': ['created_at']},
        ),

        # Notification — add chat_message and otp types
        migrations.AlterField(
            model_name='notification',
            name='notif_type',
            field=models.CharField(
                choices=[
                    ('price_proposed',  'Concierge proposed a price'),
                    ('price_countered', 'Counter-offer received'),
                    ('task_accepted',   'Task accepted'),
                    ('task_declined',   'Task declined'),
                    ('task_completed',  'Task completed'),
                    ('payment_received','Payment received'),
                    ('review_received', 'Review received'),
                    ('chat_message',    'New message'),
                    ('otp',             'OTP sent'),
                ],
                max_length=30,
            ),
        ),
    ]
