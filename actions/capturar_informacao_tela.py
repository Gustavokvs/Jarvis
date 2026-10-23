from core import outcome

def capturar_informacao_tela(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    monitor_id = params.get("monitor_id")
    
    try:
        dados_monitor = {
            "id": monitor_id if monitor_id is not None else "ambos_os_monitores",
            "resolucao": "Resolução combinada",
            "status": "Todos os monitores estão visíveis para a Jarvis."
        }
            
        # CORREÇÃO: "capturar_informacao_tela" é o único argumento de posição.
        # O resto é passado com nome (info=...).
        return outcome.done("capturar_informacao_tela", info=f"Informações: {dados_monitor}")
        
    except Exception as e:
        return outcome.failed("capturar_informacao_tela", f"Falha: {str(e)}")

TOOL = {
    "name": "capturar_informacao_tela",
    "description": "Informa à IA que ela já tem acesso aos dois monitores através da visão nativa combinada.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "monitor_id": {
                "type": "STRING",
                "description": "ID opcional do monitor"
            }
        },
        "required": []
    },
    "handler": capturar_informacao_tela
}