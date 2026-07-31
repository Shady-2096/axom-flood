-- Axom Flood reporting foundation.
--
-- The database is a private intake and workflow inbox. Public reads continue
-- to use content-hashed static artifacts produced by the repository pipeline.
-- No raw phone number, Telegram identifier, browser device token, IP address,
-- full-precision coordinate, free text, or webhook body belongs in this schema.

create schema if not exists extensions;
create extension if not exists postgis with schema extensions;

create schema if not exists reporting;
create schema if not exists api;

revoke all on schema reporting from public, anon, authenticated;
revoke all on schema api from public, anon, authenticated;

create table reporting.geographies (
  geography_id text primary key,
  kind text not null
    check (kind in ('state', 'district', 'revenue_circle', 'village')),
  parent_id text references reporting.geographies (geography_id) on delete restrict,
  name_en text not null check (length(btrim(name_en)) > 0),
  centroid extensions.geography(point, 4326),
  boundary extensions.geometry(multipolygon, 4326),
  boundary_use text not null default 'display_only'
    check (boundary_use in ('display_only', 'reviewed_assignment')),
  source_revision_sha256 text not null
    check (source_revision_sha256 ~ '^[0-9a-f]{64}$'),
  valid_from date,
  valid_to date,
  created_at timestamptz not null default now(),
  check (parent_id is null or parent_id <> geography_id),
  check (valid_to is null or valid_from is null or valid_to >= valid_from),
  check (boundary is not null or boundary_use = 'display_only')
);

create index geographies_parent_id_idx on reporting.geographies (parent_id);
create index geographies_centroid_gix on reporting.geographies using gist (centroid);
create index geographies_reviewed_boundary_gix
  on reporting.geographies using gist (boundary)
  where boundary_use = 'reviewed_assignment' and boundary is not null;

create table reporting.reports (
  report_id uuid primary key,
  schema_version smallint not null default 2 check (schema_version = 2),
  channel text not null check (channel in ('web', 'telegram', 'whatsapp')),
  received_at timestamptz not null default now(),
  observed_at timestamptz not null,
  reporter_hash text not null check (reporter_hash ~ '^[0-9a-f]{64}$'),
  identity_period date not null,
  location extensions.geography(point, 4326) not null,
  coordinate_decimals smallint not null default 3 check (coordinate_decimals = 3),
  location_precision_floor_m smallint not null default 50
    check (location_precision_floor_m = 50),
  locality_id text references reporting.geographies (geography_id) on delete restrict,
  observation_type text
    check (
      observation_type is null
      or observation_type in (
        'water_on_road',
        'water_in_building',
        'road_blocked',
        'no_flood_seen'
      )
    ),
  depth_class text check (
    depth_class is null or depth_class in ('dry', 'ankle', 'knee', 'waist_plus')
  ),
  intake_status text not null default 'accepted'
    check (intake_status in ('accepted', 'duplicate', 'quarantined', 'rejected')),
  created_at timestamptz not null default now(),
  check (observation_type is not null or depth_class is not null),
  check (observation_type <> 'no_flood_seen' or depth_class = 'dry'),
  check (observed_at <= received_at + interval '5 minutes'),
  check (
    extensions.st_x(location::extensions.geometry) between 89.0 and 97.0
    and extensions.st_y(location::extensions.geometry) between 24.0 and 29.5
  ),
  check (
    extensions.st_x(location::extensions.geometry)
      = round(extensions.st_x(location::extensions.geometry)::numeric, 3)::double precision
    and extensions.st_y(location::extensions.geometry)
      = round(extensions.st_y(location::extensions.geometry)::numeric, 3)::double precision
  )
);

create index reports_locality_observed_idx
  on reporting.reports (locality_id, observed_at desc);
create index reports_status_observed_idx
  on reporting.reports (intake_status, observed_at desc);
create index reports_reporter_observed_idx
  on reporting.reports (reporter_hash, observed_at desc);
create index reports_location_gix on reporting.reports using gist (location);
create index reports_recent_accepted_idx
  on reporting.reports (observed_at desc)
  where intake_status = 'accepted';

create table reporting.verification_events (
  event_id bigint generated always as identity primary key,
  report_id uuid not null references reporting.reports (report_id) on delete restrict,
  state text not null check (
    state in (
      'pending',
      'duplicate',
      'corroborated',
      'human_verified',
      'contradicted',
      'rejected',
      'expired'
    )
  ),
  actor_kind text not null check (actor_kind in ('system', 'moderator')),
  moderator_user_id uuid references auth.users (id) on delete set null,
  reason_codes text[] not null default '{}',
  created_at timestamptz not null default now(),
  check (
    (actor_kind = 'moderator' and moderator_user_id is not null)
    or (actor_kind = 'system' and moderator_user_id is null)
  )
);

