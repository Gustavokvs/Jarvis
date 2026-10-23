import os
import sys
from core import outcome
from core.lazyimport import installed

_PYCAW = installed("pycaw")

def mudar_volume(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    alvo = params.get("alvo", "").strip().lower()
    volume = params.get("volume", 50)

    if not alvo:
        return outcome.failed("mudar_volume", "O alvo (nome do app, 'sistema' ou 'proprio') não foi fornecido.")

    if sys.platform != "win32":
        return outcome.failed("mudar_volume", "Esta ferramenta funciona apenas no Windows.")

    if not _PYCAW:
        return outcome.failed(
            "mudar_volume", 
            "A biblioteca pycaw não está instalada. Rode no terminal: pip install pycaw comtypes"
        )

    target_volume = max(0.0, min(1.0, volume / 100.0))
    
    try:
        import comtypes
        comtypes.CoInitialize()
        
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume, IAudioEndpointVolume
        from ctypes import cast, POINTER
        
        # ==========================================
        # 1. VOLUME GERAL DO SISTEMA
        # ==========================================
        palavras_sistema = ["tudo", "sistema", "geral", "master", "pc", "computador", "windows"]
        is_sistema = any(palavra in alvo for palavra in palavras_sistema)
        
        if is_sistema:
            # IGNORA o GetSpeakers() e usa as chamadas nativas (COM API) do Windows
            from pycaw.pycaw import IMMDeviceEnumerator
            from pycaw.constants import CLSID_MMDeviceEnumerator
            
            enumerator = comtypes.CoCreateInstance(
                CLSID_MMDeviceEnumerator,
                IMMDeviceEnumerator,
                comtypes.CLSCTX_ALL
            )
            
            # Puxa o endpoint de saída (0) de multimídia (1)
            speakers = enumerator.GetDefaultAudioEndpoint(0, 1)
            interface = speakers.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
            volume_master = cast(interface, POINTER(IAudioEndpointVolume))
            volume_master.SetMasterVolumeLevelScalar(target_volume, None)
            
            print(f"[Volume] 🔊 Volume GERAL do Windows alterado para {volume}%")
            return outcome.done("mudar_volume", message=f"Volume geral do sistema ajustado para {volume}%.")

        # ==========================================
        # 2. VOLUME DA IA OU DE UM APLICATIVO
        # ==========================================
        sessions = AudioUtilities.GetAllSessions()
        encontrou_app = False
        meu_pid = os.getpid() 
        
        sinonimos_ia = ["proprio", "próprio", "seu", "sua", "você", "voce", "ia", "mim", "mesma", "ramma", "heloisa", "heloísa", "assistente"]
        
        for session in sessions:
            process = session.Process
            if not process:
                continue
                
            nome_processo = process.name().lower() if process.name() else ""
            
            nome_exibicao = ""
            try:
                nome_exibicao = session._ctl.GetDisplayName().lower()
            except Exception:
                pass
            
            is_propria_ia = any(sinonimo in alvo for sinonimo in sinonimos_ia) and (process.pid == meu_pid)
            is_app_alvo = (alvo in nome_processo) or (alvo in nome_exibicao)
            
            if is_propria_ia or is_app_alvo:
                volume_interface = session._ctl.QueryInterface(ISimpleAudioVolume)
                volume_interface.SetMasterVolume(target_volume, None)
                encontrou_app = True
                
                nome_sucesso = "SEU PRÓPRIO VOLUME" if is_propria_ia else (nome_exibicao or nome_processo)
                print(f"[Volume] 🔊 {nome_sucesso} alterado para {volume}%")

        if encontrou_app:
            return outcome.done("mudar_volume", message=f"Volume ajustado para {volume}%.")
        else:
            return outcome.failed(
                "mudar_volume", 
                f"Não encontrei áudio ativo para '{alvo}'. O app precisa estar emitindo som no momento para liberar o controle."
            )

    except Exception as e:
        return outcome.failed("mudar_volume", f"Erro inesperado: {e}")
        
    finally:
        try:
            import comtypes
            comtypes.CoUninitialize()
        except Exception:
            pass

# ── Declaração da Ferramenta para a IA ──────────────
TOOL = {
    "name": "mudar_volume",
    "description": (
        "Altera o volume do sistema inteiro, de um aplicativo específico ou o SEU PRÓPRIO volume no Windows. "
        "Use alvo='sistema' para o volume geral do PC. Use alvo='proprio' SEMPRE que o usuário mandar alterar o "
        "seu volume (ex: 'abaixe sua voz', 'aumente o volume da Heloisa'). Para outros apps, use o nome (ex: 'spotify', 'discord', 'chrome'). "
        "O aplicativo alvo precisa estar emitindo som para funcionar."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "alvo": {
                "type": "STRING",
                "description": "O que alterar: 'sistema', 'proprio' (para a sua própria voz), ou nome do aplicativo (ex: 'discord')."
            },
            "volume": {
                "type": "INTEGER",
                "description": "Nível do volume desejado de 0 a 100."
            }
        },
        "required": ["alvo", "volume"]
    },
    "handler": mudar_volume,
}