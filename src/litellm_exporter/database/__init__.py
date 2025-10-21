import logging
import time
from typing import Any, Dict, Optional

import backoff
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from ..config import DatabaseConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnection:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection_pool = None
        self.setup_connection_pool()

    def setup_connection_pool(self):
        try:
            self.connection_pool = pool.SimpleConnectionPool(
                self.config.min_connections,
                self.config.max_connections,
                host=self.config.host,
                port=self.config.port,
                database=self.config.name,
                user=self.config.user,
                password=self.config.password,
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Error creating connection pool: {e}")
            raise

    def check_table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %(table_name)s
            );
            """
            result = self.execute_query(query, {"table_name": table_name})
            return result[0]["exists"] if result else False
        except Exception as e:
            logger.warning(f"Could not check if table {table_name} exists: {e}")
            return False

    def wait_for_required_tables(self, required_tables: list, max_wait_time: int = 300) -> bool:
        """Wait for required tables to exist with exponential backoff."""
        start_time = time.time()
        wait_time = 1
        
        while time.time() - start_time < max_wait_time:
            missing_tables = []
            for table in required_tables:
                if not self.check_table_exists(table):
                    missing_tables.append(table)
            
            if not missing_tables:
                logger.info("All required tables are available")
                return True
            
            logger.info(f"Waiting for tables: {missing_tables}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 30)  # Exponential backoff, max 30s
        
        logger.error(f"Timeout waiting for required tables: {missing_tables}")
        return False

    @backoff.on_exception(backoff.expo, Exception, max_tries=5)
    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> list:
        conn = None
        cur = None
        try:
            conn = self.connection_pool.getconn()
            conn.autocommit = (
                True  # Enable autocommit mode to avoid explicit commit operations
            )
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(query, params or {})
            return cur.fetchall()
        except Exception as e:
            logger.error(f"Database query error: {e}")
            raise
        finally:
            if cur:
                cur.close()
            if conn:
                self.connection_pool.putconn(conn)
