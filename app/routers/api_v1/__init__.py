from fastapi import APIRouter

from app.routers.api_v1 import auth, clock, companies, leave, me, projects, schedule, sites, zkteco

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(companies.router, tags=["companies"])
router.include_router(projects.router, tags=["projects"])
router.include_router(me.router, tags=["me"])
router.include_router(sites.router, tags=["sites"])
router.include_router(schedule.router, tags=["schedule"])
router.include_router(leave.router, tags=["leave"])
router.include_router(clock.router, tags=["clock"])
router.include_router(zkteco.router, tags=["zkteco"])
