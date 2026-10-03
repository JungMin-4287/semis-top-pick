#!/usr/bin/env python3
from __future__ import annotations
import json,re,hashlib
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
import requests,feedparser
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data.json"
S=requests.Session()
S.headers.update({"User-Agent":"Mozilla/5.0 (compatible; FoosungMaterialsTracker/2.0)","Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7"})
URLS={
 "tungsten":"https://www.mysteel.com/zta/APT/zuixinhangqing/",
 "wf6":"https://www.mysteel.com/hot/1666539.html",
 "lipf6":"https://list1.mysteel.com/zhishi/glflsljgzs.html",
 "lithium":"https://list1.mysteel.com/zhishi/tsljgzxjgzst.html"
}
def load(): return json.loads(DATA.read_text(encoding="utf-8"))
def save(x): DATA.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def text(url):
 r=S.get(url,timeout=25);r.raise_for_status();r.encoding=r.apparent_encoding or r.encoding
 return BeautifulSoup(r.text,"html.parser").get_text(" ",strip=True)
def num(pats,t):
 for pat,mult in pats:
  m=re.search(pat,t,re.I|re.S)
  if m:
   try:return float(m.group(1).replace(",",""))*mult
   except:pass
 return None
def source_date(*ts):
 vals=[]
 for t in ts:
  vals+=re.findall(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}",t or "")
 if not vals:return None
 out=[]
 for v in vals:
  p=re.split(r"[-/.]",v);out.append(f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}")
 return max(out)
def collect_tungsten(old):
 errs=[];a=w=""
 try:a=text(URLS["tungsten"])
 except Exception as e:errs.append("tungsten:"+type(e).__name__)
 try:w=text(URLS["wf6"])
 except Exception as e:errs.append("wf6:"+type(e).__name__)
 op=old.get("prices",{})
 def keep(k):return (op.get(k) or {}).get("value")
 conc=num([(r"(?:钨精矿|黑钨精矿)[^0-9]{0,35}([0-9]{2,3}(?:\.[0-9]+)?)\s*万元",10000),(r"(?:钨精矿|黑钨精矿)[^0-9]{0,35}([0-9]{5,6})\s*元",1)],a)
 apt=num([(r"APT[^0-9]{0,35}([0-9]{2,3}(?:\.[0-9]+)?)\s*万元",10000),(r"APT[^0-9]{0,35}([0-9]{5,6})\s*元",1)],a)
 wp=num([(r"(?:钨粉|钨粉末)[^0-9]{0,35}([0-9]{3,4}(?:\.[0-9]+)?)\s*元",1)],a)
 wc=num([(r"(?:碳化钨粉|碳化钨)[^0-9]{0,35}([0-9]{3,4}(?:\.[0-9]+)?)\s*元",1)],a)
 wf=num([(r"(?:六氟化钨|WF6)[^0-9]{0,100}([0-9]{4}(?:\.[0-9]+)?)\s*元\s*/?\s*(?:kg|公斤|千克)",1),(r"主流价格[^0-9]{0,20}([0-9]{4})",1)],w)
 band=re.search(r"([0-9]{4})\s*[-~—至]\s*([0-9]{4})\s*元\s*/?\s*(?:kg|公斤|千克)",w)
 oldwf=op.get("wf6_5n") or {}
 lo,hi=(float(band.group(1)),float(band.group(2))) if band else (oldwf.get("low"),oldwf.get("high"))
 prices={
 "concentrate":{"value":conc if conc is not None else keep("concentrate"),"unit":"CNY/t","label":"텅스텐 정광","grade":"65% WO3, China reference","source":"Mysteel"},
 "apt":{"value":apt if apt is not None else keep("apt"),"unit":"CNY/t","label":"APT","grade":"WO3 88.5%","source":"Mysteel"},
 "w_powder":{"value":wp if wp is not None else keep("w_powder"),"unit":"CNY/kg","label":"W powder","grade":"99.7%, China reference","source":"Mysteel"},
 "wc_powder":{"value":wc if wc is not None else keep("wc_powder"),"unit":"CNY/kg","label":"WC powder","grade":"99.7%, China reference","source":"Mysteel"},
 "wf6_5n":{"value":wf if wf is not None else keep("wf6_5n"),"low":lo,"high":hi,"unit":"CNY/kg","label":"WF6 5N","grade":"99.999%, 47L","source":"Mysteel/Longzhong"},
 "wf6_7n_reference":op.get("wf6_7n_reference",{"value":3600,"unit":"CNY/kg","label":"WF6 7N reference","grade":"news reference","stale":True})
 }
 return prices,source_date(a,w),errs

