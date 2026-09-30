from django.apps import AppConfig


class ErrandM8AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ErrandM8App'

    def ready(self):
        import ErrandM8App.signals


