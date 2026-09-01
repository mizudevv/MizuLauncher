# MizuLauncher Admin Panel

Static HTML/Tailwind/JavaScript panel for Vercel.

## Setup

1. Copy `config.example.js` to `config.js`.
2. Put only the Supabase Project URL and Publishable/anon key into `config.js`.
3. Never put `service_role` or `sb_secret` into this folder.
4. Deploy this folder to Vercel.

The panel uses Supabase Auth in the browser and RLS/Edge Functions for authorization. The browser can read all `player_control` rows only when the authenticated user satisfies the admin RLS policy. Status mutations go through `mizu-admin-action`, which verifies the admin on the server.
