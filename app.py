from flask import Flask, request, jsonify, send_from_directory
import os, json, re, random, requests
from difflib import SequenceMatcher
from collections import deque
from urllib.parse import quote

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NLP_FILE = os.path.join(BASE_DIR, "nlp_data.json")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
CONTEXT_SIZE = 5
user_context = {}
king_mode = set()
password_pending = set()
WEATHER_API_KEY = "6a7a443921825622e552d0cde2d2b688"

TURKISH_CITIES = ["adana","ankara","istanbul","izmir","bursa","antalya","mersin","konya"] # Örnek, tümünü ekleyebilirsin

if not os.path.exists(NLP_FILE):
    with open(NLP_FILE,"w",encoding="utf-8") as f:
        json.dump([],f,ensure_ascii=False,indent=2)

def load_json(file):
    try:
        with open(file,"r",encoding="utf-8") as f: return json.load(f)
    except: return []

def save_json(file,data):
    with open(file,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)

birimler = {"sıfır":0,"bir":1,"iki":2,"üç":3,"dört":4,"beş":5,"altı":6,"yedi":7,"sekiz":8,"dokuz":9}
onlar = {"on":10,"yirmi":20,"otuz":30,"kırk":40,"elli":50,"altmış":60,"yetmiş":70,"seksen":80,"doksan":90}
buyukler = {"yüz":100,"bin":1000,"milyon":1000000,"milyar":1000000000}
islemler = {"artı":"+","eksi":"-","çarpı":"*","x":"*","bölü":"/"}

def kelime_sayiyi_rakamla(metin):
    for k,v in islemler.items(): metin = re.sub(r'\b'+re.escape(k)+r'\b',v,metin)
    tokens,temp= [],0
    for k in metin.lower().split():
        if k in birimler: temp+=birimler[k]
        elif k in onlar: temp+=onlar[k]
        elif k in buyukler: temp=max(temp,1)*buyukler[k]; tokens.append(str(temp)); temp=0
        elif k in "+-*/()": 
            if temp!=0: tokens.append(str(temp)); temp=0
            tokens.append(k)
        else: 
            if temp!=0: tokens.append(str(temp)); temp=0
            tokens.append(k)
    if temp!=0: tokens.append(str(temp))
    return " ".join(tokens)

def hesapla(metin):
    try:
        if re.fullmatch(r'[\d\.\+\-\*\/\(\) ]+',metin): return str(eval(metin,{"__builtins__":None},{}))
    except: return None
    return None

nlp_data = load_json(NLP_FILE)
def benzer_mi(a,b,esik=0.85): return SequenceMatcher(None,a,b).ratio()>=esik
def token_word_in_text(token,text): return re.search(r'\b'+re.escape(token)+r'\b',text,flags=re.IGNORECASE) is not None
def nlp_cevap(mesaj):
    temiz=re.sub(r'[^\w\s]','',(mesaj or "").lower()).strip()
    if not temiz: return None
    for item in nlp_data:
        for trig in item.get("triggers",[]):
            if trig.strip().lower()==temiz or token_word_in_text(trig.lower(),temiz) or benzer_mi(trig.lower(),temiz):
                return random.choice(item.get("responses",["Hmm, anladım."]))
    return None

def kaydet_context(user_id,mesaj,cevap):
    if user_id not in user_context: user_context[user_id]=deque(maxlen=CONTEXT_SIZE)
    user_context[user_id].append({"mesaj":mesaj,"cevap":cevap})

def hava_durumu(sehir):
    try:
        url=f"http://api.openweathermap.org/data/2.5/weather?q={quote(sehir.strip())}&appid={WEATHER_API_KEY}&units=metric&lang=tr"
        res=requests.get(url,timeout=6).json()
        if str(res.get("cod",""))=="200" and "main" in res:
            temp=res["main"]["temp"]; desc=res["weather"][0]["description"]
            return f"{sehir.title()} şehrinde hava {temp}°C, {desc}."
        return f"{sehir.title()} şehri için hava durumu bulunamadı."
    except: return "Hava durumu alınamadı."

