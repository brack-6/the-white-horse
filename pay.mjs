import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";
import { createPaymentHeader } from "x402/client";

const account = privateKeyToAccount(process.env.PRIVKEY);
console.log("💳 Signer:", account.address);

const walletClient = createWalletClient({ 
  account, 
  chain: base, 
  transport: http("https://mainnet.base.org") 
});

async function poll(url, sessionId, maxWait = 180000) {
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    const r = await fetch(`${url}/session/${sessionId}`);
    const d = await r.json();
    console.log("⏳ Status:", d.status);
    if (d.status === "ready") return d;
    if (d.status === "refused") throw new Error("Refused: " + d.reason);
    await new Promise(r => setTimeout(r, 6000));
  }
  throw new Error("Timed out waiting for pint");
}

async function testPayment() {
  const url = "https://brack-hive.tail4f568d.ts.net/pub";
  const init = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: "jar3d", pint: "stochastic_cider", prompt: "What should I build next?" }),
  };

  const probe = await fetch(`${url}/order`, init);
  if (probe.status !== 402) { console.log("No 402:", await probe.json()); return; }

  const requirements = await probe.json();
  console.log("📋 Requirements:", JSON.stringify(requirements, null, 2));
  console.log("💰 Paying...");
  const selected = requirements.accepts[0];
  console.log("📋 Selected:", JSON.stringify(selected, null, 2));
  const paymentHeader = await Promise.race([
    createPaymentHeader(walletClient, 1, selected),
    new Promise((_, reject) => setTimeout(() => reject(new Error("Payment header creation timeout")), 30000))
  ]);

  const response = await fetch(`${url}/order`, {
    ...init,
    headers: { ...init.headers, "X-PAYMENT": paymentHeader },
    signal: AbortSignal.timeout(60000)
  });

  const data = await response.json();
  console.log("Raw response:", JSON.stringify(data, null, 2));
  console.log("🍺 Order placed:", data.status, "session:", data.session_id || data.sessionId);

  if (data.session_id || data.sessionId) {
    const sessionId = data.session_id || data.sessionId;
    const result = await poll(url, sessionId);
    console.log("✅ Pint ready!");
    console.log("Sober:", result.sober_output?.slice(0, 100));
    console.log("Drunk:", result.drunk_output?.slice(0, 100));
  }
}

testPayment().catch(e => console.error("❌", e.message));
