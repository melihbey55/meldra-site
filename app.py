from flask import Flask, request, jsonify, send_from_directory
import os, json, re, random, requests
from difflib import SequenceMatcher
from collections import deque
from urllib.parse import quote

app = Flask(__name__)

# -----------------------------
# Dosya yolları
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NLP_FILE = os.path.join(BASE_DIR, "nlp_data.json")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
CONTEXT_SIZE = 5
user_context = {}
king_mode = set()
password_pending = set()

# OpenWeatherMap API Key
WEATHER_API_KEY = "6a7a443921825622e552d0cde2d2b688"

# Türk şehirleri
TURKISH_CITIES = [
    "adana","adiyaman","afyonkarahisar","agri","amasya","ankara","antalya","artvin","aydin","balikesir",
    "bilecik","bingol","bitlis","bolu","burdur","bursa","canakkale","cankiri","corum","denizli","diyarbakir",
    "edirne","elazig","erzincan","erzurum","eskisehir","gaziantep","giresun","gumushane","hakkari","hatay",
    "isparta","mersin","istanbul","izmir","kahramanmaras","karabuk","karaman","kars","kastamonu","kayseri",
    "kirklareli","kirsehir","kocaeli","konya","kutahya","malatya","manisa","mardin","mus","nevsehir",
    "nigde","ordu","osmaniye","rize","sakarya","samsun","sanliurfa","siirt","sinop","sivas","sirnak","tekirdag",
    "tokat","trabzon","tunceli","usak","van","yalova","yozgat","zonguldak"
]

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
        if k in birimlers: temp_sayi += birimler[k]
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
        if re.fullmatch(r'[\d\.\+\-\*\/ ]+', metin):
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
# Hava durumu
# -----------------------------
def hava_durumu(sehir):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={quote(sehir.strip())}&appid={WEATHER_API_KEY}&units=metric&lang=tr"
        res = requests.get(url, timeout=6).json()
        cod = str(res.get("cod",""))
        if cod=="200" and "main" in res:
            temp = res["main"]["temp"]
            desc = res["weather"][0]["description"]
            return f"{sehir.title()} şehrinde hava {temp}°C, {desc}."
        return f"{sehir.title()} şehri için hava durumu bulunamadı."
    except: return "Hava durumu alınamadı."

def mesajdaki_sehir(mesaj):
    mesaj_norm = re.sub(r'[^\w\s]','', mesaj.lower())
    for city in TURKISH_CITIES:
        if city in mesaj_norm: return city
    return None

# -----------------------------
# Wikipedia araştırma
# -----------------------------
def wiki_ara(konu):
    try:
        headers = {"User-Agent": "MeldraBot/1.0 (https://example.com)"}
        search_url = f"https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(konu)}&format=json"
        res = requests.get(search_url, headers=headers, timeout=10).json()
        search_results = res.get("query", {}).get("search", [])
        if search_results:
            title = search_results[0]["title"]
            summary_url = f"https://tr.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
            summary_res = requests.get(summary_url, headers=headers, timeout=10).json()
            if "extract" in summary_res:
                return summary_res["extract"]
    except:
        return None
    return None

# -----------------------------
# Geliştirilmiş WikiHow tarifleri
# -----------------------------
def wikihow_tarif(konu):
    try:
        headers = {"User-Agent": "MeldraBot/1.0 (https://example.com)"}
        
        # WikiHow arama
        search_url = f"https://www.wikihow.com/api.php?action=search&query={quote(konu)}&format=json"
        res = requests.get(search_url, headers=headers, timeout=10).json()
        
        if "results" in res and res["results"]:
            # İlk sonucu al
            first_result = res["results"][0]
            title = first_result.get("title", "Tarif")
            page_id = first_result.get("pageid")
            
            # Detaylı içerik için
            detail_url = f"https://www.wikihow.com/api.php?action=parse&pageid={page_id}&format=json"
            detail_res = requests.get(detail_url, headers=headers, timeout=10).json()
            
            if "parse" in detail_res:
                # Malzemeler ve adımları çıkarmaya çalış
                text = detail_res["parse"].get("text", {}).get("*", "")
                
                # Malzemeleri bul
                malzemeler = []
                malzeme_match = re.findall(r'<li class="material">(.*?)</li>', text)
                if malzeme_match:
                    malzemeler = malzeme_match
                else:
                    # Alternatif malzeme arama
                    malzeme_match = re.findall(r'<b>Malzemeler:</b>(.*?)<br/>', text, re.DOTALL)
                    if malzeme_match:
                        malzemeler = re.findall(r'<li>(.*?)</li>', malzeme_match[0])
                
                # Adımları bul
                adimlar = []
                adim_match = re.findall(r'<div class="step">.*?<b>(.*?)</b>.*?</div>', text, re.DOTALL)
                if adim_match:
                    adimlar = [re.sub(r'<.*?>', '', adim).strip() for adim in adim_match[:10]]  # İlk 10 adım
                
                # URL
                url = f"https://www.wikihow.com/{first_result.get('url', '').replace(' ', '-')}"
                
                cevap = f"🍳 {title} - Tarif:\n\n"
                
                if malzemeler:
                    cevap += "📋 **Malzemeler:**\n"
                    for i, malzeme in enumerate(malzemeler[:15], 1):  # İlk 15 malzeme
                        temiz_malzeme = re.sub(r'<.*?>', '', malzeme).strip()
                        cevap += f"{i}. {temiz_malzeme}\n"
                    cevap += "\n"
                
                if adimlar:
                    cevap += "👨‍🍳 **Hazırlanışı:**\n"
                    for i, adim in enumerate(adimlar, 1):
                        cevap += f"{i}. {adim}\n"
                else:
                    cevap += f"\n🔗 Detaylı tarif için: {url}"
                
                return cevap
                
    except Exception as e:
        print(f"WikiHow hatası: {e}")
    
    return None

