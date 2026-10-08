import {relevantEvents} from './flow.mjs';
import {parameterNames, toolNames} from './details.mjs';
import {REASONS} from './timing.mjs';

export const purposeNames = {intent:'需求解析', supplement:'合并补充', followup:'换用追问', suggest:'默认补全建议',
 compute_agent:'写计划与适用性评估', validator_agent:'解释与审查', extraction:'资料抽取'};
const AGENTS = {intent:'需求与规划', supplement:'需求与规划', followup:'需求与规划', suggest:'需求与规划',
 compute_agent:'专业计算', validator_agent:'验证与解释', extraction:'资料抽取'};
const CALLERS = {requirements:'需求与规划', supplement:'需求与规划', suggest:'需求与规划', compute_agent:'专业计算',
 validator_agent:'验证与解释', extraction:'资料抽取'};
const PARAMETERS = {...parameterNames, frequency_mhz:'载波频率', modulation:'调制方式',
 rx_sensitivity_dbm:'接收灵敏度', required_margin_db:'要求余量'};
const TOOLS = {...toolNames, fspl_mhz:'自由空间损耗', calc_link_margin:'链路余量计算'};
const STATUS = {running:'运行中', completed:'完成', failed:'失败'};
const time = value => Date.parse(value);
const ordered = values => [...values].sort((a,b) => (time(a.at) - time(b.at) || 0) || (a.seq || 0) - (b.seq || 0));
const identity = (event, index) => String(event.seq ?? event.id ?? event.event_id ?? `${event.run_id || ''}:${event.at || ''}:${index}`);

function modelCard(state, start, end, index) {
 const details = {...start.details, ...end?.details}, purpose = details.purpose || details.caller || '';
 const duration = end ? (Number.isFinite(details.latency_ms) ? details.latency_ms : time(end.at) - time(start.at)) : null;
 return {kind:'model', agent:AGENTS[purpose] || CALLERS[details.caller] || details.caller || '需求与规划',
  purpose, status:end?.phase || 'running', model:details.model_id || '',
  duration_ms:Number.isFinite(duration) ? Math.max(0, duration) : null, reason:details.reason || '', started_at:start.at,
  finished_at:end?.at || null, caller:details.caller || '', task_id:state.task_id, revision:state.revision,
  run_id:start.run_id, key:`model:${identity(start,index)}`};
}

function toolCard(details, key, at) {
 if (details.tool_id === 'calc_link_margin' || details.tool === 'calc_link_margin') {
  return {kind:'tool', tool:'calc_link_margin', label:details.label || '', arguments:details.arguments || {},
   result:details.result || {}, steps:details.steps || [], key, started_at:at};
 }
 return {kind:'tool', agent:'专业计算', tool:details.tool_id || details.tool || details.card?.id || details.card || '',
  inputs:details.inputs || {}, output:details.output || {value:details.value, unit:details.unit || ''}, key, started_at:at};
}

// Activity is observation only. Never change the saved business state or its events.
export function records(state, events = []) {
 if (!state) return [];
 const current = ordered(relevantEvents(state, events)), cards = [], open = new Map();
 for (const [index,event] of current.entries()) {
  const details = event.details || {};
  if (event.node === 'llm') {
   const slot = `${event.run_id || ''}|${details.caller || ''}|${details.purpose || ''}`;
   if (event.phase === 'started') {
    const card = modelCard(state, event, null, index);
    cards.push(card);
    const queue = open.get(slot) || [];
    queue.push({event,card,index}); open.set(slot,queue);
   } else if (['completed','failed'].includes(event.phase)) {
    const queue = open.get(slot);
    const match = details.attempt == null ? 0 : queue?.findIndex(entry => entry.event.details?.attempt === details.attempt);
    const started = queue?.length && match >= 0 ? queue.splice(match,1)[0] : null;
    if (started) Object.assign(started.card, modelCard(state, started.event, event, started.index));
   }
  } else if (event.node === 'tool' && event.phase === 'completed') {
   cards.push(toolCard(details, `tool:${identity(event,index)}`, event.at));
  }
 }
 if (!current.length) {
  const calls = state.final_report?.tool_calls;
  const steps = Array.isArray(calls) && calls.length ? calls : state.result?.steps || [];
  for (const [index,step] of steps.entries()) cards.push({...toolCard(step, `history:${index}`, null), historical:true});
 }
 return cards.sort((a,b) => (time(a.started_at) - time(b.started_at)) || 0);
}

