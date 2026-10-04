"""Shared scope policy for single-link, one-way plans over the supported cards."""
import re
from formula_rag.parsing import extract_request
from planning.requirements_contract import require, SERVICE_LABELS
from planning.services.plans import TARGETS


# A feasibility question is the model's reading of "link margin"; the rules have no keyword for it.
FEASIBILITY = r'can.{0,15}(?:link|communicat)|is.{0,15}(?:feasible|sufficient)|能(?:不能)?通|能否(?:打)?通|通不通|够不够|够用|行不行|可行吗|能否满足|能不能满足|是否满足|满不满足|能满足吗|稳定|更稳|稳不稳|可靠|能(?:不能|否)?传|传(?:视频|图像|数据|语音)|连到|连通|建链|more (?:stable|reliable)|stabl|reliab'
# A link request that names no quantity ("连到乡镇，传视频，要稳定") or names a modulation asks whether
# the link holds: link margin is offered to the model even when its card shares no word with the text.
LINK_REQUEST = re.compile(FEASIBILITY + r'|(?<![A-Za-z0-9])(?:[BQ]PSK|\d+\s*-?\s*(?:QAM|PSK)|QAM\s*-?\s*\d+)', re.I)


# The service a request names ("传视频", "video link"): a report label only, never a calculation input,
# and no promise about throughput. Bare "数据"/"data" is too common to name the service on its own.
SERVICE = re.compile('|'.join(f'(?P<{kind}>{pattern})' for kind, pattern in (
    ('video', r'(?:传输|回传|传送|发送|传)?(?:实时|高清)?视频(?:传输|回传|业务|监控|通话|会议)?'
              r'|\b(?:(?:stream|transmit|send|carry|deliver|transfer)(?:s|ing)?\s+(?:hd\s+|live\s+)?)?video'
              r'(?:\s+(?:link|stream|feed|traffic|transmission|surveillance))?\b'),
    ('voice', r'(?:传输|发送|传)?语音(?:通信|通话|业务|传输)?|\bvoice(?:\s+(?:link|traffic|calls?|service))?\b'),
    ('data', r'(?:传输|回传|发送|传)数据(?:业务)?|数据(?:传输|业务|回传|通信|链路)'
             r'|\b(?:transmit|send|carry|transfer)(?:s|ing)?\s+data\b|\bdata\s+(?:link|traffic|transmission|service|transfer)\b'))),
    re.I)
# A bare "数据"/"data" still counts as a second service ("传视频，数据也要"), so a single label is not given;
# reference material ("数据手册", "the data shows") does not.
BARE_DATA = re.compile(r'数据(?!手册|表|库|集|源|格式|速率|率|量)|\bdata\b(?!\s*(?:sheets?|base|set|rate|shows?|showed|indicates?))', re.I)
# Services joined by a connector ("视频业务和语音业务", "高清视频和实时语音", "video traffic and voice calls")
# share one predicate, so one negation covers them all ("……都不需要"); the gap may carry a modifier.
JOIN = re.compile(r'\s*(?:和|与|及|以及|跟|或|还有|、|/|&|\band\b|\bor\b)\s*(?:传输?|发送)?\s*(?:实时|高清|\bhd\b|\blive\b)?\s*', re.I)
# A clause ends at punctuation or a contrast ("但是", "而是", "but"): "not video but voice" names voice.
CLAUSE = re.compile(r'[，,。；;！!？?\n]|而是|但是|不过|\bbut\b|\binstead\b|\brather\b', re.I)
# Negation before the service ("不是视频", "不需要任何视频", "不传视频", "not video") or after it ("视频不用传").
# A bare "不" counts only right before the match, so "不卡顿地传视频" still names video.
NEGATED_BEFORE = re.compile(r"(?:(?:不是|并非|而非|不需要|不用|无需|不必|没有|不要|不考虑|不含|不包括|不传|别)[^\s，,。；;]{0,4}|不|非)$"
                            r"|\b(?:no|not|without|don't|doesn't|never)\b(?:\s+[\w-]+){0,2}\s*$", re.I)
NEGATED_AFTER = re.compile(r'^\s*(?:就|也|都|暂|暂时|先|并)?(?:不用|不需要|不需|无需|不必|没必要|不要|不传|不考虑|不做)'
                           r"|^\s*(?:is|are)?\s*(?:not|isn't|aren't)\s+(?:needed|required)\b", re.I)


