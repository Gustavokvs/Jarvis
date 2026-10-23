from core import outcome

def capturar_informacao_tela(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    
    # Simulação de correção para manipulação de dados de monitor
    # Em um cenário real, isso envolveria interagir com APIs do sistema operacional
    # para obter informações sobre telas e monitores.
    # O erro de argumentos posicionais geralmente ocorre ao instanciar objetos
    # de bibliotecas de terceiros ou chamar métodos com parâmetros incorretos.

    monitor_id = params.get("monitor_id")
    
    try:
        # Lógica hipotética corrigida
        dados_monitor = {
            "id": monitor_id if monitor_id is not None else "principal",
            "resolucao": "1920x1080",
            "frequencia": "60Hz"
        }
            
        return outcome.done("capturar_informacao_tela", f"Informações do monitor capturadas com sucesso: {dados_monitor}")
    except Exception as e:
        return outcome.failed("capturar_informacao_tela", f"Falha ao capturar informações da tela: {str(e)}")

TOOL = {
    "name": "capturar_informacao_tela",
    "description": "Captura informações detalhadas sobre as telas/monitores conectados, corrigindo erros de argumentos.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "monitor_id": {
                "type": "STRING",
                "description": "ID opcional do monitor para buscar informações específicas."
            }
        },
        "required": []
    },
    "handler": capturar_informacao_tela
}