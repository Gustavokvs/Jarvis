from core import outcome
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

def get_google_news(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    topic = params.get("topic")
    lang = params.get("lang", "pt-BR")
    region = params.get("region", "BR")

    if not topic:
        return outcome.failed("get_google_news", "Tópico não especificado.")

    base_url = "https://news.google.com/rss/search"
    query = f"{base_url}?q={topic}&hl={lang}&gl={region}"

    try:
        req_response = requests.get(query)
        req_response.raise_for_status()
        
        root = ET.fromstring(req_response.content)
        articles = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title').text
            link = item.find('link').text
            
            # Simple summary approximation from description, removal of HTML
            description_html = item.find('description').text
            soup = BeautifulSoup(description_html, "html.parser")
            summary = soup.get_text(separator=' ')[:200] + "..."

            articles.append(f"Título: {title}\nLink: {link}\nResumo: {summary}\n")

        if not articles:
            return outcome.done("get_google_news", message=f"Nenhuma notícia encontrada para o tópico: {topic}.")

        final_result = f"Últimas notícias sobre {topic}:\n\n" + "\n".join(articles)
        return outcome.done("get_google_news", message=final_result)

    except Exception as e:
        return outcome.failed("get_google_news", f"Erro ao buscar notícias: {str(e)}")

TOOL = {
    "name": "get_google_news",
    "description": "Busca e resume as últimas notícias do Google News sobre um tópico específico.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "topic": {
                "type": "STRING",
                "description": "O tópico da notícia a ser pesquisado."
            },
            "lang": {
                "type": "STRING",
                "description": "O código do idioma (ex: pt-BR)."
            },
            "region": {
                "type": "STRING",
                "description": "O código da região (ex: BR)."
            }
        },
        "required": ["topic"]
    },
    "handler": get_google_news
}