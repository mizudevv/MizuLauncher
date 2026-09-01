-- MizuLauncher Secure Architecture
-- Run this file after the original supabase_setup.sql.
-- IMPORTANT: never put SUPABASE_SERVICE_ROLE_KEY in the launcher or admin-panel browser code.

create schema if not exists private;

create table if not exists public.player_control (
    user_id uuid primary key references auth.users(id) on delete cascade,
    email text not null default '',
    windows_username text not null default '',
    ip_address inet,
    local_ip inet,
    hwid_hash text not null default '',
    last_login_at timestamptz,
    last_seen_at timestamptz,
    is_developer boolean not null default false,
    is_admin boolean not null default false,
    can_play boolean not null default true,
    can_download boolean not null default true,
    kill_switch boolean not null default false,
    updated_at timestamptz not null default now()
);

create index if not exists player_control_last_seen_idx on public.player_control(last_seen_at desc);
create index if not exists player_control_dev_idx on public.player_control(is_developer) where is_developer = true;
create index if not exists player_control_admin_idx on public.player_control(is_admin) where is_admin = true;

create table if not exists public.drm_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    game_id text not null,
    token_hash text not null unique,
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    revoked_at timestamptz
);

create index if not exists drm_tokens_lookup_idx on public.drm_tokens(token_hash, game_id);
create index if not exists drm_tokens_expiry_idx on public.drm_tokens(expires_at);

create or replace function private.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
    select exists (
        select 1 from public.player_control
        where user_id = auth.uid() and is_admin = true
    );
$$;

create or replace function private.is_developer()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
    select exists (
        select 1 from public.player_control
        where user_id = auth.uid() and is_developer = true
    );
$$;

revoke all on function private.is_admin() from public, anon, authenticated;
revoke all on function private.is_developer() from public, anon, authenticated;

grant select on public.player_control to authenticated;
grant usage on schema private to authenticated;

grant select on public.drm_tokens to authenticated;

alter table public.player_control enable row level security;
alter table public.drm_tokens enable row level security;

-- A player can read only their own security state. Admins can read all players.
drop policy if exists player_control_read_self_or_admin on public.player_control;
create policy player_control_read_self_or_admin
on public.player_control
for select to authenticated
using ((select auth.uid()) = user_id or (select private.is_admin()));

-- No direct INSERT/UPDATE/DELETE policies are granted to normal clients.
-- Telemetry and admin actions are performed through Edge Functions using service_role server-side.

drop policy if exists drm_tokens_no_client_read on public.drm_tokens;
-- Intentionally no client policy: the browser/launcher cannot enumerate DRM grants.

-- Create a profile row automatically when a Supabase Auth user is registered.
create or replace function public.handle_new_launcher_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.player_control(user_id, email, last_seen_at, updated_at)
    values (new.id, coalesce(new.email, ''), now(), now())
    on conflict (user_id) do update
        set email = excluded.email,
            updated_at = now();
    return new;
end;
$$;

drop trigger if exists on_auth_user_created_launcher on auth.users;
create trigger on_auth_user_created_launcher
after insert on auth.users
for each row execute procedure public.handle_new_launcher_user();

-- Backfill existing accounts.
insert into public.player_control(user_id, email)
select id, coalesce(email, '') from auth.users
on conflict (user_id) do update set email = excluded.email;

-- Admin RPCs: only an admin can change these flags.
create or replace function public.admin_set_player_status(target_user_id uuid, action_name text, enabled boolean)
returns public.player_control
language plpgsql
security definer
set search_path = public
as $$
declare
    result public.player_control;
begin
    if not private.is_admin() then
        raise exception 'not_admin' using errcode = '42501';
    end if;

    if action_name = 'play' then
        update public.player_control
        set can_play = enabled, updated_at = now()
        where user_id = target_user_id
        returning * into result;
    elsif action_name = 'download' then
        update public.player_control
        set can_download = enabled, updated_at = now()
        where user_id = target_user_id
        returning * into result;
    elsif action_name = 'kill_switch' then
        update public.player_control
        set kill_switch = enabled, updated_at = now()
        where user_id = target_user_id
        returning * into result;
    else
        raise exception 'unsupported_action' using errcode = '22023';
    end if;

    if result.user_id is null then
        raise exception 'player_not_found' using errcode = 'P0002';
    end if;
    return result;
end;
$$;

revoke all on function public.admin_set_player_status(uuid, text, boolean) from public, anon;
grant execute on function public.admin_set_player_status(uuid, text, boolean) to authenticated;

-- Optional cleanup helper for expired DRM grants. Run manually from SQL Editor or a scheduled job.
create or replace function public.cleanup_expired_drm_tokens()
returns integer
language sql
security definer
set search_path = public
as $$
    with deleted as (
        delete from public.drm_tokens
        where expires_at < now() or revoked_at is not null
        returning 1
    )
    select count(*)::integer from deleted;
$$;
revoke all on function public.cleanup_expired_drm_tokens() from public, anon, authenticated;

-- Set your developer/admin account manually after registering it:
-- update public.player_control
-- set is_developer = true, is_admin = true
 where user_id = '7090789e-1403-453e-ae30-9cc2b89db040';
