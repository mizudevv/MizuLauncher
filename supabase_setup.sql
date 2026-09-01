-- MizuLauncher Supabase setup
-- Run this whole file in Supabase Dashboard -> SQL Editor.

create table if not exists public.launcher_catalog (
    id bigint primary key,
    data jsonb not null default '{"schema_version":1,"updated_at":"","games":[]}'::jsonb,
    updated_at timestamptz not null default now()
);

insert into public.launcher_catalog (id, data)
values (1, '{"schema_version":1,"updated_at":"","games":[]}'::jsonb)
on conflict (id) do nothing;

create table if not exists public.launcher_admins (
    user_id uuid primary key references auth.users(id) on delete cascade,
    created_at timestamptz not null default now()
);

create or replace function public.is_launcher_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.launcher_admins
    where user_id = auth.uid()
  );
$$;

revoke all on function public.is_launcher_admin() from public;
grant execute on function public.is_launcher_admin() to authenticated;

grant select on public.launcher_catalog to anon;
grant select, update on public.launcher_catalog to authenticated;

alter table public.launcher_catalog enable row level security;
alter table public.launcher_admins enable row level security;

drop policy if exists "launcher_catalog_public_read" on public.launcher_catalog;
drop policy if exists "launcher_catalog_admin_update" on public.launcher_catalog;
create policy "launcher_catalog_public_read"
on public.launcher_catalog
for select
to anon, authenticated
using (true);

create policy "launcher_catalog_admin_update"
on public.launcher_catalog
for update
to authenticated
using ((select public.is_launcher_admin()))
with check ((select public.is_launcher_admin()));

revoke all on public.launcher_admins from anon;
grant select on public.launcher_admins to authenticated;

drop policy if exists "launcher_admins_self_read" on public.launcher_admins;
create policy "launcher_admins_self_read"
on public.launcher_admins
for select
to authenticated
using (user_id = auth.uid());

-- After creating your developer user in Authentication -> Users,
-- insert their UUID below:
insert into public.launcher_admins (user_id) values ('7090789e-1403-453e-ae30-9cc2b89db040');
