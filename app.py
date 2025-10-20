from flask import Flask, request, jsonify, send_from_directory
import os, re, random, requests
from collections import deque, defaultdict
from urllib.parse import quote
from datetime import datetime
import time
import hashlib
import logging
import math
from typing import Dict, List, Optional, Tuple, Any

# Logging ayarı
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================
# ÇEVRESEL DEĞİŞKENLER - GÜVENLİ
# =============================

# Environment variables'dan API key'leri al
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY', '6a7a443921825622e552d0cde2d2b688')
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '94ac5f3a6ea34ed0918d28958c7e7aa6')
GOOGLE_SEARCH_KEY = os.environ.get('GOOGLE_SEARCH_KEY', 'AIzaSyCphCUBFyb0bBVMVG5JupVOjKzoQq33G-c')
GOOGLE_CX = os.environ.get('GOOGLE_CX', 'd15c352df36b9419f')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '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')

# =============================
# GLOBAL DEĞİŞKENLER
# =============================

conversation_history = defaultdict(lambda: deque(maxlen=20))
user_states = defaultdict(lambda: {'waiting_for_city': False})

# Türk şehirleri
TURKISH_CITIES = [
    "adana", "adiyaman", "afyon", "afyonkarahisar", "agri", "aksaray", "amasya", "ankara", "antalya",
    "ardahan", "artvin", "aydin", "balikesir", "bartin", "batman", "bayburt", "bilecik", "bingol",
    "bitlis", "bolu", "burdur", "bursa", "canakkale", "cankiri", "corum", "denizli", "diyarbakir",
    "duzce", "edirne", "elazig", "erzincan", "erzurum", "eskisehir", "gaziantep", "giresun",
    "gumushane", "hakkari", "hatay", "igdir", "isparta", "istanbul", "izmir", "kahramanmaras",
    "karabuk", "karaman", "kars", "kastamonu", "kayseri", "kilis", "kirikkale", "kirklareli",
    "kirsehir", "kocaeli", "konya", "kutahya", "malatya", "manisa", "mardin", "mersin", "mugla",
    "mus", "nevsehir", "nigde", "ordu", "osmaniye", "rize", "sakarya", "samsun", "sanliurfa",
    "siirt", "sinop", "sivas", "sirnak", "tekirdag", "tokat", "trabzon", "tunceli", "usak",
    "van", "yalova", "yozgat", "zonguldak"
]

# Türkçe karakter normalizasyonu
TURKISH_CHAR_MAP = {
    'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
    'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
}

# =============================
# SÜPER GELİŞMİŞ MATEMATİK MOTORU - TAM FİKS
# =============================

