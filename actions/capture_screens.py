from core import outcome

def capture_screens(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    skill_name = "capture_screens"
    
    try:
        # Placeholder logic for capturing screen information.
        # In a real scenario, this would involve system calls or using library like MSS.
        screens_info = [
            {"id": 1, "resolution": "1920x1080", "primary": True},
            {"id": 2, "resolution": "2560x1440", "primary": False}
        ]
        
        return outcome.done(skill_name, f"Captured information for {len(screens_info)} screens.", screens_info)
    except Exception as e:
        return outcome.failed(skill_name, f"Failed to capture screen information: {str(e)}")

TOOL = {
    "name": "capture_screens",
    "description": "Captures information about all connected displays/monitors.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": []
    },
    "handler": capture_screens
}