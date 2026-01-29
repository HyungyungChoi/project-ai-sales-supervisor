-- 1. Add file_url column to reference_materials
ALTER TABLE reference_materials ADD COLUMN IF NOT EXISTS file_url TEXT;

-- 2. Create 'references' bucket
insert into storage.buckets (id, name, public)
values ('references', 'references', true)
on conflict (id) do nothing;

-- 3. Policy: Public Read Access
drop policy if exists "Give public access to references" on storage.objects;
create policy "Give public access to references"
on storage.objects for select
using ( bucket_id = 'references' );

-- 4. Policy: Authenticated Upload Access
drop policy if exists "Allow authenticated uploads to references" on storage.objects;
create policy "Allow authenticated uploads to references"
on storage.objects for insert
to authenticated
with check ( bucket_id = 'references' );
