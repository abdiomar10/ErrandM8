from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Task, Profile, Review, PriceCounter


# ---------------------------------------------------------------------------
# Auth forms
# ---------------------------------------------------------------------------

class CustomUserCreationForm(UserCreationForm):
    USER_TYPE_CHOICES = [
        ('client', 'Client — I need things done'),
        ('runner', 'Runner — I pick up nearby jobs'),
    ]
    email = forms.EmailField(required=True, label='Email address')
    user_type = forms.ChoiceField(
        choices=USER_TYPE_CHOICES,
        required=True,
        label='I want to',
        widget=forms.RadioSelect,
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class CustomAuthenticationForm(AuthenticationForm):
    """Thin wrapper so we can style it consistently."""
    pass


# ---------------------------------------------------------------------------
# Task form
# ---------------------------------------------------------------------------

class TaskForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label='Deadline (optional)',
    )

    class Meta:
        model = Task
        fields = [
            'title', 'description', 'category',
            'phone_number', 'location_from', 'location_to',
            'client_budget', 'deadline',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'e.g. Pick up groceries from Carrefour Westlands',
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe exactly what needs to be done, any special instructions…',
            }),
            'phone_number': forms.TextInput(attrs={'placeholder': '+254…'}),
            'location_from': forms.TextInput(attrs={'placeholder': 'e.g. Westlands Mall'}),
            'location_to': forms.TextInput(attrs={'placeholder': 'e.g. Upper Hill office'}),
            'client_budget': forms.NumberInput(attrs={
                'placeholder': 'Optional — your max budget in KSh',
                'min': 0, 'step': 50,
            }),
        }
        labels = {
            'client_budget': 'Your budget (KSh, optional)',
            'location_from': 'Pickup location',
            'location_to': 'Drop-off location',
        }


# ---------------------------------------------------------------------------
# Price counter form (runner → client or client → runner)
# ---------------------------------------------------------------------------

class PriceCounterForm(forms.ModelForm):
    class Meta:
        model = PriceCounter
        fields = ['amount', 'note']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'placeholder': 'Your price (KSh)',
                'min': 0, 'step': 50,
            }),
            'note': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Optional — explain your price or ask a question',
            }),
        }
        labels = {
            'amount': 'Proposed price (KSh)',
            'note': 'Message (optional)',
        }


# ---------------------------------------------------------------------------
# Review form
# ---------------------------------------------------------------------------

class ReviewForm(forms.ModelForm):
    SCORE_CHOICES = [(i, '★' * i) for i in range(1, 6)]
    score = forms.ChoiceField(
        choices=SCORE_CHOICES,
        widget=forms.RadioSelect,
        label='Rating',
    )

    class Meta:
        model = Review
        fields = ['score', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Tell others about your experience with this runner…',
            }),
        }
        labels = {
            'comment': 'Comment (optional)',
        }

    def clean_score(self):
        return int(self.cleaned_data['score'])


# ---------------------------------------------------------------------------
# Profile edit form
# ---------------------------------------------------------------------------

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['phone_number', 'bio']
        widgets = {
            'phone_number': forms.TextInput(attrs={'placeholder': '+254…'}),
            'bio': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'A short description about yourself…',
            }),
        }