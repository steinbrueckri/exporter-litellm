import logging
import os
import signal
import sys
import time

from prometheus_client import start_http_server

from .config import DatabaseConfig, MetricsConfig
from .database import DatabaseConnection
from .metrics import LiteLLMMetrics, MetricsCollector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    logger.debug("Signal handlers configured")
    # Initialize configurations
    metrics_config = MetricsConfig()
    db_config = DatabaseConfig()

    # Initialize connections and collectors
    db_connection = DatabaseConnection(db_config)
    metrics = LiteLLMMetrics()
    collector = MetricsCollector(db_connection, metrics, metrics_config)

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
        if hasattr(db_connection, 'close'):
            logger.debug("Closing database connection")
            db_connection.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
