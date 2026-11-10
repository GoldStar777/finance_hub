from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": "Finance Hub",
        "version": "2.0.0",
        "offline": True
    }

