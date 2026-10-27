from django.contrib import admin

from tags.models import ProvisionTag, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("slug", "name_pl", "name_en", "parent")
    search_fields = ("slug", "name_pl", "name_en")


@admin.register(ProvisionTag)
class ProvisionTagAdmin(admin.ModelAdmin):
    list_display = ("tag", "provision", "source", "confidence")
    list_filter = ("source", "tag")
    raw_id_fields = ("provision",)