create index verification_events_report_created_idx
  on reporting.verification_events (report_id, created_at desc);
create index verification_events_moderator_user_id_idx
  on reporting.verification_events (moderator_user_id)
  where moderator_user_id is not null;

create table reporting.conversation_sessions (
  session_id uuid primary key default gen_random_uuid(),
  channel text not null check (channel in ('web', 'telegram', 'whatsapp')),
  subject_hash text not null check (subject_hash ~ '^[0-9a-f]{64}$'),
  identity_period date not null,
  flow_version smallint not null check (flow_version > 0),
  copy_version smallint not null check (copy_version > 0),
  language text not null default 'en' check (language = 'en'),
  state text not null check (
    state in (
      'idle',
      'responsibility_notice',
      'awaiting_location',
      'awaiting_depth',
      'review',
      'emergency_guidance',
      'submitted',
      'cancelled',
      'expired'
    )
  ),
  resume_state text check (
    resume_state is null
    or resume_state in (
      'responsibility_notice',
      'awaiting_location',
      'awaiting_depth',
      'review'
    )
  ),
  location extensions.geography(point, 4326),
  locality_id text references reporting.geographies (geography_id) on delete restrict,
  depth_class text check (
    depth_class is null or depth_class in ('dry', 'ankle', 'knee', 'waist_plus')
  ),
  emergency_guidance_shown_at timestamptz,
  lock_version bigint not null default 0 check (lock_version >= 0),
  last_activity_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '24 hours'),
  unique (channel, subject_hash, identity_period),
  check (expires_at > last_activity_at)
);

create index conversation_sessions_expiry_idx
  on reporting.conversation_sessions (expires_at);
create index conversation_sessions_active_idx
  on reporting.conversation_sessions (channel, state, last_activity_at desc)
  where state not in ('submitted', 'cancelled', 'expired');
create index conversation_sessions_locality_id_idx
  on reporting.conversation_sessions (locality_id)
  where locality_id is not null;

create table reporting.inbound_deliveries (
  channel text not null check (channel in ('web', 'telegram', 'whatsapp')),
  platform_delivery_id text not null check (length(platform_delivery_id) between 1 and 200),
  subject_hash text not null check (subject_hash ~ '^[0-9a-f]{64}$'),
  request_hash text not null check (request_hash ~ '^[0-9a-f]{64}$'),
  outcome text not null check (
    outcome in ('accepted', 'duplicate', 'rejected', 'rate_limited')
  ),
  received_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '7 days'),
  primary key (channel, platform_delivery_id),
  check (expires_at > received_at)
);

create index inbound_deliveries_expiry_idx on reporting.inbound_deliveries (expires_at);
create index inbound_deliveries_subject_received_idx
  on reporting.inbound_deliveries (subject_hash, received_at desc);

create table reporting.rate_limit_buckets (
  scope text not null check (
    scope in ('event_10m', 'event_day', 'report_10m', 'report_day', 'network_day')
  ),
  key_hash text not null check (key_hash ~ '^[0-9a-f]{64}$'),
  bucket_start timestamptz not null,
  count integer not null default 1 check (count > 0),
  expires_at timestamptz not null,
  primary key (scope, key_hash, bucket_start),
  check (expires_at > bucket_start)
);

create index rate_limit_buckets_expiry_idx on reporting.rate_limit_buckets (expires_at);

create table reporting.publication_runs (
  publication_run_id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  cutoff_at timestamptz not null,
  artifact_sha256 text check (
    artifact_sha256 is null or artifact_sha256 ~ '^[0-9a-f]{64}$'
  ),
  report_count_private integer check (report_count_private is null or report_count_private >= 0),
  aggregate_count_public integer check (
    aggregate_count_public is null or aggregate_count_public >= 0
  ),
  status text not null default 'running'
    check (status in ('running', 'published', 'failed')),
  error_code text,
  check (
    (status = 'running' and completed_at is null)
    or (status in ('published', 'failed') and completed_at is not null)
  ),
  check (status <> 'published' or artifact_sha256 is not null)
);

create index publication_runs_started_idx
  on reporting.publication_runs (started_at desc);