// Model log timestamps represent each HTTP call. One activity span can include retries.
export function matchModelCalls(card, calls = []) {
 if (card.kind !== 'model') return [];
 const agent = card.purpose === 'intent' ? 'requirements' : card.purpose === 'supplement' ? 'supplement' : card.caller;
 const start = time(card.started_at), end = card.finished_at ? time(card.finished_at) : Infinity;
 if (!Number.isFinite(start)) return [];
 return ordered(calls.filter(call => call.task_id === card.task_id && call.revision === card.revision && call.agent === agent &&
  (call.run_id == null || call.run_id === card.run_id) &&
  time(call.at) >= start - 2000 && time(call.at) <= end + 2000));
}

export function numeric(value) {
 return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : String(value ?? '—');
}
function unit(name) {
 return name.endsWith('_dbm') ? 'dBm' : name.endsWith('_dbi') ? 'dBi' : name.endsWith('_db') ? 'dB' :
  name.endsWith('_mhz') ? 'MHz' : name.endsWith('_ghz') ? 'GHz' : name.endsWith('_km') ? 'km' :
  name.endsWith('_m') ? 'm' : name.endsWith('_deg') ? '°' : '';
}
export function parameterLine(inputs = {}) {
 return Object.entries(inputs).map(([name,value]) => `${PARAMETERS[name] || name} = ${numeric(value)}${unit(name) ? ' ' + unit(name) : ''}`).join('，');
}
export function modelLine(card) {
 const agent = card.agent === '资料抽取' ? card.agent : `${card.agent} Agent`;
 return `${agent} → ${card.model || '本机模型'} · ${purposeNames[card.purpose] || card.purpose} · ${STATUS[card.status] || card.status}` +
  (card.duration_ms == null ? '' : ` · ${(card.duration_ms / 1000).toFixed(1)} s`);
}
export function toolLine(card) {
 return `专业计算 Agent → ${card.tool}：${parameterLine(card.inputs || card.arguments)} → ` +
  (card.tool === 'calc_link_margin' ? `${numeric(card.result?.link_margin_db)} dB` : `${numeric(card.output?.value)} ${card.output?.unit || ''}`).trimEnd();
}

