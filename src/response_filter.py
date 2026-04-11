"""Response filtering and kwargs validation for Taiga MCP tools."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Kwargs Validation ---
# Allowed kwargs per resource type for security and validation
# Based on Taiga API fields: https://docs.taiga.io/api.html
ALLOWED_KWARGS: Dict[str, set] = {
    "project": {
        "name",
        "is_private",
        "is_featured",
        "description",
        "tags",
        "total_story_points",
        "total_milestones",
        "is_looking_for_people",
        "looking_for_people_note",
        "is_epics_activated",
        "is_backlog_activated",
        "is_kanban_activated",
        "is_wiki_activated",
        "is_issues_activated",
        "videoconferences",
        "videoconferences_extra_data",
        "creation_template",
        "is_contact_activated",
    },
    "user_story": {
        "description",
        "status",
        "is_closed",
        "points",
        "milestone",
        "tags",
        "assigned_to",
        "assigned_users",
        "watchers",
        "client_requirement",
        "team_requirement",
        "is_blocked",
        "blocked_note",
        "backlog_order",
        "sprint_order",
        "kanban_order",
        "due_date",
        "due_date_reason",
    },
    "task": {
        "description",
        "status",
        "milestone",
        "user_story",
        "assigned_to",
        "watchers",
        "is_iocaine",
        "tags",
        "is_blocked",
        "blocked_note",
        "due_date",
        "due_date_reason",
        "taskboard_order",
    },
    "issue": {
        "description",
        "status",
        "priority",
        "severity",
        "type",
        "milestone",
        "assigned_to",
        "watchers",
        "tags",
        "is_blocked",
        "blocked_note",
        "due_date",
        "due_date_reason",
    },
    "epic": {
        "description",
        "status",
        "assigned_to",
        "watchers",
        "tags",
        "color",
        "client_requirement",
        "team_requirement",
        "epics_order",
    },
    "milestone": {
        "name",
        "estimated_start",
        "estimated_finish",
        "disponibility",
        "slug",
        "order",
        "watchers",
    },
    "wiki_page": {
        "content",
        "slug",
        "watchers",
    },
}

# --- Response Field Filtering ---
# Define which fields to include at each verbosity level per resource type
# - 'minimal': Core identification fields only
# - 'standard': Useful fields for typical AI operations (includes 'version' for updates)
# - 'full': None = return all fields (no filtering)
RESPONSE_FIELDS: Dict[str, Dict[str, Optional[List[str]]]] = {
    "project": {
        "minimal": ["id", "name", "slug"],
        "standard": [
            "id",
            "name",
            "slug",
            "description",
            "is_private",
            "tags",
            "created_date",
            "modified_date",
            "version",
        ],
        "full": None,
    },
    "user_story": {
        "minimal": ["id", "ref", "subject", "status", "project"],
        "standard": [
            "id",
            "ref",
            "subject",
            "description",
            "status",
            "status_extra_info",
            "assigned_to",
            "assigned_to_extra_info",
            "milestone",
            "project",
            "tags",
            "is_blocked",
            "is_closed",
            "due_date",
            "version",
        ],
        "full": None,
    },
    "task": {
        "minimal": ["id", "ref", "subject", "status", "project"],
        "standard": [
            "id",
            "ref",
            "subject",
            "description",
            "status",
            "status_extra_info",
            "assigned_to",
            "assigned_to_extra_info",
            "user_story",
            "milestone",
            "project",
            "tags",
            "is_blocked",
            "due_date",
            "version",
        ],
        "full": None,
    },
    "issue": {
        "minimal": ["id", "ref", "subject", "status", "priority", "severity", "project"],
        "standard": [
            "id",
            "ref",
            "subject",
            "description",
            "status",
            "status_extra_info",
            "priority",
            "priority_extra_info",
            "severity",
            "severity_extra_info",
            "type",
            "type_extra_info",
            "assigned_to",
            "assigned_to_extra_info",
            "milestone",
            "project",
            "tags",
            "is_blocked",
            "due_date",
            "version",
        ],
        "full": None,
    },
    "epic": {
        "minimal": ["id", "ref", "subject", "status", "project"],
        "standard": [
            "id",
            "ref",
            "subject",
            "description",
            "status",
            "status_extra_info",
            "assigned_to",
            "assigned_to_extra_info",
            "project",
            "tags",
            "color",
            "version",
        ],
        "full": None,
    },
    "milestone": {
        "minimal": ["id", "name", "slug", "project"],
        "standard": [
            "id",
            "name",
            "slug",
            "estimated_start",
            "estimated_finish",
            "closed",
            "project",
            "version",
        ],
        "full": None,
    },
    "member": {
        "minimal": ["id", "user", "full_name"],
        "standard": [
            "id",
            "user",
            "full_name",
            "email",
            "role",
            "role_name",
            "is_admin",
            "project",
        ],
        "full": None,
    },
    "wiki_page": {
        "minimal": ["id", "slug", "project"],
        "standard": ["id", "slug", "content", "project", "version"],
        "full": None,
    },
    "milestone_stats": {
        "minimal": ["total_points", "completed_points"],
        "standard": [
            "total_points",
            "completed_points",
            "total_userstories",
            "completed_userstories",
            "total_tasks",
            "completed_tasks",
            "iocaine_doses",
            "days",
        ],
        "full": None,
    },
    "epic_related_user_story": {
        "minimal": ["epic", "user_story", "order"],
        "standard": ["epic", "user_story", "order"],
        "full": None,
    },
    "history_entry": {
        "minimal": ["id", "type", "key", "comment", "user", "created_at"],
        "standard": [
            "id",
            "type",
            "key",
            "comment",
            "comment_html",
            "user",
            "created_at",
            "diff",
            "values_diff",
            "is_hidden",
        ],
        "full": None,
    },
}

VALID_VERBOSITY_LEVELS = {"minimal", "standard", "full"}


def validate_kwargs(resource_type: str, kwargs: dict, strict: bool = False) -> dict:
    """Validate kwargs against allowed fields for a resource type.

    Args:
        resource_type: The type of resource (e.g., 'project', 'user_story')
        kwargs: The kwargs dict to validate
        strict: If True, raise ValueError on unexpected kwargs. If False, log and strip.

    Returns:
        Validated kwargs dict with only allowed fields

    Raises:
        ValueError: If strict=True and unexpected kwargs are found
    """
    if not kwargs:
        return {}

    allowed = ALLOWED_KWARGS.get(resource_type)
    if allowed is None:
        logger.warning(f"No kwargs allowlist defined for resource type '{resource_type}'")
        return kwargs

    unexpected = set(kwargs.keys()) - allowed
    if unexpected:
        if strict:
            raise ValueError(
                f"Unexpected kwargs for {resource_type}: {unexpected}. Allowed: {allowed}"
            )
        else:
            logger.warning(f"Stripping unexpected kwargs for {resource_type}: {unexpected}")
            return {k: v for k, v in kwargs.items() if k in allowed}

    return kwargs


def filter_response(response, resource_type: str, verbosity: str = "standard"):
    """Filter response fields based on verbosity level.

    Args:
        response: API response (dict, list of dicts, or None)
        resource_type: Type of resource (user_story, task, etc.)
        verbosity: One of 'minimal', 'standard', 'full'

    Returns:
        Filtered response with only requested fields

    Note: 'version' is always included in 'standard' level as it's required
    for update operations (optimistic concurrency control).
    """
    if response is None:
        return None

    if verbosity not in VALID_VERBOSITY_LEVELS:
        logger.warning(f"Invalid verbosity '{verbosity}', using 'standard'")
        verbosity = "standard"

    if verbosity == "full":
        return response

    if resource_type not in RESPONSE_FIELDS:
        logger.debug(f"No filter config for '{resource_type}', returning full response")
        return response

    fields = RESPONSE_FIELDS[resource_type].get(verbosity)
    if fields is None:
        return response

    field_set = set(fields)

    def filter_dict(d: Dict) -> Dict:
        return {k: v for k, v in d.items() if k in field_set}

    if isinstance(response, list):
        return [filter_dict(item) for item in response]
    return filter_dict(response)
