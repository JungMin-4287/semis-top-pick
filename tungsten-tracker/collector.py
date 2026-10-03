#!/usr/bin/env python3
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
import feedparser

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data.json"
UA="Mozilla/5.0 (compatible; TungstenBottleneckTracker/1.0)"
S=requests.Session()
S.headers.update({"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7"})
MYSTEEL="https://www.mysteel.com/zta/APT/zuixinhangqing/"
WF6="https://www.mysteel.com/hot/1666539.html"

def load():
    return json.loads(DATA.read_text(encoding="utf-8"))

def save(x):
    DATA.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def fetch_text(url,timeout=25):
    r=S.get(url,timeout=timeout)
    r.raise_for_status()
    r.encoding=r.apparent_encoding or r.encoding
    return BeautifulSoup(r.text,"html.parser").get_text(" ",strip=True)

def first_number(patterns,text):
    for pat,mult in patterns:
        m=re.search(pat,text,re.I|re.S)
        if m:
            try:return float(m.group(1).replace(",",""))*mult
            except:pass
    return None

def latest_date(*texts):
    vals=[]
    for t in texts:
        vals += re.findall(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}",t or "")
    if not vals:return None
    norm=[]
    for v in vals:
        p=re.split(r"[-/.]",v); norm.append(f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}")
    return max(norm)

def collect_prices(old):
    errors=[]; a=""; w=""
    try:a=fetch_text(MYSTEEL)
    except Exception as e:errors.append("Mysteel tungsten: "+type(e).__name__+": "+str(e))
    try:w=fetch_text(WF6)
    except Exception as e:errors.append("Mysteel WF6: "+type(e).__name__+": "+str(e))
    op=old.get("prices",{})
    def keep(k):return (op.get(k) or {}).get("value")
    conc=first_number([(r"(?:钨精矿|黑钨精矿)[^0-9]{0,30}([0-9]{2,3}(?:\.[0-9]+)?)\s*万元",10000),(r"(?:钨精矿|黑钨精矿)[^0-9]{0,30}([0-9]{5,6})\s*元",1)],a)
    apt=first_number([(r"APT[^0-9]{0,30}([0-9]{2,3}(?:\.[0-9]+)?)\s*万元",10000),(r"APT[^0-9]{0,30}([0-9]{5,6})\s*元",1)],a)
    wp=first_number([(r"(?:钨粉|钨粉末)[^0-9]{0,30}([0-9]{3,4}(?:\.[0-9]+)?)\s*元",1)],a)
    wc=first_number([(r"(?:碳化钨粉|碳化钨)[^0-9]{0,30}([0-9]{3,4}(?:\.[0-9]+)?)\s*元",1)],a)
    wf=first_number([(r"(?:六氟化钨|WF6)[^0-9]{0,80}([0-9]{4}(?:\.[0-9]+)?)\s*元\s*/?\s*(?:kg|公斤|千克)",1),(r"主流价格[^0-9]{0,20}([0-9]{4})",1)],w)
    band=re.search(r"([0-9]{4})\s*[-~—至]\s*([0-9]{4})\s*元\s*/?\s*(?:kg|公斤|千克)",w)
    lo,hi=(float(band.group(1)),float(band.group(2))) if band else ((op.get("wf6_5n") or {}).get("low"),(op.get("wf6_5n") or {}).get("high"))
    prices={
      "concentrate":{"value":conc if conc is not None else keep("concentrate"),"unit":"CNY/t","label":"텅스텐 정광","grade":"65% WO3, China reference","source":"Mysteel"},
      "apt":{"value":apt if apt is not None else keep("apt"),"unit":"CNY/t","label":"APT","grade":"WO3 88.5%","source":"Mysteel"},
      "w_powder":{"value":wp if wp is not None else keep("w_powder"),"unit":"CNY/kg","label":"W powder","grade":"99.7%, China reference","source":"Mysteel"},
      "wc_powder":{"value":wc if wc is not None else keep("wc_powder"),"unit":"CNY/kg","label":"WC powder","grade":"99.7%, China reference","source":"Mysteel"},
      "wf6_5n":{"value":wf if wf is not None else keep("wf6_5n"),"low":lo,"high":hi,"unit":"CNY/kg","label":"WF6 5N","grade":"99.999%, 47L","source":"Mysteel/Longzhong"},
      "wf6_7n_reference":op.get("wf6_7n_reference",{"value":3600,"unit":"CNY/kg","label":"WF6 7N reference","grade":"news reference","stale":True})
    }
    return prices,latest_date(a,w),errors

