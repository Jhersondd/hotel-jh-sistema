import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PORT: int = 5000
    HOTEL_NAME: str = "Hotel JH"
    CHECKIN_TIME: str = "14:00"
    CHECKOUT_TIME: str = "11:00"
    BANK_TRANSFER_DETAILS: str = "Transfiere a BCP Cta: 191-12345678-0-12 o Yape/Plin al 987654321 a nombre de Hotel JH."

    # Evolution API
    EVOLUTION_URL: str = "http://evolution_api:8080"
    EVOLUTION_API_KEY: str = "EvolutionHotelSecretKey2026!"
    EVOLUTION_INSTANCE_NAME: str = "hotel_principal"

    # Chatwoot
    CHATWOOT_URL: str = "http://chatwoot_web:3000"
    CHATWOOT_API_TOKEN: str = ""
    CHATWOOT_ACCOUNT_ID: int = 1

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Google Sheets
    GOOGLE_SHEET_ID: str = ""
    GOOGLE_CREDENTIALS_FILE: str = "/app/credentials.json"

    # TTLock
    TTLOCK_CLIENT_ID: str = ""
    TTLOCK_CLIENT_SECRET: str = ""
    TTLOCK_USERNAME: str = ""
    TTLOCK_PASSWORD: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
