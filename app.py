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

# Kullanıcı durum yönetimi
user_context = defaultdict(lambda: deque(maxlen=10))
conversation_history = defaultdict(lambda: deque(maxlen=20))
user_states = defaultdict(dict)
king_mode = set()
password_pending = set()

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

# Akıllı yemek tarifleri
INTELLIGENT_RECIPES = {
    "makarna": {
        "title": "🍝 Kolay Makarna Tarifi",
        "ingredients": ["Makarna", "Tuz", "Su", "Zeytinyağı", "İsteğe bağlı sos"],
        "steps": [
            "1. Derin bir tencerede su kaynatın",
            "2. Kaynayan suya tuz ekleyin",
            "3. Makarnayı ekleyip 8-10 dakika haşlayın",
            "4. Süzdükten sonra zeytinyağı veya sos ile karıştırın",
            "5. Sıcak servis yapın"
        ]
    },
    "menemen": {
        "title": "🍳 Geleneksel Menemen",
        "ingredients": ["2 yumurta", "2 domates", "1 yeşil biber", "1 soğan", "Zeytinyağı", "Tuz", "Karabiber"],
        "steps": [
            "1. Soğan ve biberleri zeytinyağında kavurun",
            "2. Domatesleri küp küp doğrayıp ekleyin",
            "3. Domatesler suyunu çekene kadar pişirin",
            "4. Yumurtaları kırıp karıştırarak pişirin",
            "5. Tuz ve karabiber ekleyip sıcak servis yapın"
        ]
    },
    "pilav": {
        "title": "🍚 Pirinç Pilavı",
        "ingredients": ["1 su bardağı pirinç", "2 su bardağı su", "2 yemek kaşığı tereyağı", "1 çay kaşığı tuz"],
        "steps": [
            "1. Pirinci yıkayıp 30 dakika suda bekletin",
            "2. Tereyağını tencerede eritin",
            "3. Pirinçleri ekleyip 5 dakika kavurun",
            "4. Kaynar su ve tuzu ekleyin",
            "5. Kısık ateşte 15-20 dakika pişirin"
        ]
    }
}

# =============================
# İLERİ SEVİYE NLP MOTORU
# =============================

