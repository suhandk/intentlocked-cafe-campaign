from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.approval_service import ApprovalService
from backend.art_routes import router as art_router
from backend.art_service import ArtService
from backend.campaign_routes import router as campaign_router
from backend.change_service import ChangeService
from backend.config import Settings
from backend.contracts import Cost, ErrorBody, Health, TraceEvent
from backend.db import Store
from backend.delivery_routes import router as delivery_router
from backend.errors import ProviderError
from backend.future_contracts import BoundaryCatalog
from backend.generation_routes import router as generation_router
from backend.generation_service import GenerationService
from backend.guardian.routes import router as guardian_router
from backend.inference_client import InferenceClient
from backend.meta_routes import router as meta_router
from backend.meta_service import MetaService
from backend.optimization_routes import router as optimization_router
from backend.optimization_service import OptimizationService
from backend.planning import router as planning_router
from backend.social_profiles import router as social_router
from backend.video_routes import router as video_router
from backend.video_service import VideoService
from backend.website_routes import router as website_router
from backend.website_service import WebsiteError, WebsiteService
from backend.work_routes import router as work_router
from backend.work_service import WorkService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    from backend.meta_logging import install

    install()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(config.database_path)
        client = InferenceClient(config, store)
        app.state.store, app.state.client = store, client
        app.state.settings = config
        app.state.generation = GenerationService(store, client)
        app.state.art = ArtService(store, client, config)
        app.state.optimization = OptimizationService(store, client)
        app.state.changes = ChangeService(store, client)
        app.state.approvals = ApprovalService(store, client, app.state.optimization)
        app.state.work = WorkService(app)
        store.work = app.state.work
        app.state.meta = MetaService(app)
        app.state.video = VideoService(app)
        app.state.website = WebsiteService(store, config)
        try:
            yield
        finally:
            await app.state.website.close()
            await app.state.work.close()
            await app.state.meta.close()
            await app.state.video.close()
            await app.state.generation.close()
            await app.state.optimization.close()
            await client.close()
            store.close()

    app = FastAPI(
        title="Intent-Locked Campaigns",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin, "https://127.0.0.1:3000", "https://localhost:3000"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Owner-Delivery-Token"],
    )

    def error(code, message, status=400, trace_id=None, retryable=False, details=None):
        return JSONResponse(
            status_code=status,
            content=ErrorBody(
                code=code,
                message=message,
                trace_id=trace_id or uuid4().hex,
                retryable=retryable,
                details=details or {},
            ).model_dump(),
        )

    @app.middleware("http")
    async def local_host_boundary(request: Request, call_next):
        from urllib.parse import urlparse

        # Only the signed webhook and opaque media grants may use the explicitly
        # configured public origin. Owner/work/export routes remain local-only.
        public_meta = (
            bool(config.meta_public_origin)
            and config.meta_enabled
            and request.url.scheme == "https"
            and request.url.hostname == urlparse(config.meta_public_origin).hostname
            and (
                request.url.path == "/api/meta/webhook"
                or request.url.path.startswith("/api/meta/media/")
            )
        )
        if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"} and not public_meta:
            return error("HOST_REJECTED", "Only local hosts are allowed", 400)
        website = request.url.path.startswith(("/api/website/", "/api/websites/"))
        if website:
            secret_route = request.url.path.endswith(("/connection", "/publish")) or (
                request.url.path == "/api/website/token" and request.method == "DELETE"
            )
            if secret_route and request.url.scheme != "https":
                return error(
                    "HTTPS_REQUIRED",
                    "Publishing credentials require HTTPS; download zip instead",
                    403,
                )
            origin = request.headers.get("origin")
            allowed = {config.frontend_origin, "https://127.0.0.1:3000", "https://localhost:3000"}
            if origin and origin not in allowed:
                return error("ORIGIN_REJECTED", "Website request origin rejected", 403)
            if request.method in {"POST", "PUT"}:
                # Bound uploads and bodies before DTO validation or secret processing.
                try:
                    declared = int(request.headers.get("content-length", "0"))
                except ValueError:
                    return error("BODY_INVALID", "Invalid request size", 400)
                if declared > 7_100_000:
                    return error("BODY_TOO_LARGE", "Website request is too large", 413)
                received = bytearray()
                async for chunk in request.stream():
                    received.extend(chunk)
                    if len(received) > 7_100_000:
                        return error("BODY_TOO_LARGE", "Website request is too large", 413)
                request._body = bytes(received)
        return await call_next(request)

    @app.exception_handler(WebsiteError)
    async def website_error(_: Request, exc: WebsiteError):
        return error(exc.code, exc.message, exc.status)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        return error("INTERNAL_ERROR", "An internal operation failed", 500)

    @app.exception_handler(ProviderError)
    async def provider_error(_: Request, exc: ProviderError):
        conflicts = {
            "REVISION_CONFLICT",
            "FACTS_LOCKED",
            "IDEMPOTENCY_CONFLICT",
            "GENERATION_BUSY",
            "OPTIMIZATION_BUSY",
            "WORK_QUEUE_FULL",
            "META_DEADLINE",
        }
        invalid = {
            "IMAGE_TRANSPORT_UNVERIFIED",
            "IMAGE_KEY_MISSING",
            "IMAGE_PARAMETER_UNSUPPORTED",
            "FACTS_INCOMPLETE",
            "REVIEW_REQUIRED",
            "FORMS_INVALID",
            "FORMS_NOT_READY",
            "DATE_DAY_CONFLICT",
            "DUPLICATE_FACT",
            "DUPLICATE_SELECTION",
            "GUARDIAN_SELECTION",
            "GENERATION_SELECTION",
            "ELIGIBILITY_UNRESOLVED",
            "ELIGIBILITY_CONFLICT",
            "STRATEGY_NEEDS_INPUT",
            "ART_INVALID",
            "ART_BLOCKED",
            "TEXT_OVERFLOW",
            "GRAPHEME_OVERFLOW",
            "APPROVAL_PENDING",
            "OPTIMIZATION_SELECTION",
            "EDIT_REJECTED",
            "CHANGE_INVALID",
            "APPROVAL_INVALID",
            "EXPORT_UNAUTHORIZED",
            "WORK_INVALID",
            "RETRY_UNSAFE",
            "META_INVALID",
            "META_MEDIA",
            "META_CONSENT",
            "META_TEMPLATE",
            "META_WINDOW",
            "META_CONFIGURATION",
            "META_CONTAINER",
            "VIDEO_DISABLED",
            "VIDEO_LIVE_REQUIRED",
            "VISION_UNSUPPORTED",
        }
        status = (
            403
            if exc.body.code
            in {"META_OWNER_REQUIRED", "META_SIGNATURE", "META_DISABLED", "META_NOT_VERIFIED"}
            else 409
            if exc.body.code in conflicts
            else 422
            if exc.body.code in invalid
            else 404
            if exc.body.code
            in {
                "CAMPAIGN_NOT_FOUND",
                "GENERATION_NOT_FOUND",
                "ASSET_NOT_FOUND",
                "OPTIMIZATION_NOT_FOUND",
                "DELIVERY_NOT_FOUND",
                "WORK_NOT_FOUND",
                "SAVED_OUTPUT_MISSING",
                "META_NOT_FOUND",
                "VIDEO_NOT_FOUND",
            }
            else 502
        )
        return JSONResponse(status_code=status, content=exc.body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Locations/types only: do not reflect untrusted values or validator context.
        fields = [
            ".".join(map(str, item["loc"])) + ": " + item["type"] for item in exc.errors()[:20]
        ]
        return error(
            "VALIDATION_ERROR",
            "Request does not match the API schema",
            422,
            details={"fields": fields},
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return error(
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Route unavailable" if exc.status_code == 404 else "Request rejected",
            exc.status_code,
        )

    @app.get("/api/health", response_model=Health)
    async def health():
        return Health(
            mode={"mock": "MOCK", "live": "LIVE", "cached": "SAVED DEMO OUTPUT"}[
                config.inference_mode
            ],
            video_enabled=config.enable_video,
            text_model=config.text_model,
            image_model=config.image_model,
            image_generation_enabled=config.image_generation_enabled,
            image_provider=config.image_provider,
            image_configuration_notice=(
                "Add OPENAI_API_KEY to backend .env and restart, or select local artwork"
                if config.image_provider == "openai" and not config.image_generation_enabled
                else None
            ),
            vision_supported=config.vision_supported,
            provider="OpenRouter"
            if "openrouter.ai" in config.inference_base_url
            else "Configured gateway",
        )

    @app.get("/api/ready", response_model=Health, responses={503: {"model": ErrorBody}})
    async def ready(request: Request):
        try:
            request.app.state.store.connection.execute("SELECT 1").fetchone()
        except Exception:
            return error("STORAGE_UNAVAILABLE", "Storage is not ready", 503, retryable=True)
        return await health()

    @app.get("/api/cost", response_model=Cost)
    async def cost(request: Request):
        return request.app.state.store.cost()

    @app.get("/api/traces", response_model=list[TraceEvent])
    async def traces(request: Request):
        return request.app.state.store.traces()

    app.include_router(campaign_router)
    app.include_router(guardian_router)
    app.include_router(generation_router)
    app.include_router(art_router)
    app.include_router(optimization_router)
    app.include_router(delivery_router)
    app.include_router(work_router)
    app.include_router(meta_router)
    app.include_router(social_router)
    app.include_router(planning_router)
    app.include_router(video_router)
    app.include_router(website_router)
    original_openapi = app.openapi

    def contract_openapi():
        schema = original_openapi()
        definitions = BoundaryCatalog.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )["$defs"]
        for name, definition in definitions.items():
            schema["components"]["schemas"].setdefault(name, definition)
        schema["info"]["x-reserved-boundaries"] = (
            "B8 release DTOs remain reserved; B1-B7 campaign workflows implemented"
        )
        return schema

    app.openapi = contract_openapi
    return app


app = create_app()
