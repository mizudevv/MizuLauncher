import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
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

    const adminClient = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: me, error: meError } = await adminClient.from("player_control").select("is_admin").eq("user_id", user.id).maybeSingle();
    if (meError) throw meError;
    if (!me?.is_admin) throw new Error("not_admin");

    const body = await req.json().catch(() => ({}));
    const action = String(body.action ?? "");
    const targetUserId = String(body.target_user_id ?? "");
    const value = Boolean(body.value);
    if (!targetUserId) throw new Error("missing_target_user_id");
    const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
    if (action === "play") patch.can_play = value;
    else if (action === "download") patch.can_download = value;
    else if (action === "kill_switch") patch.kill_switch = value;
    else throw new Error("unsupported_action");

    const { data, error } = await adminClient.from("player_control").update(patch).eq("user_id", targetUserId).select("user_id,can_play,can_download,kill_switch").single();
    if (error) throw error;

    return new Response(JSON.stringify({ ok: true, data }), { headers: { ...cors, "Content-Type": "application/json" }, status: 200 });
  } catch (error) {
    return new Response(JSON.stringify({ ok: false, error: String(error?.message ?? error) }), { headers: { ...cors, "Content-Type": "application/json" }, status: 403 });
  }
});