class SuperMathEngine:
    def __init__(self):
        self.number_words = {
            "sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5,
            "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
            "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60,
            "yetmiş": 70, "seksen": 80, "doksan": 90,
            "yüz": 100, "bin": 1000, "milyon": 1000000
        }
        
        self.operation_words = {
            "artı": "+", "eksi": "-", "çarpı": "*", "bölü": "/", "x": "*", "kere": "*",
            "üzeri": "**", "karekök": "sqrt", "kare": "**2", "küp": "**3"
        }
        
        self.math_constants = {
            "pi": str(math.pi), "π": str(math.pi),
            "e": str(math.e)
        }
        
        self.trig_functions = {
            "sin": math.sin, "cos": math.cos, "tan": math.tan, "cot": lambda x: 1/math.tan(x),
            "arcsin": math.asin, "arccos": math.acos, "arctan": math.atan
        }

    def parse_turkish_number(self, text: str) -> Optional[float]:
        """Türkçe yazılı sayıları sayıya çevirir"""
        words = text.lower().split()
        total = 0
        current = 0
        
        for word in words:
            if word in self.number_words:
                value = self.number_words[word]
                if value >= 100:
                    if current == 0:
                        current = 1
                    current *= value
                    if value >= 1000:
                        total += current
                        current = 0
                else:
                    current += value
            else:
                # Sayı değilse parsing'i durdur
                break
        
        return total + current if current > 0 else None

    def extract_numbers_from_text(self, text: str) -> List[float]:
        """Metinden sayıları çıkarır"""
        numbers = []
        # Ondalıklı sayıları ve tam sayıları bul
        matches = re.findall(r'\d+\.?\d*', text)
        for match in matches:
            try:
                numbers.append(float(match))
            except ValueError:
                continue
        return numbers

    def solve_advanced_math(self, expression: str) -> Optional[str]:
        """Gelişmiş matematik problemlerini çözer"""
        expr_lower = expression.lower().replace(' ', '')
        numbers = self.extract_numbers_from_text(expression)
        
        # Trigonometri fonksiyonları
        trig_patterns = [
            (r'sin\(?(\d+)\)?', lambda x: math.sin(math.radians(float(x)))),
            (r'cos\(?(\d+)\)?', lambda x: math.cos(math.radians(float(x)))),
            (r'tan\(?(\d+)\)?', lambda x: math.tan(math.radians(float(x)))),
            (r'cot\(?(\d+)\)?', lambda x: 1/math.tan(math.radians(float(x)))),
        ]
        
        for pattern, func in trig_patterns:
            match = re.search(pattern, expr_lower)
            if match:
                try:
                    value = float(match.group(1))
                    result = func(value)
                    return f"🧮 {expression} = {result:.4f}"
                except:
                    pass

        # Üs alma işlemleri
        if 'üzeri' in expression.lower() or '**' in expression or '^' in expression:
            if numbers and len(numbers) >= 2:
                base = numbers[0]
                exponent = numbers[1]
                result = base ** exponent
                return f"🧮 {base} üzeri {exponent} = {result}"

        # Karekök işlemleri
        if 'karekök' in expression.lower() or 'sqrt' in expression.lower():
            if numbers:
                result = math.sqrt(numbers[0])
                return f"🧮 √{numbers[0]} = {result:.4f}"

        # Hipotenüs hesaplama
        if 'hipotenüs' in expression.lower() or 'hipotenus' in expression.lower():
            if len(numbers) >= 2:
                a, b = numbers[:2]
                hipo = math.sqrt(a**2 + b**2)
                return f"🧮 {a} ve {b} kenarlı üçgenin hipotenüsü = {hipo:.2f}"

        # Alan hesaplamaları
        if 'alan' in expression.lower():
            if numbers:
                if 'kare' in expression.lower():
                    a = numbers[0]
                    return f"🧮 Kenarı {a} olan karenin alanı = {a**2}"
                elif 'dikdörtgen' in expression.lower() and len(numbers) >= 2:
                    a, b = numbers[:2]
                    return f"🧮 {a} x {b} dikdörtgenin alanı = {a*b}"
                elif 'daire' in expression.lower() or 'çember' in expression.lower():
                    r = numbers[0]
                    return f"🧮 Yarıçapı {r} olan dairenin alanı = {math.pi * r**2:.2f}"
                elif 'üçgen' in expression.lower() and len(numbers) >= 2:
                    a, h = numbers[:2]
                    return f"🧮 Tabanı {a} ve yüksekliği {h} olan üçgenin alanı = {0.5 * a * h}"

        # Hacim hesaplamaları
        if 'hacim' in expression.lower():
            if numbers:
                if 'küp' in expression.lower():
                    a = numbers[0]
                    return f"🧮 Kenarı {a} olan küpün hacmi = {a**3}"
                elif 'küre' in expression.lower():
                    r = numbers[0]
                    return f"🧮 Yarıçapı {r} olan kürenin hacmi = {(4/3) * math.pi * r**3:.2f}"
                elif 'silindir' in expression.lower() and len(numbers) >= 2:
                    r, h = numbers[:2]
                    return f"🧮 Yarıçapı {r} ve yüksekliği {h} olan silindirin hacmi = {math.pi * r**2 * h:.2f}"

        # Matematik sabitleri
        if 'pi' in expression.lower() or 'π' in expression:
            return f"🧮 π (pi) sayısı = {math.pi:.10f}..."

        return None

    def calculate_expression(self, expression: str) -> Optional[float]:
        """Matematik ifadesini güvenli şekilde hesaplar"""
        try:
            # Güvenlik kontrolü - sadece matematiksel karakterlere izin ver
            allowed_chars = set('0123456789+-*/.() ')
            if all(c in allowed_chars for c in expression.replace(' ', '')):
                # Basit işlemler için eval
                result = eval(expression, {"__builtins__": {}}, {})
                return float(result) if isinstance(result, (int, float)) else None
        except:
            pass
        return None

    def calculate(self, text: str) -> Optional[str]:
        """Ana matematik hesaplama fonksiyonu"""
        # Önce gelişmiş matematik problemlerini çöz
        advanced_result = self.solve_advanced_math(text)
        if advanced_result:
            return advanced_result

        # Basit matematik ifadelerini işle
        text_lower = text.lower()
        
        # Matematiksel ifadeleri kontrol et (3+5, 10-2, vb.)
        simple_math_pattern = r'(\d+\.?\d*)\s*([+\-*/])\s*(\d+\.?\d*)'
        match = re.search(simple_math_pattern, text)
        if match:
            try:
                num1 = float(match.group(1))
                operator = match.group(2)
                num2 = float(match.group(3))
                
                if operator == '+':
                    result = num1 + num2
                elif operator == '-':
                    result = num1 - num2
                elif operator == '*':
                    result = num1 * num2
                elif operator == '/':
                    if num2 != 0:
                        result = num1 / num2
                    else:
                        return "❌ Sıfıra bölme hatası!"
                
                return f"🧮 {text} = {result}"
            except:
                pass

        # Türkçe matematik ifadelerini dönüştür
        math_expr = text_lower
        for turkish, symbol in self.operation_words.items():
            math_expr = math_expr.replace(turkish, symbol)
        
        for constant, value in self.math_constants.items():
            math_expr = math_expr.replace(constant, value)

        # Basit hesaplama deneyelim
        try:
            result = self.calculate_expression(math_expr)
            if result is not None:
                return f"🧮 {text} = {result}"
        except:
            pass

        # Türkçe sayıları işle (örn: "beş artı üç")
        turkish_ops = ['artı', 'eksi', 'çarpı', 'bölü']
        if any(op in text_lower for op in turkish_ops):
            parts = re.split(r'(artı|eksi|çarpı|bölü)', text_lower)
            if len(parts) == 3:
                num1_text, op, num2_text = parts
                num1 = self.parse_turkish_number(num1_text.strip())
                num2 = self.parse_turkish_number(num2_text.strip())
                
                if num1 is not None and num2 is not None:
                    if 'artı' in op:
                        return f"🧮 {text} = {num1 + num2}"
                    elif 'eksi' in op:
                        return f"🧮 {text} = {num1 - num2}"
                    elif 'çarpı' in op:
                        return f"🧮 {text} = {num1 * num2}"
                    elif 'bölü' in op:
                        if num2 != 0:
                            return f"🧮 {text} = {num1 / num2}"
                        else:
                            return "❌ Sıfıra bölme hatası!"

        return None

math_engine = SuperMathEngine()

