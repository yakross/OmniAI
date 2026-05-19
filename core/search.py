import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import concurrent.futures

class WebSearcher:
    """
    Real-time web search utility for OMNI-AI.
    Combines Google News RSS (for real-time news/updates) and Wikipedia API (for factual information).
    Incredibly fast, 100% free, and now visits and scrapes up to 50 links in parallel.
    """

    @staticmethod
    def scrape_url(url: str, timeout=4) -> str:
        """Visita una URL en paralelo, descarga su HTML y extrae el contenido de texto principal limpio."""
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return ""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code != 200:
                return ""
            
            # Detectar si es XML (a veces los RSS o feeds se confunden)
            content_type = r.headers.get('Content-Type', '').lower()
            if 'xml' in content_type or 'pdf' in content_type:
                return ""

            soup = BeautifulSoup(r.content, "html.parser")
            
            # Limpiar etiquetas innecesarias
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button", "iframe", "head", "noscript", "meta"]):
                tag.decompose()
            
            # Buscar párrafos y títulos para un escaneo estructurado y de calidad
            elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'li'])
            text_blocks = []
            for el in elements:
                txt = el.get_text(strip=True)
                if len(txt) > 25:  # Ignorar líneas basura cortas (como links de menu)
                    text_blocks.append(txt)
            
            if not text_blocks:
                # Caída de respaldo si no hay etiquetas estructuradas
                text = soup.get_text(separator=" ", strip=True)
                lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 35]
                text = " ".join(lines)
            else:
                text = " ".join(text_blocks)
                
            # Normalizar espacios en blanco
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Retornar los primeros 1500 caracteres del contenido de la web para contexto enriquecido
            return text[:1500]
        except Exception:
            return ""

    @staticmethod
    def search_google_news(query: str, max_results=5) -> list[dict]:
        """Search Google News RSS to get latest headlines, snippets, and links."""
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=es-419&gl=US&ceid=US:es-419"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code != 200:
                return []
            
            soup = BeautifulSoup(r.text, "xml")
            items = soup.find_all("item")
            
            results = []
            for item in items[:max_results]:
                title = item.find("title").get_text(strip=True) if item.find("title") else ""
                link = item.find("link").get_text(strip=True) if item.find("link") else ""
                pub_date = item.find("pubDate").get_text(strip=True) if item.find("pubDate") else ""
                description = item.find("description").get_text(strip=True) if item.find("description") else ""
                
                # Clean Google News source from title (e.g. "Title - El País" -> "Title")
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                
                # Clean snippet
                snippet_soup = BeautifulSoup(description, "html.parser")
                snippet = snippet_soup.get_text(strip=True)
                # If the snippet is just the title again, make it empty or format it
                if snippet == title:
                    snippet = "Última noticia relevante sobre este tema."
 
                results.append({
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                    "date": pub_date,
                    "source": "Google News"
                })
            return results
        except Exception:
            return []

    @staticmethod
    def search_wikipedia(query: str, max_results=3) -> list[dict]:
        """Search Wikipedia API for factual and encyclopedic definitions in Spanish."""
        url = "https://es.wikipedia.org/w/api.php"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "utf8": 1,
            "formatversion": 2
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=5)
            if r.status_code != 200:
                return []
            
            data = r.json()
            search_results = data.get("query", {}).get("search", [])
            
            results = []
            for item in search_results[:max_results]:
                title = item.get("title", "")
                pageid = item.get("pageid")
                snippet_raw = item.get("snippet", "")
                
                # Clean html tags from Wikipedia snippets
                snippet = BeautifulSoup(snippet_raw, "html.parser").get_text(strip=True)
                
                # Construct page link
                link = f"https://es.wikipedia.org/?curid={pageid}" if pageid else f"https://es.wikipedia.org/wiki/{urllib.parse.quote(title)}"
                
                results.append({
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                    "date": "Wikipedia",
                    "source": "Wikipedia"
                })
            return results
        except Exception:
            return []

    @staticmethod
    def search_duckduckgo(query: str, max_results=10) -> list[dict]:
        """Search DuckDuckGo HTML interface for direct, real publisher URLs and clean snippets."""
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code != 200:
                return []
            
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            
            # Find result div items
            divs = soup.find_all("div", class_="result")
            for div in divs[:max_results]:
                title_a = div.find("a", class_="result__a")
                snippet_elem = div.find("a", class_="result__snippet")
                url_elem = div.find("a", class_="result__url")
                
                if not title_a:
                    continue
                
                title = title_a.get_text(strip=True)
                raw_url = title_a.get("href", "")
                
                # Extract clean direct URL
                parsed_url = raw_url
                if "/l/?" in raw_url:
                    parsed = urllib.parse.urlparse(raw_url)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    if "uddg" in query_params:
                        parsed_url = query_params["uddg"][0]
                
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                
                # Extract clean source domain name
                source = "Web"
                if url_elem:
                    source = url_elem.get_text(strip=True).replace("www.", "").split("/")[0]
                elif parsed_url:
                    parsed_domain = urllib.parse.urlparse(parsed_url).netloc
                    source = parsed_domain.replace("www.", "")
                
                results.append({
                    "title": title,
                    "link": parsed_url,
                    "snippet": snippet,
                    "date": "Reciente",
                    "source": source
                })
            return results
        except Exception:
            return []

    @classmethod
    def search(cls, query: str, max_results=5) -> list[dict]:
        """Runs Wikipedia, DuckDuckGo, and Google News searches, merging and scraping results in parallel."""
        # Simple query cleaning: remove conversational fillers
        clean_query = query.lower()
        fillers = ["busca en internet", "busca sobre", "busca", "busca en la web", "investiga sobre", "quien es", "que es", "informacion de"]
        for f in fillers:
            clean_query = clean_query.replace(f, "")
        clean_query = clean_query.strip()
        
        if not clean_query:
            clean_query = query

        # Allocate max_results dynamically:
        # Wikipedia (15%, min 1), DuckDuckGo (55%, min 2), Google News (30%, min 2)
        wiki_n = max(1, int(max_results * 0.15))
        ddg_n = max(2, int(max_results * 0.55))
        news_n = max(2, max_results - wiki_n - ddg_n)

        wiki_results = cls.search_wikipedia(clean_query, max_results=wiki_n)
        ddg_results = cls.search_duckduckgo(clean_query, max_results=ddg_n)
        news_results = cls.search_google_news(clean_query, max_results=news_n)
        
        # Merge results: wikipedia first, then duckduckgo (best for direct scraping), then news
        merged = wiki_results + ddg_results + news_results
        results_to_scrape = merged[:max_results]

        if not results_to_scrape:
            return []

        # Realizar el escaneo de los links en paralelo si se solicita
        # Usamos ThreadPoolExecutor de Python para descargar los links en paralelo de manera ultra-rápida.
        max_workers = min(35, len(results_to_scrape))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Lanzar tareas de scraping concurrentes
            future_to_item = {
                executor.submit(cls.scrape_url, item["link"]): item
                for item in results_to_scrape
            }
            
            for future in concurrent.futures.as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    scraped_text = future.result()
                    if scraped_text and len(scraped_text) > 120:
                        # Enriquecer el snippet con el contenido real de la página
                        item["snippet"] = scraped_text
                        item["scraped"] = True
                    else:
                        item["scraped"] = False
                except Exception:
                    item["scraped"] = False

        return results_to_scrape