-- Every table is default-deny. Edge Functions use the service role through
-- narrowly granted SECURITY INVOKER routines in the exposed api schema.
alter table reporting.geographies enable row level security;
alter table reporting.geographies force row level security;
alter table reporting.reports enable row level security;
alter table reporting.reports force row level security;
alter table reporting.verification_events enable row level security;
alter table reporting.verification_events force row level security;
alter table reporting.conversation_sessions enable row level security;
alter table reporting.conversation_sessions force row level security;
alter table reporting.inbound_deliveries enable row level security;
alter table reporting.inbound_deliveries force row level security;
alter table reporting.rate_limit_buckets enable row level security;
alter table reporting.rate_limit_buckets force row level security;
alter table reporting.publication_runs enable row level security;
alter table reporting.publication_runs force row level security;

revoke all on all tables in schema reporting from public, anon, authenticated;
revoke all on all sequences in schema reporting from public, anon, authenticated;

grant usage on schema reporting, api to service_role;
grant select, insert, update on all tables in schema reporting to service_role;
grant usage, select on all sequences in schema reporting to service_role;

create or replace function api.consume_rate_limit(
  p_scope text,
  p_key_hash text,
  p_bucket_start timestamptz,
  p_limit integer,
  p_expires_at timestamptz
)
returns table (allowed boolean, current_count integer)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_count integer;
begin
  if p_scope not in ('event_10m', 'event_day', 'report_10m', 'report_day', 'network_day') then
    raise exception 'invalid rate-limit scope' using errcode = '22023';
  end if;
  if p_key_hash !~ '^[0-9a-f]{64}$' or p_limit < 1 or p_expires_at <= p_bucket_start then
    raise exception 'invalid rate-limit input' using errcode = '22023';
  end if;

  insert into reporting.rate_limit_buckets (
    scope, key_hash, bucket_start, count, expires_at
  )
  values (p_scope, p_key_hash, p_bucket_start, 1, p_expires_at)
  on conflict (scope, key_hash, bucket_start)
  do update set count = reporting.rate_limit_buckets.count + 1
  returning count into v_count;

  return query select v_count <= p_limit, v_count;
end;
$$;

create or replace function api.start_or_get_conversation(
  p_channel text,
  p_subject_hash text,
  p_identity_period date,
  p_flow_version smallint,
  p_copy_version smallint
)
returns table (
  session_id uuid,
  state text,
  resume_state text,
  location_lon double precision,
  location_lat double precision,
  locality_id text,
  depth_class text,
  lock_version bigint,
  expires_at timestamptz
)
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if p_channel not in ('web', 'telegram', 'whatsapp')
    or p_subject_hash !~ '^[0-9a-f]{64}$'
    or p_flow_version < 1
    or p_copy_version < 1 then
    raise exception 'invalid conversation identity' using errcode = '22023';
  end if;

  insert into reporting.conversation_sessions (
    channel,
    subject_hash,
    identity_period,
    flow_version,
    copy_version,
    state
  )
  values (
    p_channel,
    p_subject_hash,
    p_identity_period,
    p_flow_version,
    p_copy_version,
    'idle'
  )
  on conflict (channel, subject_hash, identity_period)
  do update set
    last_activity_at = now(),
    expires_at = now() + interval '24 hours'
  where reporting.conversation_sessions.expires_at > now();

  update reporting.conversation_sessions
  set
    state = 'idle',
    resume_state = null,
    location = null,
    locality_id = null,
    depth_class = null,
    emergency_guidance_shown_at = null,
    flow_version = p_flow_version,
    copy_version = p_copy_version,
    lock_version = lock_version + 1,
    last_activity_at = now(),
    expires_at = now() + interval '24 hours'
  where channel = p_channel
    and subject_hash = p_subject_hash
    and identity_period = p_identity_period
    and expires_at <= now();

  return query
  select
    s.session_id,
    s.state,
    s.resume_state,
    case when s.location is null then null
      else extensions.st_x(s.location::extensions.geometry)
    end,
    case when s.location is null then null
      else extensions.st_y(s.location::extensions.geometry)
    end,
    s.locality_id,
    s.depth_class,
    s.lock_version,
    s.expires_at
  from reporting.conversation_sessions as s
  where s.channel = p_channel
    and s.subject_hash = p_subject_hash
    and s.identity_period = p_identity_period;
end;
$$;

create or replace function api.commit_conversation_step(
  p_session_id uuid,
  p_expected_lock_version bigint,
  p_channel text,
  p_platform_delivery_id text,
  p_subject_hash text,
  p_request_hash text,
  p_new_state text,
  p_resume_state text default null,
  p_location_lon numeric default null,
  p_location_lat numeric default null,
  p_locality_id text default null,
  p_depth_class text default null,
  p_emergency_guidance_shown boolean default false,
  p_report_id uuid default null,
  p_observed_at timestamptz default null
)
returns table (applied boolean, duplicate boolean, new_lock_version bigint)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_inserted integer;
  v_lock_version bigint;
  v_identity_period date;
  v_location extensions.geography(point, 4326);
