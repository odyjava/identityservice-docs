#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(new URL("../api.html", import.meta.url), "utf8");
const match = html.match(/<script>\s*\(function \(\) \{[\s\S]*?<\/script>/);
assert.ok(match, "api.html 缺少瀏覽器語言導向程式");
const source = match[0].replace(/^<script>|<\/script>$/g, "");

function route(languages, saved = null) {
  let destination = null;
  vm.runInNewContext(source, {
    navigator: { language: languages[0] || "", languages },
    localStorage: { getItem: () => saved },
    location: {
      hash: "#section",
      search: "?source=test",
      replace: (value) => { destination = value; },
    },
  });
  return destination;
}

assert.equal(route(["zh-CN"]), "api.zh-Hans.html?source=test#section");
assert.equal(route(["zh-SG"]), "api.zh-Hans.html?source=test#section");
assert.equal(route(["zh-TW"]), null);
assert.equal(route(["zh-HK"]), null);
assert.equal(route(["en-US"]), "api.en.html?source=test#section");
assert.equal(route(["fr-FR"]), "api.en.html?source=test#section");
assert.equal(route(["en-US"], "zh-Hant"), null);
assert.equal(route(["zh-TW"], "en"), "api.en.html?source=test#section");

console.log("語言導向測試通過");
