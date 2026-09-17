from pathlib import Path
from html import escape
import json, re, hashlib

ROOT=Path(__file__).resolve().parent
W,H=1840,2130
parts=[]
def add(s): parts.append(s)
def text(x,y,lines,size=23,color="#24374d",weight=400,anchor="middle",step=31):
    if isinstance(lines,str): lines=[lines]
    add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-size="{size}" font-weight="{weight}">')
    for i,line in enumerate(lines):
        add(f'<tspan x="{x}" dy="{0 if i==0 else step}">{escape(line)}</tspan>')
    add('</text>')
def label(x,y,s,color="#4c5d71",size=19):
    width=sum(1 if ord(c)>255 else .57 for c in s)*size+20
    add(f'<rect x="{x-width/2}" y="{y-size+1}" width="{width}" height="{size+8}" rx="5" fill="#fff" fill-opacity=".97"/>')
    text(x,y,s,size,color)
def edge(id,d,color="#6c8096",dashed=False,width=2.6):
    # A white halo makes crossings distinct instead of looking like junctions.
    add(f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{width+5}" stroke-linejoin="round"/>')
    add(f'<path id="{id}" d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" marker-end="url(#arrow-{color[1:]})"'+(' stroke-dasharray="7 6"' if dashed else '')+'/>')
def box(id,x,y,w,h,title,desc=(),kind="program",title_size=25,desc_size=22):
    palettes={"user":("#edf7f1","#6aa48a"),"agent":("#f3edfb","#a88ac4"),"program":("#edf4fc","#7c9abc"),"tool":("#ebf6f6","#77aaad"),"store":("#f3f5f8","#9ba8b8"),"stop":("#fff0eb","#c5907e")}
    fill,stroke=palettes[kind]
    add(f'<g id="node-{id}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2 if id in ("U","CHOICE") else 13}" fill="{fill}" stroke="{stroke}" stroke-width="1.7"/>')
    total=30+len(desc)*29
    top=y+(h-total)/2+23
    text(x+w/2,top,title,title_size,weight=650)
    if desc: text(x+w/2,top+31,desc,desc_size,color="#4b5d73",step=29)
    add('</g>')
def cylinder(id,x,y,w,h,title,desc):
    add(f'<g id="node-{id}"><path d="M{x},{y+12} C{x},{y-4} {x+w},{y-4} {x+w},{y+12} V{y+h-12} C{x+w},{y+h+4} {x},{y+h+4} {x},{y+h-12} Z" fill="#f3f5f8" stroke="#9ba8b8" stroke-width="1.7"/>')
    add(f'<path d="M{x},{y+12} C{x},{y+28} {x+w},{y+28} {x+w},{y+12}" fill="none" stroke="#9ba8b8" stroke-width="1.3"/>')
    text(x+w/2,y+47,title,24,weight=650)
    if desc: text(x+w/2,y+79,desc,21,step=28)
    add('</g>')

colors=["#6c8096","#398b9e","#7759a8","#b77736","#8b98aa"]
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="svg-title svg-desc">')
add('<title id="svg-title">通信筹划多 Agent 协同流程 v1.4</title><desc id="svg-desc">包含十九个主要节点。三个专业 Agent 分别接受调度、分别提交产物、分别检索共享知识；所有数值由程序计算，确认后执行，当前版本审查有效后发布。</desc>')
add('<defs>')
for c in colors:
    add(f'<marker id="arrow-{c[1:]}" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L9,4 L0,8 Z" fill="{c}"/></marker>')
add('</defs>')
add('<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC","SimHei",sans-serif;} path,rect{vector-effect:non-scaling-stroke;}</style>')
add(f'<rect width="{W}" height="{H}" fill="#fff"/>')
text(92,57,"通信筹划 · 多 Agent 协同流程",39,weight=700,anchor="start")
text(94,92,"v1.4  ·  19 个主要节点，三个专业 Agent 独立连线",22,color="#65758a",anchor="start")
add('<rect x="110" y="220" width="1620" height="1490" rx="24" fill="#fbfcfe" stroke="#c6d1df" stroke-width="1.6"/>')
text(140,259,"LangGraph / StateGraph",25,weight=650,anchor="start")
text(1700,259,"按状态调度角色 · 程序约束流程",20,color="#68788c",anchor="end")
add('<rect x="110" y="1745" width="1620" height="335" rx="22" fill="#fbfcfe" stroke="#c6d1df" stroke-width="1.6"/>')
text(140,1783,"共享知识支持",25,weight=650,anchor="start")
text(1700,1783,"下列名称引用上方三个 Agent · 按需调用同一检索服务",20,color="#68788c",anchor="end")

# Main flow. Each Agent has a different source port and a separate destination port.
edge("U-START","M920 191 V285")
edge("START-O","M920 353 V415")
edge("O-RK","M680 520 V566 H370 V625","#398b9e")
edge("O-CP","M920 520 V625","#7759a8")
edge("O-VE","M1160 520 V566 H1470 V625","#b77736")
edge("RK-FW","M370 729 V765","#398b9e")
edge("FW-SU","M370 849 V900","#398b9e")
edge("CP-SU","M920 729 V900","#7759a8")
edge("VE-SU","M1470 729 V900","#b77736")
edge("SU-GATE","M920 984 V1010")
edge("GATE-O","M807.5 1045 H610 V996 H75 V465 H620")
edge("GATE-HITL","M695 1080 H550")
edge("HITL-SU","M170 1110 H135 V942 H170")
edge("GATE-STOP","M1145 1080 H1290")
edge("GATE-TOOL","M920 1150 V1220")
edge("GATE-OUT","M807.5 1115 H635 V1200 H380 V1230")
edge("TOOL-EA","M920 1332 V1390")
edge("EA-CMP","M920 1478 V1535")
edge("CMP-SU","M1130 1584 H1710 V954 H1670")
edge("OUT-CHOICE","M380 1338 V1435")
edge("SU-GS","M1670 925 H1690 V1492 H1670","#8b98aa",True,2)
edge("GS-O","M1480 1554 V1672 H1770 V465 H1220","#8b98aa",True,2)

# Independent knowledge calls are shown below, apart from task-control lines.
edge("RK-RAG","M370 1834 V1890","#398b9e",True,2.5)
edge("CP-RAG","M920 1834 V1890","#7759a8",True,2.5)
edge("VE-RAG","M1470 1834 V1890","#b77736",True,2.5)
edge("RAG-KB","M920 1970 V1993","#8b98aa",True,2)

box("U",710,115,420,76,"用户输入自然语言",["目标、条件或后续修改"],"user")
box("START",710,285,420,68,"任务入口",["新任务 / 更新已有任务"])
box("O",620,415,600,105,"Orchestrator Agent · 总控",["依据任务状态选择合法下一步"],"agent",28)
box("RK",170,625,400,104,"需求与知识 Agent",["理解目标、硬约束与缺项"],"agent")
box("CP",720,625,400,104,"计算规划 Agent",["选择模型、公式链与搜索计划"],"agent")
box("VE",1270,625,400,104,"验证与解释 Agent",["审查证据、结果与方案取舍"],"agent")
box("FW",210,765,320,84,"结构化抽取 Worker",["抽取 / 更新字段 · 自动填表"],"tool",23,20)
box("SU",170,900,1500,84,"程序校验与状态提交",["分别接收各节点产物 · 校验权限、格式与版本"],"program")
add('<g id="node-GATE"><path d="M920 1010 L1145 1080 L920 1150 L695 1080 Z" fill="#fff5df" stroke="#bc913d" stroke-width="1.8"/></g>')
text(920,1073,"确定性条件路由",25,weight=650)
text(920,1107,"缺项 / 确认 / 进度 / 预算",20)
box("HITL",170,1020,380,140,"用户核对与确认",["补充或修正表格","确认模型、约束与可调范围","Interrupt / Resume"],"user",25,20)
box("STOP",1290,1020,380,140,"停止受影响分支并报告",["能力缺口 / 故障 / 预算耗尽","保留有效部分结果"],"stop",24,20)
box("TOOL",710,1220,420,112,"确定性执行子图",["候选生成 → 前置校核","批量计算 → 后置校核"],"tool")
box("EA",710,1390,420,88,"逐方案工程评估 · 程序",["满足 / 不满足 / 暂无法判定 / 不涉及"],"tool",25,19)
box("CMP",710,1535,420,98,"方案比较 · 程序",["并列比较不同取舍","保留未达标与未完成原因"],"tool",25,21)
box("OUT",170,1230,420,108,"结果与证据包",["方案对比、数值、公式与来源","适用范围、假设与版本"])
box("CHOICE",170,1435,420,84,"用户选择并保存",["修改时继续自然语言输入"],"user")
cylinder("GS",1290,1430,380,124,"Graph State + 本地检查点",["参数、确认、计划、证据","候选、结果、审查与版本"])
box("RAG",170,1890,1500,80,"共享 RAG 检索",["模型依据、参数定义、适用条件与证据"],"tool")
cylinder("KB",665,1993,510,66,"本地知识库",[])
text(1310,2029,"标准、公式依据、经审核资料",20,color="#65758a",anchor="start")

label(504,551,"需求理解 / 参数更新","#398b9e")
label(990,589,"规划 / 调整","#7759a8")
label(1345,551,"审查 / 解释追问","#b77736")
label(448,881,"字段与依据","#398b9e")
label(920,825,"模型与计算计划","#7759a8")
label(1470,825,"审查与解释","#b77736")
label(362,996,"待规划 / 待审查")
label(623,1064,"补充 / 确认",size=18)
label(1218,1064,"无法继续",size=18)
label(1035,1187,"确认有效且可执行",size=18)
label(405,1199,"当前版本审查有效且可发布",size=18)
label(455,1385,"查看方案取舍",size=18)
label(1450,1609,"执行、评估与比较记录返回",size=19)
text(1480,1393,"共享任务数据",21,color="#718196")
text(1370,1639,"仅作必要状态读取",19,color="#718196")
text(370,1827,"需求与知识 Agent",23,color="#398b9e",weight=600)
text(920,1827,"计算规划 Agent",23,color="#7759a8",weight=600)
text(1470,1827,"验证与解释 Agent",23,color="#b77736",weight=600)
text(140,2109,"实线：任务流程    虚线：知识或状态访问    总控三个出口为条件选择，不表示必须并行执行",20,color="#68788c",anchor="start")
text(1700,2109,"目标设计 · 尚未实现",20,color="#68788c",anchor="end")
add('</svg>')
(ROOT/"通信筹划协同流程_v1.4.svg").write_text("\n".join(parts),encoding="utf-8")
print(json.dumps({"svg":str(ROOT/"通信筹划协同流程_v1.4.svg"),"nodes":19,"size":[W,H]},ensure_ascii=False))
