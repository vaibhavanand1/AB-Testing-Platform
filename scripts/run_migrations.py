import os
import sys
import time

# Locate backend directory dynamically across local and container environments
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", "backend"))
if not os.path.isdir(backend_dir):
    backend_dir = "/app/backend"

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.config import settings
from app.database import Base, engine
import app.models  # Ensures all ORM models are registered with Base.metadata


def wait_for_database(max_retries: int = 15, delay_seconds: int = 2):
    print(f"Connecting to database at {settings.database_url.split('@')[-1]}...")
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database connection verified.")
            return True
        except Exception as err:
            print(f"Database not ready yet (attempt {attempt}/{max_retries}): {err}")
            time.sleep(delay_seconds)
    raise RuntimeError("Failed to connect to database after maximum retries.")


def run():
    wait_for_database()

    ini_path = os.path.join(backend_dir, "alembic.ini")
    alembic_dir = os.path.join(backend_dir, "alembic")

    print("Running Alembic schema migrations...")
    try:
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("script_location", alembic_dir)
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(alembic_cfg, "head")
        print("Database migrations applied successfully.")
    except Exception as e:
        print(f"Alembic migration failed: {e}")
        print("Applying schema via SQLAlchemy create_all fallback...")
        Base.metadata.create_all(bind=engine)
        print("Schema verified via create_all.")


if __name__ == "__main__":
    run()
