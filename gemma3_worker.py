import requests
from requests.auth import HTTPBasicAuth
import logging
from bs4 import BeautifulSoup
import re
import random
import time
import subprocess
from urllib.parse import urljoin

# Configuración básica
WP_USER = "codigomotor"
WP_APP_PASSWORD = "DRYI VAoM WRbE QTsp Liih 14aL"
WP_BASE_URL = "https://codigomotor.kesug.com"
WP_API_URL = f"{WP_BASE_URL}/wp-json/wp/v2"
WP_POSTS_URL = f"{WP_API_URL}/posts"
WP_MEDIA_URL = f"{WP_API_URL}/media"
WP_CATEGORIES_URL = f"{WP_API_URL}/categories"
WP_TAGS_URL = f"{WP_API_URL}/tags"

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gemma3_worker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('Gemma3Worker')

# Configuración de fuentes de noticias
NEWS_SOURCES = {
    'tn': {
        'url': 'https://tn.com.ar/deportes/automovilismo/',
        'selectors': {
            'articles': 'article',
            'title': 'h2, h3, a',
            'link': 'a',
            'image': 'img'
        }
    },
    'lanacion': {
        'url': 'https://www.lanacion.com.ar/deportes/automovilismo/',
        'selectors': {
            'articles': '.mod-article',
            'title': 'h2 a',
            'link': 'h2 a',
            'image': 'img',
            'content': '.mod-description'
        },
        'requires_js': False
    },
    'tycsports': {
        'url': 'https://www.tycsports.com/automovilismo.html',
        'selectors': {
            'articles': '.news-item',
            'title': 'h3 a',
            'link': 'h3 a',
            'image': 'img',
            'content': '.news-excerpt'
        },
        'base_url': 'https://www.tycsports.com'
    }
}

class WordPressConnector:
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(WP_USER, WP_APP_PASSWORD)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
    def test_connection(self):
        """Prueba la conexión con la API de WordPress"""
        try:
            response = self.session.get(WP_POSTS_URL, params={'per_page': 1}, timeout=10)
            if response.status_code == 200:
                logger.info("✅ Conexión exitosa con WordPress REST API")
                return True
            else:
                logger.error(f"❌ Error de conexión. Código: {response.status_code}")
                logger.debug(f"Respuesta: {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Excepción al conectar: {str(e)}")
            return False

    def get_categories(self):
        """Obtiene las categorías existentes"""
        try:
            response = self.session.get(WP_CATEGORIES_URL, timeout=10)
            return {cat['name']: cat['id'] for cat in response.json()} if response.ok else {}
        except Exception as e:
            logger.error(f"Error obteniendo categorías: {str(e)}")
            return {}

    def create_post(self, title, content, categories=None, featured_media=None):
        """Crea un nuevo post en WordPress"""
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
            'categories': categories or [],
            'featured_media': featured_media
        }
        
        try:
            response = self.session.post(WP_POSTS_URL, json=post_data, timeout=15)
            if response.status_code == 201:
                logger.info(f"Post creado exitosamente: {response.json().get('link')}")
                return True
            else:
                logger.error(f"Error al crear post: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Excepción al crear post: {str(e)}")
            return False

    def upload_media(self, image_url, title):
        """Sube una imagen a la biblioteca de medios"""
        try:
            # Descargar la imagen primero
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            image_response = requests.get(image_url, headers=headers, stream=True, timeout=15)
            image_response.raise_for_status()
            
            # Preparar datos para subir
            filename = f"media_{int(time.time())}.jpg"
            files = {
                'file': (filename, image_response.content, 'image/jpeg')
            }
            
            data = {
                'title': title,
                'caption': f"Imagen para: {title}",
                'alt_text': title,
                'description': f"Imagen ilustrativa para el artículo: {title}"
            }
            
            # Subir la imagen
            response = self.session.post(
                WP_MEDIA_URL,
                files=files,
                data=data,
                timeout=20
            )
            
            if response.status_code == 201:
                logger.info(f"Imagen subida exitosamente - ID: {response.json().get('id')}")
                return response.json().get('id')
            else:
                logger.error(f"Error al subir imagen: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Excepción al subir media: {str(e)}")
            return None

