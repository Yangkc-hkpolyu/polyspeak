const assert = require('node:assert/strict');

module.exports = async function assertEnglishUI(page, state) {
  const observed = await page.evaluate(() => ({
    language: document.documentElement.lang,
    text: [document.title, document.body.innerText,
      ...Array.from(document.querySelectorAll('[aria-label], [title], [placeholder]')).flatMap(element =>
        ['aria-label', 'title', 'placeholder'].map(name => element.getAttribute(name) || ''))].join('\n')
  }));
  assert.equal(observed.language, 'en', `${state}: document language`);
  assert(!/[\u3400-\u9fff]/u.test(observed.text), `${state}: Chinese text remains in the rendered interface`);
};
