"""LawHub as an MCP server, so people can use LawHub from their own AI.

A logged-in user adds https://<host>/mcp as a connector in their assistant
(Claude, or any MCP client), authorizes it through LawHub's OAuth flow, and
their AI can then search the law, read provisions and manage the user's
topic subscriptions on their behalf. The AI does the reasoning ("I bought a
used car and cycle to work" -> which topics?), LawHub provides the data and
the actions.

Each tool runs as the user who owns the access token.
"""

from __future__ import annotations

import hashlib

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from oauth2_provider.models import get_access_token_model

from accounts.models import Subscription
from laws.models import Act, ActVersion, Provision, ProvisionText
from tags.models import ProvisionTag, Tag

SCOPE = "lawhub"
MAX_RESULTS = 25

INSTRUCTIONS = """\
LawHub keeps Polish law (driving law in this beta) split into provisions, each
tagged with topics. Users follow topics to be notified when the law on them
changes.

When the user describes their life (car, bike, job, city, plans), call
list_topics, pick the topics that genuinely apply, explain your choice in a
sentence each, and ask before calling follow_topics. Use search_law and
get_provision to answer questions about what the law says, and always cite
the act and provision address you used. LawHub's texts are an unofficial
copy; the official source is Dziennik Ustaw.
"""


class DjangoOAuthTokenVerifier:
    """Accept access tokens issued by django-oauth-toolkit for the `lawhub` scope."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return await sync_to_async(self._verify)(token)

    def _verify(self, token: str) -> AccessToken | None:
        checksum = hashlib.sha256(token.encode()).hexdigest()
        db_token = (
            get_access_token_model()
            .objects.select_related("application", "user")
            .filter(token_checksum=checksum)
            .first()
        )
        if db_token is None or db_token.user is None or not db_token.is_valid([SCOPE]):
            return None
        return AccessToken(
            token=token,
            client_id=db_token.application.client_id if db_token.application else "",
            scopes=db_token.scope.split(),
            expires_at=int(db_token.expires.timestamp()),
            resource=mcp_resource_url(),
            subject=str(db_token.user_id),
        )


def mcp_resource_url() -> str:
    return f"{settings.LAWHUB_PUBLIC_URL}/mcp"


def _current_user():
    token = get_access_token()
    if token is None or token.subject is None:
        raise PermissionError("Not authenticated with LawHub.")
    return get_user_model().objects.get(pk=int(token.subject))


def _absolute(path: str) -> str:
    return f"{settings.LAWHUB_PUBLIC_URL}{path}"


# --- tool implementations (sync; Django ORM) -------------------------------


def _list_topics() -> list[dict]:
    counts = dict(
        ProvisionTag.objects.values("tag__slug").annotate(n=Count("id")).values_list("tag__slug", "n")
    )
    return [
        {
            "slug": tag.slug,
            "name_pl": tag.name_pl,
            "name_en": tag.name_en,
            "parent": tag.slug.rpartition(".")[0] or None,
            "tagged_provisions": counts.get(tag.slug, 0),
        }
        for tag in Tag.objects.order_by("slug")
    ]


def _search_law(query: str, limit: int) -> list[dict]:
    limit = max(1, min(limit, MAX_RESULTS))
    texts = (
        ProvisionText.objects.filter(version__is_current=True)
        .filter(Q(text__icontains=query) | Q(heading__icontains=query) | Q(tail__icontains=query))
        .select_related("provision__act__jurisdiction")
        .order_by("provision__act__title", "ordinal")[:limit]
    )
    return [_provision_summary(pt) for pt in texts]


def _provision_summary(pt: ProvisionText) -> dict:
    prov = pt.provision
    return {
        "act": prov.act.source_id,
        "act_title": prov.act.title,
        "address": prov.address,
        "label": pt.label,
        "text": (f"{pt.heading} " if pt.heading else "") + pt.text + (f" {pt.tail}" if pt.tail else ""),
        "url": _absolute(prov.get_absolute_url()),
    }


def _get_provision(act: str, address: str) -> dict:
    act_obj = Act.objects.filter(source_id=act).first()
    if act_obj is None:
        raise ValueError(f"Unknown act {act!r}; use search_law to find act ids.")
    version = act_obj.current_version
    texts = (
        ProvisionText.objects.filter(version=version)
        .filter(Q(provision__address=address) | Q(provision__address__startswith=f"{address}/"))
        .order_by("ordinal")
    )
    if not texts:
        raise ValueError(f"No provision {address!r} in {act}.")
    provision = Provision.objects.get(act=act_obj, address=address)
    ancestor_ids = [p.id for p in provision.ancestors()]
    tags = sorted(set(ProvisionTag.objects.filter(provision_id__in=ancestor_ids).values_list("tag__slug", flat=True)))
    body = "\n".join(
        f"{'  ' * (pt.depth - texts[0].depth)}{pt.label} {pt.heading or ''} {pt.text} {pt.tail}".replace("  ", " ").rstrip()
        for pt in texts
    )
    return {
        "act": act,
        "act_title": act_obj.title,
        "address": address,
        "version": version.label,
        "text": body,
        "topics": tags,
        "has_pending_change": any(pt.has_pending_change for pt in texts),
        "url": _absolute(provision.get_absolute_url()),
    }


def _my_subscriptions() -> list[dict]:
    user = _current_user()
    subs = user.subscriptions.select_related("tag", "act", "provision__act")
    return [
        {
            "type": "topic" if s.tag else "act" if s.act else "provision",
            "id": s.tag.slug if s.tag else s.act.source_id if s.act else f"{s.provision.act.source_id} {s.provision.address}",
            "name": s.tag.name_pl if s.tag else s.act.title if s.act else str(s.provision),
            "origin": s.origin,
        }
        for s in subs
    ]


def _follow_topics(slugs: list[str]) -> dict:
    user = _current_user()
    tags = {t.slug: t for t in Tag.objects.filter(slug__in=slugs)}
    unknown = sorted(set(slugs) - set(tags))
    added = []
    for slug, tag in tags.items():
        _, created = Subscription.objects.get_or_create(user=user, tag=tag, defaults={"origin": Subscription.Origin.AI})
        if created:
            added.append(slug)
    return {"followed": sorted(added), "already_following": sorted(set(tags) - set(added)), "unknown": unknown}


def _unfollow_topics(slugs: list[str]) -> dict:
    user = _current_user()
    deleted, _ = user.subscriptions.filter(tag__slug__in=slugs).delete()
    return {"unfollowed": deleted}


def _recent_changes(days: int) -> list[dict]:
    """Provisions under the user's followed topics that differ from the previous
    version of their act, for act versions imported in the last `days` days."""
    user = _current_user()
    since = timezone.now() - timezone.timedelta(days=max(1, min(days, 365)))
    topic_q = Q(pk__in=[])
    for sub in user.subscriptions.filter(tag__isnull=False).select_related("tag"):
        topic_q |= sub.tag.subtree_q("tag__slug")
    tagged = set(ProvisionTag.objects.filter(topic_q).values_list("provision_id", flat=True))
    if not tagged:
        return []

    changed = []
    for version in ActVersion.objects.filter(is_current=True, imported_at__gte=since).select_related("act"):
        previous = version.act.versions.filter(version_date__lt=version.version_date).order_by("-version_date").first()
        if previous is None:
            continue  # first import of an act is not a change
        before = dict(previous.provision_texts.values_list("provision_id", "content_hash"))
        parents = dict(Provision.objects.filter(act=version.act).values_list("id", "parent_id"))
        for pt in version.provision_texts.select_related("provision__act").order_by("ordinal"):
            if before.get(pt.provision_id) == pt.content_hash:
                continue
            node = pt.provision_id
            while node is not None and node not in tagged:
                node = parents.get(node)
            if node is not None:
                change = "modified" if pt.provision_id in before else "added"
                changed.append({**_provision_summary(pt), "change": change, "version": version.label})
                if len(changed) >= MAX_RESULTS:
                    return changed
    return changed


# --- MCP server -------------------------------------------------------------

_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def build_server() -> MCPServer:
    server = MCPServer(
        name="LawHub",
        instructions=INSTRUCTIONS,
        website_url=settings.LAWHUB_PUBLIC_URL,
        token_verifier=DjangoOAuthTokenVerifier(),
        auth=AuthSettings(
            issuer_url=settings.LAWHUB_PUBLIC_URL,
            resource_server_url=mcp_resource_url(),
            required_scopes=[SCOPE],
            validate_token_resource=False,  # the verifier only accepts our own tokens
        ),
    )

    @server.tool(annotations=_READ_ONLY)
    async def list_topics() -> list[dict]:
        """List every topic users can follow, as a tree (dotted slugs; following a
        parent covers its children), with how many provisions each tags."""
        return await sync_to_async(_list_topics)()

    @server.tool(annotations=_READ_ONLY)
    async def search_law(query: str, limit: int = 10) -> list[dict]:
        """Find provisions whose wording contains `query` (Polish, e.g. "badanie techniczne").
        Returns act id, provision address, text and a link."""
        return await sync_to_async(_search_law)(query, limit)

    @server.tool(annotations=_READ_ONLY)
    async def get_provision(act: str, address: str) -> dict:
        """Full current text of one provision and everything under it, with its topics.
        `act` is an id like "DU/1997/602", `address` like "art_81/par_6"."""
        return await sync_to_async(_get_provision)(act, address)

    @server.tool(annotations=_READ_ONLY)
    async def my_subscriptions() -> list[dict]:
        """Topics, acts and provisions the user currently follows."""
        return await sync_to_async(_my_subscriptions)()

    @server.tool(annotations=_WRITE)
    async def follow_topics(slugs: list[str]) -> dict:
        """Follow topics by slug (from list_topics). Ask the user to confirm first."""
        return await sync_to_async(_follow_topics)(slugs)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    async def unfollow_topics(slugs: list[str]) -> dict:
        """Stop following topics by slug."""
        return await sync_to_async(_unfollow_topics)(slugs)

    @server.tool(annotations=_READ_ONLY)
    async def recent_changes(days: int = 30) -> list[dict]:
        """Provisions in the user's followed topics that were added or reworded in the last `days` days."""
        return await sync_to_async(_recent_changes)(days)

    return server


def build_asgi_app():
    host = settings.LAWHUB_PUBLIC_URL.split("://", 1)[-1]
    return build_server().streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,  # no sticky sessions needed; scales to zero cleanly
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[host, *settings.ALLOWED_HOSTS],
            allowed_origins=[settings.LAWHUB_PUBLIC_URL],
        ),
    )
