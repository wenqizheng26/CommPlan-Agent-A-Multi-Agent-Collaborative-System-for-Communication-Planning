"""W4-1 independent numerical and requirements regression evidence."""
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

from formula_rag.catalog import load_catalog, validate_card
from formula_rag.core import evaluate
from formula_rag.presentation import formula_view
from planning.agents.requirements import RequirementsAgent

ROOT = Path(__file__).resolve().parents[1]
IDS = ('fresnel_radius', 'knife_edge_nu', 'knife_edge_loss', 'sea_reflection_two_ray')


def exact_diffraction(nu):
    # Simpson integration of Fresnel C and S from zero to nu, independent of J approximation.
    count = 20000
    step = nu / count
    def integrate(fn):
        return step / 3 * (fn(0) + fn(nu) + sum(
            (4 if i % 2 else 2) * fn(i * step) for i in range(1, count)))
    c = integrate(lambda x: math.cos(math.pi * x * x / 2))
    s = integrate(lambda x: math.sin(math.pi * x * x / 2))
    return -20 * math.log10(math.hypot(0.5 - c, 0.5 - s) / math.sqrt(2))


def spherical_reference(p):
    # Minimize actual reflected ray length on a sphere; no P.530 cubic or corrected heights.
    radius = p['k_factor'] * 6375000
    h1, h2 = p['height1_above_sea_m'], p['height2_above_sea_m']
    angle = p['distance_km'] * 1000 / radius
    def segment(h, a):
        return math.hypot(h, 2 * math.sqrt(radius * (radius + h)) * math.sin(a / 2))
    def length(x):
        return segment(h1, x) + segment(h2, angle - x)
    # A visible arc contains the minimum stationary reflected path.
    lo = max(0, angle - math.acos(radius / (radius + h2)))
    hi = min(angle, math.acos(radius / (radius + h1)))
    if lo >= hi: raise ValueError('outside line of sight')
    ratio = (math.sqrt(5) - 1) / 2
    a, b = hi - ratio * (hi-lo), lo + ratio * (hi-lo)
    for _ in range(90):
        if length(a) < length(b):
            hi, b = b, a
            a = hi - ratio * (hi-lo)
        else:
            lo, a = a, b
            b = lo + ratio * (hi-lo)
    x = (lo+hi)/2
    direct = math.hypot(h1-h2, 2*math.sqrt((radius+h1)*(radius+h2))*math.sin(angle/2))
    tau = (length(x)-direct) * p['frequency_ghz'] / 0.3
    return x * radius / 1000, tau, -20*math.log10(2*abs(math.sin(math.pi*tau)))


def p530_geometry(p):
    # Reporting the prescribed intermediate quantities, not the independent oracle.
    d, k, h1, h2 = (p[n] for n in ('distance_km','k_factor','height1_above_sea_m','height2_above_sea_m'))
    m=d*d*1000/(4*k*6375*(h1+h2))
    c=(h1-h2)/(h1+h2)
    b=2*math.sqrt((m+1)/(3*m))*math.cos(math.pi/3+math.acos(3*c/2*math.sqrt(3*m/(m+1)**3))/3)
    d1=d*(1+b)/2
    tau=2*p['frequency_ghz']/0.3*(h1-d1*d1/(12.74*k))*(h2-(d-d1)**2/(12.74*k))*0.001/d
    return d1,tau


def regression_rows():
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        before=Path(tmp)/'before'; after=Path(tmp)/'after'
        raw=json.loads((ROOT/'knowledge/formulas.json').read_text(encoding='utf-8'))
        for folder,cards in ((before,[c for c in raw if c['id'] not in IDS]),(after,raw)):
            shutil.copytree(ROOT/'knowledge',folder/'knowledge',ignore=shutil.ignore_patterns('sources'))
            (folder/'knowledge/formulas.json').write_text(json.dumps(cards),encoding='utf-8')
        agents=[RequirementsAgent(folder,selector=False) for folder in (before,after)]
        for line in (ROOT/'tests/eval/m1_cases.jsonl').read_text(encoding='utf-8').splitlines():
            case=json.loads(line)
            if 'text' not in case: continue
            request=dict(schema_version='1.0.0',task_id='w4-regression',revision=0,request_id='w4-request',
                         raw_text=case['text'],manual_parameters={},condition=None,target=None)
            reports=[a.run(request) for a in agents]
            def signature(r):
                plan=r['calculation_plan_proposal']
                return dict(targets=r['targets'],status=r['execution_status'],
                            chain=[s['tool_id'] for s in plan['steps']] if plan else [])
            def candidates(a):
                return [h['id'] for h in a.last_retrieval['hits'] if h['id'] in a.last_retrieval['used']]
            rows.append(dict(id=case['id'],before=signature(reports[0]),after=signature(reports[1]),
                             candidates_before=candidates(agents[0]),candidates_after=candidates(agents[1]),
                             models_before=[c['model_id'] for c in reports[0]['candidate_models']],
                             models_after=[c['model_id'] for c in reports[1]['candidate_models']],
                             eligible_before=agents[0].last_retrieval['candidate_used'],
                             eligible_after=agents[1].last_retrieval['candidate_used']))
    return rows


