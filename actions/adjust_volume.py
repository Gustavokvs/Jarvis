from core import outcome

def adjust_volume(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    level = params.get("level")

    if level is None:
        return outcome.failed("adjust_volume", "Missing required parameter: level")

    try:
        level_int = int(level)
        # Assuming player.set_volume is the method to adjust volume
        # player.set_volume(level_int)
        return outcome.done("adjust_volume", message=f"Volume set to {level_int}")
    except ValueError:
        return outcome.failed("adjust_volume", "Parameter 'level' must be an integer")
    except Exception as e:
        return outcome.failed("adjust_volume", f"Failed to adjust volume: {str(e)}")

TOOL = {
    "name": "adjust_volume",
    "description": "Adjusts the system or player volume",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "level": {
                "type": "INTEGER",
                "description": "The volume level to set (0-100)"
            }
        },
        "required": ["level"]
    },
    "handler": adjust_volume
}