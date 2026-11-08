-- صفحه‌ی وضعیت (azkicenter/status) فقط این تابع رو صدا می‌زنه.
-- فقط زمان آخرین آپدیت‌ها رو برمی‌گردونه؛ هیچ دیتای کارشناس/گزارشی بیرون نمی‌ره.
-- خروجی چند صد بایته، پس روی مصرف Supabase تقریباً اثری نداره.

create or replace function public.status_heartbeat()
returns json
language sql
stable
security definer
set search_path = public
as $$
  select json_build_object(
    'now',                    now(),
    'app_date',               (select updated_date_jalali        from app_meta order by id limit 1),
    'app_time',               (select updated_time               from app_meta order by id limit 1),
    'reports_date',           (select reports_updated_date_jalali from app_meta order by id limit 1),
    'reports_time',           (select reports_updated_time       from app_meta order by id limit 1),
    'ops_updated_at',         (select max(updated_at) from center_operators_status)
  );
$$;

revoke all on function public.status_heartbeat() from public;
grant execute on function public.status_heartbeat() to anon, authenticated;
