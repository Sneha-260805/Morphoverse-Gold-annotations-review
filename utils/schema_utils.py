"""Shared schema constants for the MorphoVerse++ review app."""

EXCLUDED_LANGUAGES = {"Bodo"}
EXCLUDED_POEM_IDS = {"MV++_1443"}  # failed Telugu poem

ALLOWED_CULTURE_CATEGORIES = [
    "HOMELAND",
    "DEITY",
    "RITUAL",
    "CULTURAL_OBJECT",
    "CULTURAL_ART",
    "CULTURAL_SPACE",
    "SACRED_RIVER",
    "SACRED_PLACE",
    "DIVINE",
    "ATTIRE",
    "CULTURAL_SYMBOL",
    "FESTIVAL",
    "MUSICAL_TRADITION",
    "DEVOTIONAL_CONCEPT",
    "REGIONAL_SYMBOL",
    "SOCIAL_CUSTOM",
    "MYTHOLOGICAL_EVENT",
    "OTHER",
]

ALLOWED_EMOTIONS = [
    "peace",
    "celebration",
    "longing",
    "grief",
    "rebellion",
    "devotion",
    "resilience",
    "anger",
    "fear",
    "neutral",
    "other",
]

REVIEW_ACTIONS = ["keep", "modify", "remove", "add"]
REVIEW_DECISIONS = [
    "approved",
    "approved_with_corrections",
    "needs_major_revision",
    "rejected",
]
REVIEW_CONFIDENCE = ["high", "medium", "low"]
REVIEW_STATUS_FILTERS = [
    "all",
    "pending_review",
    "in_progress",
    "approved",
    "approved_with_corrections",
    "needs_major_revision",
    "rejected",
]
