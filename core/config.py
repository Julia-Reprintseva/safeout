from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "alert@safeout.app"

    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "safeout-files"
    s3_public_url: str = ""

    app_base_url: str = "https://safeout.app"
    secret_key: str = "change_me"

    ping_interval_minutes: int = 15
    escalation_l1_minutes: int = 15
    escalation_l2_minutes: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