const hosts = new WeakMap();
function el(tag, text, className) {
 const node = document.createElement(tag);
 if (text != null) node.textContent = String(text);
 if (className) node.className = className;
 return node;
}
function raw(tag, text, className) {
 const node = el(tag,text,className); node.setAttribute('translate','no'); return node;
}
function pretty(value) {
 if (typeof value !== 'string') return JSON.stringify(value,null,2) ?? '';
 try { return JSON.stringify(JSON.parse(value),null,2); } catch { return value; }
}
function logsContent(host, calls) {
 host.replaceChildren();
 if (!calls.length) { host.append(el('p','日志中没有对应记录','hint')); return; }
 for (const call of calls) {
  const section = el('section',null,'record-log-entry');
  section.append(raw('p', `${call.model || ''} · ${call.status || ''}${Number.isFinite(call.latency_ms) ? ` · ${(call.latency_ms / 1000).toFixed(1)} s` : ''}`));
  for (const message of call.messages || []) section.append(raw('strong',message.role),raw('pre',pretty(message.content),'record-log-text'));
  section.append(raw('strong','response'),raw('pre',pretty(call.response),'record-log-text'));
  host.append(section);
 }
}
function loadLogs(ctx, generation, runId) {
 if (ctx.logs?.generation !== generation) ctx.logs = {generation,promises:new Map()};
 const cache = ctx.logs;
 function load(run) {
  const key = run || '';
  if (cache.promises.has(key)) return cache.promises.get(key);
  const promise = Promise.resolve().then(async () => {
   const endpoint = `/api/tasks/${encodeURIComponent(ctx.task_id)}/model-calls` + (run ? `?run_id=${encodeURIComponent(run)}` : '');
   const response = await ctx.fetch(endpoint);
   if (!response.ok) throw new Error('MODEL_LOG_READ_FAILED');
   const data = await response.json(), calls = data.calls || [];
   // Old log rows have no run_id. Keep their existing time-window match without admitting other runs.
   if (run && !calls.length) return (await load(null)).filter(call => call.run_id == null);
   return calls;
  });
  cache.promises.set(key,promise);
  promise.catch(() => { if (cache.promises.get(key) === promise) cache.promises.delete(key); });
  return promise;
 }
 return load(runId);
}
async function showLogs(ctx, item) {
 const generation = ctx.generation, card = item.card;
 if (item.loaded === generation || item.loading === generation) return;
 item.loading = generation;
 item.content.replaceChildren(el('p','正在读取调用日志…','hint'));
 try {
  const calls = await loadLogs(ctx,generation,card.run_id);
  // A poll or task switch can complete while the request is in flight.
  if (generation !== ctx.generation || item.card.key !== card.key) return;
  logsContent(item.content,matchModelCalls(item.card,calls)); item.loaded = generation;
 } catch {
  if (generation === ctx.generation) item.content.replaceChildren(el('p','调用日志读取失败，请收起后重试。','hint'));
 } finally { if (item.loading === generation) item.loading = null; }
}
function cardElement(ctx, card) {
 const node = el('article',null,`record-card ${card.kind} execution-record record-${card.kind}`), badge = el('span',card.kind === 'model' ? '模型调用' : '工具计算','record-kind');
 node.setAttribute('data-record-key',card.key);
 const line = el('p',null,'record-summary'), reason = el('p',null,'hint record-reason'), body = el('div',null,'record-body');
 node.append(badge,line,reason,body);
 const item = {node,line,reason,body,card};
 if (card.kind === 'model') {
  item.details = el('details',null,'record-prompt'); item.content = el('div',null,'record-log-content');
  item.details.append(el('summary','查看 prompt 与 response'),item.content); node.append(item.details);
  item.details.addEventListener('toggle',() => { if (item.details.open) void showLogs(ctx,item); });
 }
 return item;
}
function updateCard(item, card) {
 item.card = card;
 item.line.textContent = card.kind === 'model' ? modelLine(card) : toolLine(card);
 item.reason.textContent = card.reason ? REASONS[card.reason] || card.reason : '';
 item.reason.setAttribute('translate',card.reason && !REASONS[card.reason] ? 'no' : 'yes');
 item.reason.hidden = !card.reason;
 item.body.replaceChildren();
 if (card.kind !== 'tool') return;
 const name = el('p',TOOLS[card.tool] || card.tool,'hint'); item.body.append(name);
 if (card.tool === 'calc_link_margin') {
  if (card.label) item.body.append(raw('strong',card.label));
  const result = card.result || {}, dl = el('dl',null,'record-results');
  const values = [['FSPL',result.path_loss_db,'dB'],['Prx',result.rx_power_dbm,'dBm'],['接收灵敏度',result.rx_sensitivity_dbm,'dBm'],
   ['链路余量',result.link_margin_db,'dB'],['要求余量',result.required_margin_db ?? 0,'dB']];
  for (const [label,value,units] of values) dl.append(el('dt',label),raw('dd',`${numeric(value)} ${units}`));
  const meets = typeof result.meets === 'boolean' ? result.meets : Number.isFinite(result.link_margin_db) ? result.link_margin_db >= (result.required_margin_db ?? 0) : null;
  dl.append(el('dt','是否满足'),el('dd',meets == null ? '—' : meets ? '满足' : '不满足')); item.body.append(dl);
 }
}

// Keep the host element between polls; existing cards (including open details) stay in place.
export function renderRecords(host, state, events = [], options = {}) {
 const cards = records(state,events), identity = `${state?.task_id || ''}|${state?.revision ?? ''}`;
 let ctx = hosts.get(host);
 if (!ctx || ctx.identity !== identity) {
  ctx = {identity,task_id:state?.task_id,items:new Map(),fetch:options.fetch || ((...args) => globalThis.fetch(...args)),
   note:el('p',null,'hint records-note'),list:el('div',null,'records-list')};
  host.replaceChildren(el('h3','执行记录'),ctx.note,ctx.list); hosts.set(host,ctx);
 }
 ctx.fetch = options.fetch || ((...args) => globalThis.fetch(...args));
 ctx.generation = cards.filter(card => card.kind === 'model' && card.status !== 'running').map(card => `${card.key}:${card.finished_at}`).join('|');
 ctx.note.textContent = cards.some(card => card.historical) ? '历史版本只显示工具计算' : !cards.length ? '暂无执行记录。' : '';
 ctx.note.hidden = !!cards.length && !cards.some(card => card.historical);
 const keys = new Set(cards.map(card => card.key));
 for (const [key,item] of ctx.items) if (!keys.has(key)) { item.node.remove(); ctx.items.delete(key); }
 for (const card of cards) {
  let item = ctx.items.get(card.key);
  if (!item) { item = cardElement(ctx,card); ctx.items.set(card.key,item); ctx.list.append(item.node); }
  updateCard(item,card);
  if (item.details?.open) void showLogs(ctx,item);
 }
 host.hidden = !state;
 return cards;
}