def yahoo(ticker):
    url="https://query1.finance.yahoo.com/v8/finance/chart/"+quote(ticker,safe="")+"?range=5d&interval=1d&includePrePost=false"
    r=S.get(url,timeout=20); r.raise_for_status()
    x=r.json()["chart"]["result"][0]; m=x.get("meta",{})
    price=m.get("regularMarketPrice"); prev=m.get("chartPreviousClose") or m.get("previousClose")
    if price is None:
        closes=[z for z in x.get("indicators",{}).get("quote",[{}])[0].get("close",[]) if z is not None]
        if closes:price=closes[-1]; prev=closes[-2] if len(closes)>1 else prev
    return {"ticker":ticker,"price":price,"change_pct":((price/prev)-1)*100 if price is not None and prev else None,"currency":m.get("currency"),"exchange":m.get("exchangeName")}

def collect_equities(watch):
    out=[]; errors=[]
    for x in watch.get("equities",[]):
        try:
            q=yahoo(x["ticker"]); q.update(name=x.get("name"),role=x.get("role")); out.append(q)
        except Exception as e:errors.append(x["ticker"]+": "+type(e).__name__)
    return {"as_of":datetime.now(timezone.utc).isoformat(),"items":out},errors

def classify(title):
    t=title.lower()
    if any(k in t for k in ("wf6","tungsten hexafluoride","六氟化钨")):return "WF6"
    if any(k in t for k in ("apt","ammonium paratungstate","仲钨酸铵")):return "APT"
    if any(k in t for k in ("powder","wo3","oxide","钨粉","氧化钨")):return "midstream"
    if any(k in t for k in ("quota","mine","mining","sangdong","상동")):return "mine/concentrate"
    if any(k in t for k in ("export control","出口管制","수출통제")):return "policy"
    return "tungsten"

def collect_news():
    out=[]; seen=set(); errors=[]
    qs=['tungsten OR WF6 OR "ammonium paratungstate" OR Sangdong when:14d','钨 OR 六氟化钨 OR 仲钨酸铵 OR 出口管制 when:14d']
    for q in qs:
        try:
            f=feedparser.parse("https://news.google.com/rss/search?q="+quote(q)+"&hl=en-US&gl=US&ceid=US:en")
            for e in f.entries[:30]:
                title=re.sub(r"\s+"," ",e.get("title","")).strip(); link=e.get("link","")
                key=hashlib.sha1((title+link).encode()).hexdigest()
                if not title or key in seen:continue
                seen.add(key); src=e.get("source") or {}
                out.append({"published":e.get("published",""),"title":title,"source":src.get("title","Google News") if isinstance(src,dict) else "Google News","stage":classify(title),"url":link})
        except Exception as e:errors.append("news: "+type(e).__name__)
    return out[:50],errors

def main():
    b=load(); old=b.get("latest",{})
    prices,source_date,pe=collect_prices(old)
    today=source_date or old.get("source_date") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    hist=b.get("history",[])
    row={"date":today,"concentrate":prices["concentrate"]["value"],"apt":prices["apt"]["value"],"w_powder":prices["w_powder"]["value"],"wc_powder":prices["wc_powder"]["value"],"wf6_5n":prices["wf6_5n"]["value"],"note":"auto collector"}
    found=next((x for x in hist if x.get("date")==today),None)
    if found:found.update(row)
    else:hist.append(row)
    hist.sort(key=lambda x:x.get("date","")); b["history"]=hist[-730:]
    eq,ee=collect_equities(b.get("watchlist",{})); news,ne=collect_news()
    b["latest"]={"as_of":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),"source_date":today,"prices":prices,"quota":old.get("quota",{}),"collector":{"mode":"auto","status":"ok" if not pe else "partial","notes":pe+ee+ne}}
    b["equities"]=eq
    if news:b["news"]=news
    save(b)
    print(json.dumps({"source_date":today,"price_errors":pe,"equity_errors":ee,"news_count":len(news)},ensure_ascii=False))
if __name__=="__main__":main()
