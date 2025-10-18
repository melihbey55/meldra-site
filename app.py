from flask import Flask, request, jsonify, send_from_directory
import os, json, re, random, requests
from difflib import SequenceMatcher
from collections import deque
from urllib.parse import quote
import speech_recognition as sr
from gtts import gTTS
import pygame
import io
import base64
from datetime import datetime
import threading
import time

app = Flask(__name__)

# -----------------------------
# Dosya yolları ve ayarlar
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NLP_FILE = os.path.join(BASE_DIR, "nlp_data.json")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
AUDIO_DIR = os.path.join(BASE_DIR, "audio_cache")
CONTEXT_SIZE = 5
user_context = {}
king_mode = set()
password_pending = set()

WEATHER_API_KEY = "6a7a443921825622e552d0cde2d2b688"

# Ses tanıma için
recognizer = sr.Recognizer()
microphone = sr.Microphone()

# Ses önbelleği dizini oluştur
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)

# Türkiye'deki tüm şehirler
TURKISH_CITIES = [
    "adana","adiyaman","afyonkarahisar","agri","aksaray","amasya","ankara","antalya",
    "ardahan","artvin","aydin","balikesir","bartin","batman","bayburt","bilecik","bingol",
    "bitlis","bolu","burdur","bursa","canakkale","cankiri","corum","denizli","diyarbakir",
    "duzce","edirne","elazig","erzincan","erzurum","eskisehir","gaziantep","giresun",
    "gumushane","hakkari","hatay","igdir","isparta","istanbul","izmir","kahramanmaras",
    "karabuk","karaman","kars","kastamonu","kayseri","kilis","kirikkale","kirklareli",
    "kirsehir","kocaeli","konya","kutahya","malatya","manisa","mardin","mersin","mugla",
    "mus","nevsehir","nigde","ordu","osmaniye","rize","sakarya","samsun","sanliurfa",
    "siirt","sinop","sivas","sirnak","tekirdag","tokat","trabzon","tunceli","usak",
    "van","yalova","yozgat","zonguldak"
]

# Geliştirilmiş fallback yemek tarifleri
FALLBACK_RECIPES = {
    "makarna": "🍝 Makarna tarifi: 1. Su kaynatılır. 2. Tuz eklenir. 3. Makarna eklenir ve 8-10 dk haşlanır. 4. Süzülür, sos eklenir ve servis edilir.",
    "salata": "🥗 Basit salata tarifi: Marul, domates, salatalık doğranır, zeytinyağı ve limon eklenir.",
    "çorba": "🍲 Çorba tarifi: Sebzeler doğranır, su ve tuz eklenir, kaynatılır, blendırdan geçirilir.",
    "omlet": "🍳 Omlet tarifi: 2 yumurta çırpılır, tuz biber eklenir. Tavada yağ kızdırılır, yumurta dökülür, pişirilir.",
    "pilav": "🍚 Pilav tarifi: 1 su bardağı pirinç yıkanır. Tereyağında kavrulur. 2 su bardağı su eklenir, kısık ateşte pişirilir."
}

# Kişiselleştirilmiş kullanıcı verileri
user_profiles = {}

