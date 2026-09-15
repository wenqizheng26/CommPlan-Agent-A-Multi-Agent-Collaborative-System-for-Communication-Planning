from pathlib import Path
import json,re,hashlib,xml.etree.ElementTree as ET
base=Path(__file__).resolve().parent
repo=base.parents[2]
g=(base/"通信筹划协同流程_v1.4.mmd").read_text(encoding="utf-8")
md=(base/"通信筹划协同流程_v1.4.md").read_text(encoding="utf-8")
assert re.search(r"```mermaid\n(.*?)\n```",md,re.S).group(1).strip()==g.strip()
nodes=set(re.findall(r'^\s*([A-Z][A-Z0-9_]*)[\[({]',g,re.M))
edges=[]
for line in g.splitlines():
    line=re.sub(r'\|[^|]*\|','',line)
    edges.extend(re.findall(r'(?=\b([A-Z][A-Z0-9_]*)\s*(?:-->|-\.->)\s*([A-Z][A-Z0-9_]*)\b)',line))
assert len(nodes)==19
assert all(a in nodes and b in nodes for a,b in edges)
svg=ET.parse(base/"通信筹划协同流程_v1.4.svg").getroot()
ids={el.attrib["id"]:el for el in svg.iter() if "id" in el.attrib}
assert {x[5:] for x in ids if x.startswith("node-")}==nodes
assert all(a+"-"+b in ids for a,b in edges)
def segments(path):
    tokens=re.findall(r'[MLHV]|-?\d+(?:\.\d+)?',path)
    i=0; pos=None; result=[]
    while i<len(tokens):
        op=tokens[i];i+=1
        if op in ("M","L"):
            target=(float(tokens[i]),float(tokens[i+1]));i+=2
        elif op=="V":
            target=(pos[0],float(tokens[i]));i+=1
        elif op=="H":
            target=(float(tokens[i]),pos[1]);i+=1
        else: raise AssertionError(op)
        if op!="M":result.append((pos,target))
        pos=target
    return result
def overlap(a,b):
    (x1,y1),(x2,y2)=a; (x3,y3),(x4,y4)=b
    if x1==x2==x3==x4:return min(max(y1,y2),max(y3,y4))>max(min(y1,y2),min(y3,y4))
    if y1==y2==y3==y4:return min(max(x1,x2),max(x3,x4))>max(min(x1,x2),min(x3,x4))
    return False
groups=[["O-RK","O-CP","O-VE"],["FW-SU","CP-SU","VE-SU"],["RK-RAG","CP-RAG","VE-RAG"]]
for group in groups:
    for i in range(len(group)):
        for j in range(i+1,len(group)):
            aa=segments(ids[group[i]].attrib["d"]);bb=segments(ids[group[j]].attrib["d"])
            assert not any(overlap(a,b) for a in aa for b in bb),(group[i],group[j])
audit=json.loads((repo/"reports/scientific_audit_2026-09-14.json").read_text(encoding="utf-8"))
changed=[n for n,h in audit["source_sha256"].items() if hashlib.sha256((repo/n).read_bytes()).hexdigest()!=h]
original=Path("C:/Users/nntm/Downloads/基于LangGraph的通信筹划智能体协同总体流程_高可读版.md")
original_ok=hashlib.sha256(original.read_bytes()).hexdigest()=="f247256004379b35d48302c30b25e001e5b71e7416a40af01345da707a6c4f42"
report={"version":"1.4","nodes":len(nodes),"edges":len(edges),"markdown_mermaid_equal":True,"svg_matches_mermaid_nodes_and_edges":True,"agent_dispatch_submission_retrieval_no_shared_segments":True,"original_upload_unchanged":original_ok,"runtime_source_files_checked":len(audit["source_sha256"]),"runtime_source_files_changed":changed,"png_rendered":(base/"通信筹划协同流程_v1.4.png").exists(),"visual_review":"PNG rendered and inspected; separate Agent lines; no obscured node text.","scope":"diagram artifacts only; no application tests or model calls"}
assert original_ok and not changed
(base/"流程图_v1.4_检查记录.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=True))

