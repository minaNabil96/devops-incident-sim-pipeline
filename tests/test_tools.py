"""Tests for validation tools."""

from __future__ import annotations

from src.tools.validators import (
    AlertmanagerValidator,
    KubectlValidator,
    SMARTValidator,
)


class TestAlertmanagerValidator:
    """Test Alertmanager JSON validation."""

    def test_valid_alertmanager_json(self):
        """Valid Alertmanager JSON should pass."""
        valid_json = """
        {
            "version": "4",
            "groupKey": "{}:{alertname=\\"Test\\"}",
            "status": "firing",
            "receiver": "test-receiver",
            "groupLabels": {"alertname": "Test"},
            "commonLabels": {"namespace": "production"},
            "alerts": [{"labels": {"namespace": "production"}}]
        }
        """
        is_valid, errors = AlertmanagerValidator.validate(valid_json)
        assert is_valid, f"Errors: {errors}"

    def test_invalid_namespace(self):
        """Wrong namespace should fail."""
        invalid_json = """
        {
            "version": "4",
            "groupKey": "test",
            "status": "firing",
            "receiver": "test",
            "groupLabels": {},
            "commonLabels": {"namespace": "wrong"},
            "alerts": []
        }
        """
        is_valid, errors = AlertmanagerValidator.validate(invalid_json)
        assert not is_valid
        assert any("namespace" in e.lower() for e in errors)

    def test_invalid_json(self):
        """Malformed JSON should fail."""
        is_valid, errors = AlertmanagerValidator.validate("{ not valid json")
        assert not is_valid
        assert "Invalid JSON" in errors[0]

    def test_missing_field(self):
        """Missing required field should be reported."""
        payload = """
        {
            "version": "4",
            "groupKey": "test",
            "status": "firing",
            "receiver": "test"
        }
        """
        is_valid, errors = AlertmanagerValidator.validate(payload)
        assert not is_valid
        assert any("groupLabels" in e for e in errors)


class TestKubectlValidator:
    """Test kubectl command validation."""

    def test_valid_kubectl_command(self):
        """Valid kubectl command should pass."""
        is_valid, error = KubectlValidator.validate_command(
            "kubectl get pods --namespace=production"
        )
        assert is_valid, f"Error: {error}"

    def test_missing_namespace(self):
        """Command without namespace should fail."""
        is_valid, error = KubectlValidator.validate_command("kubectl get pods")
        assert not is_valid
        assert "namespace" in error.lower()

    def test_wrong_namespace(self):
        """Command with non-production namespace should fail."""
        is_valid, error = KubectlValidator.validate_command(
            "kubectl get pods --namespace=payments"
        )
        assert not is_valid
        assert "production" in error.lower()

    def test_non_kubectl_command(self):
        """Non-kubectl commands should fail."""
        is_valid, error = KubectlValidator.validate_command("ls -la")
        assert not is_valid
        assert "kubectl" in error.lower()

    def test_extract_commands(self):
        """Extract kubectl commands from markdown code blocks."""
        text = """
        ```bash
        kubectl get pods --namespace=production
        kubectl scale deployment app --replicas=6 --namespace=production
        ```
        """
        commands = KubectlValidator.extract_commands(text)
        assert len(commands) == 2
        assert all(c.startswith("kubectl") for c in commands)


class TestSMARTValidator:
    """Test SMART action item validation."""

    def test_valid_smart_item(self):
        """Valid SMART item should pass."""
        item = {
            "id": "PCI-1",
            "description": "Implement circuit breaker for Redis",
            "owner": "Platform Team",
            "priority": "P0",
            "due_date": "2024-06-07",
        }
        is_valid, errors = SMARTValidator.validate_item(item)
        assert is_valid, f"Errors: {errors}"

    def test_missing_due_date(self):
        """Missing due date should fail."""
        item = {
            "id": "PCI-1",
            "description": "Implement circuit breaker",
            "owner": "Platform Team",
            "priority": "P0",
        }
        is_valid, errors = SMARTValidator.validate_item(item)
        assert not is_valid
        assert any("due_date" in e for e in errors)

    def test_parse_table(self):
        """Parse SMART items from a markdown table."""
        table = """
        | ID | Description | Owner | Priority | Due Date |
        |----|-------------|-------|----------|----------|
        | PCI-1 | Implement circuit breaker | Platform Team | P0 | 2024-06-07 |
        | PCI-2 | Deploy WAF rule | Security Team | P0 | 2024-06-14 |
        """
        items = SMARTValidator.parse_table(table)
        assert len(items) == 2
        assert items[0]["id"] == "PCI-1"
        assert items[0]["owner"] == "Platform Team"