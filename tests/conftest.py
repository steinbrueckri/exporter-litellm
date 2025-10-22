import os
import time
import socket
from typing import Generator
import pytest
import requests
import docker
import psycopg2



def wait_for_http_ok(
    url: str, timeout_seconds: int = 60, sleep_seconds: float = 1.0
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str = ""
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if 200 <= response.status_code < 300:
                return
            last_error = f"status={response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(sleep_seconds)
    raise TimeoutError(
        f"Timeout waiting for {url} to be ready; last_error={last_error}"
    )


def check_port_available(port: int) -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except OSError:
            return False


def wait_for_postgres_ready(
    host: str, port: int, database: str, user: str, password: str, 
    timeout_seconds: int = 30, sleep_seconds: float = 1.0
) -> None:
    """Wait for PostgreSQL to be ready for connections."""
    deadline = time.time() + timeout_seconds
    last_error: str = ""
    
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                connect_timeout=5
            )
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(sleep_seconds)
    
    raise TimeoutError(
        f"Timeout waiting for PostgreSQL at {host}:{port} to be ready; last_error={last_error}"
    )


def generate_virtual_key(litellm_url: str = None) -> dict:
    """Generate a virtual API key in LiteLLM."""
    base_url = litellm_url or os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
    url = f"{base_url}/key/generate"
    headers = {
        "Authorization": "Bearer dummy-key",
        "Content-Type": "application/json",
    }
    data = {
        "models": ["mock"],
        "metadata": {"user": "mock@steinbrueck.io"},
        "tpm_limit": 10000,  # tokens per minute
        "rpm_limit": 120,  # requests per minute
        "budget": 10.0,  # budget per 30 days
    }
    response = requests.post(url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    return response.json()


def make_chat_completion(api_key: str, litellm_url: str = None) -> dict:
    """Make a chat completion request to LiteLLM."""
    base_url = litellm_url or os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_response: dict = {}
    for i in range(3):
        payload = {
            "model": "mock",
            "messages": [
                {"role": "user", "content": f"hello #{i + 1}"},
            ],
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        last_response = resp.json()
    return last_response


@pytest.fixture(scope="session")
def docker_network() -> Generator[docker.models.networks.Network, None, None]:
    """Create Docker network for test containers."""
    client = docker.from_env()
    network_name = "litellm_test_network"
    
    # Clean up any existing network
    try:
        existing = client.networks.get(network_name)
        existing.remove()
    except docker.errors.NotFound:
        pass
    
    try:
        # Create network
        network = client.networks.create(
            network_name,
            driver="bridge"
        )
        yield network
    finally:
        # Cleanup
        try:
            network.remove()
        except (docker.errors.NotFound, NameError):
            pass


@pytest.fixture(scope="session")
def postgres_container(docker_network: docker.models.networks.Network) -> Generator[str, None, None]:
    """Start PostgreSQL container for testing."""
    client = docker.from_env()
    container_name = "litellm_test_db"
    port = "5433"  # Use different port to avoid conflicts
    
    # Check if port is available
    if not check_port_available(int(port)):
        raise RuntimeError(f"Port {port} is already in use. Please free the port or change the test configuration.")
    
    # Clean up any existing container
    try:
        existing = client.containers.get(container_name)
        existing.remove(force=True)
    except docker.errors.NotFound:
        pass
    
    try:
        # Start container using Docker client
        container = client.containers.run(
            "postgres:16",
            name=container_name,
            ports={"5432/tcp": port},
            environment={
                "POSTGRES_DB": "litellm",
                "POSTGRES_USER": "litellm",
                "POSTGRES_PASSWORD": "litellm"
            },
            network=docker_network.name,
            detach=True,
            remove=False
        )
        
        # Wait for DB to be ready
        wait_for_postgres_ready(
            host="localhost",
            port=int(port),
            database="litellm",
            user="litellm",
            password="litellm",
            timeout_seconds=30
        )
        
        # Return both localhost URL (for external access) and container URL (for LiteLLM)
        container_db_url = "postgresql://litellm:litellm@litellm_test_db:5432/litellm"
        yield container_db_url
    finally:
        # Cleanup
        try:
            container.stop()
            container.remove()
        except (docker.errors.NotFound, NameError):
            pass


@pytest.fixture(scope="session") 
def litellm_container(postgres_container: str, docker_network: docker.models.networks.Network) -> Generator[str, None, None]:
    """Start LiteLLM container for testing."""
    client = docker.from_env()
    container_name = "litellm_test"
    port = "4001"  # Use different port to avoid conflicts
    
    # Clean up any existing container
    try:
        existing = client.containers.get(container_name)
        existing.remove(force=True)
    except docker.errors.NotFound:
        pass
    
    try:
        # Get the path to the litellm config file
        test_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(test_dir, "litellm-config.yaml")
        
        # Start container using Docker client
        container = client.containers.run(
            "ghcr.io/berriai/litellm:main-stable",
            name=container_name,
            ports={"4000/tcp": port},
            environment={
                "DATABASE_URL": postgres_container,
                "STORE_MODEL_IN_DB": "false",
                "LITELLM_MASTER_KEY": "dummy-key",
                "LITELLM_SALT_KEY": "V3rySecretSaltKey",
                "OPENAI_API_KEY": "sk-mock-key"
            },
            volumes={config_file: {"bind": "/app/config.yaml", "mode": "ro"}},
            command=["--config=/app/config.yaml"],
            network=docker_network.name,
            detach=True,
            remove=False
        )
        
        # Wait for LiteLLM to be ready
        litellm_url = f"http://localhost:{port}"
        wait_for_http_ok(f"{litellm_url}/health/liveliness", timeout_seconds=60)
        
        yield litellm_url
    finally:
        # Cleanup
        try:
            container.stop()
            container.remove()
        except (docker.errors.NotFound, NameError):
            pass


@pytest.fixture(scope="session")
def exporter_process(postgres_container: str) -> Generator[None, None, None]:
    """Start the litellm_exporter process for testing."""
    import subprocess
    
    # Set environment variables for the exporter
    env = os.environ.copy()
    env.update({
        "LITELLM_DB_HOST": "localhost",
        "LITELLM_DB_PORT": "5433",
        "LITELLM_DB_NAME": "litellm",
        "LITELLM_DB_USER": "litellm",
        "LITELLM_DB_PASSWORD": "litellm",
        "DB_MIN_CONNECTIONS": "1",
        "DB_MAX_CONNECTIONS": "10",
        "METRICS_UPDATE_INTERVAL": "15",
        "METRICS_SPEND_WINDOW": "30d",
        "METRICS_REQUEST_WINDOW": "24h",
        "METRICS_ERROR_WINDOW": "1h",
    })
    
    # Start the exporter process 
    process = subprocess.Popen(
        ["uv", "run", "python", "-m", "litellm_exporter"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Wait for exporter to be ready
        exporter_base = os.getenv("EXPORTER_URL", "http://localhost:9090")
        wait_for_http_ok(f"{exporter_base}/metrics", timeout_seconds=30)
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="session")
def setup_test_data(litellm_container: str, exporter_process: None) -> None:
    """Generate test data by creating API key and making requests."""
    # Create virtual key in LiteLLM
    key_payload = generate_virtual_key(litellm_container)
    assert "key" in key_payload or "message" in key_payload
    api_key = key_payload.get("key") or key_payload.get("message")
    
    # Trigger traffic so exporter has data to expose
    make_chat_completion(api_key, litellm_container)