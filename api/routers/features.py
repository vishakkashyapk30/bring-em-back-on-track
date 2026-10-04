from fastapi import APIRouter, Depends

from api.deps import require
from common.types import Role
from features.registry import load_registry

router = APIRouter(tags=["features"])


@router.get("/features/catalog")
def catalog(s=Depends(require({Role.analyst, Role.steward}))):
    """Live: generated from features/registry.yaml."""
    specs = load_registry()
    return {"count": len(specs), "llm_count": sum(x.built_by == "ai" for x in specs),
            "features": [x.model_dump() for x in specs]}
