import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "GUV Analysis Platform"
    API_V1_STR: str = "/api"
    
    # Database
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "lab")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "labpass")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "lab_analysis")
    DATABASE_URL: str = f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: str = os.getenv("REDIS_PORT", "6379")
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    CELERY_BROKER_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
    CELERY_RESULT_BACKEND: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/2"

    # MinIO
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadminpassword")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "lab-analysis")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "False").lower() == "true"
    MINIO_HTTP_CONNECT_TIMEOUT_SECONDS: int = int(os.getenv("MINIO_HTTP_CONNECT_TIMEOUT_SECONDS", "5"))
    MINIO_HTTP_READ_TIMEOUT_SECONDS: int = int(os.getenv("MINIO_HTTP_READ_TIMEOUT_SECONDS", "18000"))
    MINIO_API_HTTP_CONNECT_TIMEOUT_SECONDS: int = int(os.getenv("MINIO_API_HTTP_CONNECT_TIMEOUT_SECONDS", "2"))
    MINIO_API_HTTP_READ_TIMEOUT_SECONDS: int = int(os.getenv("MINIO_API_HTTP_READ_TIMEOUT_SECONDS", "10"))
    MINIO_PRESIGN_EXPIRES_SECONDS: int = int(os.getenv("MINIO_PRESIGN_EXPIRES_SECONDS", "18000"))

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "development_secret_key_change_in_production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    EXTERNAL_AUTORUN_TOKEN: str = os.getenv("EXTERNAL_AUTORUN_TOKEN", "")
    EXTERNAL_AUTORUN_USERNAME: str = os.getenv("EXTERNAL_AUTORUN_USERNAME", "auto-exp")
    AUTOEXP_CALLBACK_URL: str = os.getenv("AUTOEXP_CALLBACK_URL", "http://10.30.70.120:30080/auto-exp/api/v1/notifications/callback/guv")
    AUTOEXP_CALLBACK_TOKEN: str = os.getenv("AUTOEXP_CALLBACK_TOKEN", "")
    AUTOEXP_CALLBACK_TIMEOUT_SECONDS: int = int(os.getenv("AUTOEXP_CALLBACK_TIMEOUT_SECONDS", "5"))
    AUTOEXP_CALLBACK_MAX_RETRIES: int = int(os.getenv("AUTOEXP_CALLBACK_MAX_RETRIES", "0"))

    # Pipeline
    PIPELINE_ROOT: str = os.getenv("PIPELINE_ROOT", "/app/matlab_packages/GUV_Image_Processor_V1.1.2")
    RUN_BASE_DIR: str = os.getenv("RUN_BASE_DIR", "/app/data/tasks")

    class Config:
        env_file = ".env"

settings = Settings()
