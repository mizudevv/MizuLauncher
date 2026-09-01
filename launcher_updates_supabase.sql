-- MizuLauncher: global launcher update configuration in Supabase
-- Run after your existing MizuLauncher security SQL.

create table if not exists public.launcher_updates (
    id bigint primary key,
    latest_version text not null,
    download_url text not null,
    message text not null default '',
    enabled boolean not null default true,
    updated_at timestamptz not null default now()
);

insert into public.launcher_updates (
    id, latest_version, download_url, message, enabled
)
values (
    1,
    '1.0.0',
    'https://example.com/mizulauncher',
    'Dostępna jest nowa wersja MizuLaunchera.',
    true
)
on conflict (id) do nothing;

alter table public.launcher_updates enable row level security;

revoke all on public.launcher_updates from anon;
grant select on public.launcher_updates to anon;
grant select on public.launcher_updates to authenticated;
grant update on public.launcher_updates to authenticated;

drop policy if exists "launcher_updates_public_read" on public.launcher_updates;
create policy "launcher_updates_public_read"
on public.launcher_updates
for select
to anon, authenticated
using (enabled = true);

drop policy if exists "launcher_updates_admin_update" on public.launcher_updates;
create policy "launcher_updates_admin_update"
on public.launcher_updates
for update
to authenticated
using ((select public.is_mizu_admin()))
with check ((select public.is_mizu_admin()));

-- opcjonalnie: usuń dostęp do aktualizacji zwykłym użytkownikom przez zmianę enabled=false.
