from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Q

from .models import Order


class SignupForm(UserCreationForm):
    """Customers sign up with their email address, which is also their username."""
    email = forms.EmailField()
    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60)

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # Check both fields: staff can create accounts in the admin with any username
        if get_user_model().objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
            raise forms.ValidationError("There's already an account with this email. Try logging in.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class EmailLoginForm(AuthenticationForm):
    username = forms.CharField(label="Email", max_length=254,
                               widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))

    def clean(self):
        if self.cleaned_data.get("username"):
            self.cleaned_data["username"] = self.cleaned_data["username"].strip().lower()
        return super().clean()


class CheckoutForm(forms.Form):
    fulfilment = forms.ChoiceField(choices=Order.Fulfilment.choices, widget=forms.RadioSelect,
                                   initial=Order.Fulfilment.COLLECT)
    delivery_address = forms.CharField(required=False, max_length=300,
                                       widget=forms.Textarea(attrs={"rows": 3}),
                                       help_text="Only needed for delivery.")
    phone = forms.CharField(max_length=30, widget=forms.TextInput(attrs={"autocomplete": "tel"}))
    payment_method = forms.ChoiceField(choices=Order.Payment.choices, widget=forms.RadioSelect,
                                       initial=Order.Payment.COLLECTION)
    token = forms.CharField(widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if data.get("fulfilment") == Order.Fulfilment.DELIVER and not data.get("delivery_address", "").strip():
            self.add_error("delivery_address", "Please give a delivery address.")
        return data


class CancelForm(forms.Form):
    reason = forms.CharField(max_length=200, min_length=3)