# JSON dosyası yoksa oluştur
if not os.path.exists(NLP_FILE):
    with open(NLP_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# -----------------------------
# JSON işlemleri
# -----------------------------
def load_json(file):
    if not os.path.exists(file): return []
    with open(file, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except json.JSONDecodeError: return []

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -----------------------------
# Matematik
# -----------------------------
birimler = {"sıfır":0,"bir":1,"iki":2,"üç":3,"dört":4,"beş":5,
            "altı":6,"yedi":7,"sekiz":8,"dokuz":9}
onlar = {"on":10,"yirmi":20,"otuz":30,"kırk":40,"elli":50,
         "altmış":60,"yetmiş":70,"seksen":80,"doksan":90}
buyukler = {"yüz":100,"bin":1000,"milyon":1000000,"milyar":1000000000}
islemler = {"artı":"+","eksi":"-","çarpı":"*","x":"*","bölü":"/"}

def kelime_sayiyi_rakamla(metin):
    for k,v in islemler.items():
        metin = re.sub(r'\b'+re.escape(k)+r'\b', v, metin)
    tokens, temp_sayi = [],0
    for k in metin.lower().split():
        if k in birimler: temp_sayi += birimler[k]
        elif k in onlar: temp_sayi += onlar[k]
        elif k in buyukler:
            temp_sayi = max(temp_sayi,1) * buyukler[k]
            tokens.append(str(temp_sayi))
            temp_sayi=0
        elif k in ["+","-","*","/","(",")"]:
            if temp_sayi!=0: tokens.append(str(temp_sayi))
            temp_sayi=0
            tokens.append(k)
        else:
            if temp_sayi!=0: tokens.append(str(temp_sayi))
            temp_sayi=0
            tokens.append(k)
    if temp_sayi!=0: tokens.append(str(temp_sayi))
    return " ".join(tokens)

def hesapla(metin):
    try:
        if re.fullmatch(r'[\d\.\+\-\*\/\(\) ]+', metin):
            return str(eval(metin, {"__builtins__": None}, {}))
    except: return None
    return None

# -----------------------------
# NLP
# -----------------------------
nlp_data = load_json(NLP_FILE)

def benzer_mi(a,b,esik=0.85):
    return SequenceMatcher(None,a,b).ratio() >= esik

def token_word_in_text(token, text):
    return re.search(r'\b'+re.escape(token)+r'\b', text, flags=re.IGNORECASE) is not None

def nlp_cevap(mesaj):
    temiz = re.sub(r'[^\w\s]','', (mesaj or "").lower()).strip()
    if not temiz: return None
    for item in nlp_data:
        for trig in item.get("triggers", []):
            if trig.strip().lower() == temiz or token_word_in_text(trig.lower(), temiz) or benzer_mi(trig.lower(), temiz):
                return random.choice(item.get("responses", ["Hmm, anladım."]))
    return None

# -----------------------------
# Context
# -----------------------------
def kaydet_context(user_id, mesaj, cevap):
    if user_id not in user_context:
        user_context[user_id] = deque(maxlen=CONTEXT_SIZE)
    user_context[user_id].append({"mesaj": mesaj, "cevap": cevap})

# -----------------------------
# Ses İşlemleri
# -----------------------------
def text_to_speech(text, lang='tr'):
    """Metni sese dönüştür ve base64 olarak döndür"""
    try:
        # Önbellek dosyası oluştur
        filename = f"tts_{hash(text)}_{lang}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        # Önbellekte yoksa oluştur
        if not os.path.exists(filepath):
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(filepath)
        
        # Base64'e çevir
        with open(filepath, 'rb') as f:
            audio_data = f.read()
        
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"TTS hatası: {e}")
        return None

def speech_to_text(audio_data):
    """Sesi metne dönüştür"""
    try:
        # Geçici dosya oluştur
        temp_file = os.path.join(AUDIO_DIR, "temp_audio.wav")
        with open(temp_file, 'wb') as f:
            f.write(audio_data)
        
        # Ses tanıma
        with sr.AudioFile(temp_file) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="tr-TR")
            return text
    except Exception as e:
        print(f"STT hatası: {e}")
        return None

# -----------------------------
# Hava durumu
# -----------------------------
def hava_durumu(sehir):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={quote(sehir.strip())}&appid={WEATHER_API_KEY}&units=metric&lang=tr"
        res = requests.get(url, timeout=6).json()
        if str(res.get("cod")) == "200" and "main" in res:
            temp = res["main"]["temp"]
            desc = res["weather"][0]["description"]
            nem = res["main"]["humidity"]
            return f"{sehir.title()} şehrinde hava {temp:.1f}°C, {desc}. Nem oranı %{nem}."
        return f"{sehir.title()} için hava durumu bulunamadı."
    except:
        return "Hava durumu alınamadı."

def mesajdaki_sehir(mesaj):
    mesaj_norm = re.sub(r'[^\w\s]','', mesaj.lower())
    for city in TURKISH_CITIES:
        if re.search(r'\b'+re.escape(city)+r'\b', mesaj_norm):
            return city
    return None

