"""
Validation utilities for generated incident artifacts.

Provides schema validation for Alertmanager JSON, kubectl command syntax,
and SMART action item verification.
"""

from __future__ import annotations

import json
import re
from typing import Any


class AlertmanagerValidator:
    """Validate Alertmanager v4 JSON schema compliance."""

    REQUIRED_FIELDS = {
        "version": str,
        "groupKey": str,
        "status": str,
        "receiver": str,
        "groupLabels": dict,
        "commonLabels": dict,
        "alerts": list,
    }

    @classmethod
    def validate(cls, json_str: str) -> tuple[bool, list[str]]:
        """
        Validate Alertmanager JSON structure.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: list[str] = []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {e}"]

        for field, expected_type in cls.REQUIRED_FIELDS.items():
            if field not in data:
                errors.append(f"Missing required field: {field}")
            elif not isinstance(data[field], expected_type):
                errors.append(
                    f"Field '{field}' has wrong type: "
                    f"expected {expected_type.__name__}, got {type(data[field]).__name__}"
                )

        # Validate namespace consistency
        if "commonLabels" in data:
            ns = data["commonLabels"].get("namespace")
            if ns != "production":
                errors.append(f"Namespace must be 'production', got '{ns}'")

        # Validate alerts array
        if "alerts" in data and isinstance(data["alerts"], list):
            for i, alert in enumerate(data["alerts"]):
                if not isinstance(alert, dict) or "labels" not in alert:
                    errors.append(f"Alert {i} missing 'labels'")
                elif alert["labels"].get("namespace") != "production":
                    errors.append(f"Alert {i} has wrong namespace")

        return len(errors) == 0, errors


class KubectlValidator:
    """Validate kubectl command syntax."""

    VALID_COMMANDS = {
        "get", "describe", "logs", "exec", "apply", "delete",
        "scale", "patch", "rollout", "top", "port-forward", "cp",
    }

    @classmethod
    def validate_command(cls, cmd: str) -> tuple[bool, str]:
        """
        Validate a single kubectl command.

        Returns:
            (is_valid, error_message_or_empty)
        """
        cmd = cmd.strip()
        if not cmd.startswith("kubectl"):
            return False, "Command must start with 'kubectl'"

        parts = cmd.split()
        if len(parts) < 2:
            return False, "Command too short"

        verb = parts[1]
        if verb not in cls.VALID_COMMANDS:
            return False, f"Unknown kubectl verb: {verb}"

        # Check for namespace flag
        if "--namespace" not in cmd and "-n" not in cmd:
            return False, "Missing --namespace or -n flag"

        # Check for production namespace
        if "production" not in cmd:
            return False, "Namespace must be 'production'"

        return True, ""

    @classmethod
    def extract_commands(cls, text: str) -> list[str]:
        """Extract all kubectl commands from markdown code blocks."""
        pattern = r"```(?:bash)?\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        commands: list[str] = []
        for match in matches:
            for line in match.split("\n"):
                line = line.strip()
                if line.startswith("kubectl"):
                    commands.append(line)
        return commands


class SMARTValidator:
    """Validate SMART action item criteria."""

    ACTION_VERBS = {"implement", "add", "create", "deploy", "configure", "enable", "scale", "fix", "migrate", "upgrade"}

    @classmethod
    def validate_item(cls, item: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate a single SMART action item.

        Expected keys: id, description, owner, priority, due_date
        """
        errors: list[str] = []
        required = ["id", "description", "owner", "priority", "due_date"]

        for field in required:
            if field not in item or not item.get(field):
                errors.append(f"Missing field: {field}")

        # Check for actionable verb in description
        desc = str(item.get("description", "")).lower()
        if not any(word in desc for word in cls.ACTION_VERBS):
            errors.append("Description lacks actionable verb")

        # Check for time-bound (due_date format)
        due = str(item.get("due_date", ""))
        if due and not re.match(r"\d{4}-\d{2}-\d{2}", due):
            errors.append("Due date must be in YYYY-MM-DD format")

        return len(errors) == 0, errors

    @classmethod
    def parse_table(cls, text: str) -> list[dict[str, Any]]:
        """
        Parse SMART action items from a markdown table.

        Expects columns: ID | Description | Owner | Priority | Due Date
        """
        items: list[dict[str, Any]] = []
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|")]

        for line in lines[2:]:  # skip header + separator
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 5:
                items.append(
                    {
                        "id": cells[0],
                        "description": cells[1],
                        "owner": cells[2],
                        "priority": cells[3],
                        "due_date": cells[4],
                    }
                )
        return items
