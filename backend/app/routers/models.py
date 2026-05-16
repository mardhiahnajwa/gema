from fastapi import APIRouter, BackgroundTasks

from app.services.model_catalog import get_models, get_providers_status, CACHE_TTL

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/")
async def list_models(refresh: bool = False):
    """
    List all available AI models from configured providers.

    Results are fetched live from each provider's API and cached in Redis
    for one hour. Pass ?refresh=true to force an immediate refresh.
    """
    models = await get_models(force_refresh=refresh)
    return {"models": models, "total": len(models), "cache_ttl_seconds": CACHE_TTL}


@router.post("/refresh")
async def refresh_models(background_tasks: BackgroundTasks):
    """
    Trigger a background refresh of the model catalog from all providers.
    Returns immediately; the catalog updates asynchronously.
    """
    background_tasks.add_task(get_models, True)
    return {"message": "Model catalog refresh triggered in background"}


@router.get("/providers")
async def list_providers():
    """List all AI providers and whether their API key is configured."""
    providers = get_providers_status()
    return {"providers": providers}


@router.get("/categories")
async def list_categories():
    """List model categories and their counts across configured providers."""
    models = await get_models()
    cats: dict = {}
    for m in models:
        c = m.get("category", "text")
        cats.setdefault(c, {"name": c, "count": 0, "available_count": 0})
        cats[c]["count"] += 1
        if m.get("available"):
            cats[c]["available_count"] += 1
    return {"categories": list(cats.values())}

