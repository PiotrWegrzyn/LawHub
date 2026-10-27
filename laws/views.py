from collections import defaultdict

from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from laws.models import Act, ProvisionText
from tags.models import ProvisionTag, Tag

SEARCH_LIMIT = 100


def home(request):
    return render(
        request,
        "laws/home.html",
        {
            "categories": Tag.objects.filter(parent__isnull=True).prefetch_related("children"),
            "acts": Act.objects.select_related("jurisdiction").order_by("title"),
        },
    )


def act_detail(request, jurisdiction, source_id):
    act = get_object_or_404(Act.objects.select_related("jurisdiction"), jurisdiction__code=jurisdiction, source_id=source_id)
    version = act.current_version
    texts = (
        ProvisionText.objects.filter(version=version).select_related("provision").order_by("ordinal")
        if version
        else ProvisionText.objects.none()
    )
    direct_tags = defaultdict(list)
    for link in ProvisionTag.objects.filter(provision__act=act).select_related("tag"):
        direct_tags[link.provision_id].append(link.tag)
    rows = [(pt, direct_tags.get(pt.provision_id, [])) for pt in texts]
    return render(
        request,
        "laws/act_detail.html",
        {"act": act, "version": version, "rows": rows, "act_tags": direct_tags.get(rows[0][0].provision_id, []) if rows else []},
    )


def search(request):
    query = request.GET.get("q", "").strip()
    results = []
    if len(query) >= 3:
        # Beta: substring search on current wording. Postgres full-text
        # search (Polish dictionary) replaces this in production.
        results = (
            ProvisionText.objects.filter(version__is_current=True)
            .filter(Q(text__icontains=query) | Q(heading__icontains=query) | Q(tail__icontains=query))
            .select_related("provision__act__jurisdiction")
            .order_by("provision__act__title", "ordinal")[:SEARCH_LIMIT]
        )
    return render(request, "laws/search.html", {"query": query, "results": results, "limit": SEARCH_LIMIT})
