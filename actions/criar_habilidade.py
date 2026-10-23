import os
import re
from core import outcome
from core import gemini

def criar_habilidade(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    ideia = params.get("ideia", "")

    if not ideia:
        return outcome.failed("criar_habilidade", "Nenhuma ideia foi fornecida para a nova habilidade.")

    # O "Prompt" onde ensinamos ela a programar para si mesma
    prompt_sistema = """Você é um Engenheiro de Software Python avançado. Seu objetivo é criar uma nova habilidade (Action) para você mesma dentro do sistema Mark-LVI.
    
    REGRAS OBRIGATÓRIAS DO CÓDIGO:
    1. O código deve ter a função handler (ex: def minha_funcao(parameters, response=None, player=None, session_memory=None) -> str:)
    2. Deve extrair os parâmetros usando params = parameters or {}.
    3. Deve retornar strings de sucesso ou falha usando `outcome.done(nome, msg)` ou `outcome.failed(nome, msg)`.
    4. NO FINAL DO ARQUIVO, você DEVE declarar o dicionário TOOL exatamente com esta estrutura:
       TOOL = {
           "name": "nome_da_acao",
           "description": "descrição do que faz",
           "tier": "core",
           "parameters": { "type": "OBJECT", "properties": { ... }, "required": [...] },
           "handler": minha_funcao
       }
    5. Importe 'from core import outcome' no topo.
    6. Retorne APENAS o código Python puro, sem textos adicionais, explicações ou blocos de markdown.
    """

    print(f"[Auto-Programação] 🧠 A Ramma está pensando no código para: {ideia}")
    
    # Chama o Gemini (usando a marcha SMART que configuramos no gemini.py para usar o Pro)
    codigo_gerado = gemini.text(
        contents=ideia,
        tier=gemini.SMART,
        config={"system_instruction": prompt_sistema, "temperature": 0.1}
    )

    if not codigo_gerado:
        return outcome.failed("criar_habilidade", "A IA falhou em gerar o código.")

    # Limpa a resposta caso a IA teimosamente coloque as crases do markdown (```python)
    codigo_limpo = codigo_gerado.strip()
    if codigo_limpo.startswith("```python"):
        codigo_limpo = codigo_limpo[9:]
    if codigo_limpo.startswith("```"):
        codigo_limpo = codigo_limpo[3:]
    if codigo_limpo.endswith("```"):
        codigo_limpo = codigo_limpo[:-3]
    codigo_limpo = codigo_limpo.strip()

    # Tenta descobrir o nome da ferramenta para dar o nome ao arquivo .py
    match = re.search(r'"name"\s*:\s*"([^"]+)"', codigo_limpo)
    nome_arquivo = match.group(1) if match else "nova_habilidade_gerada"
    
    caminho_arquivo = os.path.join("actions", f"{nome_arquivo}.py")

    try:
        # Salva o arquivo na própria pasta de ações
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write(codigo_limpo)
            
        print(f"[Auto-Programação] ✅ Arquivo {nome_arquivo}.py salvo com sucesso!")
        return outcome.done(
            "criar_habilidade", 
            f"A habilidade '{nome_arquivo}' foi escrita e salva. O sistema de segurança (modo_dev) irá me reiniciar em cerca de 2 segundos para aplicar a mudança."
        )
    except Exception as e:
        return outcome.failed("criar_habilidade", f"Erro fatal ao tentar salvar o arquivo no disco: {e}")

# ── Declaração da Ferramenta para a IA ──────────────
TOOL = {
    "name": "criar_habilidade",
    "description": (
        "Usa inteligência artificial para escrever o código Python de uma nova ferramenta/habilidade "
        "para você mesma e salvar no sistema. O sistema será reiniciado automaticamente logo após. "
        "Use isso SEMPRE que o usuário pedir para você aprender a fazer algo novo, integrar-se a algo ou criar um comando."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "ideia": {
                "type": "STRING",
                "description": "O que o usuário quer que a nova habilidade faça."
            }
        },
        "required": ["ideia"]
    },
    "handler": criar_habilidade,
}