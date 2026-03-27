/**
 * White Horse — Node.js Proxy Server with x402 Payments
 * Proxies to Python FastAPI backend on port 3200
 */

import express from "express";
import { createProxyMiddleware } from "http-proxy-middleware";
import { buildPaymentApp } from "./payments.js";
import rateLimit from "express-rate-limit";

const app = express();
app.set("trust proxy", 1);
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Set server timeouts
app.use((req, res, next) => {
  res.setTimeout(60000, () => {
    console.log('Request timeout');
    if (!res.headersSent) {
      res.status(408).json({ error: 'Request timeout' });
    }
  });
  next();
});

const PORT = process.env.PORT || 3201;
const PYTHON_BACKEND = process.env.PYTHON_BACKEND || "http://localhost:3200";

// Rate limiting
const limiter = rateLimit({ 
  windowMs: 60000, 
  max: 100, 
  standardHeaders: true, 
  legacyHeaders: false,
  skip: (req) => req.headers["x-free-tier"] === "AGENTFAST"
});
app.use(limiter);

// Health check
app.get("/health", (req, res) => res.json({
  service: "White Horse Proxy", 
  version: "1.0.0", 
  status: "online",
  backend: PYTHON_BACKEND
}));

// Apply x402 payment middleware
buildPaymentApp(app);

// Proxy to Python backend for all requests
const proxy = createProxyMiddleware({
  target: PYTHON_BACKEND,
  changeOrigin: true,
  timeout: 60000, // 60 seconds timeout
  proxyTimeout: 60000, // 60 seconds proxy timeout
  pathRewrite: {
    '^/': '/'
  },
  onError: (err, req, res) => {
    console.error('Proxy error:', err.message);
    res.status(503).json({ error: 'Backend service unavailable' });
  }
});

// Apply proxy after payment middleware
app.use('/', proxy);

const server = app.listen(PORT, "127.0.0.1", () => {
  console.log(`White Horse proxy with x402 payments running on port ${PORT}`);
  console.log(`Proxying to Python backend: ${PYTHON_BACKEND}`);
  console.log(`Public: https://brack-hive.tail4f568d.ts.net/white-horse`);
});

// Set server timeout
server.timeout = 60000; // 60 seconds
server.headersTimeout = 65000; // 65 seconds for headers
server.keepAliveTimeout = 65000; // 65 seconds keep alive