class ContentGenerator:
    def __init__(self):
        self.news_sources = NEWS_SOURCES
        
    def fetch_news(self, source='tn'):
        """Obtiene noticias de las fuentes configuradas"""
        if source not in self.news_sources:
            logger.error(f"Fuente no soportada: {source}")
            return []
            
        config = self.news_sources[source]
        logger.info(f"Buscando noticias en {source.upper()}...")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'es-AR,es;q=0.9',
                'Referer': 'https://www.google.com/'
            }
            
            response = requests.get(config['url'], headers=headers, timeout=15)
            response.raise_for_status()
            
            # Algunos sitios pueden requerir diferente encoding
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'html.parser')
            
            articles = soup.select(config['selectors']['articles'])[:3]  # Limitar a 3 artículos
            news_items = []
            
            for article in articles:
                try:
                    # Extracción específica para cada fuente
                    if source == 'lanacion':
                        item = self._extract_lanacion(article, config)
                    elif source == 'tycsports':
                        item = self._extract_tycsports(article, config)
                    else:  # TN u otros
                        item = self._extract_default(article, config)
                    
                    if item and item['title'] and item['url']:
                        news_items.append(item)
                        
                except Exception as e:
                    logger.warning(f"Error procesando artículo ({source}): {str(e)}")
                    continue
                    
            return news_items
            
        except Exception as e:
            logger.error(f"Error al obtener noticias de {source}: {str(e)}")
            return []
    
    def _extract_default(self, article, config):
        """Extracción genérica para la mayoría de fuentes"""
        title_elem = article.select_one(config['selectors']['title'])
        title = self.clean_text(title_elem.get_text()) if title_elem else None
        
        link_elem = article.select_one(config['selectors']['link'])
        link = link_elem.get('href') if link_elem else None
        
        if link and not link.startswith('http'):
            base = config.get('base_url', config['url'])
            link = urljoin(base, link)
            
        image_elem = article.select_one(config['selectors']['image'])
        image_url = None
        if image_elem:
            image_url = image_elem.get('src') or image_elem.get('data-src')
            if image_url and not image_url.startswith('http'):
                image_url = urljoin(config['url'], image_url)
                
        return {
            'title': title,
            'url': link,
            'image_url': image_url,
            'source': config['url'].split('/')[2]  # Extrae el dominio
        }
    
    def _extract_lanacion(self, article, config):
        """Extracción específica para La Nación"""
        item = self._extract_default(article, config)
        
        # La Nación a veces usa URLs relativas sin el protocolo
        if item['url'] and item['url'].startswith('//'):
            item['url'] = 'https:' + item['url']
            
        # Extraer resumen si está disponible
        content_elem = article.select_one(config['selectors'].get('content', ''))
        if content_elem:
            item['excerpt'] = self.clean_text(content_elem.get_text())
            
        return item
    
    def _extract_tycsports(self, article, config):
        """Extracción específica para TyC Sports"""
        item = self._extract_default(article, config)
        
        # TyC Sports usa URLs absolutas pero a veces incompletas
        if item['url'] and not item['url'].startswith('http'):
            item['url'] = urljoin(config['base_url'], item['url'])
            
        # Las imágenes en TyC suelen estar en data-src
        image_elem = article.select_one(config['selectors']['image'])
        if image_elem and not item['image_url']:
            item['image_url'] = image_elem.get('data-src') or image_elem.get('data-original')
            
        return item

    def clean_text(self, text):
        """Limpia el texto de caracteres no deseados"""
        if not text:
            return ""
            
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\sáéíóúÁÉÍÓÚñÑ.,;:!?¿¡-]', '', text)
        return text.strip()
    
    def generate_seo_title(self, original_title):
        """Genera un título optimizado para SEO"""
        modifiers = [
            "Última hora:", "Lo que debes saber sobre", 
            "Análisis completo de", "Detalles exclusivos:",
            "Impactante noticia sobre", "Todo sobre:", 
            "Lo último de:", "Informe especial:",
            "Reporte exclusivo:", "En profundidad:",
            "Actualización:", "Lo nuevo sobre:"
        ]
        
        prefixes = [
            "Automovilismo:", "Turismo Carretera:", 
            "Fórmula 1:", "Competencias:"
        ]
        
        # Eliminar palabras redundantes
        original = re.sub(r'\b(noticias|informe|reporte|actualización)\b', '', original_title, flags=re.IGNORECASE)
        original = self.clean_text(original)
        
        # Combinar aleatoriamente
        if random.random() > 0.7:
            return f"{random.choice(prefixes)} {random.choice(modifiers)} {original}"
        else:
            return f"{random.choice(modifiers)} {original}"
    
    def create_ai_prompt(self, news_item):
        """Crea el prompt para la IA"""
        return f"""
Eres un periodista especializado en automovilismo con 15 años de experiencia. 
Redacta un artículo profesional de 400-500 palabras basado en:

**Título original**: {news_item['title']}
**Fuente**: {news_item['source']}
**URL**: {news_item['url']}

Instrucciones específicas:
1. Estilo: Periodístico profesional, lenguaje claro y conciso, español rioplatense
2. Estructura obligatoria:
   - Introducción impactante (1 párrafo, 3-4 líneas)
   - Desarrollo con datos técnicos (2-3 párrafos)
   - Contexto histórico o comparativo (1 párrafo)
   - Conclusión con perspectiva profesional (1 párrafo)
3. Formato HTML válido:
   - Usar <h2> para 2 subtítulos relevantes
   - <strong> para datos importantes
   - <em> para énfasis
   - <ul>/<li> para listas cuando sea apropiado
4. SEO:
   - Incluir palabras clave naturales: "automovilismo", "competición", "carreras"
   - Densidad de keywords: 1-2% para términos principales
5. Originalidad:
   - No copiar texto de la fuente
   - Reestructurar completamente la información
   - Añadir valor con análisis propio

Ejemplo de estructura esperada:
<div class="article-content">
<p>Introducción con el dato más relevante...</p>
<h2>Subtítulo sobre aspecto técnico</h2>
<p>Desarrollo con <strong>datos específicos</strong> y contexto...</p>
<h2>Subtítulo sobre implicancias</h2>
<p>Análisis de consecuencias o comparativas históricas...</p>
<p>Conclusión con perspectiva profesional y posible evolución...</p>
<div class="article-footer">
<p>Fuente: <a href="{news_item['url']}" target="_blank" rel="nofollow">{news_item['source']}</a></p>
</div>
</div>
"""

    def generate_with_gemma3(self, prompt):
        """Genera contenido usando Gemma3 via Ollama"""
        logger.info("🧠 Generando contenido con Gemma3...")
        
        try:
            process = subprocess.Popen(
                ['ollama', 'run', 'gemma3'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            output, error = process.communicate(input=prompt, timeout=300)
            
            if process.returncode == 0:
                # Procesar la salida
                content = self.post_process_content(output)
                return content
            else:
                logger.error(f"Error en Gemma3: {error}")
                return None
                
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error("Timeout en generación de contenido")
            return None
        except Exception as e:
            logger.error(f"Error ejecutando Gemma3: {e}")
            return None
    
    def post_process_content(self, raw_content):
        """Limpia y formatea el contenido generado por la IA"""
        # Eliminar comandos y respuestas previas
        content = re.sub(r'^>>>.*?\n', '', raw_content, flags=re.MULTILINE)
        
        # Asegurar estructura HTML válida
        if '<div class="article-content">' not in content:
            content = f'<div class="article-content">\n{content}\n</div>'
            
        # Limpiar etiquetas duplicadas
        content = re.sub(r'(<h[12]>.*?</h[12]>)\s*<h[12]>', r'\1', content)
        
        # Asegurar footer de fuente
        if 'class="article-footer"' not in content:
            content = content.replace('</div>', '<div class="article-footer"></div>\n</div>', 1)
            
        return content.strip()

class AutomatedPublisher:
    def __init__(self):
        self.wp = WordPressConnector()
        self.generator = ContentGenerator()
        self.published_urls = set()
        self.source_rotation = list(NEWS_SOURCES.keys())
        self.current_source_index = 0
        
    def get_next_source(self):
        """Rota entre las fuentes de noticias disponibles"""
        source = self.source_rotation[self.current_source_index]
        self.current_source_index = (self.current_source_index + 1) % len(self.source_rotation)
        return source
        
    def run_cycle(self):
        """Ejecuta un ciclo completo de publicación"""
        source = self.get_next_source()
        logger.info(f"\n=== Iniciando ciclo con fuente: {source.upper()} ===")
        
        # Paso 1: Probar conexión
        if not self.wp.test_connection():
            logger.error("No se puede continuar sin conexión a WordPress")
            return False
            
        # Paso 2: Obtener noticias
        news_items = self.generator.fetch_news(source)
        if not news_items:
            logger.warning("No se encontraron noticias nuevas")
            return False
            
        # Paso 3: Procesar cada noticia
        for news in news_items:
            if news['url'] in self.published_urls:
                logger.info(f"Noticia ya publicada: {news['url']}")
                continue
                
            try:
                # Generar contenido
                seo_title = self.generator.generate_seo_title(news['title'])
                logger.info(f"📝 Procesando: {seo_title}")
                
                prompt = self.generator.create_ai_prompt(news)
                content = self.generator.generate_with_gemma3(prompt)
                
                if not content:
                    logger.warning("No se generó contenido, saltando...")
                    continue
                    
                # Subir imagen si existe
                featured_image = None
                if news.get('image_url'):
                    logger.info("🖼️ Subiendo imagen...")
                    featured_image = self.wp.upload_media(news['image_url'], seo_title)
                
                # Publicar el post
                logger.info("📤 Publicando artículo...")
                if self.wp.create_post(
                    title=seo_title,
                    content=content,
                    featured_media=featured_image
                ):
                    self.published_urls.add(news['url'])
                    logger.info(f"✅ Publicación exitosa: {seo_title}")
                    return True
                    
            except Exception as e:
                logger.error(f"❌ Error procesando noticia: {str(e)}")
                continue
                
        return False

    def run_continuously(self, interval_min=2, max_cycles=None):
        """Ejecuta el publicador de forma continua"""
        cycle_count = 0
        logger.info(f"\n🚀 Iniciando publicación automática. Intervalo: {interval_min} minutos")
        
        try:
            while max_cycles is None or cycle_count < max_cycles:
                start_time = time.time()
                
                success = self.run_cycle()
                cycle_count += 1
                
                elapsed = time.time() - start_time
                sleep_time = max(interval_min * 60 - elapsed, 0)
                
                if success:
                    logger.info(f"🔄 Ciclo exitoso. Esperando {sleep_time:.1f} segundos...")
                else:
                    logger.warning(f"🔄 Ciclo incompleto. Esperando {sleep_time:.1f} segundos...")
                
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Publicador detenido manualmente")
        except Exception as e:
            logger.error(f"\n💥 Error crítico: {str(e)}")

if __name__ == "__main__":
    publisher = AutomatedPublisher()
    publisher.run_continuously(interval_min=2)  # Publicar cada 2 minutos