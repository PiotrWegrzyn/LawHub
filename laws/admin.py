from django.contrib import admin

from laws.models import Act, ActVersion, Jurisdiction, Provision, ProvisionText


@admin.register(Jurisdiction)
class JurisdictionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "parent")


class ActVersionInline(admin.TabularInline):
    model = ActVersion
    extra = 0
    fields = ("version_id", "version_date", "label", "source", "is_current", "git_commit")
    readonly_fields = fields


@admin.register(Act)
class ActAdmin(admin.ModelAdmin):
    list_display = ("source_id", "title", "act_type", "status", "in_force", "jurisdiction")
    list_filter = ("jurisdiction", "act_type", "in_force")
    search_fields = ("source_id", "title")
    inlines = [ActVersionInline]


@admin.register(Provision)
class ProvisionAdmin(admin.ModelAdmin):
    list_display = ("act", "address", "kind")
    list_filter = ("kind", "act")
    search_fields = ("address",)
    raw_id_fields = ("parent",)


@admin.register(ProvisionText)
class ProvisionTextAdmin(admin.ModelAdmin):
    list_display = ("provision", "version", "label", "has_pending_change")
    list_filter = ("has_pending_change",)
    search_fields = ("text",)
    raw_id_fields = ("provision", "version")
