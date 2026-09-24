import test from 'node:test';
import assert from 'node:assert/strict';
import {formatDomain} from '../planning/web/values.mjs';
import {openQuestions,questionTitle} from '../planning/web/questions.mjs';
test('interval and candidates remain visibly different',()=>{
 assert.equal(formatDomain({kind:'interval',lower:1.9,upper:2.1}),'1.9–2.1');
 assert.equal(formatDomain({kind:'choices',values:[2,3]}),'2 / 3');
 assert.equal(formatDomain(98.4205999,6),'98.420600');
});
test('question count excludes resolved items and old states remain readable',()=>{
 const state={input_issues:[{id:'a',status:'resolved'},{id:'b',status:'open'},{id:'c',status:'open'}]};
 assert.equal(openQuestions(state).length,2);
 assert.equal(questionTitle(state),'待补充');assert.equal(questionTitle({}),'无待补充项');
 assert.deepEqual(openQuestions({}),[]);
});
