-- Create consultation_types table
create table if not exists consultation_types (
    name text primary key,
    is_active boolean default true,
    created_at timestamptz default now()
);

-- Enable RLS
alter table consultation_types enable row level security;

-- Policies for consultation_types
drop policy if exists "Allow public read types" on consultation_types;
create policy "Allow public read types" 
on consultation_types for select 
using (true);

drop policy if exists "Allow authenticated insert types" on consultation_types;
create policy "Allow authenticated insert types" 
on consultation_types for insert 
to authenticated 
with check (true);

drop policy if exists "Allow authenticated update types" on consultation_types;
create policy "Allow authenticated update types" 
on consultation_types for update 
to authenticated 
using (true);

-- Insert defaults
insert into consultation_types (name) values
('refund'), ('tech'), ('inquiry'), ('general')
on conflict (name) do nothing;

-- Ensure coaching_logs has consultation_type column
do $$
begin
    if not exists (select 1 from information_schema.columns where table_name = 'coaching_logs' and column_name = 'consultation_type') then
        alter table coaching_logs add column consultation_type text default 'general';
    end if;
end $$;

-- Backfill existing logs with 'general' if null
update coaching_logs set consultation_type = 'general' where consultation_type is null;

-- Creates reference_materials table
create table if not exists reference_materials (
    id uuid default gen_random_uuid() primary key,
    category text, -- Linked to consultation_types
    title text not null,
    summary text,
    content text,
    keywords text,
    is_active boolean default true,
    created_at timestamptz default now()
);

-- RLS for reference_materials
alter table reference_materials enable row level security;

drop policy if exists "Allow public read references" on reference_materials;
create policy "Allow public read references"
on reference_materials for select
using (true);

drop policy if exists "Allow authenticated insert references" on reference_materials;
create policy "Allow authenticated insert references"
on reference_materials for insert
to authenticated
with check (true);

drop policy if exists "Allow authenticated update references" on reference_materials;
create policy "Allow authenticated update references"
on reference_materials for update
to authenticated
using (true);

drop policy if exists "Allow authenticated delete references" on reference_materials;
create policy "Allow authenticated delete references"
on reference_materials for delete
to authenticated
using (true);
