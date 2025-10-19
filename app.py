from flask import Flask, request, jsonify, send_from_directory
import os, json, re, random, requests
from difflib import SequenceMatcher
from collections import deque, defaultdict
from urllib.parse import quote
import base64
from datetime import datetime, timedelta
import threading
import time
import hashlib
import urllib.parse
import logging
from typing import Dict, List, Optional, Tuple, Any

# Logging ayarı
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================
# KONFİGÜRASYON VE API ANAHTARLARI
# =============================

# API Anahtarları
WEATHER_API_KEY = "6a7a443921825622e552d0cde2d2b688"
NEWS_API_KEY = "94ac5f3a6ea34ed0918d28958c7e7aa6"
GOOGLE_SEARCH_KEY = "AIzaSyCphCUBFyb0bBVMVG5JupVOjKzoQq33G-c"
GOOGLE_CX = "d15c352df36b9419f"
OPENAI_API_KEY = "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"

# Dosya yolları
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NLP_FILE = os.path.join(BASE_DIR, "nlp_data.json")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")

# =============================
# GLOBAL DEĞİŞKENLER VE VERİ YAPILARI
# =============================

# Basit state management
conversation_history = defaultdict(lambda: deque(maxlen=20))
user_states = defaultdict(lambda: {'waiting_for_city': False})

# Türk şehirleri (normalize edilmiş)
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
    'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c',
    'â': 'a', 'î': 'i', 'û': 'u'
}

# =============================
# GELİŞMİŞ NLP MOTORU - KESİN ÇÖZÜM
# =============================