# -----------------------------
# Zaman ve Tarih
# -----------------------------
def get_time_info():
    now = datetime.now()
    return {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%d %B %Y"),
        "day": now.strftime("%A")
    }

# -----------------------------
# Wikipedia araştırma
# -----------------------------
def wiki_ara(konu):
    try:
        headers = {"User-Agent": "MeldraBot/1.0"}
        search_url = f"https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(konu)}&format=json"
        res = requests.get(search_url, headers=headers, timeout=10).json()
        results = res.get("query", {}).get("search", [])
        if not results:
            return None
        title = results[0]["title"]
        summary_url = f"https://tr.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
        summary_res = requests.get(summary_url, headers=headers, timeout=10).json()
        return summary_res.get("extract")
    except:
        return None

# -----------------------------
# DuckDuckGo API
# -----------------------------
def web_ara(konu):
    try:
        url = f"https://api.duckduckgo.com/?q={quote(konu)}&format=json&lang=tr"
        r = requests.get(url, timeout=8).json()
        text = r.get("AbstractText") or r.get("Heading")
        if text:
            return text
    except:
        return None
    return None

# -----------------------------
# Yemek tarifleri
# -----------------------------
def yemek_tarifi(konu):
    konu_lower = konu.lower()
    for key in FALLBACK_RECIPES:
        if key in konu_lower:
            return FALLBACK_RECIPES[key]
    return None

def tarif_var_mi(mesaj):
    return any(x in mesaj.lower() for x in ["tarifi","nasıl yapılır","yapımı","tarif"])

# -----------------------------
# Hatırlatıcı Sistemi
# -----------------------------
reminders = {}

def set_reminder(user_id, reminder_text, minutes):
    reminder_time = time.time() + minutes * 60
    if user_id not in reminders:
        reminders[user_id] = []
    reminders[user_id].append({"text": reminder_text, "time": reminder_time})
    return f"⏰ Hatırlatıcı ayarlandı: {minutes} dakika sonra"

def check_reminders(user_id):
    if user_id not in reminders:
        return []
    
    current_time = time.time()
    due_reminders = []
    remaining_reminders = []
    
    for reminder in reminders[user_id]:
        if reminder["time"] <= current_time:
            due_reminders.append(reminder["text"])
        else:
            remaining_reminders.append(reminder)
    
    reminders[user_id] = remaining_reminders
    return due_reminders

# -----------------------------
# Eğlence Özellikleri
# -----------------------------
def get_joke():
    jokes = [
        "Neden tavuklar karşıdan karşıya geçer? Cevabı bilmiyorum, ben yapay zekayım!",
        "Matematik kitabı neden üzgün? Çünkü çok fazla problemi var!",
        "Bir yapay zeka diğerine ne demiş? 1011001 0101100 0110101!",
    ]
    return random.choice(jokes)

def get_quote():
    quotes = [
        "Hayatta en hakiki mürşit ilimdir. - Mustafa Kemal Atatürk",
        "Başarı, %1 ilham ve %99 terdir. - Thomas Edison",
        "Yapay zeka insanlığın en iyi yardımcısı olabilir.",
    ]
    return random.choice(quotes)