class Week4CardTests(unittest.TestCase):
    def setUp(self): self.cards={c['id']:c for c in load_catalog(ROOT)}

    def test_schema_examples_display_and_retrieval(self):
        from planning.retrieval import DefaultRetrievalService
        service=DefaultRetrievalService(ROOT,list(self.cards.values()))
        for ident in IDS:
            card=self.cards[ident]
            self.assertEqual(validate_card(card),[])
            self.assertIn('algorithm' if card.get('kind')=='python_tool' else 'latex',formula_view(card))
            self.assertIn(ident,[h['id'] for h in service.search(card['title'],mode='lexical',top_k=8,top_n=3).hits])
            for example in card['examples']:
                out=evaluate(card,example['inputs'])
                self.assertEqual(out['status'],'ok')
                self.assertAlmostEqual(out['value'],example['expected'],delta=example['tolerance'])

    def test_fresnel_and_nu_independent(self):
        for f,a,b,h in ((2,15,15,20),(6,4,8,-10),(1,2,7,0)):
            radius=math.sqrt((0.299792458/f)*(a*1000)*(b*1000)/((a+b)*1000))
            got=evaluate(self.cards['fresnel_radius'],dict(frequency_ghz=f,d1_km=a,d2_km=b))['value']
            self.assertLessEqual(abs(got/radius-1),0.001)
            theta=h/(a*1000)+h/(b*1000)
            nu=math.copysign(math.sqrt(2*h*theta/(0.299792458/f)),h)
            got=evaluate(self.cards['knife_edge_nu'],dict(frequency_ghz=f,d1_km=a,d2_km=b,obstacle_height_m=h))['value']
            self.assertAlmostEqual(got,nu,delta=max(abs(nu)*1e-9,1e-15))

    def test_diffraction_integral(self):
        self.assertAlmostEqual(exact_diffraction(0),6.020599913279624,places=12)
        for nu in [-0.779]+[i/20 for i in range(-15,101)]:
            got=evaluate(self.cards['knife_edge_loss'],dict(knife_edge_nu=nu))['value']
            self.assertLessEqual(abs(got-exact_diffraction(nu)),0.2,nu)

    def test_spherical_geometry_and_flat_limit(self):
        for distance in (5,10,30):
            p=dict(frequency_ghz=2,distance_km=distance,height1_above_sea_m=30,height2_above_sea_m=25,k_factor=4/3)
            d1,tau,loss=spherical_reference(p)
            approx_d1,approx_tau=p530_geometry(p)
            self.assertLessEqual(abs(d1-approx_d1),0.01)
            self.assertLessEqual(abs(tau/approx_tau-1),0.005)
            self.assertAlmostEqual(evaluate(self.cards['sea_reflection_two_ray'],p)['value'],loss,delta=0.05)
        p['k_factor']=1e9
        tau=2*p['frequency_ghz']/0.3*30*25/(distance*1000)
        self.assertAlmostEqual(evaluate(self.cards['sea_reflection_two_ray'],p)['value'],-20*math.log10(2*abs(math.sin(math.pi*tau))),delta=1e-6)

    def test_boundaries(self):
        for nu in (-0.78,-1): self.assertEqual(evaluate(self.cards['knife_edge_loss'],dict(knife_edge_nu=nu))['status'],'invalid_parameters')
        sea=self.cards['sea_reflection_two_ray']; p=sea['examples'][0]['inputs']
        for name in p:
            self.assertEqual(evaluate(sea,p|{name:0})['status'],'invalid_parameters')
            self.assertEqual(evaluate(sea,{k:v for k,v in p.items() if k!=name})['status'],'missing_parameters')
        self.assertEqual(evaluate(sea,p|dict(distance_km=100))['status'],'invalid_parameters')
        self.assertEqual(evaluate(sea,p|dict(distance_km=5,frequency_ghz=0.0001))['status'],'invalid_parameters')
        for ident in IDS: self.assertEqual(evaluate(self.cards[ident],{})['status'],'missing_parameters')

    def test_requirements_unchanged(self):
        rows=regression_rows()
        self.assertEqual(len(rows),28)
        for row in rows: self.assertEqual(row['before'],row['after'],row['id'])

    def test_unplanned_cards_do_not_displace_budget_targets(self):
        text='按自由空间基准计算链路余量，频率2GHz，距离10km。'
        req=dict(schema_version='1.0.0',task_id='w4',revision=0,request_id='w4-request',
                 raw_text=text,manual_parameters={},condition=None,target=None)
        agent=RequirementsAgent(ROOT,selector=False)
        report=agent.run(req)
        self.assertEqual(report['execution_status'],'AWAITING_INPUT')
        self.assertEqual(report['calculation_plan_proposal']['selected_model'],
                         ['fspl_ghz','received_power','link_margin'])
        self.assertNotIn('EVIDENCE_UNAVAILABLE',[d['code'] for d in report['diagnostics']])
        self.assertTrue(set(agent.last_retrieval['candidate_used']).isdisjoint(IDS))

    def test_candidate_refill_respects_limits_and_lexical_grounding(self):
        from planning.retrieval import RetrievalResult
        class Retrieval:
            def update(self,cards): pass
            def search(self,*args,**kwargs):
                rows=[dict(id=i,rank=n,scores=dict(lexical=score)) for n,(i,score) in enumerate(
                    [('fresnel_radius',1),('received_power',0),('fspl_ghz',0.5),('link_margin',0.4)],1)]
                return RetrievalResult(hits=rows,used=['fresnel_radius'],mode_requested='dense',mode_used='dense',
                    degraded=False,embedding_model_id='stub',reranker_id=None,latency_ms={},corpus={},top_k=4,top_n=1)
        agent=RequirementsAgent(ROOT,selector=False,retrieval=Retrieval(),retrieval_params=dict(top_k=4,top_n=1))
        agent.run(dict(schema_version='1.0.0',task_id='w4',revision=0,request_id='w4-request',
            raw_text='按自由空间基准，频率2GHz，距离1km，求路径损耗。',manual_parameters={},condition=None,target=None))
        self.assertEqual(agent.last_retrieval['candidate_used'],['fspl_ghz'])


if __name__=='__main__': unittest.main()