def collect_battery(old):
 errs=[];l=c=""
 try:l=text(URLS["lipf6"])
 except Exception as e:errs.append("lipf6:"+type(e).__name__)
 try:c=text(URLS["lithium"])
 except Exception as e:errs.append("lithium:"+type(e).__name__)
 prev=(old.get("battery") or {}).get("latest") or {}
 pl=prev.get("lipf6") or {};pc=prev.get("lithium_carbonate") or {}
 m=re.search(r"六氟磷酸锂\s+LiPF6[^0-9]{0,30}([0-9]{5,6})\s+([0-9]{5,6})\s+([0-9]{5,6})",l,re.I|re.S)
 if m:llo,lhi,lv=map(float,m.groups())
 else:
  lv=num([(r"六氟磷酸锂[^0-9]{0,120}市场价格[^0-9]{0,30}([0-9]{5,6})",1)],l) or pl.get("value")
  llo,lhi=pl.get("low"),pl.get("high")
 util=num([(r"产能利用率：中国（月）\s*([0-9]+(?:\.[0-9]+)?)",1)],l) or prev.get("utilization_pct")
 prod=num([(r"产量：中国（月）\s*([0-9]{4,6})",1)],l) or prev.get("production_t_month")
 m2=re.search(r"电池级碳酸锂\s+Li2CO3≥99\.5%[^0-9]{0,30}([0-9]{5,6})\s+([0-9]{5,6})\s+([0-9]{5,6})",c,re.I|re.S)
 if m2:clo,chi,cv=map(float,m2.groups())
 else:
  cv=num([(r"电池级碳酸锂[^0-9]{0,100}晚盘市场价格[^0-9]{0,25}([0-9]{5,6})",1),(r"电池级碳酸锂[^0-9]{0,100}早盘市场价格[^0-9]{0,25}([0-9]{5,6})",1)],c) or pc.get("value")
  clo,chi=pc.get("low"),pc.get("high")
 return {"as_of":source_date(l,c) or prev.get("as_of"),
 "lipf6":{"value":lv,"low":llo,"high":lhi,"unit":"CNY/t","label":"LiPF6","grade":"≥99.95%","source":"Mysteel"},
 "lithium_carbonate":{"value":cv,"low":clo,"high":chi,"unit":"CNY/t","label":"Battery-grade Li2CO3","grade":"≥99.5%","source":"Mysteel"},
 "utilization_pct":util,"production_t_month":prod,"source":"Mysteel"},errs

def yahoo(t):
 url="https://query1.finance.yahoo.com/v8/finance/chart/"+quote(t,safe="")+"?range=5d&interval=1d&includePrePost=false"
 r=S.get(url,timeout=20);r.raise_for_status();x=r.json()["chart"]["result"][0];m=x.get("meta",{})
 price=m.get("regularMarketPrice");prev=m.get("chartPreviousClose") or m.get("previousClose")
 if price is None:
  closes=[z for z in x.get("indicators",{}).get("quote",[{}])[0].get("close",[]) if z is not None]
  if closes:price=closes[-1];prev=closes[-2] if len(closes)>1 else prev
 return {"ticker":t,"price":price,"change_pct":((price/prev)-1)*100 if price is not None and prev else None,"currency":m.get("currency"),"exchange":m.get("exchangeName")}
