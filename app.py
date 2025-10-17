from flask import Flask, request, jsonify, send_from_directory
import os, json, re, random, requests
from difflib import SequenceMatcher
from collections import deque
from urllib.parse import quote
from bs4 import BeautifulSoup

app = Flask(__name__)

# -----------------------------
# Dosya yolları ve ayarlar
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
        headers = {"User-Agent": "MeldraBot/1.0"}
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
# WikiHow tarifleri
# -----------------------------
def wikihow_tarif(soru):
    try:
        search_url = f"https://www.wikihow.com/wikiHowTo?search={quote(soru)}"
        headers = {"User-Agent": "MeldraBot/1.0"}
        res = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        first_link = soup.select_one("a.result_link")
        if first_link:
            link = "https://www.wikihow.com" + first_link["href"]
            page_res = requests.get(link, headers=headers, timeout=10)
            page_soup = BeautifulSoup(page_res.text, "html.parser")
            steps = page_soup.select("div.step p, div.step")
            text = "\n".join([s.get_text(strip=True) for s in steps if s.get_text(strip=True)])
            if text.strip():
                return text
    except:
        return None
    return None

# -----------------------------
# Cevap motoru
# -----------------------------
def cevap_ver(mesaj, user_id="default"):
    mesaj_raw = mesaj.strip()
    mesaj_lc = mesaj_raw.lower()

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

    if "öğret" in mesaj_lc: return "🤖 Sadece kral öğretebilir."

    # Hava durumu
    city = mesajdaki_sehir(mesaj_raw)
    if city: return hava_durumu(city)

    # WikiHow
    wh_tarif = wikihow_tarif(mesaj_raw)
    if wh_tarif:
        kaydet_context(user_id, mesaj_raw, wh_tarif)
        return wh_tarif

    # Wikipedia
    wiki_sonuc = wiki_ara(mesaj_raw)
    if wiki_sonuc:
        kaydet_context(user_id, mesaj_raw, wiki_sonuc)
        return wiki_sonuc

    # NLP
    nlp_resp = nlp_cevap(mesaj_raw)
    if nlp_resp:
        kaydet_context(user_id, mesaj_raw, nlp_resp)
        return nlp_resp

    # Matematik
    mat_text = kelime_sayiyi_rakamla(mesaj_raw).replace("x","*")
    mat_res = hesapla(mat_text)
    if mat_res is not None:
        kaydet_context(user_id, mesaj_raw, mat_res)
        return mat_res

    # Fallback
    fallback = random.choice([
        "Bunu anlamadım, tekrar sorabilir misin?",
        "Henüz bu soruyu bilmiyorum. (Sadece kral modu ile öğretilebilir.)"
    ])
    kaydet_context(user_id, mesaj_raw, fallback)
    return fallback

# -----------------------------
# Web arayüzü
# -----------------------------
@app.route("/")
def index():
    if os.path.exists(INDEX_FILE):
        return send_from_directory(os.path.dirname(INDEX_FILE), os.path.basename(INDEX_FILE))
    return "<h3 style='position:absolute;top:10px;left:10px;'>MELDRA çalışıyor — chat endpoint: POST /chat</h3>"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    mesaj = data.get("mesaj","")
    user_id = data.get("user_id","default")
    cevap = cevap_ver(mesaj, user_id)
    return jsonify({"cevap": cevap})

@app.route("/_nlp_dump", methods=["GET"])
def nlp_dump():
    return jsonify(load_json(NLP_FILE))

# -----------------------------
# Sunucu başlatma
# -----------------------------
if __name__=="__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)