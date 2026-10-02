// Local browser QA only. All model observations and composite events are test doubles.
// Run: node tests/teacher_ui_preview.mjs; Ctrl+C closes this independently owned server.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const web = path.join(root, 'planning', 'web');
const fixtures = path.join(root, 'tests', 'fixtures', 'teacher_ui');
const modules = [
 'records.mjs', 'details.mjs', 'flow.mjs', 'model-status.mjs', 'values.mjs',
 'text.mjs', 'roles.mjs', 'settings.mjs', 'timing.mjs', 'm1.mjs', 'i18n.mjs',
 'i18n-en.mjs',
];
const assets = new Map(modules.map(name => ['/' + name, [path.join(web, name), 'text/javascript']]));
assets.set('/app.css', [path.join(web, 'app.css'), 'text/css']);
for (const name of ['records-model.json', 'margin-completed.json']) {
 assets.set('/fixtures/' + name, [path.join(fixtures, name), 'application/json']);
}

const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Teacher UI test doubles</title><link rel="stylesheet" href="/app.css">
<link rel="stylesheet" href="/preview.css"><script type="module" src="/preview.mjs"></script></head>
<body><main class="preview-main"><h1>Teacher UI browser test doubles</h1>
<p class="preview-note" translate="no">TEST FIXTURE ONLY: model events, model names, prompts, responses and failures are synthetic.
Composite tool events follow the future page contract; numeric values came from the existing tool registry.
No live model, workbench or business state is changed.</p>
<div class="preview-controls"><button id="language" type="button">EN / 中文</button>
<button id="refresh-records" type="button">Refresh records (keep expanded cards)</button>
<button id="append-events" type="button">Append two composite tool events</button></div>
<p id="fetch-count" translate="no">Model log requests: 0</p>
<section id="records-preview"></section><pre id="preview-error" hidden translate="no"></pre>
</main></body></html>`;

const script = `import {renderRecords} from './records.mjs';
import {lang,setLang,install,watch} from './i18n.mjs';
const fixture=await (await fetch('/fixtures/records-model.json')).json();
const host=document.getElementById('records-preview');
const full=fixture.events;let visible=full.slice(0,6),requests=0;
if(lang()==='en'){install(await import('./i18n-en.mjs'));watch(document.body);}
const trackedFetch=async (...args)=>{requests++;document.getElementById('fetch-count').textContent='Model log requests: '+requests;return fetch(...args);};
function draw(){try{renderRecords(host,fixture.state,visible,{fetch:trackedFetch});}catch(error){const node=document.getElementById('preview-error');node.hidden=false;node.textContent=error.stack||String(error);throw error;}}
document.getElementById('refresh-records').addEventListener('click',draw);
document.getElementById('append-events').addEventListener('click',()=>{visible=full;draw();document.getElementById('append-events').disabled=true;});
document.getElementById('language').addEventListener('click',()=>{setLang(lang()==='en'?'zh':'en');location.reload();});
draw();`;

const css = `body{height:auto;overflow:auto}.preview-main{display:block;max-width:1120px;margin:0 auto;padding:24px;height:auto;overflow:visible}
.preview-main h1{font-size:24px}.preview-note{border:1px solid #b97f1d;background:#fff8df;padding:14px;line-height:1.6}
.preview-controls{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}#records-preview{min-height:200px}`;

function respond(res, status, body, type) {
 res.writeHead(status, {'Content-Type': type + '; charset=utf-8', 'Cache-Control': 'no-store',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"});
 res.end(body);
}
const server = http.createServer(async (req, res) => {
 const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
 try {
  if(req.method !== 'GET')return respond(res,405,'Only GET is supported','text/plain');
  if(pathname === '/')return respond(res,200,html,'text/html');
  if(pathname === '/preview.mjs')return respond(res,200,script,'text/javascript');
  if(pathname === '/preview.css')return respond(res,200,css,'text/css');
  if(pathname === '/api/tasks/teacher-ui-records-model/model-calls') {
   const fixture = JSON.parse(await readFile(path.join(fixtures,'records-model.json'),'utf8'));
   return respond(res,200,JSON.stringify({...fixture.model_calls,calls:[...fixture.model_calls.calls,...fixture.excluded_calls]}),'application/json');
  }
  const asset = assets.get(pathname);
  if(!asset)return respond(res,404,'Not found','text/plain');
  respond(res,200,await readFile(asset[0]),asset[1]);
 }catch(error){respond(res,500,String(error),'text/plain');}
});
server.listen(0,'127.0.0.1',()=>process.stdout.write('Teacher UI test-double preview: http://127.0.0.1:'+server.address().port+'\n'));
process.on('SIGINT',()=>server.close(()=>process.exit(0)));
process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
