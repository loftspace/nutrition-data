import sys, json, importlib.util
sys.argv=['x','none']
sp=importlib.util.spec_from_file_location('ng','norgesgruppen.py'); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
out=open(m.OUT+'/brands.jsonl','a',encoding='utf8')
for chain in ('meny','spar','joker'):
    cid=m.CHAINS[chain][0]; base=f"{m.API}/{cid}/0"
    f=m.get(base,{"page_size":1,"facets":"Category"})
    for b in f['aggregations']['Categories']['buckets'] if 'aggregations' in f else []: pass
    first=m.get(base,{"page_size":1,"fieldset":"maximal","full_response":"true","facets":"Category"})
    for b in first['aggregations']['Categories']['buckets']:
        page=1
        while True:
            d=m.get(base,{"page_size":500,"page":page,"fieldset":"minimal","facet":"Categories:"+b['key'],"sort":"ean.raw"})
            hs=d['hits'] if d else []
            for h in hs: out.write(json.dumps({"ean":h['ean'],"brand":h.get('brand'),"vendor":h.get('vendor')},ensure_ascii=False)+"\n")
            if len(hs)<500: break
            page+=1
        out.flush()
    m.log(f"brands {chain} done req={m.STATE['req']}")
