import assert from "node:assert/strict";
import test from "node:test";
import { parseMenuCsv, websiteApi, websiteDraftIssue, websiteInputError } from "../lib/website-api.ts";

test("CSV supports headers, quoted commas, escaped quotes and numeric prices", () => {
  assert.deepEqual(parseMenuCsv('name,price\r\n"Coffee, large",100\r\n"Tea ""classic""",50'), [
    { name: "Coffee, large", price: 100 }, { name: 'Tea "classic"', price: 50 },
  ]);
});
for (const csv of ['Coffee,abc', 'Coffee,-1', 'Coffee,', 'Coffee,Infinity', '"Coffee,100', '"Coffee"bad,100', 'Coffee,10,20']) {
  test(`Malformed CSV rejected: ${csv}`, () => assert.throws(() => parseMenuCsv(csv)));
}
const fields = { name: "Namma Cafe", area: "Bengaluru", phone: "", whatsapp: "", hours: [], menu: [], social_links: [] };
test("Client convenience validation blocks required/invalid inputs", () => {
  assert.equal(websiteInputError(fields), null);
  assert.match(websiteInputError({ ...fields, name: "" }), /required/);
  assert.match(websiteInputError({ ...fields, phone: "1" }), /Phone/);
  assert.match(websiteInputError({ ...fields, social_links: ["javascript:alert(1)"] }), /HTTPS/);
  assert.match(websiteInputError({ ...fields, menu: [{ name: "Coffee", price: NaN }] }), /price/);
  assert.match(websiteInputError({ ...fields, hours: [{ open: "22:00", close: "09:00" }] }), /hours/);
});

test("draft issues point to the editable step and never permit incomplete hours/menu", () => {
  assert.deepEqual(websiteDraftIssue({...fields, hours: [{day: "MON", open: "09:00", close: ""}]}), {
    message: "Finish each opening time and closing time, or remove that day", step: 2, action: "Fix opening hours",
  });
  assert.equal(websiteDraftIssue({...fields, menu: [{name: "", price: NaN}]}).step, 3);
  assert.equal(websiteDraftIssue({...fields, hours: [{day: "MON", open: "09:00", close: "18:00"}]}), null);
});

test("unavailable server and unreadable responses have actionable errors", async t => {
  t.mock.method(globalThis, "fetch", async () => { throw new DOMException("timeout", "TimeoutError"); });
  await assert.rejects(websiteApi("/website/config"), /did not respond.*retry/);
  globalThis.fetch.mock.mockImplementation(async () => new Response("upstream unavailable", {status: 502}));
  await assert.rejects(websiteApi("/website/config"), /unreadable response.*retry/);
});

test("website calls use a bounded abort signal and preserve server conflict errors", async t => {
  const deadline = t.mock.method(AbortSignal, "timeout", () => new AbortController().signal);
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options.signal instanceof AbortSignal, true);
    return Response.json({message: "Reload the current website draft"}, {status: 409});
  });
  await assert.rejects(websiteApi("/websites/test", "PUT", {}), /Reload the current website draft/);
  assert.equal(deadline.mock.calls[0].arguments[0], 15_000);
});
