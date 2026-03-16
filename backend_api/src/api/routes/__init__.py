from src.api.routes.auth import router as auth_router
from src.api.routes.exams import router as exams_router
from src.api.routes.modules import router as modules_router
from src.api.routes.progress import router as progress_router

__all__ = ["auth_router", "modules_router", "exams_router", "progress_router"]
