import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    Notes:
    - Do not hardcode secrets. Provide them via the container .env.
    - `POSTGRES_*` variables come from the database_service container wiring.
    """

    postgres_url: str
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_port: str

    jwt_secret: str
    jwt_issuer: str
    jwt_audience: str
    access_token_ttl_seconds: int

    cors_allow_origins: list[str]


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Load settings from environment variables.

    Required env vars:
    - POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT
    - JWT_SECRET

    Optional:
    - JWT_ISSUER (default: "cognitive-learning-hub")
    - JWT_AUDIENCE (default: "cognitive-learning-hub-web")
    - ACCESS_TOKEN_TTL_SECONDS (default: 86400)
    - CORS_ALLOW_ORIGINS (default: "*")
    """
    postgres_url = os.getenv("POSTGRES_URL", "")
    postgres_user = os.getenv("POSTGRES_USER", "")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "")
    postgres_db = os.getenv("POSTGRES_DB", "")
    postgres_port = os.getenv("POSTGRES_PORT", "")

    # IMPORTANT: must be set by orchestrator in .env
    jwt_secret = os.getenv("JWT_SECRET", "")

    jwt_issuer = os.getenv("JWT_ISSUER", "cognitive-learning-hub")
    jwt_audience = os.getenv("JWT_AUDIENCE", "cognitive-learning-hub-web")
    access_token_ttl_seconds = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "86400"))

    cors_origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    cors_allow_origins = ["*"] if cors_origins_raw.strip() == "*" else _split_csv(cors_origins_raw)

    return Settings(
        postgres_url=postgres_url,
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        postgres_db=postgres_db,
        postgres_port=postgres_port,
        jwt_secret=jwt_secret,
        jwt_issuer=jwt_issuer,
        jwt_audience=jwt_audience,
        access_token_ttl_seconds=access_token_ttl_seconds,
        cors_allow_origins=cors_allow_origins,
    )