# =============================
# GELİŞMİŞ NLP MOTORU - MATEMATİK ÖNCELİKLİ + KİŞİ BİLGİSİ
# =============================

class AdvancedNLU:
    def __init__(self):
        self.intent_patterns = {
            'math': {
                'patterns': [
                    r'\bhesapla', r'\bkaç\s*eder', r'\btopla', r'\bçıkar', r'\bçarp', r'\bböl',
                    r'\bartı', r'\beksi', r'\bçarpi', r'\bbölü', r'\bmatematik',
                    r'\bsin', r'\bcos', r'\btan', r'\bcot', r'\bhipotenüs', r'\balan',
                    r'\bhacim', r'\bkarekök', r'\bpi\b', r'\bπ\b', r'\büzeri',
                    r'\bküpün\s*hacmi', r'\bkarenin\s*alanı', r'\bdairenin\s*alanı',
                    r'\büçgenin\s*alanı', r'\bkürenin\s*hacmi',
                    r'\d+\s*[\+\-\*\/\^]\s*\d+',  # 5+3 gibi ifadeler
                    r'.*\d+.*[\+\-\*\/\^].*',      # Sayılar ve operatörler içeren her şey
                    r'.*\d+\.?\d*\s*(artı|eksi|çarpı|bölü|üzeri)\s*\d+\.?\d*'  # Türkçe operatörler
                ],
                'priority': 15,  # ÇOK DAHA YÜKSEK öncelik
                'keywords': ['hesapla', 'topla', 'çıkar', 'çarp', 'böl', 'artı', 'eksi', 
                           'sin', 'cos', 'tan', 'cot', 'hipotenüs', 'alan', 'hacim',
                           'küp', 'kare', 'daire', 'üçgen', 'küre', 'karekök', 'pi',
                           'üzeri', 'üs', 'kere']
            },
            'person_info': {
                'patterns': [
                    r'\bkimdir\b', r'\bkim\s*dır\b', r'\bkim\s*dir\b', r'\bkim\s*olarak\s*bilinir',
                    r'\bkim\s*denir', r'\bhayatı\s*nedir', r'\bbiografi', r'\bkaç\s*yaşında',
                    r'\bnereli', r'\bne\s*iş\s*yapar', r'\bmesleği\s*ne',
                    r'\bdoğum\s*tarihi', r'\bdoğum\s*yeri', r'\beğitim\s*hayatı',
                    r'\bkariyeri', r'\bbaşarıları', r'\beserleri'
                ],
                'priority': 12,  # Yüksek öncelik
                'keywords': ['kimdir', 'kim', 'biyografi', 'yaş', 'doğum', 'eğitim', 'kariyer']
            },
            'knowledge': {
                'patterns': [
                    r'\bnedir\b', r'\bne\s*demek', r'\bne\s*anlama\s*gelir', r'\banlamı\s*ne',
                    r'\baçıkla\b', r'\bbilgi\s*ver', r'\bne\s*demektir',
                    r'\bhakkında\b', r'\btanım\b', r'\banlam\b', r'\bne\s*denir'
                ],
                'priority': 10,
                'keywords': ['nedir', 'açıkla', 'bilgi', 'anlamı', 'ne demek', 'hakkında']
            },
            'weather': {
                'patterns': [
                    r'\bhava\s*durum', r'\bhava\s*kaç', r'\bkaç\s*derece', r'\bsıcaklık\s*kaç',
                    r'\bhavası\s*nasıl', r'\bnem\s*oranı', r'\brüzgar\s*şiddeti',
                    r'\bhava\s*durumu\s*söyle', r'\bderece\s*kaç', r'\bsıcaklık\s*ne'
                ],
                'priority': 8,
                'keywords': ['hava', 'derece', 'sıcaklık', 'nem', 'rüzgar']
            },
            'cooking': {
                'patterns': [
                    r'\btarif', r'\bnasıl\s*yapılır', r'\byapımı', r'\bmalzeme',
                    r'\bpişirme', r'\byemek\s*tarifi'
                ],
                'priority': 7,
                'keywords': ['tarif', 'yemek', 'nasıl yapılır', 'malzeme']
            },
            'time': {
                'patterns': [
                    r'\bsaat\s*kaç', r'\bkaç\s*saat', r'\bzaman\s*ne', r'\btarih\s*ne',
                    r'\bgun\s*ne'
                ],
                'priority': 6,
                'keywords': ['saat', 'zaman', 'tarih']
            },
            'news': {
                'patterns': [
                    r'\bhaber', r'\bgündem', r'\bson\s*dakika', r'\bgazete', r'\bmanşet'
                ],
                'priority': 5,
                'keywords': ['haber', 'gündem', 'son dakika']
            },
            'greeting': {
                'patterns': [
                    r'\bmerhaba', r'\bselam', r'\bhey', r'\bhi\b',
                    r'\bgünaydın', r'\biyi\s*günler', r'\bnaber', r'\bne\s*haber'
                ],
                'priority': 10,
                'keywords': ['merhaba', 'selam', 'hey', 'hi']
            },
            'thanks': {
                'patterns': [
                    r'\bteşekkür', r'\bsağ\s*ol', r'\bthanks',
                    r'\beyvallah', r'\bmersi'
                ],
                'priority': 10,
                'keywords': ['teşekkür', 'sağ ol', 'thanks']
            }
        }

    def normalize_text(self, text: str) -> str:
        """Türkçe karakterleri normalize eder"""
        text = text.lower()
        for old, new in TURKISH_CHAR_MAP.items():
            text = text.replace(old, new)
        return text

    def extract_intent(self, text: str) -> Tuple[str, float, Dict]:
        """Metinden intent çıkarır"""
        normalized = self.normalize_text(text)
        scores = {}
        intent_details = {}
        
        # ÖNCE matematik kontrolü (ÇOK DAHA AGRESİF)
        if self.is_likely_math(normalized):
            scores['math'] = 25  # ÇOK YÜKSEK puan
        
        for intent, data in self.intent_patterns.items():
            if intent in scores:  # Matematik zaten eklendiyse atla
                continue
                
            score = 0
            pattern_matches = []
            keyword_matches = []
            
            # Pattern eşleşmeleri
            for pattern in data['patterns']:
                if re.search(pattern, normalized):
                    score += 5
                    pattern_matches.append(pattern)
            
            # Keyword eşleşmeleri
            for keyword in data.get('keywords', []):
                if re.search(r'\b' + re.escape(keyword) + r'\b', normalized):
                    score += 3
                    keyword_matches.append(keyword)
            
            # Priority bonus
            score += data['priority']
            scores[intent] = score
            intent_details[intent] = {
                'score': score,
                'pattern_matches': pattern_matches,
                'keyword_matches': keyword_matches
            }
        
        if not scores:
            return 'unknown', 0.0, {}
        
        best_intent = max(scores.items(), key=lambda x: x[1])
        max_score = max(scores.values())
        
        if max_score < 10:
            confidence = 0.0
        else:
            confidence = min(best_intent[1] / (max_score + 0.1), 1.0)
        
        return best_intent[0], confidence, intent_details.get(best_intent[0], {})

    def is_likely_math(self, text: str) -> bool:
        """Metnin matematik sorgusu olup olmadığını kontrol eder"""
        # Matematik operatörleri
        math_operators = ['+', '-', '*', '/', 'x', '^', 'artı', 'eksi', 'çarpı', 'bölü', 'üzeri']
        if any(op in text for op in math_operators):
            return True
        
        # Matematik fonksiyonları
        math_funcs = ['sin', 'cos', 'tan', 'cot', 'log', 'ln', 'sqrt', 'karekök']
        if any(func in text for func in math_funcs):
            return True
        
        # Matematik terimleri
        math_terms = ['hipotenüs', 'alan', 'hacim', 'pi', 'π', 'hesapla', 'kaç eder', 
                     'küp', 'kare', 'daire', 'üçgen', 'küre', 'üs']
        if any(term in text for term in math_terms):
            return True
        
        # Sayılar ve işlemler
        if re.search(r'\d+\.?\d*\s*[\+\-\*\/\^x]\s*\d+\.?\d*', text):
            return True
        
        # Geometrik şekillerle sayılar
        if re.search(r'(küp|kare|daire|üçgen|küre).*\d+', text):
            return True
            
        return False

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Metinden entity çıkarır - GELİŞTİRİLMİŞ VERSİYON"""
        normalized = self.normalize_text(text)
        entities = {}
        
        # Şehir entity'si - sadece tam kelime eşleşmesi
        for city in TURKISH_CITIES:
            city_normalized = self.normalize_text(city)
            if re.search(r'\b' + re.escape(city_normalized) + r'\b', normalized):
                entities['city'] = city
                break
        
        # Kişi ismi entity'si
        person_patterns = [
            r'\b(recep\s*tayyip\s*erdogan|r\.?\s*t\.?\s*erdogan|erdogan)\b',
            r'\b(mustafa\s*kemal\s*ataturk|ataturk|m\.?\s*k\.?\s*ataturk)\b',
            r'\b(abdullah\s*gul|gul)\b',
            r'\b(ahmet\s*davutoglu|davutoglu)\b',
            r'\b(binali\s*yildirim|yildirim)\b',
            r'\b(ismet\s*inonu|inonu)\b',
            r'\b(kenan\s*evren|evren)\b',
            r'\b(suleyman\s*demirel|demirel)\b',
            r'\b(turgut\s*ozal|ozal)\b',
            r'\b(celal\s*bayar|bayar)\b',
        ]
        
        for pattern in person_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                entities['person'] = self.extract_person_name(normalized)
                break
        
        return entities

    def extract_person_name(self, text: str) -> str:
        """Metinden kişi ismini çıkarır"""
        # Basit bir kişi ismi çıkarımı
        text = re.sub(r'\b(kimdir|kim|hakkında|biyografi|hayatı)\b', '', text).strip()
        return text.title()

nlu_engine = AdvancedNLU()

# =============================
# API ENTEGRASYON SİSTEMİ
# =============================

class IntelligentAPI:
    def __init__(self):
        self.cache = {}
        self.cache_timeout = 300
        
    def get_cache_key(self, source: str, query: str) -> str:
        return f"{source}_{hashlib.md5(query.encode()).hexdigest()}"
    
    def cached_request(self, key: str, func, *args, **kwargs):
        now = time.time()
        if key in self.cache and now - self.cache[key]['timestamp'] < self.cache_timeout:
            return self.cache[key]['data']
        
        result = func(*args, **kwargs)
        if result:
            self.cache[key] = {'data': result, 'timestamp': now}
        return result
    
    def google_search(self, query: str) -> Optional[str]:
        """Google Custom Search API - GELİŞTİRİLMİŞ"""
        try:
            cache_key = self.get_cache_key('google', query)
            
            def search():
                # EĞER matematik sorgusu ise Google'a SORMUYORUZ!
                if nlu_engine.is_likely_math(query):
                    return None
                    
                url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_SEARCH_KEY}&cx={GOOGLE_CX}&q={quote(query)}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    results = response.json()
                    if 'items' in results and results['items']:
                        # Wikipedia dışındaki ilk 3 sonucu kontrol et
                        non_wikipedia_results = []
                        for item in results['items'][:3]:
                            title = item.get('title', '')
                            snippet = item.get('snippet', '')
                            link = item.get('link', '')
                            
                            # Wikipedia ve basit snippet'leri filtrele
                            if ('wikipedia' not in title.lower() and 
                                'wikipedia' not in snippet.lower() and
                                'wikipedia' not in link.lower() and
                                len(snippet) > 50):  # Kısa snippet'leri atla
                                non_wikipedia_results.append(f"{title}\n{snippet}")
                        
                        if non_wikipedia_results:
                            return non_wikipedia_results[0]
                        
                        # Wikipedia dışı sonuç yoksa ilk sonucu ver
                        first_result = results['items'][0]
                        return f"{first_result.get('title', '')}\n{first_result.get('snippet', '')}"
                return None
            
            return self.cached_request(cache_key, search)
            
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return None
    
    def openai_completion(self, prompt: str, max_tokens: int = 300) -> Optional[str]:
        """OpenAI GPT-3.5 API"""
        try:
            cache_key = self.get_cache_key('openai', prompt)
            
            def complete():
                headers = {
                    'Authorization': f'Bearer {OPENAI_API_KEY}',
                    'Content-Type': 'application/json'
                }
                
                data = {
                    'model': 'gpt-3.5-turbo',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': max_tokens,
                    'temperature': 0.7
                }
                
                response = requests.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers=headers,
                    json=data,
                    timeout=25
                )
                
                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content'].strip()
                else:
                    logger.error(f"OpenAI API error: {response.status_code}")
                    return None
            
            return self.cached_request(cache_key, complete)
            
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return None
    
    def get_weather(self, city: str) -> Optional[str]:
        """OpenWeatherMap API"""
        try:
            cache_key = self.get_cache_key('weather', city)
            
            def fetch_weather():
                url = f"http://api.openweathermap.org/data/2.5/weather?q={quote(city)},TR&appid={WEATHER_API_KEY}&units=metric&lang=tr"
                response = requests.get(url, timeout=8)
                
                if response.status_code == 200:
                    data = response.json()
                    temp = data['main']['temp']
                    feels_like = data['main']['feels_like']
                    humidity = data['main']['humidity']
                    desc = data['weather'][0]['description'].capitalize()
                    wind_speed = data.get('wind', {}).get('speed', 'N/A')
                    
                    return (f"🌤️ {city.title()} Hava Durumu:\n"
                           f"• Sıcaklık: {temp:.1f}°C (Hissedilen: {feels_like:.1f}°C)\n"
                           f"• Durum: {desc}\n"
                           f"• Nem: %{humidity}\n"
                           f"• Rüzgar: {wind_speed} m/s\n"
                           f"• Güncelleme: {datetime.now().strftime('%H:%M')}")
                else:
                    return f"❌ {city.title()} için hava durumu bulunamadı."
            
            return self.cached_request(cache_key, fetch_weather)
            
        except Exception as e:
            logger.error(f"Weather API error: {e}")
            return "🌫️ Hava durumu servisi geçici olarak kullanılamıyor."

api_client = IntelligentAPI()

# =============================
# KONUŞMA YÖNETİCİSİ
# =============================

class ConversationManager:
    def __init__(self):
        self.context_size = 5
    
    def add_message(self, user_id: str, role: str, content: str):
        """Konuşma geçmişine mesaj ekler"""
        conversation_history[user_id].append({
            'role': role,
            'content': content,
            'timestamp': datetime.now()
        })

conv_manager = ConversationManager()

# =============================
# ANA CEVAP ÜRETME MOTORU - MATEMATİK ÖNCELİKLİ + KİŞİ BİLGİSİ
# =============================

class ResponseEngine:
    def __init__(self):
        self.greeting_responses = [
            "Merhaba! Ben Meldra, size nasıl yardımcı olabilirim? 🌟",
            "Selam! Harika görünüyorsunuz! Size nasıl yardım edebilirim? 😊",
            "Hey! Meldra burada. Ne yapmak istersiniz? 🚀"
        ]
        
        self.thanks_responses = [
            "Rica ederim! Size yardımcı olabildiğim için mutluyum! 😊",
            "Ne demek! Her zaman buradayım! 🌟",
            "Ben teşekkür ederim! Başka bir şeye ihtiyacınız var mı? 🎉"
        ]

    def generate_response(self, message: str, user_id: str = "default") -> str:
        """Ana cevap üretme fonksiyonu"""
        start_time = time.time()
        
        # Konuşma geçmişine kullanıcı mesajını ekle
        conv_manager.add_message(user_id, 'user', message)
        
        # ÖNCE matematik kontrolü (EN YÜKSEK ÖNCELİK)
        math_result = math_engine.calculate(message)
        if math_result:
            self.finalize_response(user_id, math_result, start_time)
            return math_result
        
        # SONRA NLU analizi
        intent, confidence, intent_details = nlu_engine.extract_intent(message)
        entities = nlu_engine.extract_entities(message)
        
        logger.info(f"NLU Analysis - Intent: {intent}, Confidence: {confidence:.2f}, Entities: {entities}")
        
        # State management
        state = user_states[user_id]
        
        # waiting_for_city state'inde miyiz?
        if state.get('waiting_for_city'):
            return self.handle_city_response(message, user_id, intent, entities)
        
        # INTENT İŞLEME
        if confidence > 0.6:
            response = self.handle_intent(intent, confidence, entities, message, user_id, intent_details)
            if response:
                self.finalize_response(user_id, response, start_time)
                return response
        
        # DÜŞÜK GÜVENİLİRLİK - Akıllı cevap
        return self.handle_unknown_intent(message, user_id)

    def handle_city_response(self, message: str, user_id: str, intent: str, entities: Dict) -> str:
        """Şehir beklerken gelen mesajı işler"""
        state = user_states[user_id]
        
        # Şehir bulmaya çalış
        for city in TURKISH_CITIES:
            if city in nlu_engine.normalize_text(message):
                state['waiting_for_city'] = False
                weather = api_client.get_weather(city)
                return weather
        
        # Eğer teşekkür veya selam ise state'i temizle
        if intent in ['thanks', 'greeting']:
            state['waiting_for_city'] = False
            if intent == 'thanks':
                return random.choice(self.thanks_responses)
            else:
                return random.choice(self.greeting_responses)
        
        # Hala şehir bulunamadıysa tekrar sor
        return "🌤️ Hangi şehir için hava durumu bilgisi istiyorsunuz? Lütfen sadece şehir ismi yazın."

    def handle_intent(self, intent: str, confidence: float, entities: Dict, message: str, user_id: str, intent_details: Dict) -> Optional[str]:
        """Intent'i işler"""
        state = user_states[user_id]
        
        if intent == 'greeting':
            return random.choice(self.greeting_responses)
        
        elif intent == 'thanks':
            return random.choice(self.thanks_responses)
        
        elif intent == 'weather':
            return self.handle_weather_intent(entities, user_id)
        
        elif intent == 'person_info':
            return self.handle_person_info_intent(message, entities)
        
        elif intent == 'knowledge':
            return self.handle_knowledge_intent(message)
        
        elif intent == 'math':
            # Matematik intent'i geldiyse tekrar dene
            math_result = math_engine.calculate(message)
            if math_result:
                return math_result
            return "❌ Matematik işlemini anlayamadım. Lütfen şu şekillerde sorun:\n• '5 + 3' veya '5 artı 3'\n• 'sin 30' veya 'cos 45'\n• '3 ve 4 hipotenüs'\n• 'kenarı 5 olan karenin alanı'"
        
        elif intent == 'time':
            now = datetime.now()
            days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
            return f"🕒 {now.strftime('%H:%M:%S')} - {now.strftime('%d/%m/%Y')} {days[now.weekday()]}"
        
        return None

    def handle_weather_intent(self, entities: Dict, user_id: str) -> Optional[str]:
        """Hava durumu sorgularını işler"""
        state = user_states[user_id]
        city = entities.get('city')
        
        if city:
            # Şehir varsa direkt hava durumu getir
            return api_client.get_weather(city)
        else:
            # Şehir yoksa state'i set et ve sor
            state['waiting_for_city'] = True
            return "🌤️ Hangi şehir için hava durumu bilgisi istiyorsunuz?"

    def handle_person_info_intent(self, message: str, entities: Dict) -> str:
        """Kişi bilgisi sorgularını işler - DETAYLI CEVAP"""
        # Özel kişi isimleri için optimize edilmiş OpenAI prompt'u
        person_name = entities.get('person', '')
        
        if not person_name:
            # Entity yoksa mesajdan kişi ismini çıkarmaya çalış
            person_name = nlu_engine.extract_person_name(message)
        
        if person_name:
            # OpenAI'a özel olarak kişi bilgisi için prompt gönder
            prompt = (
                f"'{person_name}' hakkında detaylı bilgi ver. "
                f"Lütfen şu bilgileri içeren kapsamlı bir biyografi sun:\n"
                f"- Doğum tarihi ve yeri\n"
                f"- Eğitim hayatı\n" 
                f"- Kariyeri ve önemli pozisyonları\n"
                f"- Başarıları ve eserleri\n"
                f"- Önemli olaylar ve tarihler\n"
                f"Bilgileri maddeler halinde ve net bir şekilde ver. "
                f"Wikipedia'dan kopyala yapıştır yapma, kendi cümlelerinle özetle."
            )
            
            ai_response = api_client.openai_completion(prompt, max_tokens=500)
            
            if ai_response and len(ai_response) > 50:
                return f"👤 {person_name} Hakkında:\n\n{ai_response}"
        
        # Genel bilgi intent'ine yönlendir
        return self.handle_knowledge_intent(message)

    def handle_knowledge_intent(self, message: str) -> str:
        """Bilgi sorgularını işler - GELİŞTİRİLMİŞ"""
        # Önce OpenAI'ı dene (daha akıllı ve detaylı cevaplar için)
        enhanced_prompt = (
            f"Kullanıcı şunu sordu: '{message}'. "
            f"Lütfen detaylı, kapsamlı ve doğru bir cevap ver. "
            f"Eğer bir kişi, yer, olay veya kavram hakkındaysa:\n"
            f"- Temel bilgileri ver\n"
            f"- Önemli detayları ekle\n" 
            f"- Tarihsel bağlamı açıkla\n"
            f"- Güncel bilgileri dahil et\n"
            f"Wikipedia'dan kopyala yapıştır yapma, kendi cümlelerinle özetle ve bilgiyi düzenli sun."
        )
        
        ai_response = api_client.openai_completion(enhanced_prompt, max_tokens=400)
        
        if ai_response and len(ai_response) > 30:
            return f"🤖 {ai_response}"
        
        # OpenAI cevap vermezse Google search (Wikipedia olmayan sonuçlar)
        search_result = api_client.google_search(message)
        if search_result:
            return f"🔍 {search_result}"
        
        return "🤔 Bu konuda yeterli bilgim bulunmuyor. Lütfen sorunuzu farklı şekilde ifade edin veya daha spesifik bir soru sorun."

    def handle_unknown_intent(self, message: str, user_id: str) -> str:
        """Bilinmeyen intent'leri işler"""
        # Önce matematik olabilir mi kontrol et
        math_result = math_engine.calculate(message)
        if math_result:
            return math_result
        
        # Sonra OpenAI'ı dene
        ai_response = api_client.openai_completion(
            f"Kullanıcı şunu sordu: '{message}'. "
            "Kısa, net ve bilgilendirici bir cevap ver."
        )
        
        if ai_response:
            return ai_response
        
        return "🤔 Anlayamadım, lütfen daha açıklayıcı şekilde sorabilir misiniz?"

    def finalize_response(self, user_id: str, response: str, start_time: float):
        """Cevabı sonlandırır ve loglar"""
        conv_manager.add_message(user_id, 'assistant', response)
        response_time = (time.time() - start_time) * 1000
        logger.info(f"Response generated in {response_time:.2f}ms")

