"""Stage 1: enumerate food/supplement products on tights.no via the public WP REST API (robots.txt allows /wp-json/)."""
import requests, json, time, sys, os
BASE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..')
OUT=os.path.join(BASE,'data/raw/tights/list.jsonl'); LOG=os.path.join(BASE,'logs/tights.log')
UA="macro-library-personal/1.0 (single-user personal research; github.com/Maxaubert)"
S=requests.Session(); S.headers['User-Agent']=UA
def log(m):
    open(LOG,'a',encoding='utf8').write(time.strftime('%F %T ')+m+'\n'); print(m,flush=True)
def get(url,params):
    for a in range(6):
        time.sleep(1.05)
        r=S.get(url,params=params,timeout=60)
        if r.status_code==200: return r
        log(f'HTTP {r.status_code} {r.url}')
        if r.status_code in (400,): return r
        time.sleep(2**a*2)
    raise SystemExit('blocked')
log('stage1 start')
cats=[]
for p in range(1,6):
    r=get('https://www.tights.no/wp-json/wp/v2/product_cat',{'per_page':100,'page':p,'_fields':'id,name,slug,parent'})
    if r.status_code!=200: break
    cats+=r.json()
json.dump(cats,open(os.path.join(BASE,'data/raw/tights/categories.json'),'w',encoding='utf8'),ensure_ascii=False)
seen=set()
if os.path.exists(OUT):
    seen={json.loads(l)['id'] for l in open(OUT,encoding='utf8')}
f=open(OUT,'a',encoding='utf8'); page=1; n=0
while True:
    r=get('https://www.tights.no/wp-json/wp/v2/product',{'per_page':100,'page':page,'product_cat':'57,58,4279,12491',
        '_fields':'id,slug,link,title,content,excerpt,product_cat,class_list,date,modified,status'})
    if r.status_code!=200: break
    d=r.json()
    if not d: break
    for x in d:
        if x['id'] in seen: continue
        f.write(json.dumps(x,ensure_ascii=False)+'\n'); n+=1
    f.flush(); log(f'page {page} got {len(d)} new total {n}')
    if page>=int(r.headers.get('X-WP-TotalPages',1)): break
    page+=1
log('stage1 done new='+str(n))
