-- Add the coarsened coordinate to the export contract.
--
-- `api.export_report_candidates` returned locality and depth but no position,
-- which left the Python crowd pipeline unable to build a report record at all:
-- `build_crowd_report` requires latitude and longitude. Without them there was
-- no path from an accepted database row to a published artifact, so reports
-- would have accumulated in Postgres and never reached anyone.
--
-- Exposing the coordinate here is not a privacy regression. The column is
-- already constrained to three decimals (~100 m) and to the Assam bounding box
-- by `reporting.reports`, this function stays `security invoker` and remains
-- granted to `service_role` only, and the public artifact the exporter feeds
-- publishes aggregates rather than individual positions.

create or replace function api.export_report_candidates(
  p_since timestamptz,
  p_until timestamptz
)
returns table (
  report_id uuid,
  observed_at timestamptz,
  locality_id text,
  depth_class text,
  reporter_hash text,
  verification_state text,
  longitude double precision,
  latitude double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
  select
    r.report_id,
    r.observed_at,
    r.locality_id,
    r.depth_class,
    r.reporter_hash,
    coalesce(v.state, 'pending') as verification_state,
    extensions.st_x(r.location::extensions.geometry) as longitude,
    extensions.st_y(r.location::extensions.geometry) as latitude
  from reporting.reports as r
  left join lateral (
    select e.state
    from reporting.verification_events as e
    where e.report_id = r.report_id
    order by e.created_at desc, e.event_id desc
    limit 1
  ) as v on true
  where r.intake_status = 'accepted'
    and r.locality_id is not null
    and r.observed_at >= p_since
    and r.observed_at < p_until
  order by r.observed_at, r.report_id;
$$;

revoke all on function api.export_report_candidates(timestamptz, timestamptz)
  from public, anon, authenticated;
grant execute on function api.export_report_candidates(timestamptz, timestamptz)
  to service_role;