response_engine = ResponseEngine()

# =============================
# FLASK ROUTE'LARI
# =============================

@app.route("/")
def index():
    """Ana sayfa - Gelişmiş sohbet arayüzü"""
    return """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MELDRA AI - Ultra Gelişmiş Yapay Zeka</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            
            .header p {
                opacity: 0.9;
                font-size: 1.1em;
            }
            
            .chat-container {
                display: flex;
                height: 600px;
            }
            
            .sidebar {
                width: 300px;
                background: #f8f9fa;
                padding: 20px;
                border-right: 1px solid #e9ecef;
                overflow-y: auto;
            }
            
            .features-grid {
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            
            .feature-card {
                background: white;
                padding: 15px;
                border-radius: 10px;
                border-left: 4px solid #667eea;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .feature-card h4 {
                color: #667eea;
                margin-bottom: 5px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .chat-area {
                flex: 1;
                display: flex;
                flex-direction: column;
            }
            
            .messages {
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background: #fafafa;
            }
            
            .message {
                margin-bottom: 15px;
                padding: 12px 16px;
                border-radius: 15px;
                max-width: 80%;
                word-wrap: break-word;
            }
            
            .user-message {
                background: #667eea;
                color: white;
                margin-left: auto;
                border-bottom-right-radius: 5px;
            }
            
            .bot-message {
                background: white;
                border: 1px solid #e9ecef;
                margin-right: auto;
                border-bottom-left-radius: 5px;
            }
            
            .input-area {
                padding: 20px;
                border-top: 1px solid #e9ecef;
                background: white;
            }
            
            .input-group {
                display: flex;
                gap: 10px;
            }
            
            #messageInput {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid #ddd;
                border-radius: 25px;
                outline: none;
                font-size: 16px;
            }
            
            #messageInput:focus {
                border-color: #667eea;
            }
            
            #sendButton {
                padding: 12px 24px;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 25px;
                cursor: pointer;
                font-size: 16px;
                transition: background 0.3s;
            }
            
            #sendButton:hover {
                background: #5a6fd8;
            }
            
            .typing-indicator {
                display: none;
                padding: 10px 16px;
                color: #666;
                font-style: italic;
            }
            
            .status-dot {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #4CAF50;
                margin-right: 5px;
            }
            
            .api-status {
                background: rgba(102, 126, 234, 0.1);
                padding: 10px;
                border-radius: 10px;
                margin-top: 15px;
                font-size: 0.9em;
            }
            
            .math-examples {
                background: rgba(40, 167, 69, 0.1);
                padding: 10px;
                border-radius: 10px;
                margin-top: 15px;
                font-size: 0.8em;
            }
            
            .math-examples h5 {
                color: #28a745;
                margin-bottom: 5px;
            }
            
            .person-examples {
                background: rgba(255, 193, 7, 0.1);
                padding: 10px;
                border-radius: 10px;
                margin-top: 15px;
                font-size: 0.8em;
            }
            
            .person-examples h5 {
                color: #ffc107;
                margin-bottom: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 MELDRA AI v6.2</h1>
                <p>MATEMATİK MOTORU TAM FİKS + DETAYLI KİŞİ BİLGİLERİ</p>
            </div>
            
            <div class="chat-container">
                <div class="sidebar">
                    <div class="features-grid">
                        <div class="feature-card">
                            <h4>🧮 SÜPER MATEMATİK</h4>
                            <p>Artık Google'a sormuyor!</p>
                        </div>
                        <div class="feature-card">
                            <h4>👤 Kişi Bilgileri</h4>
                            <p>Detaylı biyografi ve bilgiler</p>
                        </div>
                        <div class="feature-card">
                            <h4>🌤️ Hava Durumu</h4>
                            <p>Gerçek zamanlı hava bilgileri</p>
                        </div>
                        <div class="feature-card">
                            <h4>🤖 Akıllı Cevaplar</h4>
                            <p>OpenAI ile doğru bilgiler</p>
                        </div>
                    </div>
                    
                    <div class="api-status">
                        <p><span class="status-dot"></span> Matematik Motoru: AKTİF</p>
                        <p><span class="status-dot"></span> Kişi Bilgisi: DETAYLI</p>
                        <p><span class="status-dot"></span> Google Search: AKILLI FİLTRE</p>
                    </div>
                    
                    <div class="math-examples">
                        <h5>🎯 MATEMATİK TESTLERİ:</h5>
                        <p>• kenarı 4 olan küpün hacmi</p>
                        <p>• 2 üzeri 3</p>
                        <p>• sin 30, cos 45</p>
                        <p>• 3 ve 4 hipotenüs</p>
                    </div>
                    
                    <div class="person-examples">
                        <h5>👤 KİŞİ TESTLERİ:</h5>
                        <p>• Recep Tayyip Erdoğan kimdir</p>
                        <p>• Atatürk biyografi</p>
                        <p>• Binali Yıldırım kaç yaşında</p>
                        <p>• Abdullah Gül nereli</p>
                    </div>
                </div>
                
                <div class="chat-area">
                    <div class="messages" id="messages">
                        <div class="message bot-message">
                            🚀 <strong>MELDRA AI v6.2</strong> - MATEMATİK + KİŞİ BİLGİSİ TAM FİKS!<br><br>
                            🎯 <strong>YENİ ÖZELLİKLER:</strong><br>
                            • Matematik sorguları ARTIK Google'a gitmiyor<br>
                            • Kişi sorgularında DETAYLI biyografi<br>
                            • "recep tayyip kimdir" = detaylı bilgi<br>
                            • Tüm geometri ve trigonometri çalışıyor<br><br>
                            Hemen bir matematik veya kişi sorusu sorun! 🧮👤
                        </div>
                    </div>
                    
                    <div class="typing-indicator" id="typingIndicator">
                        Meldra yazıyor...
                    </div>
                    
                    <div class="input-area">
                        <div class="input-group">
                            <input type="text" id="messageInput" placeholder="Matematik veya kişi sorusu sorun..." autocomplete="off">
                            <button id="sendButton">Gönder</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const messagesContainer = document.getElementById('messages');
            const messageInput = document.getElementById('messageInput');
            const sendButton = document.getElementById('sendButton');
            const typingIndicator = document.getElementById('typingIndicator');
            
            function addMessage(content, isUser = false) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
                messageDiv.innerHTML = content.replace(/\\n/g, '<br>');
                messagesContainer.appendChild(messageDiv);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function showTyping() {
                typingIndicator.style.display = 'block';
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function hideTyping() {
                typingIndicator.style.display = 'none';
            }
            
            async function sendMessage() {
                const message = messageInput.value.trim();
                if (!message) return;
                
                // Kullanıcı mesajını ekle
                addMessage(message, true);
                messageInput.value = '';
                
                // Typing göstergesini göster
                showTyping();
                
                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            mesaj: message,
                            user_id: 'web_user'
                        })
                    });
                    
                    const data = await response.json();
                    
                    // Typing göstergesini gizle
                    hideTyping();
                    
                    if (data.status === 'success') {
                        addMessage(data.cevap);
                    } else {
                        addMessage('❌ Bir hata oluştu. Lütfen tekrar deneyin.');
                    }
                } catch (error) {
                    hideTyping();
                    addMessage('❌ Bağlantı hatası. Lütfen tekrar deneyin.');
                }
            }
            
            // Enter tuşu ile gönder
            messageInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
            
            // Buton ile gönder
            sendButton.addEventListener('click', sendMessage);
            
            // Input'a odaklan
            messageInput.focus();
        </script>
    </body>
    </html>
    """

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True)
        mesaj = data.get("mesaj", "").strip()
        user_id = data.get("user_id", "default")
        
        if not mesaj:
            return jsonify({
                "cevap": "Lütfen bir mesaj girin.",
                "status": "error"
            })
        
        cevap = response_engine.generate_response(mesaj, user_id)
        
        return jsonify({
            "cevap": cevap,
            "status": "success",
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return jsonify({
            "cevap": "⚠️ Sistem geçici olarak hizmet veremiyor. Lütfen daha sonra tekrar deneyin.",
            "status": "error"
        })

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "active", 
        "version": "6.2.0",
        "timestamp": datetime.now().isoformat(),
        "features": [
            "MATEMATİK MOTORU TAM FİKS",
            "DETAYLI KİŞİ BİLGİLERİ", 
            "Google Search Akıllı Filtre",
            "Gelişmiş Geometri Hesaplamaları",
            "Trigonometri & Üs Alma",
            "Wikipedia Filtreleme"
        ],
        "statistics": {
            "active_users": len(conversation_history),
            "cached_items": len(api_client.cache),
            "uptime": "running"
        }
    })

