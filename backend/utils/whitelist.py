from typing import Iterable, List, Optional, Sequence

from core.config.settings import settings


def normalize_user_id(user_id: Optional[str]) -> str:
    """Normalize usernames for case-insensitive whitelist matching."""
    return (user_id or "").strip().casefold()


def is_user_in_whitelist(user_id: Optional[str], whitelist: Sequence[str]) -> bool:
    """Return whether the user is present in the given whitelist."""
    normalized_user_id = normalize_user_id(user_id)
    if not normalized_user_id:
        return False

    return any(normalize_user_id(candidate) == normalized_user_id for candidate in whitelist)


def is_feature_whitelist_user(user_id: Optional[str]) -> bool:
    """Return whether the user is in the configured feature whitelist."""
    return is_user_in_whitelist(user_id, settings.feature_whitelist)


def is_frontend_log_whitelist_user(user_id: Optional[str]) -> bool:
    """Return whether the user can upload frontend diagnostic logs."""
    return is_user_in_whitelist(user_id, settings.frontend_log_whitelist)


def is_whitelist_user(user_id: Optional[str]) -> bool:
    """Backward-compatible alias for the feature whitelist check."""
    return is_feature_whitelist_user(user_id)


def unique_users(user_ids: Iterable[str]) -> List[str]:
    """Preserve input order while removing empty values and duplicates."""
    seen = set()
    filtered: List[str] = []

    for user_id in user_ids:
        normalized_user_id = normalize_user_id(user_id)
        if not normalized_user_id or normalized_user_id in seen:
            continue
        seen.add(normalized_user_id)
        filtered.append(user_id)

    return filtered


def filter_feature_whitelist_users(user_ids: Iterable[str]) -> List[str]:
    """Keep only users present in the configured feature whitelist."""
    return [user_id for user_id in unique_users(user_ids) if is_feature_whitelist_user(user_id)]


def filter_whitelist_users(user_ids: Iterable[str]) -> List[str]:
    """Backward-compatible alias for the feature whitelist filter."""
    return filter_feature_whitelist_users(user_ids)


def filter_tts_pregenerate_users(user_ids: Iterable[str]) -> List[str]:
    """
    Filter users eligible for automatic TTS pregeneration.

    When `tts_pregenerate_all_users` is enabled, keep all eligible users.
    Otherwise only keep users from the feature whitelist.
    """
    unique_user_ids = unique_users(user_ids)
    if settings.tts_pregenerate_all_users:
        return unique_user_ids
    return filter_feature_whitelist_users(unique_user_ids)
