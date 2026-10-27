from django.shortcuts import get_object_or_404, render

from laws.models import ProvisionText
from tags.models import ProvisionTag, Tag

PROVISION_LIMIT = 200


def tag_list(request):
    rows = [(tag, tag.slug.count(".")) for tag in Tag.objects.all()]
    return render(request, "tags/tag_list.html", {"rows": rows})


def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    links = ProvisionTag.objects.filter(tag.subtree_q("tag__slug")).select_related("provision__act", "tag")
    provision_ids = {link.provision_id for link in links}
    texts = (
        ProvisionText.objects.filter(provision_id__in=provision_ids, version__is_current=True)
        .select_related("provision__act__jurisdiction")
        .order_by("provision__act__title", "ordinal")[:PROVISION_LIMIT]
    )
    following = (
        request.user.is_authenticated and request.user.subscriptions.filter(tag=tag).exists()
    )
    return render(
        request,
        "tags/tag_detail.html",
        {
            "tag": tag,
            "children": tag.children.all(),
            "texts": texts,
            "total": len(provision_ids),
            "limit": PROVISION_LIMIT,
            "following": following,
        },
    )