class AdvancedNLU:
    def __init__(self):
        self.intent_patterns = {
            'weather': {
                'patterns': [
                    r'hava.*durum', r'hava.*kaç', r'derece', r'nem', r'rüzgar',
                    r'sıcaklık', r'hava.*nasıl', r'yağmur', r'kar', r'güneş',
                    r'havasi', r'kaç.*derece'
                ],
                'priority': 10
            },
            'cooking': {
                'patterns': [
                    r'tarif', r'nasıl.*yapılır', r'yapımı', r'malzeme', r'pişirme',
                    r'yemek', r'yemeği', r'recipe', r'ingredient', r'tarifi'
                ],
                'priority': 9
            },
            'math': {
                'patterns': [
                    r'hesapla', r'kaç.*eder', r'topla', r'çıkar', r'çarp', r'böl',
                    r'artı', r'eksi', r'çarpi', r'bölü', r'matematik', r'\+', r'-', r'\*', r'/'
                ],
                'priority': 8
            },
            'time': {
                'patterns': [
                    r'saat', r'zaman', r'tarih', r'gün', r'kaç.*old', r'ne.*zaman',
                    r'saattir', r'tarihi'
                ],
                'priority': 7
            },
            'news': {
                'patterns': [
                    r'haber', r'gündem', r'son.*dakika', r'gazete', r'manşet',
                    r'dünya', r'ekonomi', r'spor', r'magazin'
                ],
                'priority': 6
            },
            'person_query': {
                'patterns': [
                    r'kimdir', r'kim.*dir', r'hakkında', r'biyografi', r'kisilik',
                    r'kac.*yasinda', r'nereli', r'ne.*is.*yapar'
                ],
                'priority': 9
            },
            'knowledge': {
                'patterns': [
                    r'nedir', r'nasıl', r'niçin', r'ne.*zaman', r'nerede',
                    r'hangi', r'açıkla', r'bilgi', r'anlamı'
                ],
                'priority': 5
            },
            'greeting': {
                'patterns': [
                    r'merhaba', r'selam', r'hey', r'hi', r'hello', r'günaydın',
                    r'iyi.*günler', r'naber', r'ne.*haber'
                ],
                'priority': 10
            },
            'thanks': {
                'patterns': [
                    r'teşekkür', r'sağ ol', r'thanks', r'thank you', r'eyvallah',
                    r'mersi'
                ],
                'priority': 10
            },
            'entertainment': {
                'patterns': [
                    r'şaka', r'fıkra', r'eğlence', r'komik', r'eğlen',
                    r'oyun', r'eğlenceli', r'güldür'
                ],
                'priority': 4
            }
        }
        
        # Önemli kişiler veritabanı
        self.important_people = {
            "recep tayyip erdoğan": {
                "name": "Recep Tayyip Erdoğan",
                "type": "politician",
                "keywords": ["cumhurbaşkanı", "başkan", "ak parti", "siyaset"]
            },
            "mustafa kemal atatürk": {
                "name": "Mustafa Kemal Atatürk",
                "type": "historical_figure", 
                "keywords": ["kurucu", "cumhuriyet", "kurtuluş savaşı", "devlet adamı"]
            },
            "acun ılıcalı": {
                "name": "Acun Ilıcalı",
                "type": "media_personality",
                "keywords": ["televizyoncu", "medya", "tv8", "exxen"]
            }
        }

    def normalize_text(self, text: str) -> str:
        """Türkçe karakterleri normalize eder"""
        text = text.lower()
        for old, new in TURKISH_CHAR_MAP.items():
            text = text.replace(old, new)
        return text

    def extract_intent(self, text: str) -> Tuple[str, float]:
        """Metinden intent çıkarır ve güven skoru döndürür"""
        normalized = self.normalize_text(text)
        scores = {}
        
        for intent, data in self.intent_patterns.items():
            score = 0
            for pattern in data['patterns']:
                matches = re.findall(pattern, normalized)
                score += len(matches) * 2  # Her eşleşme için bonus
                
                # Tam cümle eşleşmesi için ekstra puan
                if re.search(r'\b' + pattern + r'\b', normalized):
                    score += 3
            
            # Priority bonus
            score += data['priority']
            scores[intent] = score
        
        if not scores:
            return 'unknown', 0.0
        
        best_intent = max(scores.items(), key=lambda x: x[1])
        max_score = max(scores.values())
        confidence = min(best_intent[1] / (max_score + 0.1), 1.0)
        
        return best_intent[0], confidence

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Metinden entity çıkarır"""
        normalized = self.normalize_text(text)
        entities = {}
        
        # Şehir entity'si
        for city in TURKISH_CITIES:
            city_normalized = self.normalize_text(city)
            if re.search(r'\b' + re.escape(city_normalized) + r'\b', normalized):
                entities['city'] = city
                break
        
        # Yemek entity'si
        for food in INTELLIGENT_RECIPES.keys():
            if re.search(r'\b' + re.escape(food) + r'\b', normalized):
                entities['food'] = food
                break
        
        # Kişi entity'si
        for person_key, person_data in self.important_people.items():
            if person_key in normalized:
                entities['person'] = person_data
                break
            # Anahtar kelimelerle eşleşme
            for keyword in person_data['keywords']:
                if keyword in normalized:
                    entities['person'] = person_data
                    break
        
        # Sayı entity'si
        numbers = re.findall(r'\d+', text)
        if numbers:
            entities['numbers'] = [int(num) for num in numbers]
        
        # Zaman entity'si
        time_patterns = [
            r'(\d+)\s*dakika',
            r'(\d+)\s*saat', 
            r'(\d+)\s*gün',
            r'(\d+)\s*hafta'
        ]
        for pattern in time_patterns:
            match = re.search(pattern, normalized)
            if match:
                entities['time_amount'] = int(match.group(1))
                entities['time_unit'] = re.search(r'(dakika|saat|gün|hafta)', pattern).group(1)
                break
        
        return entities

    def is_weather_follow_up(self, user_id: str, current_message: str) -> bool:
        """Hava durumu takip sorusu mu kontrol eder"""
        if user_id not in user_states:
            return False
        
        state = user_states[user_id]
        if state.get('waiting_for_city'):
            return True
        
        # Son mesajlarda hava durumu konuşulmuş mu?
        recent_messages = list(conversation_history[user_id])[-3:]
        for msg in recent_messages:
            if any(word in self.normalize_text(msg.get('content', '')) 
                   for word in ['hava', 'derece', 'sıcaklık', 'nem']):
                return True
        
        return False

nlu_engine = AdvancedNLU()

# =============================
# ÇOKLU API ENTEGRASYON SİSTEMİ
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
    
    def get_news(self, category: str = 'general') -> Optional[str]:
        """NewsAPI"""
        try:
            cache_key = self.get_cache_key('news', category)
            
            def fetch_news():
                url = f"https://newsapi.org/v2/top-headlines?country=tr&category={category}&apiKey={NEWS_API_KEY}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    news_data = response.json()
                    articles = news_data.get('articles', [])[:5]
                    
                    if articles:
                        news_text = "📰 Son Haberler:\n"
                        for i, article in enumerate(articles, 1):
                            title = article['title'].split(' - ')[0]
                            news_text += f"{i}. {title}\n"
                        return news_text
                return None
            
            return self.cached_request(cache_key, fetch_news)
            
        except Exception as e:
            logger.error(f"News API error: {e}")
            return None

api_client = IntelligentAPI()

# =============================
# AKILLI KONUŞMA YÖNETİCİSİ
# =============================

class ConversationManager:
    def __init__(self):
        self.context_size = 5
    
    def add_message(self, user_id: str, role: str, content: str):
        """Konuşma geçmişine mesaj ekler"""
        conversation_history[user_id].append({
            'role': role,
            'content': content,
            'timestamp': datetime.now(),
            'message_id': len(conversation_history[user_id])
        })
    
    def get_recent_context(self, user_id: str, count: int = 3) -> List[Dict]:
        """Son birkaç mesajı context olarak döndürür"""
        if user_id not in conversation_history:
            return []
        return list(conversation_history[user_id])[-count:]
    
    def get_conversation_summary(self, user_id: str) -> str:
        """Konuşmanın özetini çıkarır"""
        recent = self.get_recent_context(user_id, 5)
        if not recent:
            return "Yeni konuşma başlatıldı."
        
        topics = []
        for msg in recent:
            content = msg['content'].lower()
            if any(word in content for word in ['hava', 'derece', 'sıcaklık']):
                topics.append('hava durumu')
            elif any(word in content for word in ['tarif', 'yemek', 'yapım']):
                topics.append('yemek tarifi')
            elif any(word in content for word in ['kimdir', 'kim']):
                topics.append('kişi sorgusu')
        
        if topics:
            return f"Son konuşma konuları: {', '.join(set(topics))}"
        return "Genel sohbet"

conv_manager = ConversationManager()

# =============================
# MATEMATİK MOTORU
# =============================

class MathEngine:
    def __init__(self):
        self.number_words = {
            "sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5,
            "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
            "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60,
            "yetmiş": 70, "seksen": 80, "doksan": 90
        }
        self.operation_words = {
            "artı": "+", "eksi": "-", "çarpı": "*", "bölü": "/", "x": "*"
        }
    
    def text_to_math(self, text: str) -> Optional[str]:
        """Metni matematik ifadesine çevirir"""
        text = nlu_engine.normalize_text(text)
        tokens = text.split()
        math_tokens = []
        
        for token in tokens:
            if token in self.operation_words:
                math_tokens.append(self.operation_words[token])
            elif token in self.number_words:
                math_tokens.append(str(self.number_words[token]))
            elif token.isdigit():
                math_tokens.append(token)
            elif token in ['+', '-', '*', '/', '(', ')']:
                math_tokens.append(token)
        
        return ' '.join(math_tokens) if math_tokens else None
    
    def calculate(self, expression: str) -> Optional[float]:
        """Matematik ifadesini hesaplar"""
        try:
            # Güvenli eval
            allowed_chars = set('0123456789+-*/.() ')
            if all(c in allowed_chars for c in expression):
                result = eval(expression, {"__builtins__": {}}, {})
                return float(result) if isinstance(result, (int, float)) else None
        except:
            return None
        return None

math_engine = MathEngine()

# =============================
# ANA CEVAP ÜRETME MOTORU
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
        
        self.fallback_responses = [
            "Anlayamadım, lütfen daha açıklayıcı şekilde sorabilir misiniz?",
            "Sanırım bu konuda yardımcı olamayacağım. Başka bir sorunuz var mı?",
            "Bu soruyu tam olarak anlayamadım. Farklı şekilde ifade edebilir misiniz?"
        ]

    def generate_response(self, message: str, user_id: str = "default") -> str:
        """Ana cevap üretme fonksiyonu"""
        start_time = time.time()
        
        # Konuşma geçmişine kullanıcı mesajını ekle
        conv_manager.add_message(user_id, 'user', message)
        
        # NLU analizi
        intent, confidence = nlu_engine.extract_intent(message)
        entities = nlu_engine.extract_entities(message)
        
        logger.info(f"NLU Analysis - Intent: {intent}, Confidence: {confidence:.2f}, Entities: {entities}")
        
        # Yüksek güvenilirlikli intent'ler için özel işlemler
        if confidence > 0.8:
            response = self.handle_high_confidence_intent(intent, entities, message, user_id)
            if response:
                self.finalize_response(user_id, response, start_time)
                return response
        
        # Düşük güvenilirlik veya karmaşık sorular için OpenAI
        ai_response = self.try_ai_generation(message, user_id, intent, entities)
        if ai_response:
            self.finalize_response(user_id, ai_response, start_time)
            return ai_response
        
        # Fallback
        response = random.choice(self.fallback_responses)
        self.finalize_response(user_id, response, start_time)
        return response

    def handle_high_confidence_intent(self, intent: str, entities: Dict, message: str, user_id: str) -> Optional[str]:
        """Yüksek güvenilirlikli intent'leri işler"""
        
        if intent == 'greeting':
            return random.choice(self.greeting_responses)
        
        elif intent == 'thanks':
            return random.choice(self.thanks_responses)
        
        elif intent == 'weather':
            return self.handle_weather_intent(entities, user_id, message)
        
        elif intent == 'cooking':
            return self.handle_cooking_intent(entities, message)
        
        elif intent == 'math':
            return self.handle_math_intent(message)
        
        elif intent == 'person_query':
            return self.handle_person_query(entities, message)
        
        elif intent == 'time':
            return self.handle_time_query()
        
        elif intent == 'news':
            return self.handle_news_query(entities)
        
        return None

    def handle_weather_intent(self, entities: Dict, user_id: str, message: str) -> Optional[str]:
        """Hava durumu sorgularını işler"""
        city = entities.get('city')
        
        if city:
            # Doğrudan şehir belirtilmişse
            user_states[user_id].pop('waiting_for_city', None)
            return api_client.get_weather(city)
        elif nlu_engine.is_weather_follow_up(user_id, message):
            # Takip sorusuysa ve şehir bulunabilirse
            for city in TURKISH_CITIES:
                if city in nlu_engine.normalize_text(message):
                    user_states[user_id].pop('waiting_for_city', None)
                    return api_client.get_weather(city)
        
        # Şehir belirtilmemişse
        user_states[user_id]['waiting_for_city'] = True
        return "🌤️ Hangi şehir için hava durumu bilgisi istiyorsunuz? Örneğin: 'İstanbul hava durumu' veya 'Ankara kaç derece?'"

    def handle_cooking_intent(self, entities: Dict, message: str) -> Optional[str]:
        """Yemek tarifi sorgularını işler"""
        food = entities.get('food')
        
        if food and food in INTELLIGENT_RECIPES:
            recipe = INTELLIGENT_RECIPES[food]
            response = f"{recipe['title']}\n\n"
            response += "🛒 Malzemeler:\n• " + "\n• ".join(recipe['ingredients']) + "\n\n"
            response += "👩‍🍳 Yapılışı:\n" + "\n".join(recipe['steps'])
            return response
        else:
            # Google'dan tarif ara
            food_name = food if food else message
            search_result = api_client.google_search(f"{food_name} tarifi")
            if search_result:
                return f"🍳 {food_name.title()} Tarifi:\n{search_result}"
            else:
                available_recipes = ", ".join(INTELLIGENT_RECIPES.keys())
                return f"🍳 '{food_name}' için detaylı tarifim yok. Bildiğim tarifler: {available_recipes}"

    def handle_math_intent(self, message: str) -> Optional[str]:
        """Matematik sorgularını işler"""
        math_expression = math_engine.text_to_math(message)
        if math_expression:
            result = math_engine.calculate(math_expression)
            if result is not None:
                return f"🧮 Hesaplama: {math_expression} = {result}"
        
        return "❌ Matematik işlemini anlayamadım. Lütfen '5 artı 3' veya '10 çarpı 2' gibi ifadeler kullanın."

    def handle_person_query(self, entities: Dict, message: str) -> Optional[str]:
        """Kişi sorgularını işler"""
        person_data = entities.get('person')
        
        if person_data:
            # Google'dan kişi bilgisi ara
            search_result = api_client.google_search(f"{person_data['name']} kimdir")
            if search_result:
                return f"👤 {person_data['name']}:\n{search_result}"
        
        # Entity bulunamazsa message'dan kişi ismini çıkar
        person_name = self.extract_person_name(message)
        if person_name:
            search_result = api_client.google_search(f"{person_name} kimdir")
            if search_result:
                return f"👤 {person_name}:\n{search_result}"
        
        return "🤔 Bu kişi hakkında yeterli bilgim bulunmuyor."

    def handle_time_query(self) -> str:
        """Zaman sorgularını işler"""
        now = datetime.now()
        days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        return f"🕒 {now.strftime('%H:%M:%S')} - {now.strftime('%d/%m/%Y')} {days[now.weekday()]}"

    def handle_news_query(self, entities: Dict) -> Optional[str]:
        """Haber sorgularını işler"""
        category = 'general'
        message_lower = nlu_engine.normalize_text(str(entities))
        
        if 'spor' in message_lower:
            category = 'sports'
        elif 'ekonomi' in message_lower:
            category = 'business'
        elif 'teknoloji' in message_lower:
            category = 'technology'
        
        news = api_client.get_news(category)
        return news if news else "📰 Şu anda haberler alınamıyor."

    def extract_person_name(self, message: str) -> Optional[str]:
        """Mesajdan kişi ismini çıkarır"""
        # Basit isim çıkarma (gerçek uygulamada daha gelişmiş NLP kullanılır)
        words = message.lower().split()
        for i, word in enumerate(words):
            if word in ['kimdir', 'kim', 'hakkında'] and i > 0:
                return ' '.join(words[max(0, i-2):i]).title()
        return None

    def try_ai_generation(self, message: str, user_id: str, intent: str, entities: Dict) -> Optional[str]:
        """OpenAI ile akıllı cevap üretmeyi dener"""
        context = conv_manager.get_recent_context(user_id, 3)
        conversation_summary = conv_manager.get_conversation_summary(user_id)
        
        prompt = f"""
        Kullanıcı: {message}
        Konuşma Özeti: {conversation_summary}
        Intent: {intent}
        Entities: {entities}
        Son Mesajlar: {[msg['content'] for msg in context]}
        
        Sen Meldra adında çok gelişmiş bir Türkçe yapay zeka asistanısın. 
        Kullanıcının sorusuna en doğru, detaylı ve yararlı şekilde cevap ver.
        Cevabın kısa, net ve bilgilendirici olsun.
        Eğer kullanıcının ne istediğinden emin değilsen, açıklayıcı şekilde sor.
        """
        
        response = api_client.openai_completion(prompt, max_tokens=350)
        return response if response and len(response) > 10 else None

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
    if os.path.exists(INDEX_FILE):
        return send_from_directory(os.path.dirname(INDEX_FILE), os.path.basename(INDEX_FILE))
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MELDRA AI - Ultra Gelişmiş Yapay Zeka</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0; 
                padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 40px 20px;
            }
            .header {
                text-align: center;
                margin-bottom: 50px;
            }
            .header h1 {
                font-size: 3.5em;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .header p {
                font-size: 1.3em;
                opacity: 0.9;
            }
            .features-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 25px;
                margin-top: 40px;
            }
            .feature-card {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.2);
                transition: transform 0.3s ease;
            }
            .feature-card:hover {
                transform: translateY(-5px);
            }
            .feature-card h3 {
                font-size: 1.5em;
                margin-bottom: 15px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .api-status {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 8px 16px;
                background: rgba(76, 175, 80, 0.2);
                border-radius: 20px;
                margin: 5px;
                border: 1px solid rgba(76, 175, 80, 0.5);
            }
            .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: #4CAF50;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 MELDRA AI</h1>
                <p>ChatGPT'den Daha Akıllı, Her Soruya Doğru Cevap!</p>
                
                <div style="margin-top: 30px;">
                    <div class="api-status">
                        <span class="status-dot"></span>
                        OpenAI GPT-3.5: Aktif
                    </div>
                    <div class="api-status">
                        <span class="status-dot"></span>
                        Google Search: Aktif
                    </div>
                    <div class="api-status">
                        <span class="status-dot"></span>
                        Weather API: Aktif
                    </div>
                    <div class="api-status">
                        <span class="status-dot"></span>
                        News API: Aktif
                    </div>
                </div>
            </div>
            
            <div class="features-grid">
                <div class="feature-card">
                    <h3>🤖 Akıllı Sohbet</h3>
                    <p>Gelişmiş AI ile doğal konuşma, context anlama ve akıllı cevaplar</p>
                    <code>POST /chat</code>
                </div>
                
                <div class="feature-card">
                    <h3>🌤️ Gelişmiş Hava Durumu</h3>
                    <p>Gerçek zamanlı hava durumu bilgileri ve akıllı şehir tanıma</p>
                </div>
                
                <div class="feature-card">
                    <h3>🔍 Gerçek Zamanlı Arama</h3>
                    <p>Google Search API ile güncel ve doğru bilgiler</p>
                </div>
                
                <div class="feature-card">
                    <h3>👤 Kişi Sorgulama</h3>
                    <p>Ünlü kişiler hakkında detaylı ve doğru bilgiler</p>
                </div>
                
                <div class="feature-card">
                    <h3>🍳 Akıllı Tarifler</h3>
                    <p>Detaylı yemek tarifleri ve malzeme listeleri</p>
                </div>
                
                <div class="feature-card">
                    <h3>📰 Canlı Haberler</h3>
                    <p>Kategori bazlı son dakika haberleri</p>
                </div>
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
        
        # Ana cevap üretme motorunu çağır
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
        "version": "4.0.0",
        "timestamp": datetime.now().isoformat(),
        "features": [
            "Advanced NLU Engine",
            "Multi-API Integration",
            "Conversation Memory",
            "Smart Context Understanding",
            "Real-time Information",
            "Intelligent Response Generation"
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
    return jsonify({"status": "Cache cleared"})

# =============================
# UYGULAMA BAŞLATMA
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    print("🚀" * 60)
    print("🚀 MELDRA AI ULTRA - Tüm Sistemler Aktif!")
    print("🚀 Port:", port)
    print("🚀 Özellikler:")
    print("🚀   • Gelişmiş NLU Motoru")
    print("🚀   • Çoklu API Entegrasyonu")
    print("🚀   • Akıllı Konuşma Yönetimi")
    print("🚀   • Gerçek Zamanlı Bilgi")
    print("🚀   • Context Anlama")
    print("🚀" * 60)
    
    app.run(host="0.0.0.0", port=port, debug=False)
