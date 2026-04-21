from .application import router as application_router
from .navigation import router as navigation_router
from .payments import router as payments_router

routers = [
    navigation_router,
    application_router,
    payments_router,
]