class AdvancedNLU:
    def __init__(self):
        # DAHA SPESİFİK INTENT PATTERN'LERİ
        self.intent_patterns = {
            'weather': {
                'patterns': [
                    r'\bhava\s*durum', r'\bhava\s*kaç', r'\bkaç\s*derece', r'\bsıcaklık\s*kaç',
                    r'\bhavası\s*nasıl', r'\bnem\s*oranı', r'\brüzgar\s*şiddeti',
                    r'\bhava\s*durumu\s*söyle', r'\bderece\s*kaç', r'\bsıcaklık\s*ne',
                    r'\bweather', r'\btemperature'
                ],
                'priority': 8,
                'requires_city': True,
                'keywords': ['hava', 'derece', 'sıcaklık', 'nem', 'rüzgar', 'weather', 'temperature']
            },
            'knowledge': {
                'patterns': [
                    r'\bnedir\b', r'\bne\s*demek', r'\bne\s*anlama\s*gelir', r'\banlamı\s*ne',
                    r'\baçıkla\b', r'\bbilgi\s*ver', r'\bne\s*demektir', r'\bwhat is',
                    r'\bkimdir\b', r'\bkim\s*dır\b', r'\bhakkında\b', r'\bbiografi',
                    r'\bne\s*iş\s*yapar', r'\bnereli', r'\bkaç\s*yaşında'
                ],
                'priority': 10,
                'requires_city': False,
                'keywords': ['nedir', 'kimdir', 'açıkla', 'bilgi', 'anlamı', 'ne demek']
            },
            'cooking': {
                'patterns': [
                    r'\btarif', r'\bnasıl\s*yapılır', r'\byapımı', r'\bmalzeme',
                    r'\bpişirme', r'\byemek\s*tarifi', r'\brecipe', r'\bingredient'
                ],
                'priority': 9,
                'requires_city': False,
                'keywords': ['tarif', 'yemek', 'nasıl yapılır', 'malzeme']
            },
            'math': {
                'patterns': [
                    r'\bhesapla', r'\bkaç\s*eder', r'\btopla', r'\bçıkar', r'\bçarp', r'\bböl',
                    r'\bartı', r'\beksi', r'\bçarpi', r'\bbölü', r'\bmatematik'
                ],
                'priority': 8,
                'requires_city': False,
                'keywords': ['hesapla', 'topla', 'çıkar', 'çarp', 'böl']
            },
            'time': {
                'patterns': [
                    r'\bsaat\s*kaç', r'\bkaç\s*saat', r'\bzaman\s*ne', r'\btarih\s*ne',
                    r'\bgun\s*ne', r'\bwhat time', r'\bwhat date'
                ],
                'priority': 7,
                'requires_city': False,
                'keywords': ['saat', 'zaman', 'tarih']
            },
            'news': {
                'patterns': [
                    r'\bhaber', r'\bgündem', r'\bson\s*dakika', r'\bgazete', r'\bmanşet',
                    r'\bdünya', r'\bekonomi', r'\bspor', r'\bmagazin'
                ],
                'priority': 6,
                'requires_city': False,
                'keywords': ['haber', 'gündem', 'son dakika']
            },
            'greeting': {
                'patterns': [
                    r'\bmerhaba', r'\bselam', r'\bhey', r'\bhi\b', r'\bhello',
                    r'\bgünaydın', r'\biyi\s*günler', r'\bnaber', r'\bne\s*haber'
                ],
                'priority': 10,
                'requires_city': False,
                'keywords': ['merhaba', 'selam', 'hey', 'hi', 'hello']
            },
            'thanks': {
                'patterns': [
                    r'\bteşekkür', r'\bsağ\s*ol', r'\bthanks', r'\bthank you',
                    r'\beyvallah', r'\bmersi'
                ],
                'priority': 10,
                'requires_city': False,
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
        """Metinden intent çıkarır - ÇOK DAHA KESİN VERSİYON"""
        normalized = self.normalize_text(text)
        scores = {}
        intent_details = {}
        
        for intent, data in self.intent_patterns.items():
            score = 0
            pattern_matches = []
            keyword_matches = []
            
            # Pattern eşleşmeleri
            for pattern in data['patterns']:
                if re.search(pattern, normalized):
                    score += 5  # Pattern eşleşmesi daha yüksek puan
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
                'keyword_matches': keyword_matches,
                'requires_city': data['requires_city']
            }
        
        if not scores:
            return 'unknown', 0.0, {}
        
        # En yüksek skorlu intent'i bul
        best_intent = max(scores.items(), key=lambda x: x[1])
        max_score = max(scores.values())
        
        # Confidence hesapla - DAHA KESİN
        if max_score < 10:  # Çok düşük skor
            confidence = 0.0
        else:
            confidence = min(best_intent[1] / (max_score + 0.1), 1.0)
        
        return best_intent[0], confidence, intent_details.get(best_intent[0], {})

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Metinden entity çıkarır - DAHA AKILLI"""
        normalized = self.normalize_text(text)
        entities = {}
        
        # Şehir entity'si - SADECE BAĞIMSIZ KELİME OLARAK
        for city in TURKISH_CITIES:
            city_normalized = self.normalize_text(city)
            # Sadece tam kelime eşleşmesi (başka kelimenin içinde geçmemesi için)
            if re.search(r'\b' + re.escape(city_normalized) + r'\b', normalized):
                entities['city'] = city
                break
        
        return entities

    def should_handle_as_weather(self, intent: str, entities: Dict, intent_details: Dict) -> bool:
        """Gerçekten hava durumu sorgusu mu?"""
        # Sadece weather intent'i ve şehir entity'si varsa
        if intent != 'weather':
            return False
        
        # Pattern veya keyword eşleşmesi yoksa hava durumu değildir
        if not intent_details.get('pattern_matches') and not intent_details.get('keyword_matches'):
            return False
            
        return True

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
        """Google Custom Search API"""
        try:
            cache_key = self.get_cache_key('google', query)
            
            def search():
                url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_SEARCH_KEY}&cx={GOOGLE_CX}&q={quote(query)}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    results = response.json()
                    if 'items' in results and results['items']:
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
# BASİT KONUŞMA YÖNETİCİSİ
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
# YENİ CEVAP MOTORU - KESİN ÇÖZÜM
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
        """Ana cevap üretme fonksiyonu - KESİN ÇÖZÜM"""
        start_time = time.time()
        
        # Konuşma geçmişine kullanıcı mesajını ekle
        conv_manager.add_message(user_id, 'user', message)
        
        # NLU analizi
        intent, confidence, intent_details = nlu_engine.extract_intent(message)
        entities = nlu_engine.extract_entities(message)
        
        logger.info(f"NLU Analysis - Intent: {intent}, Confidence: {confidence:.2f}, Entities: {entities}")
        
        # State management
        state = user_states[user_id]
        
        # ÖNEMLİ: waiting_for_city state'inde miyiz?
        if state.get('waiting_for_city'):
            return self.handle_city_response(message, user_id, intent, entities)
        
        # INTENT İŞLEME - YÜKSEK GÜVENİLİRLİK GEREKLİ
        if confidence > 0.7:  # Daha yüksek threshold
            response = self.handle_intent(intent, confidence, entities, message, user_id, intent_details)
            if response:
                self.finalize_response(user_id, response, start_time)
                return response
        
        # DÜŞÜK GÜVENİLİRLİK - Google search veya OpenAI
        return self.handle_unknown_intent(message, user_id, intent, entities)

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
        """Intent'i işler - KESİN KURALLAR"""
        state = user_states[user_id]
        
        if intent == 'greeting':
            return random.choice(self.greeting_responses)
        
        elif intent == 'thanks':
            return random.choice(self.thanks_responses)
        
        elif intent == 'weather':
            # ÖNEMLİ: Sadece gerçekten hava durumu sorgusu ise işle
            if not nlu_engine.should_handle_as_weather(intent, entities, intent_details):
                return None
                
            return self.handle_weather_intent(entities, user_id)
        
        elif intent == 'knowledge':
            return self.handle_knowledge_intent(message, entities)
        
        elif intent == 'cooking':
            return self.handle_cooking_intent(message)
        
        elif intent == 'math':
            return self.handle_math_intent(message)
        
        elif intent == 'time':
            now = datetime.now()
            days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
            return f"🕒 {now.strftime('%H:%M:%S')} - {now.strftime('%d/%m/%Y')} {days[now.weekday()]}"
        
        return None

    def handle_weather_intent(self, entities: Dict, user_id: str) -> Optional[str]:
        """Hava durumu sorgularını işler - SADECE GERÇEK SORGULAR"""
        state = user_states[user_id]
        city = entities.get('city')
        
        if city:
            # Şehir varsa direkt hava durumu getir
            return api_client.get_weather(city)
        else:
            # Şehir yoksa state'i set et ve sor
            state['waiting_for_city'] = True
            return "🌤️ Hangi şehir için hava durumu bilgisi istiyorsunuz?"

    def handle_knowledge_intent(self, message: str, entities: Dict) -> str:
        """Bilgi sorgularını işler - Google search"""
        search_result = api_client.google_search(message)
        if search_result:
            return f"🔍 {search_result}"
        else:
            return "🤔 Bu konuda yeterli bilgim bulunmuyor. Lütfen sorunuzu farklı şekilde ifade edin."

    def handle_cooking_intent(self, message: str) -> str:
        """Yemek tarifi sorgularını işler"""
        search_result = api_client.google_search(f"{message} tarifi")
        if search_result:
            return f"🍳 {search_result}"
        else:
            return "🍳 Bu yemek tarifi hakkında detaylı bilgim bulunmuyor."

    def handle_math_intent(self, message: str) -> str:
        """Matematik sorgularını işler - Basit işlemler"""
        try:
            # Basit matematik ifadelerini bul
            numbers = re.findall(r'\d+', message)
            if '+' in message:
                result = sum(map(int, numbers))
                return f"🧮 Sonuç: {result}"
            elif '-' in message and len(numbers) >= 2:
                result = int(numbers[0]) - int(numbers[1])
                return f"🧮 Sonuç: {result}"
            elif 'x' in message or '*' in message:
                result = int(numbers[0]) * int(numbers[1]) if len(numbers) >= 2 else int(numbers[0])
                return f"🧮 Sonuç: {result}"
            elif '/' in message and len(numbers) >= 2:
                result = int(numbers[0]) / int(numbers[1])
                return f"🧮 Sonuç: {result}"
            else:
                return "❌ Matematik işlemini anlayamadım. Lütfen '5 artı 3' gibi ifadeler kullanın."
        except:
            return "❌ Matematik işlemini anlayamadım."

    def handle_unknown_intent(self, message: str, user_id: str, intent: str, entities: Dict) -> str:
        """Bilinmeyen intent'leri işler"""
        # Önce Google search dene
        search_result = api_client.google_search(message)
        if search_result:
            return f"🔍 {search_result}"
        
        # Google search sonuç vermezse OpenAI'ı dene
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
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MELDRA AI - Akıllı Asistan</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0; 
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container { 
                max-width: 800px; 
                margin: 0 auto; 
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .status {
                background: rgba(255,255,255,0.1);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 MELDRA AI v4.2</h1>
                <p>Kesin Çözüm - Akıllı Intent Algılama</p>
            </div>
            <div class="status">
                <h3>✅ Sistem Aktif</h3>
                <p>Gelişmiş NLP ile doğru intent algılama</p>
                <p>Artık "samsun fen lisesi" hava durumu değil!</p>
            </div>
            <div>
                <p>API Endpoint: <code>POST /chat</code></p>
            </div>
        </div>
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
            "cevap": "⚠️ Sistem geçici olarak hizmet veremiyor.",
            "status": "error"
        })

@app.route("/reset", methods=["POST"])
def reset_state():
    """State'i sıfırla"""
    data = request.get_json(force=True)
    user_id = data.get("user_id", "default")
    user_states[user_id] = {'waiting_for_city': False}
    return jsonify({"status": "State reset"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    print("🚀" * 50)
    print("🚀 MELDRA AI v4.2 - KESİN ÇÖZÜM AKTİF!")
    print("🚀 Artık 'samsun fen lisesi' hava durumu değil!")
    print("🚀 Port:", port)
    print("🚀" * 50)
    
    app.run(host="0.0.0.0", port=port, debug=False)
