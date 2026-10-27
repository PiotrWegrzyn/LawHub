from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.forms import QuestionnaireForm, SignupForm
from accounts.models import Profile, Subscription
from laws.models import Act
from tags.models import Tag
from tags.tagger import TagRules


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        Profile.objects.create(user=user)
        login(request, user)
        return redirect("accounts:questionnaire")
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def questionnaire(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    rules = TagRules.load()
    form = QuestionnaireForm(request.POST or None, questions=rules.questionnaire, initial={**profile.answers, "city": profile.city})
    if request.method == "POST" and form.is_valid():
        answers = {key: form.cleaned_data[key] for key in rules.questionnaire}
        profile.answers, profile.city = answers, form.cleaned_data["city"]
        profile.save()
        # Suggestions are regenerated each time; subscriptions the user added
        # by hand are never touched.
        request.user.subscriptions.filter(suggested=True).delete()
        suggested = Tag.objects.filter(slug__in=rules.suggest(answers))
        for tag in suggested:
            Subscription.objects.get_or_create(user=request.user, tag=tag, defaults={"suggested": True})
        messages.success(request, f"Zaproponowaliśmy {suggested.count()} tematów do obserwowania.")
        return redirect("accounts:subscriptions")
    return render(request, "accounts/questionnaire.html", {"form": form})


@login_required
def subscriptions(request):
    subs = request.user.subscriptions.select_related("tag", "act", "provision__act").order_by("-suggested", "tag__slug")
    return render(request, "accounts/subscriptions.html", {"subscriptions": subs})


@login_required
@require_POST
def follow_tag(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    Subscription.objects.get_or_create(user=request.user, tag=tag)
    return redirect(tag.get_absolute_url())


@login_required
@require_POST
def follow_act(request, act_id):
    act = get_object_or_404(Act, pk=act_id)
    Subscription.objects.get_or_create(user=request.user, act=act)
    return redirect(act.get_absolute_url())


@login_required
@require_POST
def unfollow(request, pk):
    get_object_or_404(Subscription, pk=pk, user=request.user).delete()
    return redirect(request.POST.get("next") or "accounts:subscriptions")
