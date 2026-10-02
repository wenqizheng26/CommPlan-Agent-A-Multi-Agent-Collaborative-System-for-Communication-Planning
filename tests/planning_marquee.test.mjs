import test from 'node:test';
import assert from 'node:assert/strict';
import {headerText} from '../planning/web/marquee.mjs';

test('header shows the question on one line and marks it while processing',()=>{
 assert.equal(headerText(null,null),'未开始');
 assert.equal(headerText(null,{request:{raw_text:'  A 站到 B 站\n能通吗？ '}}),'A 站到 B 站 能通吗？');
 assert.equal(headerText({request:{raw_text:'新问题'}},{request:{raw_text:'旧问题'}}),'处理中 · 新问题');
 assert.equal(headerText({request:{raw_text:''}},null),'处理中');
});

test('a restore placeholder shows the saved question instead of its own text',()=>{
 const placeholder={placeholder:true,request:{raw_text:'正在恢复运行观察，原文以提交后的记录为准。'}};
 assert.equal(headerText(placeholder,{request:{raw_text:'已保存的问题'}}),'处理中 · 已保存的问题');
 assert.equal(headerText(placeholder,null),'处理中');
});
