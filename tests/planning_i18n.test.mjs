import test from 'node:test';
import assert from 'node:assert/strict';
import {install,t} from '../planning/web/i18n.mjs';
import * as en from '../planning/web/i18n-en.mjs';
import {readFileSync} from 'node:fs';

test('attachment guidance translates while preserving the supplied document title',()=>{
 install(en);
 assert.equal(t('已添加：附件验收手册（模拟）。请选择片段，抽取并核对草稿后填写审核人，通过后才能参与计算。'),
  'Added: 附件验收手册（模拟）. Select sections, extract and check the draft, then enter a reviewer. Only approved data can be used in calculations.');
});

test('confirmed supplementary results translate their registered labels',()=>{
 install(en);
 for(const text of ['按已确认输入，海面反射附加损耗（相对自由空间） 5.13 dB。','按已确认输入，第一菲涅耳区半径 33.50 m。',
  '按已确认输入，绕射参数 0.60 1。','按已确认输入，单刃形绕射损耗 10.20 dB。']){
  assert.match(t(text),/^With the confirmed inputs,/);
  assert.doesNotMatch(t(text),/[\u3400-\u9fff]/u);
 }
});

test('supplementary and MHz loss cards translate each displayed Chinese sentence in full',()=>{
 install(en);
 const ids=['fresnel_radius','knife_edge_nu','knife_edge_loss','sea_reflection_two_ray','fspl_mhz'];
 const cards=JSON.parse(readFileSync(new URL('../knowledge/formulas.json',import.meta.url),'utf8')).filter(c=>ids.includes(c.id));
 assert.equal(cards.length,5);
 for(const c of cards){
  const texts=[c.title,c.description,...Object.values(c.parameters).flatMap(p=>[p.description,p.default?.note]),
   ...c.applicability.notes,c.algorithm,...c.sources.map(s=>s.derivation)].filter(Boolean);
  for(const text of texts){
   if(!/[\u3400-\u9fff]/u.test(text))continue;
   assert.ok(Object.hasOwn(en.EXACT,text),`${c.id}: ${text}`);
   assert.notEqual(t(text),text);
   assert.doesNotMatch(t(text),/[\u3400-\u9fff]/u);
  }
 }
});

test('without a dictionary the Chinese source is shown as is',()=>{
 install({});
 assert.equal(t('确认执行'),'确认执行');
});

test('whole strings, templates and server errors translate; unknown text is left alone',()=>{
 install(en);
 assert.equal(t('确认执行'),'Confirm and run');
 assert.equal(t('  确认执行 '),'  Confirm and run ');
 assert.equal(t('3/8 校验通过'),'3/8 checks passed');
 assert.equal(t('词项检索 · 知识库 12 条 · 返回 8/8 · 送入 3 · 15 ms · 请求向量，向量未就绪'),
  'Lexical retrieval · 12 entries · returned 8/8 · sent 3 · 15 ms · requested dense, embeddings not ready');
 assert.equal(t('未找到该任务，请检查任务编号或新建任务。 [TASK_NOT_FOUND]'),'Task not found; check the task ID or start a new task. [TASK_NOT_FOUND]');
 assert.equal(t('Qwen3 4B · Q4_K_M · 标准 未加载。'),'Qwen3 4B · Q4_K_M · standard is not loaded.');
 // A sentence with one unknown phrase stays whole rather than half translated.
 assert.equal(t('需求理解，某个没有登记的说法'),'需求理解，某个没有登记的说法');
 assert.equal(t('2 GHz'),'2 GHz');
});

test('conclusions and questions read as English sentences',()=>{
 install(en);
 assert.equal(t('按已确认自由空间条件，链路余量 -3.20 dB（扣除预留余量后低于门限），低于要求的 8 dB；发射功率至少需 41.20 dBm 才能满足，超过所选电台的额定发射功率 30 dBm。'),
  'Under the confirmed free-space conditions, the link margin is -3.20 dB (below the threshold after the reserved margin), below the required 8 dB; '
  +'the transmit power must be at least 41.20 dBm, exceeds the selected radio’s rated transmit power of 30 dBm.');
 assert.equal(t('按已确认自由空间条件，候选 1：98.42 dB；候选 2：101.94 dB。'),'Under the confirmed free-space conditions: candidate 1: 98.42 dB; candidate 2: 101.94 dB.');
 assert.equal(t('站点库中没有“G站”。请在补充中说明或编辑原文。'),'The site library has no “G站”. Say so in an addition or edit the text.');
 assert.equal(t('两端站点 A站、B站 的坐标与天线高度取自站址表（模拟）。'),'Coordinates and antenna heights of Site A and Site B come from Site table (simulated).');
 assert.equal(t('发射功率（dBm）'),'Transmit power (dBm)');
 assert.equal(t('需求解析：本机运行的是 qwen3-4b，不是所选的 qwen35-9b。请在设置里切换模型；已改用确定性规则。'),
  'Request parsing: This machine is running qwen3-4b, not the selected qwen35-9b. Switch models in the settings; switched to deterministic rules.');
 assert.equal(t('✓ 独立复算'),'✓ Independent recomputation');
 assert.equal(t('超过所选电台的额定发射功率 30 dBm'),'Exceeds the selected radio’s rated transmit power of 30 dBm');
});

test('names and quotes captured as written are not translated',()=>{
 install(en);
 assert.equal(t('已驳回 · 审核人 张三 · 2026/9/28 10:00:00 · 原文不符'),'Rejected · reviewer 张三 · 2026/9/28 10:00:00 · 原文不符');
 assert.equal(t('“链路余量”不能作为余量要求'),'“链路余量” cannot be a margin requirement');
});