def equities(watch):
 out=[];errs=[]
 for x in watch.get("equities",[]):
  try:q=yahoo(x["ticker"]);q.update(name=x.get("name"),role=x.get("role"));out.append(q)
  except Exception as e:errs.append(x["ticker"]+":"+type(e).__name__)
 return {"as_of":datetime.now(timezone.utc).isoformat(),"items":out},errs
def classify(title):
 t=title.lower()
 for ks,label in [(("lipf6","lithium hexafluorophosphate","六氟磷酸锂"),"LiPF6"),(("wf6","tungsten hexafluoride","六氟化钨"),"WF6"),(("apt","ammonium paratungstate","仲钨酸铵"),"APT"),(("powder","wo3","oxide","钨粉","氧化钨"),"midstream"),(("quota","mine","mining","sangdong","상동"),"mine/concentrate"),(("export control","出口管制","수출통제"),"policy")]:
  if any(k in t for k in ks):return label
 return "materials"
def news():
 out=[];seen=set();errs=[]
 qs=['tungsten OR WF6 OR "ammonium paratungstate" OR Sangdong when:14d','LiPF6 OR "lithium hexafluorophosphate" OR 六氟磷酸锂 when:14d','후성 WF6 LiPF6 when:30d']
 for q in qs:
  try:
   f=feedparser.parse("https://news.google.com/rss/search?q="+quote(q)+"&hl=en-US&gl=US&ceid=US:en")
   for e in f.entries[:30]:
    title=re.sub(r"\s+"," ",e.get("title","")).strip();link=e.get("link","");key=hashlib.sha1((title+link).encode()).hexdigest()
    if not title or key in seen:continue
    seen.add(key);src=e.get("source") or {}
    out.append({"published":e.get("published",""),"title":title,"source":src.get("title","Google News") if isinstance(src,dict) else "Google News","stage":classify(title),"url":link})
  except Exception as e:errs.append("news:"+type(e).__name__)
 return out[:60],errs
def main():
 b=load();old=b.get("latest",{})
 prices,tdate,te=collect_tungsten(old)
 today=tdate or old.get("source_date") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
 hist=b.get("history",[]);row={"date":today,"concentrate":prices["concentrate"]["value"],"apt":prices["apt"]["value"],"w_powder":prices["w_powder"]["value"],"wc_powder":prices["wc_powder"]["value"],"wf6_5n":prices["wf6_5n"]["value"],"note":"auto collector"}
 found=next((x for x in hist if x.get("date")==today),None);found.update(row) if found else hist.append(row);hist.sort(key=lambda x:x.get("date",""));b["history"]=hist[-730:]
 batt,be=collect_battery(b);bh=(b.get("battery") or {}).get("history",[]);bd=batt.get("as_of") or today
 brow={"date":bd,"lipf6":batt["lipf6"]["value"],"lithium_carbonate":batt["lithium_carbonate"]["value"],"utilization_pct":batt.get("utilization_pct"),"production_t_month":batt.get("production_t_month"),"note":"auto collector"}
 bf=next((x for x in bh if x.get("date")==bd),None);bf.update(brow) if bf else bh.append(brow);bh.sort(key=lambda x:x.get("date",""));b["battery"]={"latest":batt,"history":bh[-730:]}
 eq,ee=equities(b.get("watchlist",{}));nw,ne=news()
 b["latest"]={"as_of":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),"source_date":today,"prices":prices,"quota":old.get("quota",{}),"collector":{"mode":"auto","status":"ok" if not(te+be) else "partial","notes":te+be+ee+ne}}
 b["equities"]=eq
 if nw:b["news"]=nw
 save(b)
 print(json.dumps({"tungsten_date":today,"battery_date":bd,"errors":te+be+ee+ne,"news":len(nw)},ensure_ascii=False))
if __name__=="__main__":main()
