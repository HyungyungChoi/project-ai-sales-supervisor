-- 1. Create a new storage bucket for recordings
-- (If it fails saying unique violation, it means it already exists, which is fine)
insert into storage.buckets (id, name, public)
values ('recordings', 'recordings', true)
on conflict (id) do nothing;

-- 2. Policy: Allow public read access (Anyone can listen)
-- Drop existing policy if it exists to avoid errors on retry
drop policy if exists "Give public access to recordings" on storage.objects;

create policy "Give public access to recordings"
on storage.objects for select
using ( bucket_id = 'recordings' );

-- 3. Policy: Allow authenticated uploads (Only logged-in users can upload)
drop policy if exists "Allow authenticated uploads" on storage.objects;

create policy "Allow authenticated uploads"
on storage.objects for insert
to authenticated
with check ( bucket_id = 'recordings' );
