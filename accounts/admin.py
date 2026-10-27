from django.contrib import admin

from accounts.models import Profile, Subscription


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "tag", "act", "provision", "origin")
    list_filter = ("origin",)
    raw_id_fields = ("provision",)