@app.route("/clear_cache", methods=["POST"])
def clear_cache():
    api_client.cache.clear()
    user_states.clear()
    return jsonify({"status": "Cache and states cleared"})

@app.route("/reset", methods=["POST"])
def reset_state():
    """Kullanıcı state'ini sıfırla"""
    data = request.get_json(force=True)
    user_id = data.get("user_id", "default")
    user_states[user_id] = {'waiting_for_city': False}
    return jsonify({"status": f"State reset for user {user_id}"})

# =============================
# UYGULAMA BAŞLATMA
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    print("🚀" * 60)
    print("🚀 MELDRA AI v6.2 - MATEMATİK + KİŞİ BİLGİSİ TAM FİKS!")
    print("🚀 Port:", port)
    print("🚀 ÖZELLİKLER:")
    print("🚀   • Matematik sorguları ARTIK Google'a gitmiyor!")
    print("🚀   • Kişi sorgularında DETAYLI biyografi!")
    print("🚀   • 'recep tayyip kimdir' = detaylı bilgi")
    print("🚀   • 'kenarı 4 olan küpün hacmi' = 64")
    print("🚀   • Tüm geometri ve trigonometri çalışıyor")
    print("🚀" * 60)
    
    app.run(host="0.0.0.0", port=port, debug=False)
