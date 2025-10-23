import logging
import logging.config
import os
import signal
import sys
import time
from typing import Optional

from prometheus_client import start_http_server

from .config import DatabaseConfig, MetricsConfig
from .database import DatabaseConnection
from .metrics import LiteLLMMetrics, MetricsCollector

__version__ = "1.3.1"


# Configure logging
def setup_logging(log_level: Optional[str] = None) -> logging.Logger:
    """Setup structured logging configuration for containerized environment."""

    # Get log level from environment or parameter
    level = log_level or os.getenv("LOG_LEVEL", "INFO").upper()

    # Create formatter for console output
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout for container logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level))
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level))
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # Set specific logger levels to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("prometheus_client").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


# Initialize logger
logger = setup_logging()

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def main():
    """Main application entry point."""
    logger.info("Starting LiteLLM Exporter", extra={"version": __version__})

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    logger.debug("Signal handlers configured")

    # Initialize configurations
    logger.debug("Initializing configurations")
    metrics_config = MetricsConfig()
    db_config = DatabaseConfig()
    logger.debug("Configurations loaded successfully")

    # Initialize connections and collectors
    logger.info("Initializing database connection and metrics collector")
    db_connection = DatabaseConnection(db_config)
    metrics = LiteLLMMetrics()
    collector = MetricsCollector(db_connection, metrics, metrics_config)

    # Wait for required tables to be available
    logger.info("Checking for required database tables...")
    if not collector.check_tables_availability():
        logger.warning(
            "Required tables not available, but continuing with graceful degradation"
        )
    else:
        logger.info("All required tables are available")

    logger.info("Database connection and metrics collector initialized")

    # Start the metrics server
    metrics_port = int(os.getenv("METRICS_PORT", "9090"))
    start_http_server(metrics_port)
    logger.info(f"Metrics server started on port {metrics_port}")
    logger.info(
        f"Using time windows: spend={metrics_config.spend_window}, "
        f"request={metrics_config.request_window}, error={metrics_config.error_window}"
    )
    logger.info(f"Metrics update interval: {metrics_config.update_interval} seconds")

    # Update metrics based on configured interval
    logger.info("Starting metrics collection loop")
    try:
        while not shutdown_requested:
            logger.debug("Updating all metrics")
            collector.update_all_metrics()
            logger.debug("Metrics update completed")

            # Use interruptible sleep - check for shutdown every second
            for _ in range(metrics_config.update_interval):
                if shutdown_requested:
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        logger.warning("Received KeyboardInterrupt, shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down gracefully...")
        # Close database connection if needed
        if hasattr(db_connection, "close"):
            logger.debug("Closing database connection")
            db_connection.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
