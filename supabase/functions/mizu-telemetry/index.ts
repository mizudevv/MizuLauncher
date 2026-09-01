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
    if (!authHeader.startsWith("Bearer ")) throw new Error("missing_auth");

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

    const authClient = createClient(supabaseUrl, anonKey, {
      global: { headers: { Authorization: authHeader } },
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data: { user }, error: authError } = await authClient.auth.getUser();
    if (authError || !user) throw new Error("unauthorized");

    const body = await req.json().catch(() => ({}));
    const windowsUsername = String(body.windows_username ?? "").slice(0, 128);
    const hwidHash = String(body.hwid_hash ?? "").slice(0, 128);
    const localIp = String(body.local_ip ?? "").slice(0, 64);
    const event = String(body.event ?? "launcher_start").slice(0, 64);
    const appVersion = String(body.app_version ?? "unknown").slice(0, 64);

    const ip =
      req.headers.get("cf-connecting-ip") ??
      (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() ??
      null;

    const adminClient = createClient(supabaseUrl, serviceRoleKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });

    const now = new Date().toISOString();
    const patch: Record<string, unknown> = {
      email: user.email ?? "",
      windows_username: windowsUsername,
      hwid_hash: hwidHash,
      local_ip: localIp,
      ip_address: ip,
      last_seen_at: now,
      updated_at: now,
    };
    if (event === "login" || event === "launcher_start") patch.last_login_at = now;

    const { error } = await adminClient
      .from("player_control")
      .upsert({ user_id: user.id, ...patch }, { onConflict: "user_id" });
    if (error) throw error;

    return new Response(JSON.stringify({ ok: true, user_id: user.id, event, app_version: appVersion }), {
      headers: { ...cors, "Content-Type": "application/json" },
      status: 200,
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: String(error?.message ?? error) }), {
      headers: { ...cors, "Content-Type": "application/json" },
      status: 401,
    });
  }
});