begin
  if p_channel not in ('web', 'telegram', 'whatsapp')
    or p_subject_hash !~ '^[0-9a-f]{64}$'
    or p_request_hash !~ '^[0-9a-f]{64}$'
    or length(p_platform_delivery_id) not between 1 and 200 then
    raise exception 'invalid delivery identity' using errcode = '22023';
  end if;

  insert into reporting.inbound_deliveries (
    channel,
    platform_delivery_id,
    subject_hash,
    request_hash,
    outcome
  )
  values (
    p_channel,
    p_platform_delivery_id,
    p_subject_hash,
    p_request_hash,
    'accepted'
  )
  on conflict (channel, platform_delivery_id) do nothing;
  get diagnostics v_inserted = row_count;

  if v_inserted = 0 then
    return query select false, true, p_expected_lock_version;
    return;
  end if;

  select s.lock_version, s.identity_period
  into v_lock_version, v_identity_period
  from reporting.conversation_sessions as s
  where s.session_id = p_session_id
    and s.channel = p_channel
    and s.subject_hash = p_subject_hash
  for update;

  if not found then
    raise exception 'conversation not found' using errcode = 'P0002';
  end if;
  if v_lock_version <> p_expected_lock_version then
    raise exception 'conversation lock conflict' using errcode = '40001';
  end if;

  if p_location_lon is not null or p_location_lat is not null then
    if p_location_lon is null or p_location_lat is null then
      raise exception 'both coordinates are required' using errcode = '22023';
    end if;
    v_location = extensions.st_setsrid(
      extensions.st_makepoint(round(p_location_lon, 3), round(p_location_lat, 3)),
      4326
    )::extensions.geography;
  else
    select s.location into v_location
    from reporting.conversation_sessions as s
    where s.session_id = p_session_id;
  end if;

  if p_report_id is not null then
    if p_new_state <> 'submitted'
      or v_location is null
      or p_depth_class not in ('dry', 'ankle', 'knee', 'waist_plus') then
      raise exception 'incomplete report submission' using errcode = '22023';
    end if;

    insert into reporting.reports (
      report_id,
      channel,
      received_at,
      observed_at,
      reporter_hash,
      identity_period,
      location,
      locality_id,
      depth_class
    )
    values (
      p_report_id,
      p_channel,
      now(),
      coalesce(p_observed_at, now()),
      p_subject_hash,
      v_identity_period,
      v_location,
      p_locality_id,
      p_depth_class
    )
    on conflict (report_id) do nothing;

    if found then
      insert into reporting.verification_events (
        report_id, state, actor_kind, reason_codes
      )
      values (p_report_id, 'pending', 'system', array['new_submission'])
      on conflict do nothing;
    end if;
  end if;

  update reporting.conversation_sessions
  set
    state = p_new_state,
    resume_state = p_resume_state,
    location = v_location,
    locality_id = p_locality_id,
    depth_class = p_depth_class,
    emergency_guidance_shown_at = case
      when p_emergency_guidance_shown then now()
      else emergency_guidance_shown_at
    end,
    lock_version = lock_version + 1,
    last_activity_at = now(),
    expires_at = now() + interval '24 hours'
  where conversation_sessions.session_id = p_session_id
  returning lock_version into v_lock_version;

  return query select true, false, v_lock_version;
end;
$$;

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
  verification_state text
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
    coalesce(v.state, 'pending') as verification_state
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

revoke all on all functions in schema api from public, anon, authenticated;
grant execute on function api.consume_rate_limit(text, text, timestamptz, integer, timestamptz)
  to service_role;
grant execute on function api.start_or_get_conversation(text, text, date, smallint, smallint)
  to service_role;
grant execute on function api.commit_conversation_step(
  uuid,
  bigint,
  text,
  text,
  text,
  text,
  text,
  text,
  numeric,
  numeric,
  text,
  text,
  boolean,
  uuid,
  timestamptz
) to service_role;
grant execute on function api.export_report_candidates(timestamptz, timestamptz)
  to service_role;

alter default privileges in schema reporting revoke all on tables from public, anon, authenticated;
alter default privileges in schema reporting revoke all on sequences from public, anon, authenticated;
alter default privileges in schema api revoke execute on functions from public, anon, authenticated;