def service_groups(text):
    """Service mentions in order, joined ones grouped: the named phrases plus a bare "数据"/"data" outside them."""
    named = list(SERVICE.finditer(text))
    mentions = sorted(named + [m for m in BARE_DATA.finditer(text) if not any(n.start() <= m.start() < n.end() for n in named)],
                      key=lambda m: m.start())
    groups = []
    for found in mentions:
        if groups and JOIN.fullmatch(text[groups[-1][-1].end():found.start()]):
            groups[-1].append(found)
        else:
            groups.append([found])
    return groups


def negated(text, group):
    return bool(NEGATED_BEFORE.search(CLAUSE.split(text[:group[0].start()])[-1])
                or NEGATED_AFTER.search(CLAUSE.split(text[group[-1].end():])[0]))


def service_label(text):
    """The one service the text asks for, or None when it names none or several (no guessing)."""
    kept = [found for group in service_groups(text) if not negated(text, group) for found in group]
    named = [found for found in kept if found.re is SERVICE]
    if not named or len({found.lastgroup or 'data' for found in kept}) != 1:
        return None
    found = named[0]
    return dict(kind=found.lastgroup, label=SERVICE_LABELS[found.lastgroup], mention=found.group(),
                span=[found.start(), found.end()])


def validate_target_semantics(model):
    for target in model.get('targets', []):
        require(not re.fullmatch(r'\s*(?:解释|介绍|什么是|定义|说明什么是|解释什么是).*(?:余量|损耗|功率|电平)[。？?]?\s*',target['evidence']),'MODEL_TARGET_CONCEPT')
        require(not re.search(r'^(?:explain|define|describe|what does).*(?:loss|margin|power|radius)', target['evidence'].strip(), re.I), 'MODEL_TARGET_CONCEPT')
        parsed = extract_request(target['evidence'])
        feasible = target['id'] == 'link_margin' and re.search(FEASIBILITY, target['evidence'], re.I)
        margin_goal=(target['id']=='link_margin' and bool(re.search(r'(?:要求|需要|希望|至少|不低于|要留|留出|得有).{0,18}余量|余量.{0,18}(?:要求|需要|至少|不低于|达到|达标|[0-9]+\s*dB)',target['evidence'],re.I)))
        require(target['id'] in TARGETS and (parsed['targets'] == [target['id']] or bool(feasible) or margin_goal)
                and not parsed['unsupported_targets'], 'MODEL_TARGET_SEMANTICS')


def intent_conflict(request, parsed):
    target, condition = request['target'], request['condition']
    for clause in re.split(r'[，,。；;\n]', request['raw_text']):
        if re.search(r'(?:不要|不用|不必|无需|不)(?:再|进行)?(?:计算|求出|求|算)(?:.*?)(?:路径损耗|传播损耗|传输损耗)', clause):
            # An explicitly excluded task cannot be reinstated by a dropdown or
            # an affirmative clause elsewhere in the same request.
            return True
        if re.search(r'(?:do not|don.t|not to)\s+(?:calculate|compute|find)', clause, re.I):
            return True
        if re.search(r'(?:not|without)\s+(?:using\s+)?free[ -]space', clause, re.I):
            return True
        if re.search(r'(?:不采用|不用|不要用|不使用|不按|非|不是)(?:.*?自由空间)', clause):
            return True
    return bool((target and parsed['target_origin'] == 'explicit_text' and set(parsed['targets']) != {target})
                or (condition == 'non_free_space' and 'free_space' in parsed['conditions'])
                or (condition in {'free_space','free_space_reference'} and 'non_free_space' in parsed['conditions']))


def outside_scope(text, parsed, targets, conditions):
    if parsed['unsupported_targets'] or any(t not in TARGETS for t in targets):
        return True
    for clause in re.split(r'[，,。；;\n]', text):
        # Only a complete, unambiguous disclaimer is exempt. A negative word
        # inside a contrast or double negative cannot erase a positive request.
        if re.fullmatch(r'\s*(?:不代表|不要求|无需|不计算|不要计算|不求)(?:真实|实际)?(?:海面|海上|海域)(?:传播)?损耗\s*', clause):
            continue
        if re.search(r'(?:真实|实际).{0,8}(?:海面|海上|海域).{0,8}(?:损耗|传播)', clause):
            return True
        if re.search(r'(?:actual|real).{0,20}(?:sea|ocean).{0,20}(?:loss|propagation)|(?:actual|real).{0,20}(?:loss|propagation).{0,20}(?:sea|ocean)', clause, re.I):
            return True
        if re.search(r'双程|往返|雷达回波|双向雷达|two[ -]way|round[ -]trip|radar echo', clause, re.I):
            return True
    supplements = bool(targets) and set(targets) <= {'fresnel_radius', 'knife_edge_nu', 'knife_edge_loss', 'sea_reflection_two_ray'}
    return not supplements and 'non_free_space' in conditions and 'free_space_reference' not in conditions
