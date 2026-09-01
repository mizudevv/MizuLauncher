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
    const authHeader = req.headers.get("Authorization") ?? "";
    if (!authHeader.startsWith("Bearer ")) throw new Error("unauthorized");
    const url = Deno.env.get("SUPABASE_URL")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const authClient = createClient(url, anonKey, { global: { headers: { Authorization: authHeader } }, auth: { persistSession: false, autoRefreshToken: false } });
    const { data: { user }, error: authError } = await authClient.auth.getUser();
    if (authError || !user) throw new Error("unauthorized");

    const body = await req.json().catch(() => ({}));
    const gameId = String(body.game_id ?? "").trim();
    const purpose = String(body.purpose ?? "play").trim();
    if (!gameId) throw new Error("missing_game_id");

    const adminClient = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: control, error: controlError } = await adminClient
      .from("player_control")
      .select("can_play,can_download,kill_switch")
      .eq("user_id", user.id)
      .maybeSingle();
    if (controlError) throw controlError;
    if (!control || !control.can_play || control.kill_switch) throw new Error("play_blocked");
    if (purpose === "download" && !control.can_download) throw new Error("download_blocked");

    const token = `${crypto.randomUUID()}-${crypto.randomUUID()}-${crypto.randomUUID()}`;
    const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    const tokenHash = await sha256Hex(token);
    const { error: insertError } = await adminClient.from("drm_tokens").insert({
      user_id: user.id,
      game_id: gameId,
      token_hash: tokenHash,
      expires_at: expiresAt,
    });
    if (insertError) throw insertError;

    return new Response(JSON.stringify({
      ok: true,
      game_id: gameId,
      user_id: user.id,
      token,
      expires_at: expiresAt,
      status: "authorized",
    }), { headers: { ...cors, "Content-Type": "application/json" }, status: 200 });
  } catch (error) {
    return new Response(JSON.stringify({ ok: false, error: String(error?.message ?? error) }), {
      headers: { ...cors, "Content-Type": "application/json" },
      status: 403,
    });
  }
});
