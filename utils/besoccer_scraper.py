# utils/besoccer_scraper.py
# ==========================================
# BESOCCER SCRAPER - VERSIÓN ORIGINAL CORREGIDA
# Mantiene el código que funcionaba + añade solo lo necesario
# ==========================================

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import json
import time
import os
import re

class BeSoccerScraper:
    """Scraper optimizado con URLs correctas"""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        # Cache optimizado
        self.cache = {}
        self.cache_timeout = 1800  # 30 minutos
        
        # Cache para URLs completas de partidos (lo más importante)
        self.cache_urls_partidos = {}

    def obtener_alineaciones_partido(self, match_id_o_url, equipo_local="", equipo_visitante="", fecha_partido=None):
        """
        Obtiene alineaciones usando las URLs correctas
        CORREGIDO: Acepta fecha_partido para buscar en la fecha correcta
        """
        try:
            print(f"🎯 Procesando partido: {match_id_o_url}")
            
            # Determinar match_id
            if match_id_o_url.startswith('http'):
                match_id = self._extraer_match_id_de_url(match_id_o_url)
                url_partido_oficial = match_id_o_url
            else:
                match_id = match_id_o_url
                url_partido_oficial = None
            
            # Verificar cache de alineaciones
            cache_key = f"alineaciones_{match_id}"
            if self._verificar_cache(cache_key):
                print(f"✅ Usando alineaciones del cache")
                return self.cache[cache_key]['data']
            
            # IMPORTANTE: Necesitamos la URL completa con los slugs de equipos
            if not url_partido_oficial or '/partido/' not in url_partido_oficial:
                print(f"🔍 Buscando URL completa del partido...")
                # AHORA SÍ PASAMOS fecha_partido
                url_partido_oficial = self._buscar_url_completa_partido(match_id, equipo_local, equipo_visitante, fecha_partido)
                
                if not url_partido_oficial:
                    return {
                        'encontrado': False,
                        'error': 'URL completa no encontrada',
                        'alineacion_local': [],
                        'alineacion_visitante': [],
                        'mensaje': 'No se pudo encontrar la URL completa del partido'
                    }
            
            print(f"✅ URL oficial: {url_partido_oficial}")
            
            # Construir URL de alineaciones
            url_alineaciones = self._construir_url_alineaciones(url_partido_oficial)
            print(f"📍 URL alineaciones: {url_alineaciones}")
            
            # Obtener alineaciones
            try:
                response = self.session.get(url_alineaciones, timeout=8)  # Timeout más agresivo
                response.raise_for_status()

                # Verificar que la respuesta tiene contenido útil
                if len(response.content) < 1000:  # HTML muy pequeño = probable error
                    return {
                        'encontrado': False,
                        'error': 'Respuesta HTML muy pequeña',
                        'mensaje': 'La página de alineaciones parece incompleta'
                    }
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extraer con el método que funciona
                alineaciones_info = self._extraer_con_metodo_panel(soup)
                
                if alineaciones_info['encontrado']:
                    self._guardar_cache(cache_key, alineaciones_info)
                
                return alineaciones_info
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Error de conexión: {str(e)}")
                return {
                    'encontrado': False,
                    'error': f'Error de conexión: {str(e)}',
                    'alineacion_local': [],
                    'alineacion_visitante': [],
                    'mensaje': 'No se pudo conectar'
                }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                'encontrado': False,
                'error': str(e),
                'alineacion_local': [],
                'alineacion_visitante': [],
                'mensaje': f'Error: {str(e)}'
            }

    def _buscar_url_completa_partido(self, match_id, equipo_local="", equipo_visitante="", fecha_partido=None):
        """
        Busca la URL completa del partido con los slugs de equipos
        CORREGIDO: Usa la fecha del partido si se proporciona
        """
        # Primero verificar si la tenemos en cache
        if match_id in self.cache_urls_partidos:
            print(f"✅ URL completa encontrada en cache")
            return self.cache_urls_partidos[match_id]
        
        # IMPORTANTE: Si tenemos fecha_partido, buscar SOLO en esa fecha
        if fecha_partido:
            print(f"📅 Buscando en la fecha del partido: {fecha_partido}")
            url = f"https://es.besoccer.com/livescore/{fecha_partido}"
            
            try:
                print(f"  🔍 Buscando en: {url}")
                response = self.session.get(url, timeout=8)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Buscar en tableMatches
                    table_matches = soup.find('div', id='tableMatches')
                    if table_matches:
                        match_links = table_matches.find_all('a', class_='match-link')
                        
                        for link in match_links:
                            href = link.get('href', '')
                            if match_id in href:
                                url_completa = f"https://es.besoccer.com{href}" if href.startswith('/') else href
                                print(f"  ✅ Encontrado: {url_completa}")
                                
                                # Guardar en cache
                                self.cache_urls_partidos[match_id] = url_completa
                                
                                return url_completa
                
            except Exception as e:
                print(f"  ⚠️ Error: {e}")
        
        # Si no se proporcionó fecha o no se encontró, buscar en fechas cercanas
        print("🔍 Buscando en fechas cercanas como fallback...")
        fechas = [
            datetime.now() - timedelta(days=1),
            datetime.now(),
            datetime.now() + timedelta(days=1)
        ]
        
        for fecha in fechas:
            fecha_str = fecha.strftime('%Y-%m-%d')
            url = f"https://es.besoccer.com/livescore/{fecha_str}"
            
            try:
                print(f"  🔍 Buscando en: {url}")
                response = self.session.get(url, timeout=8)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Buscar en tableMatches
                    table_matches = soup.find('div', id='tableMatches')
                    if table_matches:
                        match_links = table_matches.find_all('a', class_='match-link')
                        
                        for link in match_links:
                            href = link.get('href', '')
                            if match_id in href:
                                url_completa = f"https://es.besoccer.com{href}" if href.startswith('/') else href
                                print(f"  ✅ Encontrado: {url_completa}")
                                
                                # Guardar en cache
                                self.cache_urls_partidos[match_id] = url_completa
                                
                                return url_completa
                
                time.sleep(0.2)
                
            except Exception as e:
                print(f"  ⚠️ Error en {url}: {e}")
                continue
        
        return None

    def obtener_partidos_por_fecha(self, fecha_str):
        """
        OPTIMIZADO: Va directo a la URL de livescore sin duplicar búsquedas
        """
        try:
            print(f"🎯 Obteniendo partidos para {fecha_str}...")
            
            # Verificar cache
            cache_key = f"partidos_{fecha_str}"
            if self._verificar_cache(cache_key):
                print("✅ Usando partidos del cache")
                return self.cache[cache_key]['data']
            
            # URL DIRECTA - sin búsquedas duplicadas
            url = f"https://es.besoccer.com/livescore/{fecha_str}"
            print(f"📍 URL directa: {url}")
            
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                partidos = []
                
                # Buscar en tableMatches
                table_matches = soup.find('div', id='tableMatches')
                if table_matches:
                    match_links = table_matches.find_all('a', class_='match-link match-home')
                    
                    for link in match_links:
                        partido = self._extraer_partido_con_url_completa(link)
                        if partido:
                            partidos.append(partido)
                
                # Formatear partidos
                partidos_formateados = []
                for p in partidos:
                    partido_formateado = {
                        'id': f"livescore_{p['match_id']}",
                        'fecha': fecha_str,
                        'hora': p.get('hora', 'TBD'),
                        'equipo_local': p['equipo_local'],
                        'equipo_visitante': p['equipo_visitante'],
                        'liga': 'Partidos del día',
                        'competicion': 'Livescore',
                        'estado': p.get('estado', 'programado'),
                        'estadio': '',
                        'escudo_local': p.get('escudo_local', ''),
                        'escudo_visitante': p.get('escudo_visitante', ''),
                        'besoccer_id': p['match_id'],
                        'url_partido': p.get('url_partido', ''),
                        'url_completa': p.get('url_completa', ''),  # IMPORTANTE: Guardar URL completa
                        'resultado_local': p.get('resultado_local'),
                        'resultado_visitante': p.get('resultado_visitante'),
                        'alineacion_local': [],
                        'alineacion_visitante': []
                    }
                    
                    # Guardar URL completa en cache
                    if p.get('url_completa') and p['match_id']:
                        self.cache_urls_partidos[p['match_id']] = p['url_completa']
                    
                    partidos_formateados.append(partido_formateado)
                
                if partidos_formateados:
                    self._guardar_cache(cache_key, partidos_formateados)
                
                print(f"✅ {len(partidos_formateados)} partidos encontrados")
                return partidos_formateados
                
            except Exception as e:
                print(f"❌ Error obteniendo partidos: {e}")
                return []
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return []

    def _extraer_partido_con_url_completa(self, link):
        """
        Extrae partido guardando la URL completa con slugs
        """
        try:
            href = link.get('href', '')
            if not href:
                return None
            
            # IMPORTANTE: Guardar el href completo
            url_completa = f"https://es.besoccer.com{href}" if href.startswith('/') else href
            
            # Extraer match_id del href
            match_id = None
            partes = href.split('/')
            for parte in partes:
                if parte.isdigit() and len(parte) >= 8:
                    match_id = parte
                    break
            
            if not match_id:
                return None
            
            # Buscar equipos
            team_box = link.find('div', class_='team-box')
            if not team_box:
                return None
            
            team_names = team_box.find_all('div', class_='team-name')
            if len(team_names) < 2:
                return None
            
            equipo_local = team_names[0].get_text().strip()
            equipo_visitante = team_names[1].get_text().strip()
            
            # Hora/Resultado
            marker = team_box.find('div', class_='marker')
            hora = "TBD"
            estado = "programado"
            resultado_local = None
            resultado_visitante = None
            
            if marker:
                hora_elem = marker.find('p', class_='match_hour')
                if hora_elem:
                    hora = hora_elem.get_text().strip()
                else:
                    # Buscar resultado
                    resultado_elem = marker.find('span')
                    if resultado_elem:
                        resultado_text = resultado_elem.get_text().strip()
                        match = re.search(r'(\d+)-(\d+)', resultado_text)
                        if match:
                            resultado_local = int(match.group(1))
                            resultado_visitante = int(match.group(2))
                            hora = "FIN"
                            estado = "finalizado"
            
            # Escudos
            escudos = team_box.find_all('img', class_='team-shield')
            escudo_local = escudos[0].get('src', '') if len(escudos) > 0 else ''
            escudo_visitante = escudos[1].get('src', '') if len(escudos) > 1 else ''
            
            return {
                'match_id': match_id,
                'equipo_local': equipo_local,
                'equipo_visitante': equipo_visitante,
                'hora': hora,
                'estado': estado,
                'escudo_local': escudo_local,
                'escudo_visitante': escudo_visitante,
                'resultado_local': resultado_local,
                'resultado_visitante': resultado_visitante,
                'url_partido': url_completa,
                'url_completa': url_completa  # IMPORTANTE: Guardar URL completa
            }
            
        except Exception as e:
            return None

    def _extraer_con_metodo_panel(self, soup):
        """
        Extrae usando el método panel que sabemos que funciona
        """
        print("🎯 Extrayendo alineaciones...")
        
        # Buscar los panels
        panel_lineup = soup.find('div', class_='panel panel-lineup')
        panel_bench = soup.find('div', class_='panel panel-bench')
        
        if not panel_lineup:
            return {
                'encontrado': False,
                'mensaje': 'Alineaciones no disponibles'
            }
        
        alineacion_local = []
        alineacion_visitante = []
        
        # Procesar titulares
        player_wrappers = panel_lineup.find_all('div', class_='player-wrapper')
        print(f"  📊 Titulares encontrados: {len(player_wrappers)}")
        
        for wrapper in player_wrappers:
            jugador = self._extraer_jugador_rapido(wrapper, es_titular=True)
            if jugador:
                equipo = jugador.get('equipo', 'desconocido')
                if equipo == 'local':
                    alineacion_local.append(jugador)
                elif equipo == 'visitante':
                    alineacion_visitante.append(jugador)
                else:
                    if len(alineacion_local) <= len(alineacion_visitante):
                        alineacion_local.append(jugador)
                    else:
                        alineacion_visitante.append(jugador)
        
        # Procesar suplentes
        if panel_bench:
            suplentes_links = panel_bench.find_all('a', class_='col-bench')
            print(f"  📊 Suplentes encontrados: {len(suplentes_links)}")
            
            for link in suplentes_links:
                jugador = self._extraer_suplente_rapido(link)
                if jugador:
                    equipo = jugador.get('equipo', 'desconocido')
                    if equipo == 'local':
                        alineacion_local.append(jugador)
                    elif equipo == 'visitante':
                        alineacion_visitante.append(jugador)
                    else:
                        suplentes_local = len([j for j in alineacion_local if not j['es_titular']])
                        suplentes_visitante = len([j for j in alineacion_visitante if not j['es_titular']])
                        if suplentes_local <= suplentes_visitante:
                            alineacion_local.append(jugador)
                        else:
                            alineacion_visitante.append(jugador)
        
        # Validar
        if len(alineacion_local) >= 11 and len(alineacion_visitante) >= 11:
            return {
                'encontrado': True,
                'metodo': 'panel_lineup_bench',
                'alineacion_local': alineacion_local,
                'alineacion_visitante': alineacion_visitante,
                'mensaje': f'Alineaciones: {len(alineacion_local)} vs {len(alineacion_visitante)}'
            }
        else:
            return {
                'encontrado': False,
                'mensaje': f'Alineaciones incompletas: {len(alineacion_local)} vs {len(alineacion_visitante)}'
            }

    def _extraer_jugador_rapido(self, wrapper, es_titular=True):
        """Extracción rápida de jugador"""
        try:
            nombre = ""
            posicion = "N/A"
            imagen_url = ""
            url_besoccer = ""
            equipo = self._determinar_equipo(wrapper)
            
            # Primero intentar encontrar el enlace del jugador
            link_jugador = wrapper.find('a', attrs={'data-cy': 'fieldPlayer'})
            if not link_jugador:
                link_jugador = wrapper.find('a')  # Fallback a cualquier enlace
            
            # Extraer URL del href si existe
            if link_jugador and link_jugador.get('href'):
                href = link_jugador.get('href')
                if '/jugador/' in href:
                    url_besoccer = f"https://es.besoccer.com{href}" if href.startswith('/') else href
                    print(f"✅ URL extraída del href: {url_besoccer}")
            
            # JSON-LD para otros datos
            json_script = wrapper.find('script', type='application/ld+json')
            if json_script:
                try:
                    data = json.loads(json_script.get_text())
                    if data.get('@type') == 'Person':
                        nombre = self._limpiar_texto(data.get('name', ''))
                        posicion = self._mapear_posicion(data.get('jobtitle', 'N/A'))
                        imagen_url = data.get('image', '')
                        # Si encontramos URL en JSON-LD, úsala (tiene prioridad)
                        if data.get('url'):
                            url_besoccer = data.get('url')
                            print(f"✅ URL del JSON-LD: {url_besoccer}")
                except Exception as e:
                    print(f"❌ Error parseando JSON-LD: {e}")
            
            # Si no hay nombre del JSON-LD, buscar en el link
            if not nombre and link_jugador:
                name_div = link_jugador.find('div', class_='name name-lineups')
                if name_div:
                    nombre = self._limpiar_texto(name_div.get_text())
                else:
                    nombre = self._limpiar_texto(link_jugador.get_text())
            
            if not nombre:
                return None
            
            # Si no encontramos posición en JSON, intentar extraerla
            if posicion == "N/A":
                posicion = self._extraer_posicion(wrapper)
            
            return {
                'nombre': nombre,
                'numero': self._extraer_numero(wrapper),
                'posicion': posicion,
                'es_titular': es_titular,
                'imagen_url': imagen_url,
                'url_besoccer': url_besoccer,
                'equipo': equipo
            }
        except Exception as e:
            print(f"Error extrayendo jugador: {e}")
            return None

    def _extraer_suplente_rapido(self, link):
        """Extracción rápida de suplente"""
        try:
            # Determinar equipo
            clases = link.get('class', [])
            equipo = 'local' if 'local' in clases else 'visitante' if 'visitor' in clases else 'desconocido'
            
            nombre = ""
            posicion = "N/A"
            imagen_url = ""
            url_besoccer = ""
            
            # Extraer URL del href del enlace
            href = link.get('href', '')
            if href and '/jugador/' in href:
                url_besoccer = f"https://es.besoccer.com{href}" if href.startswith('/') else href
                print(f"✅ URL de suplente extraída del href: {url_besoccer}")
            
            # JSON-LD
            json_script = link.find('script', type='application/ld+json')
            if json_script:
                try:
                    data = json.loads(json_script.get_text())
                    if data.get('@type') == 'Person':
                        nombre = self._limpiar_texto(data.get('name', ''))
                        jobtitle = data.get('jobtitle', '')
                        if jobtitle:
                            posicion = self._mapear_posicion(jobtitle)
                        imagen_url = data.get('image', '')
                        # Si hay URL en JSON-LD, tiene prioridad
                        if data.get('url'):
                            url_besoccer = data.get('url')
                except:
                    pass
            
            # Si no hay nombre, buscar en p.name
            if not nombre:
                name_elem = link.find('p', class_='name')
                if name_elem:
                    nombre = self._limpiar_texto(name_elem.get_text())
            
            # Si no hay posición del JSON, buscar en role-box
            if posicion == "N/A":
                posicion = self._extraer_posicion(link)
            
            if not nombre:
                return None
            
            return {
                'nombre': nombre,
                'numero': self._extraer_numero(link),
                'posicion': posicion,
                'es_titular': False,
                'imagen_url': imagen_url,
                'url_besoccer': url_besoccer,
                'equipo': equipo
            }
        except Exception as e:
            print(f"Error extrayendo suplente: {e}")
            return None

    # ==========================================
    # MÉTODOS AUXILIARES - VERSIÓN ORIGINAL QUE FUNCIONABA
    # ==========================================
    
    def _limpiar_texto(self, texto):
        """Limpia texto"""
        if not texto:
            return ""
        texto_str = str(texto)
        texto_limpio = re.sub(r'<[^>]+>', '', texto_str)
        texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
        return texto_limpio
    
    def _extraer_numero(self, elem):
        """Extrae número - VERSIÓN CORREGIDA PARA HTML REAL"""
        # Para titulares: buscar en div.name.num-lineups > span.bold
        num_div = elem.find('div', class_='name num-lineups')
        if num_div:
            span_bold = num_div.find('span', class_='bold')
            if span_bold:
                texto = span_bold.get_text().strip()
                if texto.isdigit():
                    return texto
        
        # Para suplentes: buscar en span.number.bold
        numero_elem = elem.find('span', class_='number bold')
        if numero_elem:
            texto = numero_elem.get_text().strip()
            if texto.isdigit():
                return texto
        
        # Fallback: cualquier span.bold con número
        spans_bold = elem.find_all('span', class_='bold')
        for span in spans_bold:
            texto = span.get_text().strip()
            if texto.isdigit():
                return texto
        
        return "?"
    
    def _extraer_posicion(self, elem):
        """Extrae posición - VERSIÓN CORREGIDA"""
        # Primero intentar desde JSON-LD
        json_script = elem.find('script', type='application/ld+json')
        if json_script:
            try:
                data = json.loads(json_script.get_text())
                if data.get('jobtitle'):
                    return self._mapear_posicion(data['jobtitle'])
            except:
                pass
        
        # Para suplentes: buscar en role-box
        role_box = elem.find('div', class_='role-box')
        if role_box:
            t_up = role_box.find('span', class_='t-up')
            if t_up:
                # Obtener texto y filtrar el número
                texto_completo = t_up.get_text().strip()
                # Separar palabras y buscar la posición (no números)
                palabras = texto_completo.split()
                for palabra in palabras:
                    if not palabra.isdigit() and len(palabra) <= 10:
                        pos = self._mapear_posicion(palabra)
                        if pos != "N/A":
                            return pos
        
        return "N/A"
    
    def _extraer_imagen(self, elem):
        """Extrae imagen"""
        img = elem.find('img')
        if img:
            src = img.get('src', '')
            if src:
                if src.startswith('/'):
                    return f"https://es.besoccer.com{src}"
                return src
        return ""
    
    def _determinar_equipo(self, elem):
        """Determina equipo"""
        current = elem
        for _ in range(5):
            if current.parent:
                current = current.parent
                clases = current.get('class', [])
                if 'local' in clases:
                    return 'local'
                if 'visitor' in clases or 'visitante' in clases:
                    return 'visitante'
        return 'desconocido'
    
    def _mapear_posicion(self, texto):
        """Mapea posiciones - VERSIÓN ORIGINAL QUE FUNCIONABA"""
        if not texto:
            return "N/A"
        
        texto = texto.lower().strip()
        
        mapeo = {
            'por': 'Portero', 'portero': 'Portero', 'gk': 'Portero',
            'def': 'Defensa', 'defensa': 'Defensa', 'cb': 'Defensa', 'lb': 'Defensa', 'rb': 'Defensa',
            'med': 'Medio', 'medio': 'Medio', 'cm': 'Medio', 'dm': 'Medio', 'am': 'Medio',
            'del': 'Delantero', 'delantero': 'Delantero', 'fw': 'Delantero', 'st': 'Delantero'
        }
        
        return mapeo.get(texto, texto.title() if len(texto) <= 10 else "N/A")
    
    def _construir_url_alineaciones(self, url_oficial):
        """Construye URL de alineaciones correctamente"""
        if url_oficial.endswith('/alineaciones'):
            return url_oficial
        
        # La URL oficial ya debe tener el formato correcto con slugs
        url_limpia = url_oficial.split('#')[0].split('?')[0]
        return f"{url_limpia}/alineaciones" if not url_limpia.endswith('/') else f"{url_limpia}alineaciones"
    
    def _verificar_cache(self, cache_key):
        """Verifica cache"""
        if cache_key not in self.cache:
            return False
        if time.time() - self.cache[cache_key]['timestamp'] > self.cache_timeout:
            del self.cache[cache_key]
            return False
        return True
    
    def _guardar_cache(self, cache_key, data):
        """Guarda en cache"""
        self.cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def _extraer_match_id_de_url(self, url):
        """MÉTODO AÑADIDO: Extrae el match_id de una URL completa"""
        try:
            # Buscar un número de 8 o más dígitos en la URL
            partes = url.split('/')
            for parte in partes:
                if parte.isdigit() and len(parte) >= 8:
                    return parte
            return None
        except:
            return None
    
    def limpiar_cache(self):
        """Limpia cache"""
        self.cache = {}
        self.cache_urls_partidos = {}
        print("🗑️ Cache limpiado")

    def obtener_datos_perfil_jugador(self, url_perfil):
        """
        Obtiene datos adicionales del perfil de un jugador en BeSoccer
        
        Args:
            url_perfil: URL del perfil del jugador (ej: https://es.besoccer.com/jugador/s-miettinen-3161334)
        
        Returns:
            dict con los datos del jugador o None si hay error
        """
        try:
            print(f"🔍 Obteniendo datos del perfil: {url_perfil}")
            
            # Verificar cache
            cache_key = f"perfil_{url_perfil}"
            if self._verificar_cache(cache_key):
                print(f"✅ Usando perfil del cache")
                return self.cache[cache_key]['data']
            
            response = self.session.get(url_perfil, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            datos_jugador = {
                'nombre_completo': None,
                'edad': None,
                'altura': None,
                'peso': None,
                'nacionalidad': None,
                'valor_mercado': None,
                'elo': None,
                'dorsal': None,
                'posicion_principal': None,
                'posicion_secundaria': None,
                'equipo_actual': None,
                'escudo_equipo': None,
                'liga_actual': None,
                'pais_nacimiento': None,
                'pie_preferido': None,
                'fuente': 'BeSoccer'
            }
            
            # Buscar en el panel principal con clase "panel"
            panel_principal = soup.find('div', class_='panel')
            if panel_principal:
                panel_head = panel_principal.find('div', class_='panel-head')
                if panel_head:
                    # Nombre mostrado (apodo)
                    panel_title = panel_head.find('h2', class_='panel-title')
                    if panel_title:
                        datos_jugador['nombre_mostrado'] = panel_title.get_text(strip=True)
                        print(f"   - nombre_mostrado: {datos_jugador['nombre_mostrado']}")
                    
                    # Nombre completo real
                    panel_subtitle = panel_head.find('div', class_='panel-subtitle')
                    if panel_subtitle:
                        nombre_completo = panel_subtitle.get_text(strip=True)
                        if nombre_completo:
                            datos_jugador['nombre_completo'] = nombre_completo
                            print(f"   - nombre_completo: {datos_jugador['nombre_completo']}")

            # 1. Buscar panel con estadísticas (edad, altura, peso, valor, ELO)
            stat_list = soup.find('div', class_='panel-body stat-list jc-sa ph5')
            if stat_list:
                stats = stat_list.find_all('div', class_='stat')
                
                for stat in stats:
                    big_row = stat.find('div', class_='big-row')
                    small_rows = stat.find_all('div', class_='small-row')
                    
                    if big_row and small_rows:
                        valor = big_row.get_text().strip()
                        for small_row in small_rows:
                            texto = small_row.get_text().strip().lower()
                            
                            if 'años' in texto:
                                datos_jugador['edad'] = int(valor) if valor.isdigit() else valor
                            elif 'kgs' in texto:
                                datos_jugador['peso'] = int(valor) if valor.isdigit() else valor
                            elif 'cms' in texto:
                                datos_jugador['altura'] = int(valor) if valor.isdigit() else valor
                            elif 'm.€' in texto or 'k€' in texto:
                                datos_jugador['valor_mercado'] = valor + (' M€' if 'm.€' in texto else ' K€')
                            elif 'elo' in texto:
                                round_row = stat.find('div', class_='round-row')
                                if round_row:
                                    span = round_row.find('span')
                                    if span and span.get_text().strip().isdigit():
                                        datos_jugador['elo'] = int(span.get_text().strip())

                    # Nacionalidad (bandera principal)
                    img_flag = stat.find('img', attrs={'alt': True})
                    if img_flag and not datos_jugador['nacionalidad']:
                        datos_jugador['nacionalidad'] = img_flag.get('alt', '')
                    
                    # Dorsal
                    dorsal_div = stat.find('div', class_='round-row mb5 black')
                    if dorsal_div:
                        span = dorsal_div.find('span')
                        if span and span.get_text().strip().isdigit():
                            datos_jugador['dorsal'] = int(span.get_text().strip())
            
            # 2. Buscar posiciones específicas del jugador
            panel_positions = soup.find('div', class_='panel role-positions')
            if panel_positions:
                role_box = panel_positions.find('div', class_='role-box')
                if role_box:
                    # Posición principal
                    main_role = role_box.find('div', class_='main-role')
                    if main_role:
                        spans = main_role.find_all('span')
                        if len(spans) >= 2:
                            datos_jugador['posicion_principal'] = spans[0].get_text().strip()
                    # Posiciones secundarias (tomar la primera si existe)
                    position_list = role_box.find('ul', class_='position-list')
                    if position_list:
                        first_li = position_list.find('li')
                        if first_li:
                            spans = first_li.find_all('span')
                            if len(spans) >= 1:
                                datos_jugador['posicion_secundaria'] = spans[0].get_text().strip()
            
            # 3. Buscar datos de carrera (equipo actual, liga)
            carrera_head = soup.find('div', class_='table-head', string=lambda s: s and "Datos de su Carrera" in s)
            if carrera_head:
                carrera_body = carrera_head.find_next('div', class_='table-body')
                if carrera_body:
                    # Equipo actual
                    equipo_row = carrera_body.find('a', attrs={'data-cy': 'currentTeam'})
                    if equipo_row:
                        datos_jugador['equipo_actual'] = equipo_row.get_text(strip=True)
                        img_tag = equipo_row.find('img')
                        if img_tag:
                            datos_jugador['escudo_equipo'] = img_tag.get('src', '')

                    # Competición actual
                    liga_row = carrera_body.find('a', attrs={'data-cy': 'currentCompetition'})
                    if liga_row:
                        datos_jugador['liga_actual'] = liga_row.get_text(strip=True)

            # 4. Datos personales (país nacimiento, pie preferido)
            personal_head = soup.find('div', class_='table-head', string=lambda s: s and "Datos personales" in s)
            if personal_head:
                personal_body = personal_head.find_next('div', class_='table-body')
                if personal_body:
                    # País nacimiento
                    nacimiento_row = personal_body.find('a', attrs={'data-cy': 'birthplace'})
                    if nacimiento_row:
                        datos_jugador['pais_nacimiento'] = nacimiento_row.get_text(strip=True)
                    
                    # Pie preferido
                    pie_row = personal_body.find('div', string=lambda s: s and "Pie preferido" in s)
                    if pie_row and pie_row.find_next('div'):
                        datos_jugador['pie_preferido'] = pie_row.find_next('div').get_text(strip=True)

            # Guardar en cache
            self._guardar_cache(cache_key, datos_jugador)
            
            print("✅ Datos obtenidos de BeSoccer:")
            for key, value in datos_jugador.items():
                if value:
                    print(f"   - {key}: {value}")
            
            return datos_jugador
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de conexión con BeSoccer: {e}")
            return None
        except Exception as e:
            print(f"❌ Error obteniendo datos del perfil: {e}")
            import traceback
            traceback.print_exc()
            return None

# ==========================================
# CLASE AUXILIAR PARA LIVESCORE - SIMPLIFICADA
# ==========================================

class BeSoccerAlineacionesScraper:
    """Scraper para búsqueda en livescore - SIMPLIFICADO"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        self.cache = {}
        self.cache_timeout = 900

    def buscar_partidos_en_fecha(self, fecha_str):
        """SIMPLIFICADO: Solo busca en la URL directa"""
        try:
            print(f"🌐 Buscando partidos para {fecha_str}...")
            
            # Verificar cache
            cache_key = f"livescore_{fecha_str}"
            if self._verificar_cache(cache_key):
                print(f"✅ Usando datos del cache")
                return self.cache[cache_key]['data']
            
            # URL DIRECTA - sin duplicación
            url = f"https://es.besoccer.com/livescore/{fecha_str}"
            print(f"📍 URL: {url}")
            
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                partidos = []
                
                # Buscar en tableMatches
                table_matches = soup.find('div', id='tableMatches')
                if table_matches:
                    match_links = table_matches.find_all('a', class_='match-link match-home')
                    
                    for link in match_links:
                        partido = self._extraer_partido_con_url(link)
                        if partido:
                            partidos.append(partido)
                
                if partidos:
                    self._guardar_cache(cache_key, partidos)
                
                print(f"✅ {len(partidos)} partidos encontrados")
                return partidos
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return []
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return []

    def _extraer_partido_con_url(self, link):
        """Extrae partido guardando URL completa"""
        try:
            href = link.get('href', '')
            if not href:
                return None
            
            # URL completa
            url_completa = f"https://es.besoccer.com{href}" if href.startswith('/') else href
            
            # Match ID
            match_id = None
            partes = href.split('/')
            for parte in partes:
                if parte.isdigit() and len(parte) >= 8:
                    match_id = parte
                    break
            
            if not match_id:
                return None
            
            # Equipos
            team_box = link.find('div', class_='team-box')
            if not team_box:
                return None
            
            team_names = team_box.find_all('div', class_='team-name')
            if len(team_names) < 2:
                return None
            
            equipo_local = team_names[0].get_text().strip()
            equipo_visitante = team_names[1].get_text().strip()
            
            # Hora/Estado
            marker = team_box.find('div', class_='marker')
            hora = "TBD"
            estado = "programado"
            resultado_local = None
            resultado_visitante = None
            
            if marker:
                hora_elem = marker.find('p', class_='match_hour')
                if hora_elem:
                    hora = hora_elem.get_text().strip()
                else:
                    resultado_elem = marker.find('span')
                    if resultado_elem:
                        resultado_text = resultado_elem.get_text().strip()
                        match = re.search(r'(\d+)-(\d+)', resultado_text)
                        if match:
                            resultado_local = int(match.group(1))
                            resultado_visitante = int(match.group(2))
                            hora = "FIN"
                            estado = "finalizado"
            
            # Escudos
            escudos = team_box.find_all('img', class_='team-shield')
            escudo_local = escudos[0].get('src', '') if len(escudos) > 0 else ''
            escudo_visitante = escudos[1].get('src', '') if len(escudos) > 1 else ''
            
            return {
                'match_id': match_id,
                'equipo_local': equipo_local,
                'equipo_visitante': equipo_visitante,
                'hora': hora,
                'estado': estado,
                'escudo_local': escudo_local,
                'escudo_visitante': escudo_visitante,
                'resultado_local': resultado_local,
                'resultado_visitante': resultado_visitante,
                'url_partido': url_completa,
                'url_completa': url_completa,  # IMPORTANTE
                'fuente': 'livescore'
            }
            
        except Exception as e:
            return None

    def _verificar_cache(self, cache_key):
        """Verifica cache"""
        if cache_key not in self.cache:
            return False
        if time.time() - self.cache[cache_key]['timestamp'] > self.cache_timeout:
            del self.cache[cache_key]
            return False
        return True

    def _guardar_cache(self, cache_key, data):
        """Guarda en cache"""
        self.cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }


# ==========================================
# FUNCIONES HELPER
# ==========================================

def obtener_partidos_besoccer(fecha_str):
    """Helper para obtener partidos"""
    try:
        scraper = BeSoccerScraper()
        return scraper.obtener_partidos_por_fecha(fecha_str)
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def obtener_alineaciones_besoccer(besoccer_id, equipo_local="", equipo_visitante="", fecha_partido=None):
    """Helper para obtener alineaciones - CORREGIDO con fecha opcional"""
    try:
        print(f"🔍 Buscando alineaciones para: {besoccer_id}")
        if fecha_partido:
            print(f"📅 Fecha del partido: {fecha_partido}")
        scraper = BeSoccerScraper()
        return scraper.obtener_alineaciones_partido(besoccer_id, equipo_local, equipo_visitante, fecha_partido)
    except Exception as e:
        print(f"❌ Error: {e}")
        return {
            'encontrado': False,
            'error': str(e),
            'alineacion_local': [],
            'alineacion_visitante': [],
            'mensaje': 'Error al obtener alineaciones'
        }


