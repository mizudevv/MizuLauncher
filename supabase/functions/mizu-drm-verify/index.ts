import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const sha256Hex = async (value: string) => {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  try {
    const url = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const adminClient = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const body = await req.json().catch(() => ({}));
    const gameId = String(body.game_id ?? "").trim();
    const userId = String(body.user_id ?? "").trim();
    const token = String(body.token ?? "").trim();
    if (!gameId || !userId || !token) throw new Error("missing_fields");

    const tokenHash = await sha256Hex(token);
    const { data: grant, error: grantError } = await adminClient
      .from("drm_tokens")
      .select("id,user_id,game_id,expires_at,revoked_at")
      .eq("token_hash", tokenHash)
      .eq("game_id", gameId)
      .eq("user_id", userId)
      .maybeSingle();
    if (grantError) throw grantError;
    if (!grant || grant.revoked_at || new Date(grant.expires_at).getTime() <= Date.now()) {
      return new Response(JSON.stringify({ ok: false, authorized: false, reason: "token_invalid_or_expired" }), {
        headers: { ...cors, "Content-Type": "application/json" }, status: 403,
      });
    }

    const { data: control, error: controlError } = await adminClient
      .from("player_control")
      .select("can_play,kill_switch")
      .eq("user_id", userId)
      .maybeSingle();
    if (controlError) throw controlError;
    const authorized = Boolean(control?.can_play && !control?.kill_switch);

    return new Response(JSON.stringify({ ok: true, authorized, status: authorized ? "authorized" : "blocked" }), {
      headers: { ...cors, "Content-Type": "application/json" }, status: authorized ? 200 : 403,
    });
  } catch (error) {
    return new Response(JSON.stringify({ ok: false, authorized: false, error: String(error?.message ?? error) }), {
      headers: { ...cors, "Content-Type": "application/json" }, status: 400,
    });
  }
});