# -----------------------------
# Cevap motoru - GELİŞTİRİLMİŞ
# -----------------------------
def cevap_ver(mesaj, user_id="default"):
    mesaj_raw = mesaj.strip()
    mesaj_lc = mesaj_raw.lower().strip()

    # Hatırlatıcıları kontrol et
    due_reminders = check_reminders(user_id)
    if due_reminders:
        reminder_text = "⏰ Hatırlatıcılarınız:\n" + "\n".join(f"• {reminder}" for reminder in due_reminders)
        kaydet_context(user_id, mesaj_raw, reminder_text)
        return reminder_text

    # Kral modu
    if mesaj_lc=="her biji amasya":
        password_pending.add(user_id)
        return "Parolayı giriniz:"
    if user_id in password_pending:
        if mesaj_lc=="0567995561":
            password_pending.discard(user_id)
            king_mode.add(user_id)
            return "✅ Öğrenme modu aktif."
        else:
            password_pending.discard(user_id)
            return "⛔ Yanlış parola."
    if mesaj_lc in ["ben yüce kral melih çakar","ben yuce kral melih cakar"]:
        king_mode.add(user_id)
        return "👑 Öğrenme modu aktif!"
    if user_id in king_mode and mesaj_lc.startswith("soru:") and "cevap:" in mesaj_lc:
        try:
            soru = mesaj_lc.split("soru:",1)[1].split("cevap:",1)[0].strip()
            cevap = mesaj_lc.split("cevap:",1)[1].strip()
            if soru and cevap:
                nlp_data_local = load_json(NLP_FILE)
                nlp_data_local.append({"triggers":[soru], "responses":[cevap]})
                save_json(NLP_FILE, nlp_data_local)
                global nlp_data
                nlp_data = nlp_data_local
                kaydet_context(user_id, soru, cevap)
                return f"✅ '{soru}' sorusunu öğrendim."
        except:
            return "⚠️ Hatalı format."

    if "öğret" in mesaj_lc: 
        return "🤖 Sadece kral öğretebilir."

    # Zaman ve tarih sorguları
    if any(x in mesaj_lc for x in ["saat kaç", "saat ne", "zaman"]):
        time_info = get_time_info()
        cevap = f"🕒 Şu an saat {time_info['time']}, {time_info['date']} {time_info['day']}"
        kaydet_context(user_id, mesaj_raw, cevap)
        return cevap

    # Eğlence özellikleri
    if any(x in mesaj_lc for x in ["şaka yap", "şaka söyle", "güldür"]):
        joke = get_joke()
        kaydet_context(user_id, mesaj_raw, joke)
        return joke

    if any(x in mesaj_lc for x in ["alıntı", "quote", "söz"]):
        quote = get_quote()
        kaydet_context(user_id, mesaj_raw, quote)
        return quote

    # Hatırlatıcı
    if "hatırlatıcı" in mesaj_lc or "hatırlat" in mesaj_lc:
        match = re.search(r'(\d+)\s*dakika?\s*sonra\s*(.+)', mesaj_lc)
        if match:
            minutes = int(match.group(1))
            reminder_text = match.group(2)
            cevap = set_reminder(user_id, reminder_text, minutes)
            kaydet_context(user_id, mesaj_raw, cevap)
            return cevap

    # NLP
    nlp_resp = nlp_cevap(mesaj_raw)
    if nlp_resp:
        kaydet_context(user_id, mesaj_raw, nlp_resp)
        return nlp_resp

    # Matematik
    mat_text = kelime_sayiyi_rakamla(mesaj_raw).replace("x","*")
    mat_res = hesapla(mat_text)
    if mat_res is not None:
        cevap = f"🧮 Cevap: {mat_res}"
        kaydet_context(user_id, mesaj_raw, cevap)
        return cevap

    # Hava durumu
    city = mesajdaki_sehir(mesaj_raw)
    if city: 
        cevap = hava_durumu(city)
        kaydet_context(user_id, mesaj_raw, cevap)
        return cevap

    # Yemek tarifi
    if tarif_var_mi(mesaj_raw):
        konu = re.sub(r'(tarifi|nasıl yapılır|yapımı|tarif)', '', mesaj_raw, flags=re.IGNORECASE).strip()
        tarif = yemek_tarifi(konu)
        if tarif:
            kaydet_context(user_id, mesaj_raw, tarif)
            return tarif
        else:
            cevap = f"'{konu}' için tarif bulunamadı."
            kaydet_context(user_id, mesaj_raw, cevap)
            return cevap

    # Wikipedia
    wiki_sonuc = wiki_ara(mesaj_raw)
    if wiki_sonuc:
        kaydet_context(user_id, mesaj_raw, wiki_sonuc)
        return wiki_sonuc

    # Web araması (DuckDuckGo fallback)
    web_sonuc = web_ara(mesaj_raw)
    if web_sonuc:
        kaydet_context(user_id, mesaj_raw, web_sonuc)
        return web_sonuc

    fallback = random.choice([
        "Bunu anlamadım, tekrar sorabilir misin?",
        "Henüz bu soruyu bilmiyorum. (Sadece kral modu ile öğretilebilir.)",
        "Bu konuda yardımcı olamıyorum, başka bir şey sorabilir misin?",
        "Sanırım bu soruyu anlamadım, daha basit şekilde sorar mısın?"
    ])
    kaydet_context(user_id, mesaj_raw, fallback)
    return fallback

