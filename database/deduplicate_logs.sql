-- Remove duplicate coaching_logs based on user_id and created_at
-- Keeps the first entry and deletes subsequent duplicates that occurred within the same second
-- (Assuming duplicates were created by the bug in the same transaction window)

with duplicates as (
  select id,
         row_number() over (
           partition by user_id, consultation_type, ai_score, date_trunc('second', created_at)
           order by created_at asc
         ) as rnum
  from coaching_logs
)
delete from coaching_logs
where id in (
  select id from duplicates where rnum > 1
);
