// Verification-only local TLS proxy. Never used as a production hosting profile.
import https from "node:https";
import http from "node:http";
import fs from "node:fs";
const [cert, key] = process.argv.slice(2);
https.createServer({ cert: fs.readFileSync(cert), key: fs.readFileSync(key) }, (req, res) => {
  const api = req.url.startsWith("/api/");
  const upstream = (api ? https : http).request({ hostname: "localhost", port: api ? 8000 : 3001,
    path: req.url, method: req.method, headers: { ...req.headers, host: `localhost:${api ? 8000 : 3001}` },
    ...(api ? { ca: fs.readFileSync(cert) } : {}) }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res); });
  upstream.on("error", () => { res.writeHead(502); res.end("Verification upstream unavailable"); });
  req.pipe(upstream);
}).listen(3000, "localhost");
