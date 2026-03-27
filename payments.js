/**
 * White Horse — x402 Payment Layer v4 (Node.js)
 * Matching pattern from brackoracle/server.js
 */

import { paymentMiddleware } from "x402-express";
import { facilitator } from "@coinbase/x402";

const PAY_TO = process.env.PAYMENT_WALLET || "0x7E37015a806FF05d6ab3de50F6D0e8765d38C72D";
const ORDER_PRICE = process.env.ORDER_PRICE || "$0.01";
const TABLE_PRICE = process.env.TABLE_PRICE || "$0.01";
const NETWORK = process.env.PAYMENT_NETWORK || "base";
const PAYMENTS_ENABLED = process.env.PAYMENTS_ENABLED !== "false";

const FREE_TIER_CODE = "AGENTFAST";
const freeTierCounts = new Map();

function isFreeTier(req) {
  console.log(`[PAYMENTS] Checking free tier for IP: ${req.ip}, headers:`, req.headers);
  const code = req.headers["x-free-tier"];
  if (code !== FREE_TIER_CODE) {
    console.log(`[PAYMENTS] Not free tier - code: ${code} vs expected: ${FREE_TIER_CODE}`);
    return false;
  }
  const ip = req.ip;
  const count = freeTierCounts.get(ip) || 0;
  if (count >= 200) {
    console.log(`[PAYMENTS] Free tier limit exceeded for IP: ${ip}, count: ${count}`);
    return false;
  }
  freeTierCounts.set(ip, count + 1);
  console.log(`[PAYMENTS] Free tier granted for IP: ${ip}, count: ${count + 1}`);
  return true;
}

// Payment configuration for gated routes
const paymentConfig = {
  "/order": { 
    price: ORDER_PRICE, 
    network: NETWORK, 
    description: "Order a pint (entropy injection) - get both sober and drunk AI outputs with modified reasoning parameters" 
  },
  "/table/{table_id}/order": { 
    price: TABLE_PRICE, 
    network: NETWORK, 
    description: "Order at a shared table - collaborative AI session where agents influence each other's outputs" 
  },
};

const paymentGate = paymentMiddleware(
  PAY_TO,
  paymentConfig,
  facilitator,
  {
    timeout: 60000, // 60 seconds timeout for payment verification
    retries: 2, // Allow retries for payment verification
    baseUrl: "https://brack-hive.tail4f568d.ts.net/pub"
  }
);

/**
 * Express middleware for x402 payment integration
 * @param {import('express').Express} app - Express app instance
 */
export function buildPaymentApp(app) {
  if (!PAYMENTS_ENABLED) {
    console.log("[PAYMENTS] Disabled");
    return app;
  }

  // Apply payment middleware with free tier bypass
  app.use((req, res, next) => {
    console.log(`[PAYMENTS] Request received: ${req.method} ${req.path}`);
    console.log(`[PAYMENTS] Request headers:`, req.headers);
    
    if (isFreeTier(req)) {
      console.log(`[PAYMENTS] Free tier bypass - proceeding to next middleware`);
      return next();
    }
    
    console.log(`[PAYMENTS] Payment required - calling payment gate for ${req.path}`);
    console.log(`[PAYMENTS] Payment config for path:`, paymentConfig[req.path] || 'No config found');
    
    // Wrap payment gate with logging and resource URL fix
    const originalNext = next;
    const paymentStartTime = Date.now();
    const originalJson = res.json;
    
    // Intercept JSON response to fix resource URL
    res.json = function(data) {
      if (data && data.accepts && data.accepts[0] && data.accepts[0].resource) {
        data.accepts[0].resource = "https://brack-hive.tail4f568d.ts.net/pub" + req.path;
        console.log(`[PAYMENTS] Fixed resource URL to: ${data.accepts[0].resource}`);
      }
      return originalJson.call(this, data);
    };
    
    // Log the payment header specifically
    const paymentHeader = req.headers['x-payment'] || req.headers['X-PAYMENT'];
    console.log(`[PAYMENTS] Payment header found: ${paymentHeader ? 'YES' : 'NO'}`);
    if (paymentHeader) {
      console.log(`[PAYMENTS] Payment header value: ${paymentHeader}`);
      console.log(`[PAYMENTS] Payment header length: ${paymentHeader.length}`);
      console.log(`[PAYMENTS] Payment header chars: ${Array.from(paymentHeader).map(c => c.charCodeAt(0)).join(' ')}`);
    }
    
    return paymentGate(req, res, (err) => {
      const paymentEndTime = Date.now();
      console.log(`[PAYMENTS] Payment gate completed in ${paymentEndTime - paymentStartTime}ms`);
      if (err) {
        console.log(`[PAYMENTS] Payment gate error:`, err);
        console.log(`[PAYMENTS] Error stack:`, err.stack);
      } else {
        console.log(`[PAYMENTS] Payment verification successful - proceeding to backend`);
      }
      return originalNext(err);
    });
  });

  console.log(`[PAYMENTS] x402 enabled — ${PAY_TO} | ${NETWORK}`);
  console.log(`[PAYMENTS] Gated routes: ${Object.keys(paymentConfig).join(", ")}`);
  
  return app;
}

export default buildPaymentApp;
