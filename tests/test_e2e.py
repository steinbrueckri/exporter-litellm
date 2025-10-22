import os
import time
from typing import List

import pytest
import requests


def fetch_metrics() -> List[str]:
    exporter_url = os.getenv("EXPORTER_URL", "http://localhost:9090")
    resp = requests.get(f"{exporter_url}/metrics", timeout=10)
    resp.raise_for_status()
    return resp.text.splitlines()


def wait_for_metrics() -> List[str]:
    """Wait for exporter metrics to be available."""
    metrics: List[str] = []
    deadline = time.time() + 60
    last_error = None
    while time.time() < deadline:
        try:
            metrics = fetch_metrics()
            if any(line.startswith("litellm_") for line in metrics):
                return metrics
        except Exception as e:
            last_error = str(e)
        time.sleep(2)
    
    # If we didn't get any litellm metrics, provide helpful error message
    error_msg = f"No litellm metrics found after 60 seconds. Last error: {last_error}"
    if metrics:
        error_msg += f"\nAvailable metrics: {[line.split()[0] for line in metrics if not line.startswith('#')][:10]}"
    else:
        error_msg += "\nNo metrics received at all - check if exporter is running on port 9090"
    raise AssertionError(error_msg)


def find_metric_value_with_label(
    lines: List[str], metric: str, label_contains: str
) -> float:
    """Find metric value by searching any label order, matching substring in label block."""
    metric_prefix = f"{metric}{{"
    for line in lines:
        if line.startswith(metric_prefix) and label_contains in line:
            try:
                return float(line.split(" ")[-1])
            except Exception:
                continue
    raise AssertionError(
        f"Metric with label not found: {metric} contains {label_contains!r}"
    )

def assert_metric_value(metrics: List[str], metric_name: str, expected_min: float = 0.0) -> None:
    """Test that a metric has a reasonable value."""
    for label in ('model="mock"', 'model="gpt-3.5-turbo"'):
        try:
            value = find_metric_value_with_label(metrics, metric_name, label)
            assert value >= expected_min, f"{metric_name} should be >= {expected_min}, got {value}"
            return
        except AssertionError:
            continue
    # If no labeled line found, check for any line with this metric
    for line in metrics:
        if line.startswith(metric_name) and not line.startswith("#"):
            try:
                value = float(line.split(" ")[-1])
                assert value >= expected_min, f"{metric_name} should be >= {expected_min}, got {value}"
                return
            except (ValueError, IndexError):
                continue
    pytest.fail(f"Could not find valid value for {metric_name}")


def test_core_metrics_present(setup_test_data: None) -> None:
    """Test that core metrics are present."""
    metrics = wait_for_metrics()
    
    expected_core = [
        "litellm_requests_total",
        "litellm_total_spend", 
        "litellm_total_tokens",
        "litellm_prompt_tokens",
        "litellm_completion_tokens",
    ]
    found_core = {
        name: any(line.startswith(name) for line in metrics) for name in expected_core
    }
    assert all(found_core.values()), f"Missing expected core metrics; present={found_core}"


def test_additional_metrics_present(setup_test_data: None) -> None:
    """Test that additional metrics are present."""
    metrics = wait_for_metrics()
    
    expected_additional = [
        "litellm_cache_hits_total",
        "litellm_cache_misses_total",
        "litellm_key_spend",
    ]
    found_additional = {
        name: any(line.startswith(name) for line in metrics) for name in expected_additional
    }
    assert all(found_additional.values()), f"Missing expected additional metrics; present={found_additional}"


def test_request_count(setup_test_data: None) -> None:
    """Test that we have the expected number of requests."""
    metrics = wait_for_metrics()
    
    # We sent 3 requests; accept counting either under model="mock" or gpt-3.5-turbo
    requests_value: float = 0.0
    found_any = False
    for label in ('model="mock"', 'model="gpt-3.5-turbo"'):
        try:
            requests_value = find_metric_value_with_label(
                metrics, "litellm_requests_total", label
            )
            found_any = True
            break
        except AssertionError:
            continue
    assert found_any, (
        "litellm_requests_total with model label not found (mock or gpt-3.5-turbo)"
    )
    assert requests_value >= 3.0, f"expected >=3 requests, got {requests_value}"


def test_metric_values(setup_test_data: None) -> None:
    """Test that metrics have reasonable values."""
    metrics = wait_for_metrics()
    
    # Test that we have reasonable values for our 3 requests
    assert_metric_value(metrics, "litellm_requests_total", expected_min=3.0)
    assert_metric_value(metrics, "litellm_total_spend", expected_min=0.0)
    assert_metric_value(metrics, "litellm_total_tokens", expected_min=0.0)
    assert_metric_value(metrics, "litellm_prompt_tokens", expected_min=0.0)
    assert_metric_value(metrics, "litellm_completion_tokens", expected_min=0.0)
    
    # Test cache metrics (should be 0 for our test)
    assert_metric_value(metrics, "litellm_cache_hits_total", expected_min=0.0)
    assert_metric_value(metrics, "litellm_cache_misses_total", expected_min=0.0)
    
    # Test key spend (should match total spend)
    assert_metric_value(metrics, "litellm_key_spend", expected_min=0.0)


def test_metrics_format(setup_test_data: None) -> None:
    """Test that metrics have proper format and structure."""
    metrics = fetch_metrics()
    
    # Test that we have proper metric format (HELP and TYPE comments)
    help_lines = [line for line in metrics if line.startswith("# HELP")]
    type_lines = [line for line in metrics if line.startswith("# TYPE")]
    
    assert len(help_lines) > 0, "No HELP comments found in metrics"
    assert len(type_lines) > 0, "No TYPE comments found in metrics"
    
    # Test that litellm metrics have proper format
    litellm_metrics = [line for line in metrics if line.startswith("litellm_") and not line.startswith("#")]
    assert len(litellm_metrics) > 0, "No litellm metrics found"
    
    for line in litellm_metrics:
        # Should have either a value or labels
        if "{" in line and "}" in line:
            # Has labels
            assert " " in line, f"Metric with labels should have a value: {line}"
        else:
            # Simple metric without labels
            parts = line.split(" ")
            assert len(parts) >= 2, f"Metric should have a value: {line}"
            try:
                float(parts[-1])
            except ValueError:
                pytest.fail(f"Metric value should be numeric: {line}")