# -----------------------------
# Web arayüzü - GELİŞTİRİLMİŞ
# -----------------------------
@app.route("/")
def index():
    if os.path.exists(INDEX_FILE):
        return send_from_directory(os.path.dirname(INDEX_FILE), os.path.basename(INDEX_FILE))
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MELDRA AI - Gelişmiş Yapay Zeka</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f0f0f0; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
            .feature { background: #e3f2fd; padding: 10px; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 MELDRA AI - Gelişmiş Yapay Zeka</h1>
            <p>Çalışıyor — API endpoint'leri:</p>
            <div class="feature">
                <h3>📝 Metin Sohbeti:</h3>
                <code>POST /chat</code>
            </div>
            <div class="feature">
                <h3>🎤 Ses Sohbeti:</h3>
                <code>POST /speech_chat</code>
            </div>
            <div class="feature">
                <h3>🔊 Metin-Ses Dönüşümü:</h3>
                <code>POST /tts</code>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    mesaj = data.get("mesaj","")
    user_id = data.get("user_id","default")
    cevap = cevap_ver(mesaj, user_id)
    return jsonify({"cevap": cevap})

@app.route("/speech_chat", methods=["POST"])
def speech_chat():
    """Sesli sohbet endpoint'i"""
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "Ses dosyası bulunamadı"}), 400
        
        audio_file = request.files['audio']
        user_id = request.form.get("user_id", "default")
        
        # Ses dosyasını oku
        audio_data = audio_file.read()
        
        # Sesi metne çevir
        text = speech_to_text(audio_data)
        if not text:
            return jsonify({"error": "Ses anlaşılamadı"}), 400
        
        # Metni işle
        cevap = cevap_ver(text, user_id)
        
        # Cevabı sese çevir
        audio_base64 = text_to_speech(cevap)
        
        return jsonify({
            "orjinal_metin": text,
            "cevap": cevap,
            "ses_cevap": audio_base64
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/tts", methods=["POST"])
def text_to_speech_api():
    """Metni sese dönüştürme endpoint'i"""
    data = request.get_json(force=True)
    text = data.get("text", "")
    lang = data.get("lang", "tr")
    
    audio_base64 = text_to_speech(text, lang)
    if audio_base64:
        return jsonify({"audio": audio_base64})
    else:
        return jsonify({"error": "Ses oluşturulamadı"}), 500

@app.route("/_nlp_dump", methods=["GET"])
def nlp_dump():
    return jsonify(load_json(NLP_FILE))

@app.route("/features", methods=["GET"])
def features():
    """Mevcut özellikleri listele"""
    features_list = [
        "🤖 Akıllı sohbet",
        "🔢 Matematik hesaplamaları",
        "🌤️ Hava durumu sorgulama",
        "🍳 Yemek tarifleri", 
        "📚 Wikipedia araştırma",
        "🔍 Web araması",
        "🎤 Sesli sohbet",
        "🔊 Metin-okuma",
        "⏰ Hatırlatıcılar",
        "😊 Şakalar ve alıntılar",
        "🕒 Zaman ve tarih",
        "👑 Kral modu (öğrenme)"
    ]
    return jsonify({"features": features_list})

if __name__=="__main__":
    port = int(os.environ.get("PORT", 5000))
    # Mikrofonu hazırla
    print("Mikrofon hazırlanıyor...")
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source)
    print(f"MELDRA AI {port} portunda başlatılıyor...")
    app.run(host="0.0.0.0", port=port, debug=False)
