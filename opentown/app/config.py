from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OpenTown"
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    secret_key: str = "change-me"
    database_url: str = "sqlite:///./opentown.db"

    tick_interval_ms: int = 500
    perception_radius: int = 6
    interaction_distance: float = 1.5
    max_nearby_objects: int = 80
    max_agents: int = 200
    # Database write-pressure controls for production.
    # Persist world_events every N ticks (1 means every tick).
    event_persist_every_n_ticks: int = 10
    # Persist agent_scores every N ticks.
    score_persist_every_n_ticks: int = 5
    # Cleanup world_events older than N days. Set 0 to disable TTL cleanup.
    world_event_retention_days: int = 7
    # Run TTL cleanup every N ticks.
    world_event_cleanup_every_n_ticks: int = 1200

    world_width: int = 140
    world_height: int = 100
    tile_size: int = 32

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OPENTOWN_",
    )


settings = Settings()
