from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class QuestionnaireForm(forms.Form):
    """Built from the `questionnaire` section of the tag rules, so adding a
    question is a YAML change, not a code change."""

    city = forms.CharField(label="Miasto", max_length=100, required=False)

    def __init__(self, *args, questions: dict[str, dict], **kwargs):
        super().__init__(*args, **kwargs)
        for key, question in questions.items():
            self.fields[key] = forms.BooleanField(label=question["label"], required=False)
        self.order_fields([*questions, "city"])
