import test from 'node:test';
import assert from 'node:assert/strict';

test('source evidence spans use Python code points, including emoji', async () => {
  const {sourceExcerpt} = await import('../planning/web/text.mjs');
  const text='📡按自由空间基准计算，频率2GHz，距离1km，求路径损耗。';
  assert.equal(sourceExcerpt(text,[11,17]),'频率2GHz');
  assert.equal(sourceExcerpt(text,[18,23]),'距离1km');
  assert.equal(sourceExcerpt('频率2000MHz',[0,9]),'频率2000MHz');
});