def mesajdaki_sehir(mesaj):
    m=re.sub(r'[^\w\s]','',mesaj.lower())
    for c in TURKISH_CITIES:
        if c in m: return c
    return None

def wiki_ara(konu):
    try:
        h={"User-Agent":"MeldraBot/1.0"}
        url=f"https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(konu)}&format=json"
        res=requests.get(url,headers=h,timeout=10).json()
        s=res.get("query",{}).get("search",[])
        if s:
            title=s[0]["title"]
            sum_url=f"https://tr.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
            sum_res=requests.get(sum_url,headers=h,timeout=10).json()
            if "extract" in sum_res: return sum_res["extract"]
    except: return None
    return None

def wikihow_tarif(konu):
    try:
        h={"User-Agent":"MeldraBot/1.0"}
        url=f"https://www.wikihow.com/api.php?action=query&list=search&srsearch={quote(konu)}&format=json"
        res=requests.get(url,headers=h,timeout=10).json()
        s=res.get("query",{}).get("search",[])
        if s:
            t=s[0]["title"]
            return f"WikiHow tarif: {t}\nLink: https://www.wikihow.com/{'-'.join(t.split())}"
    except: return None
    return None

def cevap_ver(mesaj,user_id="default"):
    m=mesaj.strip(); ml=m.lower().strip()
    if ml=="her biji amasya": password_pending.add(user_id); return "Parolayı giriniz:"
    if user_id in password_pending:
        if ml=="0567995561": password_pending.discard(user_id); king_mode.add(user_id); return "✅ Öğrenme modu aktif."
        else: password_pending.discard(user_id); return "⛔ Yanlış parola."
    if ml in ["ben yüce kral melih çakar","ben yuce kral melih cakar"]: king_mode.add(user_id); return "👑 Öğrenme modu aktif!"
    if user_id in king_mode and ml.startswith("soru:") and "cevap:" in ml:
        try:
            s=ml.split("soru:",1)[1].split("cevap:",1)[0].strip()
            c=ml.split("cevap:",1)[1].strip()
            if s and c:
                d=load_json(NLP_FILE); d.append({"triggers":[s],"responses":[c]}); save_json(NLP_FILE,d); global nlp_data; nlp_data=d
                kaydet_context(user_id,s,c)
                return f"✅ '{s}' sorusunu öğrendim."
        except: return "⚠️ Hatalı format."
    if "öğret" in ml: return "🤖 Sadece kral öğretebilir."
    city=mesajdaki_sehir(m)
    if city: return hava_durumu(city)
    wiki=wiki_ara(m)
    if wiki: kaydet_context(user_id,m,wiki); return wiki
    if any(k in m.lower() for k in ["yemek","tarif","nasıl yapılır"]):
        wh=wikihow_tarif(m)
        if wh: kaydet_context(user_id,m,wh); return wh
    nlp=nlp_cevap(m)
    if nlp: kaydet_context(user_id,m,nlp); return nlp
    mat=hesapla(kelime_sayiyi_rakamla(m).replace("x","*"))
    if mat is not None: kaydet_context(user_id,m,mat); return mat
    fb=random.choice(["Bunu anlamadım, tekrar sorabilir misin?","Henüz bu soruyu bilmiyorum. (Sadece kral modu ile öğretilebilir.)"])
    kaydet_context(user_id,m,fb)
    return fb

@app.route("/")
def index(): 
    if os.path.exists(INDEX_FILE): return send_from_directory(os.path.dirname(INDEX_FILE),os.path.basename(INDEX_FILE))
    return "<h3 style='position:absolute;top:10px;left:10px;'>MELDRA çalışıyor — chat endpoint: POST /chat</h3>"

@app.route("/chat",methods=["POST"])
def chat(): 
    data=request.get_json(force=True)
    m=data.get("mesaj","")
    uid=data.get("user_id","default")
    c=cevap_ver(m,uid)
    return jsonify({"cevap":c})

@app.route("/_nlp_dump",methods=["GET"])
def nlp_dump(): return jsonify(load_json(NLP_FILE))

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)