# -----------------------------
# Geliştirilmiş Cevap motoru
# -----------------------------
def cevap_ver(mesaj, user_id="default"):
    mesaj_raw = mesaj.strip()
    mesaj_lc = mesaj_raw.lower().strip()

    # Kral modu
    if mesaj_lc == "her biji amasya":
        password_pending.add(user_id)
        return "Parolayı giriniz:"
    
    if user_id in password_pending:
        if mesaj_lc == "0567995561":
            password_pending.discard(user_id)
            king_mode.add(user_id)  # Bu satırı ekledim
            return "Kral modu aktif! Artık her şeyi yapabilirsin."
        else:
            password_pending.discard(user_id)
            return "Parola yanlış!"

    # Matematik işlemleri
    matematik_sonuc = hesapla(kelime_sayiyi_rakamla(mesaj_raw))
    if matematik_sonuc:
        return f"Sonuç: {matematik_sonuc}"

    # Hava durumu
    sehir = mesajdaki_sehir(mesaj_lc)
    if sehir:
        return hava_durumu(sehir)

    # Yemek tarifi (geliştirilmiş)
    tarif_kelimeler = ["tarif", "nasıl yapılır", "yemek tarifi", "yapılışı", "malzemeler"]
    if any(kelime in mesaj_lc for kelime in tarif_kelimeler):
        # Tarif konusunu çıkar
        konu = mesaj_raw
        for kelime in tarif_kelimeler:
            konu = konu.lower().replace(kelime, "").strip()
        
        if konu:
            tarif = wikihow_tarif(konu + " tarifi")
            if tarif:
                return tarif
            else:
                return f"'{konu}' için detaylı tarif bulamadım. Daha basit bir açıklama yapabilir misin?"

    # WikiHow genel
    if mesaj_lc.startswith("nasıl") or " nasıl " in mesaj_lc or "yapılır" in mesaj_lc:
        tarif = wikihow_tarif(mesaj_raw)
        if tarif:
            return tarif

    # Wikipedia araştırma
    if mesaj_lc.startswith("araştır") or mesaj_lc.startswith("wiki"):
        konu = mesaj_lc.replace("araştır", "").replace("wiki", "").strip()
        if konu:
            bilgi = wiki_ara(konu)
            if bilgi:
                return f"🔍 {konu.title()} hakkında:\n\n{bilgi[:500]}..." if len(bilgi) > 500 else bilgi
            else:
                return f"'{konu}' hakkında bilgi bulamadım."

    # NLP yanıtları
    nlp_yaniti = nlp_cevap(mesaj_raw)
    if nlp_yaniti:
        return nlp_yaniti

    # Varsayılan yanıtlar
    varsayilan_yanitlar = [
        "Anlayamadım, biraz daha açıklar mısın?",
        "Bunu nasıl cevaplayacağımı bilemedim.",
        "Henüz bu konuda bilgim yok.",
        "Başka bir şey sormak ister misin?",
        "Bu konuda yardımcı olamayacağım."
    ]
    
    return random.choice(varsayilan_yanitlar)

# -----------------------------
# Flask Routes
# -----------------------------
@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_id = request.json.get('user_id', 'default')
    mesaj = request.json.get('mesaj', '').strip()
    
    if not mesaj:
        return jsonify({"cevap": "Mesaj boş olamaz!"})
    
    cevap = cevap_ver(mesaj, user_id)
    kaydet_context(user_id, mesaj, cevap)
    
    return jsonify({"cevap": cevap})

@app.route('/context/<user_id>', methods=['GET'])
def get_context(user_id):
    return jsonify({"context": list(user_context.get(user_id, []))})

@app.route('/context/<user_id>', methods=['DELETE'])
def clear_context(user_id):
    if user_id in user_context:
        user_context[user_id].clear()
    return jsonify({"status": "Context temizlendi"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)