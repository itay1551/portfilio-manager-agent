from typing import Optional

from nemoguardrails.actions import action

OFF_TOPIC_KEYWORDS = [
    "recipe",
    "cooking",
    "weather forecast",
    "sports score",
    "write me a poem",
    "tell me a joke",
    "song lyrics",
    "movie review",
    "game walkthrough",
]


@action(is_system_action=True)
async def check_financial_topic(context: Optional[dict] = None) -> str:
    """Block messages that are clearly unrelated to finance/investments."""
    user_message = (context or {}).get("user_message", "").lower()
    for keyword in OFF_TOPIC_KEYWORDS:
        if keyword in user_message:
            return "blocked"
    return "allowed"
