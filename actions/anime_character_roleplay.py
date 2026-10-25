from core import outcome

def anime_character_roleplay(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    character_name = params.get("character_name")
    action_description = params.get("action_description")

    if not character_name or not action_description:
        return outcome.failed("anime_character_roleplay", "Missing character_name or action_description.")

    result_msg = f"Incorporating {character_name}: {action_description}"
    return outcome.done("anime_character_roleplay", result_msg)

TOOL = {
    "name": "anime_character_roleplay",
    "description": "Enables roleplaying as a specific anime character performing an action.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "character_name": {
                "type": "STRING",
                "description": "The name of the anime character to embody."
            },
            "action_description": {
                "type": "STRING",
                "description": "The action or dialogue the character is performing."
            }
        },
        "required": ["character_name", "action_description"]
    },
    "handler": anime_character_roleplay
}