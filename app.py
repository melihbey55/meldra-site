from flask import Flask, request, jsonify, send_from_directory
import os, json, re, random, requests
from difflib import SequenceMatcher
from collections import deque
from urllib.parse import quote
from bs4 import BeautifulSoup

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

WEATHER_API_KEY = "6a7a443921825622e552d0cde2d2b688"

TURKISH_CITIES = [
    "adana","ankara","istanbul","izmir","antalya","bursa","gaziantep","konya",
    "kayseri","trabzon","samsun","eskisehir","diyarbakir","malatya","van","rize",
    "hatay","mardin","ordu","sakarya","mersin","tekirdag","zonguldak"
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
        if str(res.get("cod")) == "200" and "main" in res:
            temp = res["main"]["temp"]
            desc = res["weather"][0]["description"]
            return f"{sehir.title()} şehrinde hava {temp}°C, {desc}."
        return f"{sehir.title()} için hava durumu bulunamadı."
    except:
        return "Hava durumu alınamadı."

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
# Yemek tarifi (TheMealDB + Nefis Yemek Tarifleri)
# -----------------------------
def yemek_tarifi(konu):
    # 1️⃣ TheMealDB dene
    try:
        url = f"https://www.themealdb.com/api/json/v1/1/search.php?s={quote(konu)}"
        r = requests.get(url, timeout=8).json()
        meals = r.get("meals")
        if meals:
            meal = meals[0]
            name = meal["strMeal"]
            instructions = meal["strInstructions"]
            return f"🍽️ {name} tarifi:\n{instructions[:600]}..."
    except:
        pass

    # 2️⃣ Nefis Yemek Tarifleri — web scraping
    try:
        search_url = f"https://www.nefisyemektarifleri.com/?s={quote(konu)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(search_url, headers=headers, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        link = soup.select_one("div.recipe-card a")
        if not link:
            return None
        detay_url = link["href"]
        detay_html = requests.get(detay_url, headers=headers, timeout=10).text
        detay_soup = BeautifulSoup(detay_html, "html.parser")
        baslik_tag = detay_soup.select_one("h1.recipe-title")
        if not baslik_tag:
            return None
        baslik = baslik_tag.get_text(strip=True)
        adimlar = detay_soup.select("div.recipe-preparation p")
        text = " ".join([a.get_text(strip=True) for a in adimlar])[:600]
        return f"🍳 {baslik} tarifi (Nefis Yemek Tarifleri):\n{text}..."
    except:
        return None

def tarif_var_mi(mesaj):
    return any(x in mesaj.lower() for x in ["tarifi","nasıl yapılır","yapımı","tarif"])

# -----------------------------
# Cevap motoru
# -----------------------------
def cevap_ver(mesaj, user_id="default"):
    mesaj_raw = mesaj.strip()
    mesaj_lc = mesaj_raw.lower().strip()

    # 🏰 Kral modu
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

    # Hava durumu
    city = mesajdaki_sehir(mesaj_raw)
    if city: 
        return hava_durumu(city)

    # Yemek tarifi
    if tarif_var_mi(mesaj_raw):
        konu = re.sub(r'(tarifi|nasıl yapılır|yapımı|tarif)', '', mesaj_raw, flags=re.IGNORECASE).strip()
        tarif = yemek_tarifi(konu)
        if tarif:
            return tarif
        else:
            return f"'{konu}' için tarif bulunamadı."

    # Wikipedia
    wiki_sonuc = wiki_ara(mesaj_raw)
    if wiki_sonuc:
        kaydet_context(user_id, mesaj_raw, wiki_sonuc)
        return wiki_sonuc

    # Web araması (fallback)
    web_sonuc = web_ara(mesaj_raw)
    if web_sonuc:
        kaydet_context(user_id, mesaj_raw, web_sonuc)
        return web_sonuc

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

if __name__=="__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
